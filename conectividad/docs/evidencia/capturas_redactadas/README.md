# Capturas redactadas

Este hito no usa capturas de pantalla. Toda la evidencia es **texto generado por los scripts**
(`.txt`, `.json` y `.log` en `docs/evidencia/`), por dos motivos:

1. **Redacción verificable:** el texto pasa por `redactar()` antes de escribirse, y se puede
   revisar con una búsqueda (`grep`) que no contenga tokens ni passwords. En una imagen eso no se
   puede comprobar automáticamente.
2. **Trazabilidad:** cada línea conserva fecha, commit, origen, cliente, capa, resultado,
   duración y request ID (RNF18), que en una captura se pierden o quedan ilegibles.

Si se agregan capturas (por ejemplo, de Swagger), deben mostrar el header `X-Request-ID` y no
deben mostrar el `.env`, la configuración ni ninguna credencial.
