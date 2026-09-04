import os
import sqlite3
from datetime import datetime, timezone
from functools import wraps

import requests
from flask import Flask, request, redirect, url_for, session, jsonify, send_from_directory, render_template_string

app = Flask(__name__, static_folder=None)
app.secret_key = os.getenv("SECRET_KEY", "cambia-esta-clave-en-produccion")

DB = os.getenv("DATABASE_PATH", "quiniela.db")
API_KEY = os.getenv("API_FOOTBALL_KEY") or os.getenv("API_FOOTBALL")
API_URL = "https://v3.football.api-sports.io"
LEAGUE_ID = 140  # LaLiga
SEASON = int(os.getenv("FOOTBALL_SEASON", "2026"))  # temporada 2026/27
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
    """Get one LaLiga matchday from API-Football.

    API-Football documents /fixtures as the source for scores/statuses and says
    live fixture data is updated roughly every 15 seconds.
    """
    if not API_KEY:
        return [], "API_FOOTBALL_KEY no configurada en Railway."

    try:
        r = requests.get(
            f"{API_URL}/fixtures",
            headers={"x-apisports-key": API_KEY, "Accept": "application/json"},
            params={
                "league": LEAGUE_ID,
                "season": SEASON,
                "round": f"Regular Season - {round_no}",
                "timezone": "Europe/Madrid",
            },
            timeout=12,
        )
        r.raise_for_status()
        payload = r.json()
        errors = payload.get("errors") or {}
        if errors:
            return [], f"API-Football: {errors}"

        response = payload.get("response", [])
        out = []
        for x in response:
            f = x.get("fixture") or {}
            teams = x.get("teams") or {}
            goals = x.get("goals") or {}
            status_obj = f.get("status") or {}
            status = status_obj.get("short") or "NS"
            elapsed = status_obj.get("elapsed")
            hg, ag = goals.get("home"), goals.get("away")
            finished = status in {"FT", "AET", "PEN"}
            live = status in {"1H", "HT", "2H", "ET", "BT", "P"}
            status_label = {
                "NS": "Próximo",
                "TBD": "Por confirmar",
                "1H": "En juego",
                "HT": "Descanso",
                "2H": "En juego",
                "ET": "Prórroga",
                "BT": "Descanso prórroga",
                "P": "Penaltis",
                "FT": "Finalizado",
                "AET": "Finalizado",
                "PEN": "Finalizado",
                "PST": "Aplazado",
                "CANC": "Cancelado",
                "SUSP": "Suspendido",
            }.get(status, status)

            out.append({
                "id": str(f.get("id")),
                "home": (teams.get("home") or {}).get("name", ""),
                "away": (teams.get("away") or {}).get("name", ""),
                "home_logo": (teams.get("home") or {}).get("logo"),
                "away_logo": (teams.get("away") or {}).get("logo"),
                "date": f.get("date"),
                "home_goals": hg,
                "away_goals": ag,
                "status": status,
                "status_label": status_label,
                "elapsed": elapsed,
                "finished": finished,
                "live": live,
            })
        out.sort(key=lambda m: m.get("date") or "")
        return out, None
    except Exception as e:
        app.logger.warning("API-Football: %s", e)
        return [], f"No se pudo consultar API-Football: {e}"


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
        "api_configured": bool(API_KEY),
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
    c = db()
    for mid, pick in predictions.items():
        if mid in valid_ids and pick in {"1", "X", "2"}:
            c.execute(
                "INSERT OR REPLACE INTO bets(username,round,match_id,pick) VALUES(?,?,?,?)",
                (session["user"], rn, mid, pick),
            )
    c.commit()
    return jsonify({"ok": True})


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
