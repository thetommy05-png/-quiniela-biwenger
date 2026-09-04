import os
import re
import sqlite3
from datetime import datetime, timezone
from functools import wraps

import requests
from flask import Flask, request, redirect, url_for, session, jsonify, send_from_directory, render_template_string

app = Flask(__name__, static_folder=None)
app.secret_key = os.getenv("SECRET_KEY", "cambia-esta-clave-en-produccion")

DB = os.getenv("DATABASE_PATH", "quiniela.db")
# Resultados en directo mediante SofaScore (sin API key)
SOFASCORE_URL = "https://www.sofascore.com/api/v1"
TOURNAMENT_ID = 8       # LaLiga
SEASON_ID = 97268       # 2026/27
START_ROUND = 5
PRIZE_PER_HIT = 100_000


LOGIN_HTML = """<!doctype html><html lang=\"es\"><head><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>Quiniela Mediamarkera</title><style>
body{margin:0;background:#07090b;color:#fff;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif}.box{max-width:430px;margin:15vh auto;padding:28px;background:#12161b;border:1px solid #30363d;border-radius:20px}h1{font-size:30px;margin:0 0 8px}b{color:#e30613}.muted{color:#a8adb6}label{display:block;margin-top:18px}input{width:100%;box-sizing:border-box;padding:14px;border-radius:10px;border:1px solid #424850;background:#20252b;color:#fff;font-size:16px;margin-top:7px}button{width:100%;padding:14px;border:0;border-radius:10px;background:#e30613;color:#fff;font-size:16px;font-weight:800;margin-top:20px}.error{background:#3a1418;color:#ff9ca3;padding:10px;border-radius:10px;margin-top:15px}
</style></head><body><div class=\"box\"><h1>QUINIELA <b>MEDIAMARKERA</b></h1><p class=\"muted\">Jornada 5 · 100.000 € por acierto</p>{% if error %}<div class=\"error\">{{error}}</div>{% endif %}<form method=\"post\"><label>Usuario</label><input name=\"username\" value=\"RFM\" required><label>Contraseña</label><input name=\"password\" type=\"password\" required><button>Iniciar sesión</button></form></div></body></html>"""


