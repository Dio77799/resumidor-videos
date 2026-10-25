"""
Pipeline: archivo -> segmentos -> resumen por bloques -> resumen final -> notas .md

Uso por consola:
    resumidor clase.srt
    resumidor clase.mp4 --proveedor anthropic --modelo claude-opus-5-5
"""
import argparse
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import __version__

PAQUETE = Path(__file__).resolve().parent  # plantillas e interfaz: viajan con el paquete
# Resultados, subidas, trazas y .env: en la carpeta desde la que se ejecuta (o la que diga RESUMIDOR_DATOS).
DATOS = Path(os.getenv("RESUMIDOR_DATOS") or Path.cwd()).resolve()


def cargar_env(ruta: Path = DATOS / ".env") -> None:
    """Lector mínimo de .env (sin dependencias). No pisa variables ya definidas."""
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            clave, valor = linea.split("=", 1)
            if valor.strip():
                os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


cargar_env()

from . import proveedores  # noqa: E402  (lee el .env al importarse)
from .transcribir import a_srt, formato_tiempo, obtener_segmentos  # noqa: E402

PROMPTS = Path(os.getenv("RESUMIDOR_PROMPTS") or PAQUETE / "prompts")  # para usar plantillas propias
SALIDA = DATOS / "salida"
LOG = DATOS / "logs" / "trazas.jsonl"
IDIOMAS = {"es": "español", "en": "inglés", "pt": "portugués"}


def plantilla(nombre: str, **datos) -> str:
    texto = (PROMPTS / f"{nombre}.md").read_text(encoding="utf-8")
    for clave, valor in datos.items():
        texto = texto.replace("{" + clave + "}", str(valor))
    return texto


def agrupar(segmentos, tam_bloque: int) -> list[list]:
    bloques, actual, largo = [], [], 0
    for s in segmentos:
        if actual and largo + len(s.texto) > tam_bloque:
            bloques.append(actual)
            actual, largo = [], 0
        actual.append(s)
        largo += len(s.texto) + 1
    if actual:
        bloques.append(actual)
    return bloques


def tramo(bloque) -> str:
    if bloque[0].inicio is None:
        return "sin marcas de tiempo"
    return f"{formato_tiempo(bloque[0].inicio)}–{formato_tiempo(bloque[-1].fin)}"


def con_tramo(apunte: str, rango: str) -> str:
    """Añade el tramo de tiempo al primer título de sección para poder volver al video."""
    return re.sub(r"^(###\s*.+)$", lambda m: f"{m.group(1)} `[{rango}]`", apunte, count=1, flags=re.M)


def traza(evento: dict) -> None:
    LOG.parent.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"fecha": datetime.now().isoformat(timespec="seconds"), **evento}, ensure_ascii=False) + "\n")


def nombre_seguro(texto: str) -> str:
    return re.sub(r"[^\w\-]+", "_", texto, flags=re.UNICODE).strip("_")[:80] or "resumen"


@dataclass
class Resultado:
    md: Path
    srt: Path | None
    estadisticas: dict


