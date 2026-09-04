QUINIELA MEDIAMARKERA — VERSIÓN DEFINITIVA

Sube este contenido a Railway.

FUNCIONAMIENTO:
- El calendario de LaLiga 2026/2027 se sincroniza automáticamente desde una fuente pública de resultados.
- Horarios y resultados no los introduce el administrador.
- El cierre es automático: cuando comienza el primer partido de una jornada, se bloquean TODOS los partidos de esa jornada para TODOS los usuarios.
- Login con desplegable de usuarios.
- Interfaz optimizada para móvil y sin zoom exagerado.
- /health sirve para comprobar que la aplicación está viva.

RAILWAY:
1. Conecta este proyecto/ZIP a tu servicio.
2. Mantén DATABASE_URL si ya tienes PostgreSQL.
3. Mantén SECRET_KEY si ya existe.
4. Si es una instalación nueva, la contraseña inicial de todos los usuarios es 1234.
5. Railway detecta Python y Procfile automáticamente; también puedes fijar Start Command a: gunicorn app:app

IMPORTANTE:
Esta versión usa tablas con prefijo qm_ para no destruir tablas antiguas accidentalmente.