def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS bets(
        username TEXT, round INTEGER, match_id TEXT, pick TEXT,
        PRIMARY KEY(username,round,match_id))""")
    c.commit()
    return c


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return jsonify({"error": "No autenticado"}), 401
        return fn(*args, **kwargs)
    return wrapper


def outcome(home, away):
    if home is None or away is None:
        return None
    return "1" if home > away else ("2" if home < away else "X")



def fixture_matches(round_no):
    """Obtiene una jornada de LaLiga desde la API pública de SofaScore.

    La API de SofaScore tiene un endpoint específico por jornada. Usamos ese
    endpoint directamente en lugar de intentar reconstruir la jornada con
    páginas de partidos anteriores/siguientes, que puede devolver una lista
    vacía para jornadas futuras.

    Si SofaScore estuviera temporalmente inaccesible, para la jornada 5 usamos
    el calendario oficial conocido como respaldo para que la quiniela siga
    permitiendo apostar. En cuanto la API vuelva, los resultados y marcadores
    se sincronizan automáticamente.
    """
    API_BASES = [
        "https://api.sofascore.com/api/v1",
        "https://www.sofascore.com/api/v1",
    ]

    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) "
                      "AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1",
        "Accept": "application/json",
        "Referer": "https://www.sofascore.com/",
    }

    def stable_id(home, away):
        import unicodedata
        def clean(s):
            s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
            return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
        return f"{clean(home)}__{clean(away)}"

    def convert_event(event):
        home = event.get("homeTeam") or {}
        away = event.get("awayTeam") or {}
        status = event.get("status") or {}
        hs = event.get("homeScore") or {}
        aws = event.get("awayScore") or {}

        status_type = status.get("type") or "notstarted"
        status_code = status.get("code")
        finished = status_type == "finished" or status_code in {100}
        live = status_type in {"inprogress", "in_progress"}

        labels = {
            "notstarted": "Próximo",
            "inprogress": "EN DIRECTO",
            "finished": "Finalizado",
            "postponed": "Aplazado",
            "canceled": "Cancelado",
            "cancelled": "Cancelado",
        }
        label = labels.get(status_type, status_type)

        hg = hs.get("current")
        ag = aws.get("current")

        # SofaScore puede guardar el minuto en distintos campos según el partido.
        elapsed = (event.get("time") or {}).get("current")
        if elapsed is None:
            elapsed = (event.get("time") or {}).get("played")
        if elapsed is None:
            elapsed = status.get("elapsed")

        ts = event.get("startTimestamp")
        date_iso = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None

        home_name = home.get("name", "")
        away_name = away.get("name", "")

        return {
            # ID estable por enfrentamiento: funciona tanto con API como con fallback.
            "id": stable_id(home_name, away_name),
            "event_id": str(event.get("id")) if event.get("id") is not None else None,
            "home": home_name,
            "away": away_name,
            "home_logo": f"https://api.sofascore.com/api/v1/team/{home.get('id')}/image"
                         if home.get("id") else None,
            "away_logo": f"https://api.sofascore.com/api/v1/team/{away.get('id')}/image"
                         if away.get("id") else None,
            "date": date_iso,
            "home_goals": hg,
            "away_goals": ag,
            "status": status_type,
            "status_label": label,
            "elapsed": elapsed,
            "finished": finished,
            "live": live,
        }

    # 1) Fuente principal: endpoint de jornada.
    last_error = None
    for base_url in API_BASES:
        url = f"{base_url}/unique-tournament/{TOURNAMENT_ID}/season/{SEASON_ID}/events/round/{round_no}"
        try:
            r = requests.get(url, headers=headers, timeout=15)
            r.raise_for_status()
            payload = r.json()
            events = payload.get("events") or []
            if events:
                out = [convert_event(e) for e in events]
                out.sort(key=lambda m: m.get("date") or "")
                return out, None
            last_error = f"SofaScore devolvió 0 partidos para la jornada {round_no}."
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"

    # 2) Respaldo para Jornada 5: calendario oficial publicado.
    # IDs estables para que las apuestas guardadas no dependan de un event ID externo.
    fallback_rounds = {
        5: [
            ("Sevilla", "Valencia", "2026-09-11T21:00:00+02:00"),
            ("Racing de Santander", "Alavés", "2026-09-12T14:00:00+02:00"),
            ("Osasuna", "Espanyol", "2026-09-12T16:15:00+02:00"),
            ("Athletic Club", "Elche", "2026-09-12T18:30:00+02:00"),
            ("Real Madrid", "Rayo Vallecano", "2026-09-12T21:00:00+02:00"),
            ("Celta de Vigo", "Málaga", "2026-09-13T14:00:00+02:00"),
            ("Levante", "Barcelona", "2026-09-13T16:15:00+02:00"),
            ("Getafe", "Deportivo de La Coruña", "2026-09-13T18:30:00+02:00"),
            ("Real Sociedad", "Atlético de Madrid", "2026-09-13T21:00:00+02:00"),
            ("Villarreal", "Real Betis", "2026-09-14T21:00:00+02:00"),
        ]
    }

    fallback = fallback_rounds.get(int(round_no), [])
    if fallback:
        out = []
        for home, away, date_iso in fallback:
            out.append({
                "id": stable_id(home, away),
                "event_id": None,
                "home": home,
                "away": away,
                "home_logo": None,
                "away_logo": None,
                "date": date_iso,
                "home_goals": None,
                "away_goals": None,
                "status": "notstarted",
                "status_label": "Próximo",
                "elapsed": None,
                "finished": False,
                "live": False,
            })
        return out, f"Calendario de respaldo activo. SofaScore: {last_error}"

    return [], f"No se pudieron obtener los partidos de SofaScore: {last_error}"

def get_matches(round_no):
    return fixture_matches(round_no)


def current_bets(round_no):
    c = db()
    rows = c.execute(
        "SELECT match_id,pick FROM bets WHERE username=? AND round=?",
        (session["user"], round_no),
    ).fetchall()
    return {r["match_id"]: r["pick"] for r in rows}


@app.route("/")
def home():
    if "user" not in session:
        return redirect(url_for("login"))
    return send_from_directory(".", "index.html")


@app.route("/style.css")
def css_file():
    return send_from_directory(".", "style.css")


@app.route("/rfmf_logo.svg")
def logo_file():
    return send_from_directory(".", "rfmf_logo.svg")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username", "RFM").strip() or "RFM"
        p = request.form.get("password", "")
        if p == os.getenv("ADMIN_PASSWORD", "biwenger2026"):
            session["user"] = u
            return redirect(url_for("home"))
        return render_template_string(LOGIN_HTML, error="Contraseña incorrecta.")
    return render_template_string(LOGIN_HTML, error=None)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/api/matches")
@login_required
def api_matches():
    rn = max(START_ROUND, min(38, int(request.args.get("round", START_ROUND))))
    matches, api_error = get_matches(rn)
    bets = current_bets(rn)
    for m in matches:
        actual = outcome(m["home_goals"], m["away_goals"]) if m["finished"] else None
        m["pick"] = bets.get(m["id"])
        m["actual"] = actual
        m["score"] = f'{m["home_goals"]} - {m["away_goals"]}' if m["finished"] else None
        m["correct"] = bool(actual and m["pick"] == actual)
    return jsonify({
        "jornada": rn,
        "matches": matches,
        "prize_per_hit": PRIZE_PER_HIT,
        "api_configured": True,
        "api_error": api_error,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })


@app.route("/api/save", methods=["POST"])
@login_required
def api_save():
    data = request.get_json(silent=True) or {}
    rn = max(START_ROUND, min(38, int(data.get("round", START_ROUND))))
    predictions = data.get("predictions", {})
    matches, _ = get_matches(rn)
    valid_ids = {m["id"] for m in matches}
    # Si la fuente está temporalmente caída, no bloqueamos una apuesta ya enviada.
    # Los IDs enviados por el frontend se consideran válidos para la jornada.
    if not valid_ids:
        valid_ids = {str(mid) for mid in predictions.keys()}

    c = db()
    saved = 0
    for mid, pick in predictions.items():
        if str(mid) in valid_ids and pick in {"1", "X", "2"}:
            c.execute(
                "INSERT OR REPLACE INTO bets(username,round,match_id,pick) VALUES(?,?,?,?)",
                (session["user"], rn, str(mid), pick),
            )
            saved += 1
    c.commit()
    return jsonify({"ok": saved > 0, "saved": saved})


@app.route("/api/check")
@login_required
def api_check():
    rn = max(START_ROUND, min(38, int(request.args.get("round", START_ROUND))))
    matches, api_error = get_matches(rn)
    bets = current_bets(rn)
    results = []
    hits = pending = errors = 0
    for m in matches:
        actual = outcome(m["home_goals"], m["away_goals"]) if m["finished"] else None
        pick = bets.get(m["id"])
        hit = bool(actual and pick == actual)
        if actual:
            hits += int(hit)
            errors += int(not hit)
        else:
            pending += 1
        results.append({
            "id": m["id"], "home": m["home"], "away": m["away"],
            "pick": pick, "actual": actual,
            "score": f'{m["home_goals"]} - {m["away_goals"]}' if actual else None,
            "hit": hit, "status": m["status"], "status_label": m["status_label"],
            "elapsed": m["elapsed"], "live": m["live"], "finished": m["finished"],
        })
    return jsonify({
        "round": rn, "hits": hits, "pending": pending, "errors": errors,
        "prize": hits * PRIZE_PER_HIT, "results": results,
        "api_error": api_error,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })


@app.route("/api/summary")
@login_required
def api_summary():
    total_hits = total_pending = 0
    rounds = []
    c = db()
    saved_rounds = [r[0] for r in c.execute(
        "SELECT DISTINCT round FROM bets WHERE username=? AND round>=? ORDER BY round",
        (session["user"], START_ROUND),
    ).fetchall()]
    for rn in saved_rounds:
        matches, _ = get_matches(rn)
        bets = current_bets(rn)
        hits = pending = errors = 0
        for m in matches:
            actual = outcome(m["home_goals"], m["away_goals"]) if m["finished"] else None
            if actual is None:
                pending += 1
            elif bets.get(m["id"]) == actual:
                hits += 1
            else:
                errors += 1
        total_hits += hits
        total_pending += pending
        rounds.append({"round": rn, "hits": hits, "pending": pending, "errors": errors, "prize": hits * PRIZE_PER_HIT})
    return jsonify({"hits": total_hits, "prize": total_hits * PRIZE_PER_HIT, "rounds": rounds, "pending": total_pending})


if __name__ == "__main__":
    db()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
