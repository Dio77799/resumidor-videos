"""
Pipeline: archivo -> segmentos -> resumen por bloques -> resumen final -> notas .md

Uso por consola:
    resumidor clase.srt
    resumidor clase.mp4 --proveedor anthropic --modelo claude-opus-5-5
"""
import argparse
import hashlib
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
from .transcribir import EXT_MEDIA, Segmento, a_srt, formato_tiempo, obtener_segmentos  # noqa: E402

PROMPTS = Path(os.getenv("RESUMIDOR_PROMPTS") or PAQUETE / "prompts")  # para usar plantillas propias
SALIDA = DATOS / "salida"
LOG = DATOS / "logs" / "trazas.jsonl"
CACHE = DATOS / "cache"  # transcripciones ya hechas: volver a resumir el mismo archivo no gasta Whisper
IDIOMAS = {"es": "español", "en": "inglés", "pt": "portugués"}
MODOS = {"clase": "Clase o curso", "reunion": "Reunión", "charla": "Charla, podcast o entrevista"}
# Títulos de las secciones finales en todos los modos (para normalizar su nivel).
TITULOS_FINALES = ("Resumen general", "Apuntes clave", "Preguntas de repaso", "Decisiones", "Tareas pendientes",
                   "Temas abiertos", "Ideas principales", "Frases destacadas")


def plantilla(nombre: str, modo: str = "clase", **datos) -> str:
    """Busca primero la plantilla del modo (prompts/reunion/final.md) y si no existe usa la general."""
    propia = PROMPTS / modo / f"{nombre}.md"
    texto = (propia if propia.exists() else PROMPTS / f"{nombre}.md").read_text(encoding="utf-8")
    for clave, valor in datos.items():
        texto = texto.replace("{" + clave + "}", str(valor))
    return texto


def huella(ruta: Path) -> str:
    """SHA-256 del contenido: el mismo archivo con otro nombre se reconoce igual."""
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for trozo in iter(lambda: f.read(1024 * 1024), b""):
            h.update(trozo)
    return h.hexdigest()


def ruta_cache(huella_archivo: str, modelo_whisper: str, idioma: str) -> Path:
    beam = os.getenv("WHISPER_BEAM", "1")
    return CACHE / f"{huella_archivo[:32]}_{modelo_whisper}_b{beam}_{idioma}.json"


def leer_cache(ruta: Path) -> list[Segmento] | None:
    try:
        return [Segmento(*s) for s in json.loads(ruta.read_text(encoding="utf-8"))]
    except (OSError, ValueError, TypeError):
        return None


