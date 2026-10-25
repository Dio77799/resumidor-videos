"""
Estimación de tiempo y consumo eléctrico (Wh) de un resumen local.

Arranca con valores medidos en una laptop sin tarjeta gráfica (i7 de 4 núcleos) y se calibra sola
con los resúmenes que el usuario ya hizo (logs/trazas.jsonl). Es una estimación, no una medición:
supone que el equipo consume WATTS_EQUIPO vatios mientras trabaja (45 W por defecto, se cambia en .env).
"""
import json
import math
import os
from pathlib import Path

from . import proveedores

WATTS = float(os.getenv("WATTS_EQUIPO", "45"))
CARACTERES_POR_MINUTO = 900  # habla en español: ~150 palabras por minuto

# Segundos de cómputo por cada segundo de audio, en CPU con int8 y beam 1 (small y large-v3-turbo medidos; el resto estimado).
WHISPER_FACTOR = {"tiny": 0.04, "base": 0.07, "small": 0.18, "medium": 0.4, "large-v3-turbo": 0.43, "large-v3": 0.85}
SEG_LLAMADA_DESCONOCIDO = 60   # modelo local que no está en el catálogo
SEG_LLAMADA_NUBE = 15          # Claude/OpenAI: casi todo es espera de red; no consume en tu equipo
# La llamada única (video corto) escribe todos los apuntes de una vez: medido ≈ 1,8 llamadas normales.
PESO_LLAMADA_UNICA = 1.8


def _peso(llamadas: int) -> float:
    return PESO_LLAMADA_UNICA if llamadas == 1 else llamadas


def _historial(log: Path) -> list[dict]:
    if not log.exists():
        return []
    filas = []
    for linea in log.read_text(encoding="utf-8").splitlines()[-200:]:
        try:
            filas.append(json.loads(linea))
        except json.JSONDecodeError:
            continue
    return [f for f in filas if "seg_resumen" in f]


def _promedio(valores: list[float]) -> float | None:
    return sum(valores) / len(valores) if valores else None


def calibracion(log: Path) -> dict:
    """Velocidades medidas en este equipo: {"whisper": {modelo: factor}, "llm": {modelo: seg_por_llamada}}."""
    historial = _historial(log)
    whisper, llm = {}, {}
    for f in historial:
        if f.get("duracion_media") and f.get("seg_transcripcion") and not f.get("cache"):  # la caché no es medición
            whisper.setdefault(f["whisper"], []).append(f["seg_transcripcion"] / f["duracion_media"])
        if f.get("proveedor") == "ollama" and f.get("bloques"):
            llm.setdefault(f["modelo"], []).append(f["seg_resumen"] / _peso(f.get("llamadas", f["bloques"] + 1)))
    return {"whisper": {k: _promedio(v) for k, v in whisper.items()}, "llm": {k: _promedio(v) for k, v in llm.items()}}


def wh(segundos: float) -> float:
    return segundos * WATTS / 3600


def estimar(proveedor: str, modelo: str, whisper: str, duracion: float | None, caracteres: int | None,
            es_media: bool, log: Path) -> dict:
    """Tiempo total estimado y Wh que gasta tu equipo (transcripción local + resumen si es Ollama)."""
    cal = calibracion(log)
    medido = False

    seg_transcripcion = 0.0
    if es_media and duracion:
        factor = cal["whisper"].get(whisper)
        medido |= factor is not None
        seg_transcripcion = duracion * (factor or WHISPER_FACTOR.get(whisper, 0.5)) + 5  # +5 s de carga del modelo

    if caracteres is None:
        caracteres = int((duracion or 0) / 60 * CARACTERES_POR_MINUTO)
    partes = max(1, math.ceil(caracteres / proveedores.TAM_BLOQUE[proveedor]))
    llamadas = 1 if partes == 1 else partes + 1  # si cabe entero es una sola llamada; si no, partes + resumen final

    if proveedor == "ollama":
        seg = cal["llm"].get(modelo)
        medido |= seg is not None
        if seg is None:
            seg = next((m["seg_llamada"] for m in proveedores.CATALOGO_OLLAMA if m["modelo"] == modelo), SEG_LLAMADA_DESCONOCIDO)
        seg_resumen = _peso(llamadas) * seg
        seg_local = seg_transcripcion + seg_resumen
    else:
        seg_resumen, seg_local = _peso(llamadas) * SEG_LLAMADA_NUBE, seg_transcripcion

    return {
        "segundos": round(seg_transcripcion + seg_resumen),
        "wh": round(wh(seg_local), 1),
        "llamadas": llamadas,
        "medido": medido,
        "watts": WATTS,
    }


def capacidad_catalogo(log: Path, whisper: str = "small") -> dict:
    """Para cada modelo del catálogo: minutos y Wh que toma resumir una hora de video."""
    return {m["modelo"]: estimar("ollama", m["modelo"], whisper, 3600, None, True, log) for m in proveedores.CATALOGO_OLLAMA}
