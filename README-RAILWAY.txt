QUINIELA MEDIAMARKERA — DEFINITIVA V4

FUNCIONES INCLUIDAS
- Sin API de pago ni dependencia de SofaScore.
- Calendario y partidos guardados en la propia base de datos.
- Cierre AUTOMÁTICO de apuestas: la jornada se cierra al comenzar el PRIMER partido de esa jornada.
- Además, cada partido deja de poder editarse cuando comienza.
- El administrador puede introducir las fechas/horas de los partidos desde Administración.
- Resultados y marcadores se introducen desde Administración y los aciertos se recalculan automáticamente.
- Login con desplegable de usuarios: no hace falta escribir el nombre.
- Mi apuesta muestra siempre su resumen: aciertos, pendientes, fallos y premio.
- Resumen muestra todas las apuestas de todos los participantes de la jornada.
- Clasificación acumulada de todas las jornadas.
- Administración completa: jornadas, partidos, resultados, usuarios, contraseñas y gestión/edición/borrado de apuestas.
- PostgreSQL de Railway compatible (incluye corrección de filas como diccionarios).
- SQLite local compatible.
- Diseño responsive para móvil, sin el zoom/ampliación anterior.

USUARIOS INICIALES
Se crean en una base de datos nueva los usuarios configurados en app.py.
Contraseña inicial: biwenger2026
RFMF es administrador.

IMPORTANTE CON UNA BASE DE DATOS EXISTENTE
La aplicación conserva usuarios y apuestas existentes y realiza las migraciones necesarias.
Si RFMF ya existe, conserva su contraseña actual; el administrador puede restablecer las contraseñas desde Administración.

RAILWAY
1. Sustituye los archivos del repositorio por los de este ZIP.
2. NO es necesario borrar el repositorio ni crear otro.
3. Procfile: web: gunicorn app:app
4. requirements.txt instala Flask, Gunicorn y psycopg.
5. En Railway usa PostgreSQL mediante DATABASE_URL y define SECRET_KEY.
6. Haz un nuevo Deploy/Deploy Latest Commit.
7. Si Railway muestra un error, abrir Deployments > View Logs.

CIERRE AUTOMÁTICO
Para que el cierre sea automático, el administrador debe poner la fecha y hora de cada partido.
El cierre se calcula solo usando el partido más temprano de la jornada. No hay que pulsar ningún botón para cerrar.

GESTIÓN DE APUESTAS
Administración > Apuestas permite seleccionar una jornada y modificar o borrar el pronóstico de cualquier usuario, incluso después del cierre normal. Esto permite corregir incidencias como administrador.