def guardar_cache(ruta: Path, segmentos: list[Segmento]) -> None:
    ruta.parent.mkdir(exist_ok=True)
    ruta.write_text(json.dumps([[s.inicio, s.fin, s.texto] for s in segmentos], ensure_ascii=False), encoding="utf-8")


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
            una_llamada: bool = True, modo: str = "clase") -> Resultado:
    """Genera los apuntes. `progreso(fraccion 0..1, mensaje)` es opcional."""
    avisar = progreso or (lambda f, m: print(f"[{f:4.0%}] {m}"))
    modelo = modelo or proveedores.MODELOS_POR_DEFECTO[proveedor]
    if modo not in MODOS:
        raise ValueError(f"Modo desconocido: {modo}. Usa {', '.join(MODOS)}.")
    titulo = (titulo or ruta.stem).replace("_", " ").strip()
    titulo = titulo[:1].upper() + titulo[1:]
    nombre_idioma = IDIOMAS.get(idioma, idioma)
    t0 = time.time()

    # 1. Transcripción (0–40 %). Si este archivo ya se transcribió con la misma configuración, se reutiliza.
    avisar(0.0, f"Leyendo {ruta.name}…")
    es_media = ruta.suffix.lower() in EXT_MEDIA
    cache = ruta_cache(huella(ruta), modelo_whisper, idioma) if es_media else None
    segmentos = leer_cache(cache) if cache else None
    en_cache = bool(segmentos)
    if en_cache:
        avisar(0.4, "Transcripción reutilizada: este archivo ya se había transcrito (0 Wh).")
    else:
        segmentos = obtener_segmentos(ruta, modelo_whisper, idioma, lambda f, m: avisar(0.4 * f, m))
        if cache and segmentos:
            guardar_cache(cache, segmentos)
    if not segmentos:
        raise ValueError("No se encontró texto en el archivo.")
    seg_transcripcion = 0.0 if en_cache else time.time() - t0
    SALIDA.mkdir(exist_ok=True)
    base = SALIDA / f"{nombre_seguro(titulo)}_{datetime.now():%Y%m%d_%H%M%S}"
    n = 2
    while base.with_suffix(".md").exists() or base.with_suffix(".srt").exists():  # nunca pisar apuntes anteriores
        base = base.with_name(f"{base.name.rsplit('~', 1)[0]}~{n}")
        n += 1
    srt = None
    if segmentos[0].inicio is not None:
        srt = base.with_suffix(".srt")
        srt.write_text(a_srt(segmentos), encoding="utf-8")
    t1 = time.time()

    # 2. Resumen (40–100 %)
    sistema = plantilla("sistema", modo, idioma=nombre_idioma)
    bloques = agrupar(segmentos, proveedores.TAM_BLOQUE[proveedor])
    if len(bloques) == 1 and una_llamada:
        # Cabe entero: una sola llamada con todo. Ahorra casi la mitad del tiempo en modelos locales.
        avisar(0.4, f"Escribiendo los apuntes con {modelo}…")
        texto = " ".join(s.texto for s in segmentos)
        prompt = plantilla("unico", modo, titulo=titulo, tramo=tramo(segmentos), texto=texto)
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
            prompt = plantilla("seccion", modo, n=i, total=len(bloques), titulo=titulo, tramo=tramo(bloque), texto=texto)
            apunte = proveedores.completar(proveedor, sistema, prompt, modelo, api_key).strip()
            secciones.append(con_tramo(apunte, tramo(bloque)) if bloque[0].inicio is not None else apunte)

        avisar(0.9, "Escribiendo resumen general, apuntes clave y preguntas…")
        prompt = plantilla("final", modo, titulo=titulo, secciones="\n\n".join(secciones))
        final = proveedores.completar(proveedor, sistema, prompt, modelo, api_key).strip()
    # Los modelos pequeños a veces cambian el nivel de los títulos; se normalizan.
    titulos = "|".join(TITULOS_FINALES)
    final = re.sub(rf"^#{{1,6}}\s*\**({titulos})\**\s*:?\s*$", r"## \1", final, flags=re.M | re.I)

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
        "modo": modo, "cache": en_cache,
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
        description="Convierte videos, audios o transcripciones en apuntes .md (local con Ollama o con tu API key).")
    p.add_argument("archivos", type=Path, nargs="*", help="uno o varios: video, audio, .srt, .vtt o .txt")
    p.add_argument("--modo", default="clase", choices=list(MODOS),
                   help="clase (preguntas de repaso), reunion (decisiones y tareas) o charla (ideas y citas)")
    p.add_argument("--proveedor", default=os.getenv("PROVEEDOR", "ollama"), choices=["ollama", "anthropic", "openai"])
    p.add_argument("--modelo", help="por defecto: llama3.2:3b, claude-opus-5-5 o gpt-5-mini según el proveedor")
    p.add_argument("--idioma", default="es", help="idioma de los apuntes y del audio (es, en, pt…)")
    p.add_argument("--whisper", default="small", help="tiny, base, small, medium, large-v3-turbo, large-v3")
    p.add_argument("--salida", type=Path, help="carpeta donde guardar los apuntes (por defecto ./salida)")
    p.add_argument("--titulo", help="título de los apuntes (solo con un archivo; por defecto, su nombre)")
    p.add_argument("--web", action="store_true", help="abre la interfaz web en lugar de procesar archivos")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    a = p.parse_args(argv)

    if a.web:
        from .app import main as web
        return web()
    if not a.archivos:
        p.error("indica al menos un archivo o usa --web")
    if a.titulo and len(a.archivos) > 1:
        p.error("--titulo solo se puede usar con un archivo")
    faltan = [str(f) for f in a.archivos if not f.is_file()]
    if faltan:
        p.error(f"no existe: {', '.join(faltan)}")
    global SALIDA
    if a.salida:
        SALIDA = a.salida.resolve()

    fallidos = 0
    for i, archivo in enumerate(a.archivos, 1):
        if len(a.archivos) > 1:
            print(f"\n=== {i}/{len(a.archivos)} · {archivo.name}")
        try:
            r = resumir(archivo, a.proveedor, a.modelo, None, a.idioma, a.whisper, a.titulo, modo=a.modo)
            print(f"Apuntes guardados en: {r.md}  ({r.estadisticas['segundos']:.0f} s)")
        except (RuntimeError, ValueError) as e:  # dependencia que falta, proveedor caído, formato no soportado…
            fallidos += 1
            print(f"Error con {archivo.name}: {e}")
    if fallidos:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
