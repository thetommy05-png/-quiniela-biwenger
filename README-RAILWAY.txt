QUINIELA MEDIAMARKERA – V6

Esta versión sincroniza automáticamente el calendario y resultados de LaLiga mediante el feed público sin clave de ESPN. No requiere API de pago ni variable de API.

FUNCIONAMIENTO
- Al arrancar y periódicamente, la aplicación consulta el calendario completo de LaLiga 2026/27.
- Las jornadas y horarios se crean/actualizan automáticamente.
- Los resultados y marcadores se actualizan automáticamente.
- El cierre de una jornada se produce automáticamente al comenzar el primer partido de esa jornada.
- Una vez iniciado el primer partido, NINGÚN jugador puede modificar ningún pronóstico de esa jornada.
- El servidor impone el bloqueo; no depende solo de la interfaz.
- El administrador mantiene acceso a gestión de usuarios, contraseñas, apuestas y resultados.

RAILWAY
1. Sustituye los archivos del proyecto por los del ZIP.
2. No borres PostgreSQL ni sus datos.
3. No necesitas ninguna API_KEY.
4. Railway debe tener DATABASE_URL y SECRET_KEY como variables.
5. El comando de arranque es el del Procfile.

NOTA
El feed de ESPN es público y sin clave, pero es un endpoint no documentado oficialmente por ESPN. La aplicación tiene tolerancia a fallos: si el proveedor no responde, la web sigue usando los datos guardados y reintenta automáticamente.
