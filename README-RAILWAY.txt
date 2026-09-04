QUINIELA MEDIAMARKERA — VERSIÓN FINAL

ARCHIVOS QUE DEBES SUBIR A GITHUB
- app.py
- requirements.txt
- Procfile

NO BORRES
- El repositorio de GitHub.
- DATABASE_URL de Railway.
- La base de datos PostgreSQL de Railway.
- Variables de entorno que ya tengas.

VARIABLES DE ENTORNO
- DATABASE_URL: la proporciona Railway si tienes PostgreSQL conectado.
- SECRET_KEY: recomendable mantener una clave propia.
- ADMIN_USERNAME: opcional. Por defecto: RFMF
- INITIAL_PASSWORD: opcional. Por defecto: biwenger2026
- FORCE_ADMIN_RESET: opcional. Por defecto true para recuperar el acceso inicial del administrador.

ACCESO INICIAL
Usuario: RFMF
Contraseña: biwenger2026

IMPORTANTE SOBRE FORCE_ADMIN_RESET
Después de entrar como administrador y cambiar la contraseña de RFMF, cambia FORCE_ADMIN_RESET a false o elimínala.

QUÉ INCLUYE
- Calendario LaLiga 2026/27 sin API de pago.
- Marcador público con actualización automática.
- Resumen de Mi apuesta.
- Resumen de todas las apuestas.
- Clasificación.
- Administración de usuarios.
- Restablecimiento de contraseñas.
- Creación y eliminación de usuarios.
- Edición y eliminación de apuestas por el administrador.
- Apertura/cierre de jornadas.
- Sincronización manual de calendario y resultados.
- Endpoint /health para comprobar Railway.
