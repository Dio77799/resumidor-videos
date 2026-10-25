# AGENTS.md — Resumidor de videos

Reglas e historial del proyecto. Cualquier agente de IA (Claude Code, Copilot, Codex…) que trabaje aquí debe leer y respetar este archivo.

## Proyecto
Herramienta open source para convertir **videos/audios/transcripciones propias** en resúmenes y apuntes `.md`, con interfaz visual sencilla.
Se publica **la herramienta, no el contenido**: cada usuario sube su material y, si quiere, usa su propia API key.

Pipeline: `archivo (video/audio/.srt/.vtt/.txt) → transcripción (faster-whisper, local) → resumen (Ollama local | Claude | OpenAI con key del usuario) → notas .md`

## Reglas obligatorias

### 1. Legal y privacidad
- **No** descargar ni scrapear contenido de plataformas de pago (Udemy, etc.). El usuario sube archivos que tiene derecho a usar.
- **Nunca** subir al repo: contenido de usuarios, resúmenes de cursos de pago, API keys, logs, rutas o correos personales.
- API keys solo en `.env` local o en la interfaz (no se guardan en el repo). `.env` está en `.gitignore`.
- Los ejemplos del repo usan solo material con licencia libre (Creative Commons / dominio público).
- Antes de cada `git push`, revisar el diff buscando datos sensibles.

### 2. Seguridad antes de instalar (siempre, sin excepción)
Antes de cualquier `pip install`, `npm install`, extensión o programa:
1. Confirmar que sea el **paquete oficial** (nombre exacto, sin typosquatting) y su repositorio/autor.
2. Revisar que esté **mantenido** y su licencia.
3. Revisar dependencias y que no instale archivos `.pth` ni scripts sospechosos.
4. Preferir lo ya instalado o la librería estándar / API oficial.
5. Informar al usuario el resultado **antes** de instalar.

### 3. Organización y trazabilidad
- Todo dentro de esta carpeta. Mantener el estilo del proyecto: librería estándar primero (vista web con `http.server`, trazas JSONL).
- Registrar abajo cada instalación o cambio importante con fecha.
- Publicar en GitHub solo con confirmación explícita del usuario.

## Registro de cambios
| Fecha | Cambio |
|---|---|
| 2026-10-24 | Creada carpeta `resumidor_videos/` con `AGENTS.md`, `CLAUDE.md`, `README.md`, `.gitignore`, `.env.example` y `.vscode/`. Sin instalaciones. |
| 2026-10-24 | Revisión de seguridad de `faster-whisper` 1.2.1 y sus dependencias (wheels descargadas sin instalar: sin `.pth` ni scripts; `httpx2` verificado como sucesor oficial de `httpx`, de Pydantic). Pendiente de OK para instalar. |
| 2026-10-24 | Stack: librería estándar (`http.server` + HTML), sin frameworks. Ollama vía REST; Claude y OpenAI con sus SDK oficiales como dependencias opcionales. |
| 2026-10-24 | Implementados `transcribir.py`, `proveedores.py`, `resumir.py` (pipeline + CLI), `app.py` + `web/index.html` (interfaz), `prompts/` editables, `requirements.txt` y `ejemplos/clase_fotosintesis.srt` (CC0). Probado con Ollama llama3.2:3b sobre `.srt`. |
| 2026-10-24 | Instalados en `.venv` (desde wheels escaneadas, `--no-index`): faster-whisper 1.2.1, anthropic 2.3.0, openai 3.37.0. PyAV fijado `<19` (19 rompe faster-whisper 1.2.1, issue SYSTRAN/faster-whisper#1589). Probado con audio propio generado por TTS. |
| 2026-10-24 | Infraestructura del repo: LICENSE (MIT), tests `unittest` sin dependencias, CI (ruff + tests en Linux/Windows/macOS), Dependabot, plantillas de issues/PR, CONTRIBUTING, SECURITY, lanzadores `iniciar.bat`/`iniciar.sh`, skill `skills/resumir-video`. Repo público en GitHub con OK del usuario. |
| 2026-10-24 | Catálogo de modelos de Ollama descargables desde la interfaz; avisos si se pierde un trabajo; errores en la traza. Descargado para pruebas el modelo Whisper `large-v3-turbo` (pesos de Hugging Face). |
| 2026-10-24 | v0.2: paquete instalable `resumidor/` con extras `[audio]`, `[claude]`, `[openai]`, `[todo]` y comandos `resumidor` / `resumidor-web`. Estimación de tiempo y Wh (`energia.py`) calibrada con las trazas. Interfaz simplificada con temas (auto, claro, zen, nocturno). Optimizaciones medidas: Whisper beam 1 y llamada única para videos cortos (−33 % de tiempo total). `setuptools` 84.2.1 usado solo para construir (revisado; su `.pth` es el oficial de distutils). |
| 2026-10-24 | Prueba larga con material de dominio público (LibriVox, Internet Archive, MD5 verificado). Descargado `qwen3:8b` (catálogo oficial de Ollama) con OK del usuario para comparar calidad. |
| 2026-10-24 | v0.3: caché de transcripciones (SHA-256), modos clase/reunión/charla, varios archivos por comando, temas retro (fósforo verde y ámbar, diseño propio sin marcas de terceros), banner `docs/banner.svg`. Ideas tomadas de reko, mediascribe y lecture-atelier. Por pedido del usuario, se minimizan las pruebas locales para ahorrar luz. |

## Hoja de ruta
1. ✅ Interfaz web local: subir archivo, elegir proveedor (Ollama / Claude / OpenAI) y pegar API key, ver progreso y resumen.
2. ✅ Transcripción local con `faster-whisper` (previa revisión de seguridad). Acepta también `.srt/.vtt/.txt` directo (sin transcribir).
3. ✅ Resumen por capítulos + apuntes + preguntas de repaso, con plantillas de prompt editables.
4. ✅ Skill de Claude Code (`skills/resumir-video/SKILL.md`) que usa el mismo pipeline.
5. Ejemplo con video Creative Commons, README con GIF, publicar en GitHub (con OK del usuario).
6. Difusión: daily.dev, r/LocalLLaMA, LinkedIn.
