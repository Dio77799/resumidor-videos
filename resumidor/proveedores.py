"""
Proveedores de LLM. Todos exponen la misma función: completar(sistema, usuario) -> texto.

- ollama:    local y gratis, API REST de Ollama con la librería estándar.
- anthropic: SDK oficial `anthropic` (opcional), con la key del usuario.
- openai:    SDK oficial `openai` (opcional), con la key del usuario.

Las keys llegan desde la interfaz o desde .env y viven solo en memoria: nunca se escriben en disco ni en logs.
"""
import json
import os
import re
import urllib.error
import urllib.request

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")

MODELOS_POR_DEFECTO = {
    "ollama": os.getenv("OLLAMA_MODELO", "llama3.2:3b"),
    "anthropic": os.getenv("ANTHROPIC_MODELO", "claude-opus-5-5"),
    "openai": os.getenv("OPENAI_MODELO", "gpt-5-mini"),
}

# Caracteres por bloque de transcripción. Los modelos locales pequeños tienen poco contexto.
TAM_BLOQUE = {"ollama": 6000, "anthropic": 60000, "openai": 40000}

# Modelos de Claude que aceptan `fallbacks: "default"` (reintento automático si el modelo declina).
_CLAUDE_CON_FALLBACK = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}


# Modelos locales recomendados (catálogo oficial de Ollama). Pensados para correr en CPU con 8–32 GB de RAM.
# seg_llamada: segundos por petición en una laptop sin tarjeta gráfica. llama3.2:3b está medido; el resto se
# estima por tamaño (gpt-oss activa solo una parte del modelo y va más rápido de lo que su tamaño sugiere).
CATALOGO_OLLAMA = [
    {"modelo": "llama3.2:3b", "gb": 2.0, "seg_llamada": 38, "nivel": "Ligero",
     "nota": "Funciona en casi cualquier equipo. Apuntes básicos."},
    {"modelo": "gemma3:4b", "gb": 3.3, "seg_llamada": 60, "nivel": "Rápido",
     "nota": "Mejor español que llama3.2 con casi la misma velocidad."},
    {"modelo": "qwen3:8b", "gb": 5.2, "seg_llamada": 100, "nivel": "Recomendado",
     "nota": "Buen equilibrio entre calidad y velocidad. 16 GB de RAM."},
    {"modelo": "gemma3:12b", "gb": 8.1, "seg_llamada": 155, "nivel": "Preciso",
     "nota": "Apuntes más completos. Lento sin tarjeta gráfica."},
    {"modelo": "gpt-oss:20b", "gb": 14, "seg_llamada": 90, "nivel": "Máxima calidad",
     "nota": "El mejor local de la lista. 24 GB de RAM o más."},
]

# Modelos que "piensan" antes de responder. En CPU eso cuesta minutos, así que se pide pensar lo mínimo.
_PENSAMIENTO = {"qwen3": False, "deepseek-r1": False, "magistral": False, "gpt-oss": "low"}
_ETIQUETA_PENSAR = re.compile(r"<think>.*?</think>\s*", re.S)


class ErrorProveedor(RuntimeError):
    pass


def _ollama(sistema: str, usuario: str, modelo: str, **_) -> str:
    peticion = {
        "model": modelo,
        "stream": False,
        "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
        "options": {"num_ctx": 8192},
    }
    familia = modelo.split(":")[0]
    if familia in _PENSAMIENTO:
        peticion["think"] = _PENSAMIENTO[familia]
    req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=json.dumps(peticion).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=1800) as r:
            return _ETIQUETA_PENSAR.sub("", json.load(r)["message"]["content"]).strip()
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", "replace")[:300]
        if e.code == 404:
            raise ErrorProveedor(f"El modelo {modelo} no está descargado. Descárgalo desde la lista de modelos.") from e
        raise ErrorProveedor(f"Ollama respondió {e.code}: {detalle}") from e
    except urllib.error.URLError as e:
        raise ErrorProveedor("No se pudo conectar con Ollama. ¿Está abierto? (ollama serve)") from e
    except TimeoutError as e:
        raise ErrorProveedor(f"{modelo} tardó demasiado. Prueba un modelo más ligero o un archivo más corto.") from e


def descargar_ollama(modelo: str, progreso) -> None:
    """Descarga un modelo con la API de Ollama. `progreso(fraccion 0..1, mensaje)`."""
    req = urllib.request.Request(f"{OLLAMA_URL}/api/pull", data=json.dumps({"model": modelo, "stream": True}).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=3600) as r:
            for linea in r:
                if not linea.strip():
                    continue
                evento = json.loads(linea)
                if "error" in evento:
                    raise ErrorProveedor(f"Ollama: {evento['error']}")
                total, hecho = evento.get("total"), evento.get("completed")
                if total and hecho:
                    progreso(hecho / total, f"Descargando {modelo}… {hecho / 1e9:.1f} de {total / 1e9:.1f} GB")
                else:
                    progreso(None, evento.get("status", ""))
    except urllib.error.URLError as e:
        raise ErrorProveedor("No se pudo conectar con Ollama. ¿Está abierto? (ollama serve)") from e


