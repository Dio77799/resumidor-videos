---
name: resumir-video
description: Convierte un video, audio o transcripción (.srt, .vtt, .txt) del usuario en apuntes Markdown con resumen, notas por sección y preguntas de repaso, usando el pipeline de Resumidor de videos. Úsala cuando el usuario pida resumir, sacar apuntes o notas de una clase, charla o video propio.
---

# Resumir video

Usa el pipeline de este repo para que el resultado sea el mismo que en la interfaz web.

1. Confirma que el archivo es del usuario o que tiene derecho a procesarlo. No descargues contenido de plataformas de terceros.
2. Desde la raíz del repo ejecuta:
   ```bash
   resumidor "<ruta del archivo>" --proveedor ollama --idioma es
   ```
   - Si el comando no existe: `pip install -e ".[audio]"` desde la raíz del repo. Para `.srt`, `.vtt` o `.txt` no hace falta ningún extra.
   - `--proveedor anthropic` u `openai` usan la key de `.env`. Nunca pidas la key en el chat ni la escribas en archivos.
   - `--whisper` (tiny … large-v3-turbo) ajusta precisión contra velocidad; `--salida` elige la carpeta.
   - `--modo reunion` saca decisiones y tareas; `--modo charla`, ideas y frases destacadas (por defecto `clase`).
   - Acepta varios archivos a la vez; volver a procesar el mismo archivo reutiliza su transcripción.
3. El comando imprime la ruta del `.md` generado en `salida/`. Léelo y muéstrale al usuario el resumen general y dónde quedó el archivo.
4. Si el usuario quiere otro estilo de apuntes, edita las plantillas de `resumidor/prompts/` en lugar de cambiar el código.
