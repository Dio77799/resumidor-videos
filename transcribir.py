"""
Convierte el archivo de entrada en una lista de segmentos (inicio, fin, texto).

- .srt / .vtt / .txt  -> se leen directo (sin transcribir, sin dependencias).
- audio / video       -> faster-whisper en local (se importa solo si hace falta).
"""
import re
from dataclasses import dataclass
from pathlib import Path

EXT_TEXTO = {".srt", ".vtt", ".txt"}
EXT_MEDIA = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".mp3", ".wav", ".m4a", ".ogg", ".flac", ".opus"}
MODELOS_WHISPER = ["tiny", "base", "small", "medium", "large-v3-turbo", "large-v3"]


@dataclass
class Segmento:
    inicio: float | None  # segundos; None si el .txt no trae tiempos
    fin: float | None
    texto: str


def formato_tiempo(seg: float | None) -> str:
    if seg is None:
        return ""
    seg = int(seg)
    h, m, s = seg // 3600, seg % 3600 // 60, seg % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _a_segundos(marca: str) -> float:
    # 00:01:02,345 | 00:01:02.345 | 01:02.345
    partes = marca.replace(",", ".").split(":")
    partes = [float(p) for p in partes]
    while len(partes) < 3:
        partes.insert(0, 0.0)
    h, m, s = partes
    return h * 3600 + m * 60 + s


_TIEMPO = re.compile(r"((?:\d+:)?\d{1,2}:\d{2}[.,]\d{1,3})\s*-->\s*((?:\d+:)?\d{1,2}:\d{2}[.,]\d{1,3})")
_ETIQUETAS = re.compile(r"<[^>]+>")


def leer_subtitulos(texto: str) -> list[Segmento]:
    """Sirve para .srt y .vtt: busca cada línea 'inicio --> fin' y toma el texto que sigue."""
    segmentos = []
    for bloque in re.split(r"\n\s*\n", texto.replace("\r\n", "\n")):
        lineas = bloque.strip().split("\n")
        for i, linea in enumerate(lineas):
            m = _TIEMPO.search(linea)
            if m:
                cuerpo = " ".join(_ETIQUETAS.sub("", t).strip() for t in lineas[i + 1:]).strip()
                if cuerpo:
                    segmentos.append(Segmento(_a_segundos(m.group(1)), _a_segundos(m.group(2)), cuerpo))
                break
    # Los .vtt de YouTube repiten líneas entre bloques: se quitan los duplicados seguidos.
    limpios = []
    for s in segmentos:
        if not limpios or s.texto != limpios[-1].texto:
            limpios.append(s)
    return limpios


def leer_txt(texto: str) -> list[Segmento]:
    parrafos = [p.strip() for p in re.split(r"\n\s*\n", texto) if p.strip()]
    return [Segmento(None, None, p) for p in parrafos]


def transcribir_media(ruta: Path, modelo: str = "small", idioma: str | None = None, progreso=None) -> list[Segmento]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError(
            "Para audio/video falta faster-whisper (pip install -r requirements.txt). "
            "Mientras tanto puedes subir un .srt, .vtt o .txt."
        ) from e

    if progreso:
        progreso(0.0, f"Cargando modelo Whisper '{modelo}' (la primera vez se descarga)…")
    whisper = WhisperModel(modelo, device="auto", compute_type="int8")
    trozos, info = whisper.transcribe(str(ruta), language=idioma or None, vad_filter=True)
    duracion = info.duration or 0
    segmentos = []
    for t in trozos:
        segmentos.append(Segmento(t.start, t.end, t.text.strip()))
        if progreso and duracion:
            progreso(min(t.end / duracion, 1.0), f"Transcribiendo… {formato_tiempo(t.end)} / {formato_tiempo(duracion)}")
    return segmentos


def obtener_segmentos(ruta: Path, modelo_whisper: str = "small", idioma: str | None = None, progreso=None) -> list[Segmento]:
    ext = ruta.suffix.lower()
    if ext in EXT_TEXTO:
        texto = ruta.read_text(encoding="utf-8", errors="replace")
        return leer_txt(texto) if ext == ".txt" else leer_subtitulos(texto)
    if ext in EXT_MEDIA:
        return transcribir_media(ruta, modelo_whisper, idioma, progreso)
    raise ValueError(f"Formato no soportado: {ext}. Usa video, audio, .srt, .vtt o .txt.")


def a_srt(segmentos: list[Segmento]) -> str:
    """Guarda la transcripción en .srt para que el usuario la conserve."""
    def marca(s):
        ms = int(round((s or 0) * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    return "\n".join(f"{i}\n{marca(s.inicio)} --> {marca(s.fin)}\n{s.texto}\n" for i, s in enumerate(segmentos, 1))
