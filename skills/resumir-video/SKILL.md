---
name: resumir-video
description: Convierte un video, audio o transcripción (.srt, .vtt, .txt) del usuario en apuntes Markdown con resumen, notas por sección y preguntas de repaso, usando el pipeline de Resumidor de videos. Úsala cuando el usuario pida resumir, sacar apuntes o notas de una clase, charla o video propio.
---

# Resumir video

Usa el pipeline de este repo para que el resultado sea el mismo que en la interfaz web.

1. Confirma que el archivo es del usuario o que tiene derecho a procesarlo. No descargues contenido de plataformas de terceros.
2. Desde la raíz del repo ejecuta:
   ```bash
   python resumir.py "<ruta del archivo>" --proveedor ollama --idioma es
   ```
   - Audio/video necesita `pip install -r requirements.txt`. Para `.srt`, `.vtt` o `.txt` no hace falta instalar nada.
   - `--proveedor anthropic` u `openai` usan la key de `.env`. Nunca pidas la key en el chat ni la escribas en archivos.
   - `--whisper tiny|base|small|medium|large-v3` ajusta precisión contra velocidad (por defecto `small`).
3. El comando imprime la ruta del `.md` generado en `salida/`. Léelo y muéstrale al usuario el resumen general y dónde quedó el archivo.
4. Si el usuario quiere otro estilo de apuntes, edita las plantillas de `prompts/` en lugar de cambiar el código.
