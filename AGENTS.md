# AGENTS.md

## Objetivo
Mantener los cambios pequeños, locales y alineados con lo que se pidió explícitamente.

## Reglas de trabajo
- Cambia solo lo solicitado; no amplíes el alcance ni aproveches para refactorizar otras zonas.
- Si la petición afecta a varias piezas, toca únicamente las necesarias para resolverla.
- Si algo no está claro, pregunta antes de modificar archivos fuera del área afectada.
- Responde solo con lo necesario; no expliques pasos, procesos ni desarrollo interno salvo que se pida.
- Conserva el estilo existente, los nombres en español y la estructura de carpetas de `datos/`.
- No rompas compatibilidad con los datos ya guardados en SQLite ni con las rutas/formatos actuales.

## Mapa rápido del proyecto
- [server2.py](server2.py) es la app Flask principal y concentra las rutas API.
- [database.py](database.py) define el esquema SQLite y la lógica de carpetas por faena.
- [config.py](config.py) centraliza rutas, puerto y codificación de PolyBoard.
- [context_builder.py](context_builder.py) prepara el contexto para Ollama.
- [ollama_client.py](ollama_client.py) gestiona las consultas al modelo local.
- [polyboard.py](polyboard.py) lee TXT de PolyBoard y genera PDF.

## Validación
- No hay un sistema formal de tests en el repositorio.
- Si haces cambios de comportamiento, valida con una ejecución manual de `python server2.py` y una comprobación rápida de la ruta o flujo tocado.
- Para cambios de datos, verifica que la app sigue creando y leyendo correctamente la base de datos en `datos/faenas.db`.

## Cursor Cloud specific instructions
- No grabes la pantalla ni generes vídeos de walkthrough, demos o pruebas del entorno de desarrollo.
- No uses RecordScreen ni adjuntes archivos `.mp4` en el pull request ni en la respuesta.
- Valida con `curl`, logs o una captura estática solo si hace falta.

## Referencias útiles
- Dependencias: [requirements.txt](requirements.txt)
- Lanzador Windows: [Arrancar_Faenas.bat](Arrancar_Faenas.bat)
- Lanzador PowerShell: [launch_faenas.ps1](launch_faenas.ps1)