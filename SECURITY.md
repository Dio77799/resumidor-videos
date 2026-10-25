# Seguridad

## Reportar una vulnerabilidad
No abras un issue público. Usa [Report a vulnerability](https://github.com/Dio77799/resumidor-videos/security/advisories/new) en la pestaña *Security* del repo. Respondo lo antes posible.

## Diseño
- La interfaz solo escucha en `127.0.0.1` y rechaza peticiones que vengan de otros orígenes.
- Las API keys se usan en memoria para una sola petición y nunca se escriben en disco ni en los logs.
- Los archivos subidos y los resultados quedan en `entrada/` y `salida/`, que están fuera del repo (`.gitignore`).
