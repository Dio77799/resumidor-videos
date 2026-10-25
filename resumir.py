"""
Pipeline: archivo -> segmentos -> resumen por bloques -> resumen final -> notas .md

Uso por consola:
    python resumir.py clase.srt
    python resumir.py clase.mp4 --proveedor anthropic --modelo claude-opus-5-5
"""
import argparse
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent


def cargar_env(ruta: Path = BASE / ".env") -> None:
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

import proveedores  # noqa: E402  (lee el .env al importarse)
from transcribir import a_srt, formato_tiempo, obtener_segmentos  # noqa: E402

PROMPTS = BASE / "prompts"
SALIDA = BASE / "salida"
LOG = BASE / "logs" / "trazas.jsonl"
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


def traza(evento: dict) -> None:
    LOG.parent.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"fecha": datetime.now().isoformat(timespec="seconds"), **evento}, ensure_ascii=False) + "\n")


def nombre_seguro(texto: str) -> str:
    return re.sub(r"[^\w\-]+", "_", texto, flags=re.UNICODE).strip("_")[:80] or "resumen"


def resumir(ruta: Path, proveedor: str = "ollama", modelo: str | None = None, api_key: str | None = None,
            idioma: str = "es", modelo_whisper: str = "small", titulo: str | None = None, progreso=None) -> Path:
    """Devuelve la ruta del .md generado. `progreso(fraccion 0..1, mensaje)` es opcional."""
    avisar = progreso or (lambda f, m: print(f"[{f:4.0%}] {m}"))
    modelo = modelo or proveedores.MODELOS_POR_DEFECTO[proveedor]
    titulo = titulo or ruta.stem.replace("_", " ").replace("-", " ").strip().capitalize()
    nombre_idioma = IDIOMAS.get(idioma, idioma)
    t0 = time.time()

    # 1. Transcripción (0–40 %)
    avisar(0.0, f"Leyendo {ruta.name}…")
    segmentos = obtener_segmentos(ruta, modelo_whisper, idioma, lambda f, m: avisar(0.4 * f, m))
    if not segmentos:
        raise ValueError("No se encontró texto en el archivo.")
    SALIDA.mkdir(exist_ok=True)
    base = SALIDA / f"{nombre_seguro(titulo)}_{datetime.now():%Y%m%d_%H%M%S}"
    if segmentos[0].inicio is not None:
        base.with_suffix(".srt").write_text(a_srt(segmentos), encoding="utf-8")

    # 2. Resumen por bloques (40–90 %)
    sistema = plantilla("sistema", idioma=nombre_idioma)
    bloques = agrupar(segmentos, proveedores.TAM_BLOQUE[proveedor])
    secciones = []
    for i, bloque in enumerate(bloques, 1):
        avisar(0.4 + 0.5 * (i - 1) / len(bloques), f"Resumiendo parte {i} de {len(bloques)} con {modelo}…")
        texto = " ".join(s.texto for s in bloque)
        prompt = plantilla("seccion", n=i, total=len(bloques), titulo=titulo, tramo=tramo(bloque), texto=texto)
        apunte = proveedores.completar(proveedor, sistema, prompt, modelo, api_key).strip()
        if bloque[0].inicio is not None:
            # Añade el tramo de tiempo al título de la sección para poder volver al video.
            apunte = re.sub(r"^(###\s*.+)$", rf"\1 `[{tramo(bloque)}]`", apunte, count=1, flags=re.M)
        secciones.append(apunte)

    # 3. Resumen final (90–100 %)
    avisar(0.9, "Escribiendo resumen general, apuntes clave y preguntas…")
    final = proveedores.completar(proveedor, sistema, plantilla("final", titulo=titulo, secciones="\n\n".join(secciones)),
                                  modelo, api_key).strip()
    # Los modelos pequeños a veces cambian el nivel de los títulos; se normalizan.
    final = re.sub(r"^#{1,6}\s*(Resumen general|Apuntes clave|Preguntas de repaso)\s*$", r"## \1", final, flags=re.M | re.I)

    md = "\n\n".join([
        f"# {titulo}",
        f"> Generado con Resumidor de videos · {proveedor} / `{modelo}` · {datetime.now():%Y-%m-%d}",
        final,
        "## Notas por sección",
        *secciones,
    ]) + "\n"
    salida_md = base.with_suffix(".md")
    salida_md.write_text(md, encoding="utf-8")

    traza({"archivo": ruta.suffix.lower(), "proveedor": proveedor, "modelo": modelo, "segmentos": len(segmentos),
           "bloques": len(bloques), "caracteres": sum(len(s.texto) for s in segmentos),
           "segundos": round(time.time() - t0, 1)})
    avisar(1.0, "Listo")
    return salida_md


def main():
    p = argparse.ArgumentParser(description="Convierte un video, audio o transcripción en apuntes .md")
    p.add_argument("archivo", type=Path)
    p.add_argument("--proveedor", default=os.getenv("PROVEEDOR", "ollama"), choices=["ollama", "anthropic", "openai"])
    p.add_argument("--modelo")
    p.add_argument("--idioma", default="es", help="idioma de los apuntes y del audio (es, en, pt…)")
    p.add_argument("--whisper", default="small", help="modelo de faster-whisper: tiny, base, small, medium, large-v3")
    a = p.parse_args()
    print("Apuntes guardados en:", resumir(a.archivo, a.proveedor, a.modelo, None, a.idioma, a.whisper))


if __name__ == "__main__":
    main()
