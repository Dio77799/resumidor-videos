# Cómo contribuir

¡Gracias por tu interés! Las contribuciones son bienvenidas en español o inglés.

## Preparar el entorno
Para correr los tests no hace falta instalar nada: usan solo la librería estándar y un modelo falso, así que no necesitas Ollama, Whisper ni ninguna API key.
```bash
git clone https://github.com/Dio77799/resumidor-videos && cd resumidor-videos
python -m unittest discover -s tests -t .
```

Para probar la app de verdad (interfaz, audio, Claude u OpenAI):
```bash
python -m venv .venv
.venv/Scripts/activate        # Windows  (en Linux/macOS: source .venv/bin/activate)
pip install -e ".[todo]"      # o solo el extra que uses: ".[audio]", ".[claude]", ".[openai]"
resumidor ejemplos/clase_fotosintesis.srt   # necesita Ollama abierto con un modelo
resumidor --web
```

## Estilo
- El CI corre [ruff](https://docs.astral.sh/ruff/) con la configuración de `pyproject.toml` (líneas de hasta 130 caracteres). Si lo tienes, córrelo antes del PR: `ruff check .`
- Nombres de variables, funciones y mensajes en español, como el resto del código.
- Si cambias algo que se puede probar sin red ni modelos, agrega un test en `tests/`. Los tests nunca llaman a Ollama, Claude ni OpenAI: usan `mock` o una función falsa (mira `llm_falso` en `tests/test_resumir.py`).

## De issue a PR
1. Busca un issue abierto, o abre uno nuevo antes de empezar algo grande. Los marcados con `good first issue` son chicos y traen los archivos a tocar.
2. Comenta en el issue que lo vas a tomar, así no trabajamos dos personas en lo mismo.
3. Crea una rama desde `main`, haz un cambio por PR y escribe en la descripción `Closes #número`.
4. Rellena la plantilla del PR: qué cambia y cómo lo probaste. El CI corre los tests en Windows, Linux y macOS.

## Principios del proyecto
- **Librería estándar primero.** Cada dependencia nueva debe justificarse: paquete oficial, mantenido, con licencia compatible y sin scripts de instalación raros.
- **Privacidad.** Nada de keys, rutas personales, logs ni contenido de usuarios en el repo. Las keys solo viven en memoria o en `.env`.
- **Solo contenido propio.** No se aceptan funciones para descargar contenido de plataformas de pago o protegido.
- **Fácil de usar.** Si un cambio afecta a la interfaz, incluye una captura en el PR.

## Uso de IA
Este proyecto lo hago con ayuda de agentes de IA (Claude Code), con las reglas de [AGENTS.md](AGENTS.md), y yo reviso, pruebo y publico cada cambio. Por eso no tengo problema con que uses IA, pero pido lo mismo que me pido a mí:
- Entiende y prueba lo que envías. Si no puedes explicar un cambio en tus palabras, todavía no está listo.
- Dilo en el PR: marca la casilla de IA y cuenta en una línea para qué la usaste (escribir código, tests, traducir…).
- No abras PRs ni issues generados en masa por un agente sin revisión humana: los cierro sin revisar.
- No pegues API keys, `.env` ni contenido de usuarios en una herramienta de IA.
- Los agentes que trabajen en el repo deben seguir [AGENTS.md](AGENTS.md).

## Ideas por dónde empezar
- Los [issues `good first issue`](https://github.com/Dio77799/resumidor-videos/labels/good%20first%20issue).
- Nuevos proveedores compatibles (por ejemplo LM Studio o Gemini).
- Exportar a otros formatos (PDF, Anki).
- Mejorar las plantillas de `resumidor/prompts/` para modelos pequeños.
- Traducir la interfaz.

## Conducta y seguridad
Al participar aceptas el [código de conducta](CODE_OF_CONDUCT.md). Las vulnerabilidades no van en issues públicos: sigue [SECURITY.md](SECURITY.md).
