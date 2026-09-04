# Quiniela Mediamarkera

## Estructura
No utiliza `templates/` ni `static/` para plantillas Flask. `index.html` está en la raíz y los recursos CSS/logo están en `static/`.

## Railway
Variables recomendadas:
- `API_FOOTBALL_KEY`: clave de API-Football.
- `FOOTBALL_SEASON`: `2026`.
- `ADMIN_PASSWORD`: contraseña de acceso (si no se define: `biwenger2026`).
- `SECRET_KEY`: una clave larga aleatoria.
- `DATABASE_PATH`: opcional.

La aplicación:
- empieza en Jornada 5;
- 100.000 € por acierto;
- guarda las apuestas en SQLite;
- obtiene partidos y resultados desde API-Football;
- permite ver aciertos, fallos, pendientes y premio acumulado;
- refresca los partidos cada 60 segundos.
