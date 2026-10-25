"""
Proveedores de LLM. Todos exponen la misma función: completar(sistema, usuario) -> texto.

- ollama:    local y gratis, API REST de Ollama con la librería estándar.
- anthropic: SDK oficial `anthropic` (opcional), con la key del usuario.
- openai:    SDK oficial `openai` (opcional), con la key del usuario.

Las keys llegan desde la interfaz o desde .env y viven solo en memoria: nunca se escriben en disco ni en logs.
"""
import json
import os
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


class ErrorProveedor(RuntimeError):
    pass


def _ollama(sistema: str, usuario: str, modelo: str, **_) -> str:
    cuerpo = json.dumps({
        "model": modelo,
        "stream": False,
        "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
        "options": {"num_ctx": 8192},
    }).encode("utf-8")
    req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=cuerpo, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            return json.load(r)["message"]["content"]
    except urllib.error.HTTPError as e:
        raise ErrorProveedor(f"Ollama respondió {e.code}: {e.read().decode('utf-8', 'replace')[:300]}") from e
    except urllib.error.URLError as e:
        raise ErrorProveedor("No se pudo conectar con Ollama. ¿Está abierto? (ollama serve)") from e


def _anthropic(sistema: str, usuario: str, modelo: str, api_key: str | None = None) -> str:
    try:
        import anthropic
    except ImportError as e:
        raise ErrorProveedor("Falta el SDK oficial: pip install anthropic") from e

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
        raise ErrorProveedor("Falta el SDK oficial: pip install openai") from e

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


def disponibles() -> dict:
    """Qué está listo en este equipo, para avisar en la interfaz."""
    import importlib.util
    hay = lambda m: importlib.util.find_spec(m) is not None
    return {
        "ollama": bool(modelos_ollama()),
        "anthropic_sdk": hay("anthropic"),
        "openai_sdk": hay("openai"),
        "faster_whisper": hay("faster_whisper"),
        "key_anthropic_env": bool(os.getenv("ANTHROPIC_API_KEY")),
        "key_openai_env": bool(os.getenv("OPENAI_API_KEY")),
    }
