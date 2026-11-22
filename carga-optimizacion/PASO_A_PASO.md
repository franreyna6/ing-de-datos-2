# Hito 12 — Paso a paso para ejecutarlo

Todos los comandos son para **PowerShell** y se ejecutan desde la **raíz del repo**, salvo que se indique otra cosa. Se usan dos terminales: **A** para la API y **B** para los scripts.

## 1. Copiar los archivos y commitear

1. Descomprimir `Hito12_carga_optimizacion.zip` en la raíz del repo y aceptar reemplazar archivos. Se agrega la carpeta `carga-optimizacion/` y se modifican `README.md`, `api/.env.example` y cinco archivos de `api/app/`.
2. Commitear y pushear **antes de medir**, porque cada corrida registra el commit:

```powershell
git add -A
git commit -m "Hito 12: caché opcional de comentarios, scripts de carga y documentación"
git push
```

## 2. Levantar Cassandra y Redis

Abrir Docker Desktop y correr:

```powershell
cd cassandra; docker compose up -d; cd ..
cd redis;     docker compose up -d; cd ..
docker ps
```

En `docker ps` tienen que aparecer `fixture2030-cassandra` y `fixture2030-redis`. Cassandra tarda alrededor de 1 minuto en aceptar conexiones.

## 3. Preparar el entorno de Python (terminal B)

```powershell
api\.venv\Scripts\Activate.ps1
pip install psutil matplotlib
python carga-optimizacion\scripts\preparar_datos.py
```

`psutil` mide la CPU y la memoria de la API y `matplotlib` genera los gráficos. Las dos son opcionales, pero conviene instalarlas.

El último comando tiene que terminar con `Plan generado: 120000 operaciones` y el hash `ac78aea1...`.

## 4. Línea base, sin caché (~4 minutos)

**Terminal A**: levantar la API con la caché apagada. Queda corriendo sin mostrar nada, porque el log va a un archivo.

```powershell
cd api
.\.venv\Scripts\Activate.ps1
$env:CACHE_COMENTARIOS_TTL_S="0"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 *> ..\carga-optimizacion\docs\evidencia\logs_api\api_linea_base.log
```

**Terminal B**: correr la carga.

```powershell
python carga-optimizacion\scripts\ejecutar_linea_base.py
```

Al terminar, el script imprime la etiqueta de la corrida, por ejemplo `base-20261122-221500`. Anotarla y validar la integridad con esa etiqueta:

```powershell
python carga-optimizacion\scripts\validar_integridad.py base-20261122-221500
```

Tiene que decir `Veredicto: OK`.

## 5. Versión optimizada, con caché (~4 minutos)

**Terminal A**: cortar la API con **Ctrl+C** y volver a levantarla con la caché prendida:

```powershell
$env:CACHE_COMENTARIOS_TTL_S="2"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 *> ..\carga-optimizacion\docs\evidencia\logs_api\api_optimizada.log
```

**Terminal B**:

```powershell
python carga-optimizacion\scripts\ejecutar_prueba_optimizada.py
python carga-optimizacion\scripts\validar_integridad.py <etiqueta-opt>
```

## 6. Comparar (terminal B)

```powershell
python carga-optimizacion\scripts\comparar_resultados.py <etiqueta-base> <etiqueta-opt>
Select-String -Path carga-optimizacion\docs\evidencia\logs_api\*.log -Pattern "modo=" | Select-Object -First 4
```

El segundo comando muestra si la API usó el driver nativo de Cassandra (`modo=driver`) o el modo `cqlsh`.

## 7. Commitear la evidencia y avisar

```powershell
git add carga-optimizacion
git commit -m "Hito 12: evidencia de línea base, prueba optimizada y comparación"
git push
```

Después pasar el resultado del `Select-String` del paso 6 para completar las secciones *pendiente* de la documentación con los valores medidos.

## Si algo falla

| Mensaje | Qué hacer |
| :--- | :--- |
| `La API no responde en http://127.0.0.1:8000` | La terminal A no está corriendo la API, o se levantó en otro puerto. |
| `Se esperaba cache APAGADA...` o `...PRENDIDA...` | La API está en el modo equivocado. Reiniciarla con el valor correcto de `$env:CACHE_COMENTARIOS_TTL_S`. |
| `/salud informa que cassandra no esta disponible` | Esperar 1 minuto a que arranque Cassandra y revisar `docker ps`. |
| `La API no devuelve el header X-Cache` | La API corre código viejo. Revisar que el zip se haya descomprimido en la raíz y reiniciar la API. |
| `interrumpida por corte seguro` | La notebook no alcanzó. Repetir **las dos** corridas con `--escala 0.5` al final del comando de carga. |
| `Ya existe ...` | Es una etiqueta repetida. Volver a correr el script, que genera una etiqueta nueva. |