def _anthropic(sistema: str, usuario: str, modelo: str, api_key: str | None = None) -> str:
    try:
        import anthropic
    except ImportError as e:
        raise ErrorProveedor("Falta el SDK de Claude: pip install \"resumidor-videos[claude]\" (o pip install anthropic)") from e

    client = anthropic.Anthropic(api_key=api_key or None)  # sin key usa ANTHROPIC_API_KEY del .env
    extra = {}
    if modelo in _CLAUDE_CON_FALLBACK:
        extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
    try:
        with client.beta.messages.stream(
            model=modelo,
            max_tokens=16000,
            system=sistema,
            messages=[{"role": "user", "content": usuario}],
            output_config={"effort": "medium"},
            **extra,
        ) as stream:
            mensaje = stream.get_final_message()
    except anthropic.AuthenticationError as e:
        raise ErrorProveedor("API key de Anthropic inválida.") from e
    except anthropic.PermissionDeniedError as e:
        raise ErrorProveedor("Tu API key no tiene permiso para este modelo.") from e
    except anthropic.NotFoundError as e:
        raise ErrorProveedor(f"Modelo no encontrado: {modelo}") from e
    except anthropic.RateLimitError as e:
        raise ErrorProveedor("Límite de uso de Anthropic alcanzado. Espera un poco y reintenta.") from e
    except anthropic.APIStatusError as e:
        raise ErrorProveedor(f"Error de la API de Anthropic ({e.status_code}): {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise ErrorProveedor("No se pudo conectar con la API de Anthropic. Revisa tu internet.") from e

    if mensaje.stop_reason == "refusal":
        raise ErrorProveedor("El modelo declinó procesar este contenido.")
    return "".join(b.text for b in mensaje.content if b.type == "text")


def _openai(sistema: str, usuario: str, modelo: str, api_key: str | None = None) -> str:
    try:
        import openai
    except ImportError as e:
        raise ErrorProveedor("Falta el SDK de OpenAI: pip install \"resumidor-videos[openai]\" (o pip install openai)") from e

    client = openai.OpenAI(api_key=api_key or None)  # sin key usa OPENAI_API_KEY del .env
    try:
        r = client.chat.completions.create(
            model=modelo,
            messages=[{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
        )
    except openai.AuthenticationError as e:
        raise ErrorProveedor("API key de OpenAI inválida.") from e
    except openai.NotFoundError as e:
        raise ErrorProveedor(f"Modelo no encontrado: {modelo}") from e
    except openai.RateLimitError as e:
        raise ErrorProveedor("Límite de uso de OpenAI alcanzado. Espera un poco y reintenta.") from e
    except openai.APIStatusError as e:
        raise ErrorProveedor(f"Error de la API de OpenAI ({e.status_code}): {e.message}") from e
    except openai.APIConnectionError as e:
        raise ErrorProveedor("No se pudo conectar con la API de OpenAI. Revisa tu internet.") from e
    return r.choices[0].message.content or ""


_PROVEEDORES = {"ollama": _ollama, "anthropic": _anthropic, "openai": _openai}


def completar(proveedor: str, sistema: str, usuario: str, modelo: str | None = None, api_key: str | None = None) -> str:
    if proveedor not in _PROVEEDORES:
        raise ErrorProveedor(f"Proveedor desconocido: {proveedor}")
    return _PROVEEDORES[proveedor](sistema, usuario, modelo or MODELOS_POR_DEFECTO[proveedor], api_key=api_key)


def modelos_ollama() -> list[str]:
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3) as r:
            # Los modelos de embeddings no saben conversar: se ocultan.
            return [m["name"] for m in json.load(r).get("models", []) if "embed" not in m["name"]]
    except (urllib.error.URLError, OSError, ValueError):
        return []


def disponibles(instalados: list[str] | None = None) -> dict:
    """Qué está listo en este equipo, para avisar en la interfaz."""
    import importlib.util
    hay = lambda m: importlib.util.find_spec(m) is not None
    return {
        "ollama": bool(modelos_ollama() if instalados is None else instalados),
        "anthropic_sdk": hay("anthropic"),
        "openai_sdk": hay("openai"),
        "faster_whisper": hay("faster_whisper"),
        "key_anthropic_env": bool(os.getenv("ANTHROPIC_API_KEY")),
        "key_openai_env": bool(os.getenv("OPENAI_API_KEY")),
    }
