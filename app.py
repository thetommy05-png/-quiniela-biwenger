import os
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone
from functools import wraps

import requests
from flask import Flask, request, redirect, url_for, session, jsonify, send_from_directory, render_template_string

app = Flask(__name__, static_folder=None)
app.secret_key = os.getenv("SECRET_KEY", "cambia-esta-clave-en-produccion")

DB = os.getenv("DATABASE_PATH", "quiniela.db")
START_ROUND = 5
PRIZE_PER_HIT = 100_000
TOURNAMENT_ID = 8
SEASON_ID = 97268  # LaLiga 2026/27 en SofaScore

# No se necesita ninguna API key ni pago.
SOFASCORE_URL = "https://api.sofascore.com/api/v1"
ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/esp.1/scoreboard"

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


def clean_name(value):
    value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def stable_id(home, away):
    return f"{clean_name(home)}__{clean_name(away)}"


# Calendario oficial conocido de la Jornada 5. Se usa como base para que la
# quiniela funcione aunque un proveedor externo esté temporalmente bloqueado.
ROUND_CALENDAR = {
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


def calendar_fallback(round_no):
    return [{
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
    } for home, away, date_iso in ROUND_CALENDAR.get(round_no, [])]


def convert_sofascore_event(event):
    home = event.get("homeTeam") or {}
    away = event.get("awayTeam") or {}
    status = event.get("status") or {}
    hs = event.get("homeScore") or {}
    aws = event.get("awayScore") or {}

    status_type = status.get("type") or "notstarted"
    finished = status_type == "finished" or status.get("code") == 100
    live = status_type in {"inprogress", "in_progress"}

    hg = hs.get("current")
    ag = aws.get("current")
    ts = event.get("startTimestamp")
    date_iso = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None

    elapsed = (event.get("time") or {}).get("current")
    if elapsed is None:
        elapsed = (event.get("time") or {}).get("played")
    if elapsed is None:
        elapsed = status.get("elapsed")

    labels = {
        "notstarted": "Próximo",
        "inprogress": "EN DIRECTO",
        "finished": "Finalizado",
        "postponed": "Aplazado",
        "canceled": "Cancelado",
        "cancelled": "Cancelado",
    }

    home_name = home.get("name", "")
    away_name = away.get("name", "")

    return {
        "id": stable_id(home_name, away_name),
        "event_id": str(event.get("id")) if event.get("id") is not None else None,
        "home": home_name,
        "away": away_name,
        "home_logo": None,
        "away_logo": None,
        "date": date_iso,
        "home_goals": hg,
        "away_goals": ag,
        "status": status_type,
        "status_label": labels.get(status_type, status_type),
        "elapsed": elapsed,
        "finished": finished,
        "live": live,
    }


def fetch_sofascore(round_no):
    """Intenta SofaScore. Si Railway recibe 403, no rompe la aplicación."""
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.sofascore.com/",
        "Origin": "https://www.sofascore.com",
    }
    url = f"{SOFASCORE_URL}/unique-tournament/{TOURNAMENT_ID}/season/{SEASON_ID}/events/round/{round_no}"
    try:
        r = requests.get(url, headers=headers, timeout=8)
        if r.status_code != 200:
            return [], f"HTTP {r.status_code}"
        payload = r.json()
        events = payload.get("events") or []
        return [convert_sofascore_event(e) for e in events], None
    except Exception as e:
        return [], f"{type(e).__name__}: {e}"


def espn_status(event):
    competitions = event.get("competitions") or []
    comp = competitions[0] if competitions else {}
    status = comp.get("status") or event.get("status") or {}
    typ = status.get("type") or {}
    state = typ.get("state") or "pre"
    detail = status.get("type", {}).get("detail") or status.get("detail") or ""

    if state == "post":
        return "finished", "Finalizado", False, True, detail
    if state == "in":
        # ESPN detail suele contener el minuto: "45'", "2nd Half", etc.
        elapsed = None
        text = str(detail)
        m = re.search(r"(\d{1,3})\s*['’]", text)
        if m:
            elapsed = int(m.group(1))
        return "inprogress", "EN DIRECTO", True, False, elapsed
    return "notstarted", "Próximo", False, False, None