def resumir(ruta: Path, proveedor: str = "ollama", modelo: str | None = None, api_key: str | None = None,
            idioma: str = "es", modelo_whisper: str = "small", titulo: str | None = None, progreso=None,
            una_llamada: bool = True) -> Resultado:
    """Genera los apuntes. `progreso(fraccion 0..1, mensaje)` es opcional."""
    avisar = progreso or (lambda f, m: print(f"[{f:4.0%}] {m}"))
    modelo = modelo or proveedores.MODELOS_POR_DEFECTO[proveedor]
    titulo = (titulo or ruta.stem).replace("_", " ").strip()
    titulo = titulo[:1].upper() + titulo[1:]
    nombre_idioma = IDIOMAS.get(idioma, idioma)
    t0 = time.time()

    # 1. Transcripción (0–40 %)
    avisar(0.0, f"Leyendo {ruta.name}…")
    segmentos = obtener_segmentos(ruta, modelo_whisper, idioma, lambda f, m: avisar(0.4 * f, m))
    if not segmentos:
        raise ValueError("No se encontró texto en el archivo.")
    seg_transcripcion = time.time() - t0
    es_media = segmentos[0].inicio is not None and ruta.suffix.lower() not in {".srt", ".vtt"}
    SALIDA.mkdir(exist_ok=True)
    base = SALIDA / f"{nombre_seguro(titulo)}_{datetime.now():%Y%m%d_%H%M%S}"
    srt = None
    if segmentos[0].inicio is not None:
        srt = base.with_suffix(".srt")
        srt.write_text(a_srt(segmentos), encoding="utf-8")
    t1 = time.time()

    # 2. Resumen (40–100 %)
    sistema = plantilla("sistema", idioma=nombre_idioma)
    bloques = agrupar(segmentos, proveedores.TAM_BLOQUE[proveedor])
    if len(bloques) == 1 and una_llamada:
        # Cabe entero: una sola llamada con todo. Ahorra casi la mitad del tiempo en modelos locales.
        avisar(0.4, f"Escribiendo los apuntes con {modelo}…")
        texto = " ".join(s.texto for s in segmentos)
        prompt = plantilla("unico", titulo=titulo, tramo=tramo(segmentos), texto=texto)
        salida = proveedores.completar(proveedor, sistema, prompt, modelo, api_key).strip()
        partes = re.split(r"^#{1,6}\s*Notas por secci[oó]n\s*$", salida, maxsplit=1, flags=re.M | re.I)
        final = partes[0].strip()
        # Aquí las secciones no tienen tiempos propios: la duración va en la cabecera, no un tramo inventado.
        secciones = [partes[1].strip()] if len(partes) > 1 else []
    else:
        secciones = []
        for i, bloque in enumerate(bloques, 1):
            avisar(0.4 + 0.5 * (i - 1) / len(bloques), f"Resumiendo parte {i} de {len(bloques)} con {modelo}…")
            texto = " ".join(s.texto for s in bloque)
            prompt = plantilla("seccion", n=i, total=len(bloques), titulo=titulo, tramo=tramo(bloque), texto=texto)
            apunte = proveedores.completar(proveedor, sistema, prompt, modelo, api_key).strip()
            secciones.append(con_tramo(apunte, tramo(bloque)) if bloque[0].inicio is not None else apunte)

        avisar(0.9, "Escribiendo resumen general, apuntes clave y preguntas…")
        prompt = plantilla("final", titulo=titulo, secciones="\n\n".join(secciones))
        final = proveedores.completar(proveedor, sistema, prompt, modelo, api_key).strip()
    # Los modelos pequeños a veces cambian el nivel de los títulos; se normalizan.
    final = re.sub(r"^#{1,6}\s*(Resumen general|Apuntes clave|Preguntas de repaso)\s*$", r"## \1", final, flags=re.M | re.I)

    md = "\n\n".join([
        f"# {titulo}",
        f"> Generado con Resumidor de videos · {proveedor} / `{modelo}` · {datetime.now():%Y-%m-%d}"
        + (f" · duración {formato_tiempo(segmentos[-1].fin)}" if segmentos[-1].fin else ""),
        final,
        *(["## Notas por sección", *secciones] if secciones else []),
    ]) + "\n"
    salida_md = base.with_suffix(".md")
    salida_md.write_text(md, encoding="utf-8")

    estadisticas = {
        "archivo": ruta.suffix.lower(), "proveedor": proveedor, "modelo": modelo, "whisper": modelo_whisper if es_media else None,
        "duracion_media": round(segmentos[-1].fin, 1) if es_media else None, "segmentos": len(segmentos),
        "bloques": len(bloques), "llamadas": 1 if len(bloques) == 1 and una_llamada else len(bloques) + 1,
        "caracteres": sum(len(s.texto) for s in segmentos),
        "seg_transcripcion": round(seg_transcripcion, 1) if es_media else None,
        "seg_resumen": round(time.time() - t1, 1), "segundos": round(time.time() - t0, 1),
    }
    traza(estadisticas)
    avisar(1.0, "Listo")
    return Resultado(salida_md, srt, estadisticas)


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="resumidor",
        description="Convierte un video, audio o transcripción en apuntes .md (local con Ollama o con tu API key).")
    p.add_argument("archivo", type=Path, nargs="?", help="video, audio, .srt, .vtt o .txt")
    p.add_argument("--proveedor", default=os.getenv("PROVEEDOR", "ollama"), choices=["ollama", "anthropic", "openai"])
    p.add_argument("--modelo", help="por defecto: llama3.2:3b, claude-opus-5-5 o gpt-5-mini según el proveedor")
    p.add_argument("--idioma", default="es", help="idioma de los apuntes y del audio (es, en, pt…)")
    p.add_argument("--whisper", default="small", help="tiny, base, small, medium, large-v3-turbo, large-v3")
    p.add_argument("--salida", type=Path, help="carpeta donde guardar los apuntes (por defecto ./salida)")
    p.add_argument("--titulo", help="título de los apuntes (por defecto, el nombre del archivo)")
    p.add_argument("--web", action="store_true", help="abre la interfaz web en lugar de procesar un archivo")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    a = p.parse_args(argv)

    if a.web:
        from .app import main as web
        return web()
    if not a.archivo:
        p.error("indica un archivo o usa --web")
    if not a.archivo.is_file():
        p.error(f"no existe el archivo: {a.archivo}")
    global SALIDA
    if a.salida:
        SALIDA = a.salida.resolve()
    try:
        r = resumir(a.archivo, a.proveedor, a.modelo, None, a.idioma, a.whisper, a.titulo)
    except (RuntimeError, ValueError) as e:  # dependencia que falta, proveedor caído, formato no soportado…
        raise SystemExit(f"Error: {e}") from None
    print(f"Apuntes guardados en: {r.md}  ({r.estadisticas['segundos']:.0f} s)")


if __name__ == "__main__":
    main()
