# Cómo contribuir

¡Gracias por tu interés! Las contribuciones son bienvenidas en español o inglés.

## Preparar el entorno
```bash
python -m venv .venv
.venv/Scripts/activate        # Windows  (en Linux/macOS: source .venv/bin/activate)
pip install -e ".[todo]"
python -m unittest discover -s tests -t .
```

## Principios del proyecto
- **Librería estándar primero.** Cada dependencia nueva debe justificarse: paquete oficial, mantenido, con licencia compatible y sin scripts de instalación raros.
- **Privacidad.** Nada de keys, rutas personales, logs ni contenido de usuarios en el repo. Las keys solo viven en memoria o en `.env`.
- **Solo contenido propio.** No se aceptan funciones para descargar contenido de plataformas de pago o protegido.
- **Fácil de usar.** Si un cambio afecta a la interfaz, incluye una captura en el PR.

## Ideas por dónde empezar
- Nuevos proveedores compatibles (por ejemplo LM Studio o Gemini).
- Exportar a otros formatos (PDF, Anki).
- Mejorar las plantillas de `resumidor/prompts/` para modelos pequeños.
- Traducir la interfaz.

Los agentes de IA que trabajen en el repo deben seguir [AGENTS.md](AGENTS.md).