def fetch_espn_dates(dates):
    """Obtiene marcadores/calendario de ESPN sin API key."""
    found = {}
    errors = []
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

    for date_value in dates:
        try:
            r = requests.get(ESPN_URL, params={"dates": date_value}, headers=headers, timeout=8)
            r.raise_for_status()
            payload = r.json()
            for event in payload.get("events") or []:
                competitions = event.get("competitions") or []
                if not competitions:
                    continue
                comp = competitions[0]
                competitors = comp.get("competitors") or []
                if len(competitors) < 2:
                    continue

                home = next((x for x in competitors if x.get("homeAway") == "home"), competitors[0])
                away = next((x for x in competitors if x.get("homeAway") == "away"), competitors[1])
                home_team = home.get("team") or {}
                away_team = away.get("team") or {}
                home_name = home_team.get("displayName") or home_team.get("shortDisplayName") or ""
                away_name = away_team.get("displayName") or away_team.get("shortDisplayName") or ""

                state, label, live, finished, elapsed = espn_status(event)
                hg = home.get("score")
                ag = away.get("score")
                try:
                    hg = int(hg) if hg is not None else None
                except (TypeError, ValueError):
                    hg = None
                try:
                    ag = int(ag) if ag is not None else None
                except (TypeError, ValueError):
                    ag = None

                date_iso = event.get("date")
                item = {
                    "id": stable_id(home_name, away_name),
                    "event_id": str(event.get("id")) if event.get("id") else None,
                    "home": home_name,
                    "away": away_name,
                    "home_logo": home_team.get("logo"),
                    "away_logo": away_team.get("logo"),
                    "date": date_iso,
                    "home_goals": hg,
                    "away_goals": ag,
                    "status": state,
                    "status_label": label,
                    "elapsed": elapsed,
                    "finished": finished,
                    "live": live,
                }
                found[stable_id(home_name, away_name)] = item
        except Exception as e:
            errors.append(str(e))
    return found, errors


def merge_by_calendar(base, updates):
    """Mantiene nombres/orden del calendario oficial y aplica datos del proveedor."""
    aliases = {
        "sevilla": "sevilla",
        "sevilla-fc": "sevilla",
        "valencia": "valencia",
        "valencia-cf": "valencia",
        "racing-de-santander": "racing-de-santander",
        "racing-santander": "racing-de-santander",
        "alaves": "alaves",
        "deportivo-alaves": "alaves",
        "espanyol": "espanyol",
        "rcd-espanyol-de-barcelona": "espanyol",
        "celta-de-vigo": "celta-de-vigo",
        "celta": "celta-de-vigo",
        "malaga": "malaga",
        "malaga-cf": "malaga",
        "levante": "levante",
        "levante-ud": "levante",
        "barcelona": "barcelona",
        "fc-barcelona": "barcelona",
        "deportivo-de-la-coruna": "deportivo-de-la-coruna",
        "rc-deportivo": "deportivo-de-la-coruna",
        "real-sociedad": "real-sociedad",
        "atletico-de-madrid": "atletico-de-madrid",
        "real-betis": "real-betis",
        "villarreal": "villarreal",
        "real-madrid": "real-madrid",
        "rayo-vallecano": "rayo-vallecano",
        "osasuna": "osasuna",
        "athletic-club": "athletic-club",
        "elche": "elche",
        "getafe": "getafe",
    }

    def team_key(name):
        k = clean_name(name)
        return aliases.get(k, k)

    update_by_pair = {}
    for item in updates.values():
        pair = (team_key(item["home"]), team_key(item["away"]))
        update_by_pair[pair] = item

    result = []
    for m in base:
        pair = (team_key(m["home"]), team_key(m["away"]))
        u = update_by_pair.get(pair)
        if u:
            merged = dict(m)
            for key in ("event_id", "home_logo", "away_logo", "date", "home_goals", "away_goals", "status", "status_label", "elapsed", "finished", "live"):
                if u.get(key) is not None:
                    merged[key] = u[key]
            result.append(merged)
        else:
            result.append(m)
    return result


def fixture_matches(round_no):
    # Base: calendario futuro conocido. Esto evita que un 403 de SofaScore
    # deje la pantalla vacía antes de que empiece la jornada.
    base = calendar_fallback(round_no)

    # 1) Intentamos SofaScore primero.
    sofa_events, _sofa_error = fetch_sofascore(round_no)
    if sofa_events:
        updates = {m["id"]: m for m in sofa_events}
        return merge_by_calendar(base or sofa_events, updates), None

    # 2) Fallback gratuito y sin clave: ESPN. Consultamos las fechas de la jornada.
    dates = sorted({m["date"][:10].replace("-", "") for m in base})
    if dates:
        espn_updates, _errors = fetch_espn_dates(dates)
        if espn_updates:
            return merge_by_calendar(base, espn_updates), None

    # 3) Si todos los proveedores externos están inaccesibles, mantenemos el
    # calendario para poder apostar. No mostramos un falso error de resultados.
    if base:
        return base, None

    return [], "No se pudo obtener el calendario de la jornada."


def get_matches(round_no):
    return fixture_matches(round_no)


def current_bets(round_no):
    c = db()
    rows = c.execute(
        "SELECT match_id,pick FROM bets WHERE username=? AND round=?",
        (session["user"], round_no),
    ).fetchall()
    c.close()
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
        m["score"] = f'{m["home_goals"]} - {m["away_goals"]}' if actual else None
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
    c = db()
    for mid, pick in predictions.items():
        if mid in valid_ids and pick in {"1", "X", "2"}:
            c.execute(
                "INSERT OR REPLACE INTO bets(username,round,match_id,pick) VALUES(?,?,?,?)",
                (session["user"], rn, mid, pick),
            )
    c.commit()
    c.close()
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
    c.close()
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
