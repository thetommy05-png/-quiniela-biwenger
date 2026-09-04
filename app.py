import os
import sqlite3
import hashlib
from datetime import datetime, timedelta, timezone
from functools import wraps
from urllib.parse import quote

import requests
from flask import Flask, request, redirect, url_for, session, flash, render_template_string, abort, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "CAMBIA-ESTA-CLAVE-EN-RAILWAY")

DATABASE_URL = os.environ.get("DATABASE_URL")
SQLITE_PATH = os.environ.get("SQLITE_PATH", "quiniela.db")
INITIAL_PASSWORD = os.environ.get("INITIAL_PASSWORD", "biwenger2026")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "RFMF").strip() or "RFMF"
PRIZE_PER_HIT = 100_000
SEASON = 2026
LEAGUE = "esp.1"

PARTICIPANTS = [
    "Cablo Parmena", "Ojeadores de rondos", "AC Decza", "MiCapitan FC",
    "Real Funafuti FC", "El Sin Nombre", "CD Leganes", "Quinta Buitre",
    "Al Toque", "Pepino Goya", "RFMF"
]

# Public ESPN endpoint. No API key is required.
ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/esp.1/scoreboard"

# LaLiga 2026/27 round dates. The provider is still the source of truth for
# the actual kickoff time and live score; these dates are only used to locate
# the correct matchday before/after reschedulings.
ROUND_DATES = {
    1: "2026-08-15", 2: "2026-08-22", 3: "2026-08-29",
    4: "2026-09-05", 5: "2026-09-11", 6: "2026-09-16",
    7: "2026-09-18", 8: "2026-10-02", 9: "2026-10-16",
    10: "2026-10-23", 11: "2026-10-30", 12: "2026-11-06",
    13: "2026-11-20", 14: "2026-11-27", 15: "2026-12-04",
    16: "2026-12-11", 17: "2026-12-18", 18: "2027-01-01",
    19: "2027-01-08", 20: "2027-01-15", 21: "2027-01-22",
    22: "2027-01-29", 23: "2027-02-05", 24: "2027-02-12",
    25: "2027-02-19", 26: "2027-02-26", 27: "2027-03-05",
    28: "2027-03-12", 29: "2027-03-19", 30: "2027-04-02",
    31: "2027-04-09", 32: "2027-04-16", 33: "2027-04-23",
    34: "2027-04-30", 35: "2027-05-07", 36: "2027-05-14",
    37: "2027-05-21", 38: "2027-05-28",
}

app.config["JSON_SORT_KEYS"] = False


def db():
    if DATABASE_URL:
        if not psycopg or not dict_row:
            raise RuntimeError("Falta psycopg. Añádelo a requirements.txt.")
        return psycopg.connect(DATABASE_URL, row_factory=dict_row)
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def sql(conn, query, params=()):
    if DATABASE_URL:
        query = query.replace("?", "%s")
    return conn.execute(query, params)


def rowdict(row):
    if row is None:
        return None
    return dict(row)


def init_db():
    conn = db()
    if DATABASE_URL:
        statements = [
            """CREATE TABLE IF NOT EXISTS users(
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                is_admin BOOLEAN NOT NULL DEFAULT FALSE)""",
            """CREATE TABLE IF NOT EXISTS rounds(
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                open BOOLEAN NOT NULL DEFAULT TRUE)""",
            """CREATE TABLE IF NOT EXISTS matches(
                id SERIAL PRIMARY KEY,
                round_id INTEGER NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
                home TEXT NOT NULL,
                away TEXT NOT NULL,
                match_order INTEGER NOT NULL,
                external_id TEXT)""",
            """CREATE TABLE IF NOT EXISTS bets(
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
                prediction TEXT NOT NULL CHECK(prediction IN ('1','X','2')),
                PRIMARY KEY(user_id,match_id))"""
        ]
    else:
        statements = [
            """CREATE TABLE IF NOT EXISTS users(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0)""",
            """CREATE TABLE IF NOT EXISTS rounds(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                open INTEGER NOT NULL DEFAULT 1)""",
            """CREATE TABLE IF NOT EXISTS matches(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                round_id INTEGER NOT NULL,
                home TEXT NOT NULL,
                away TEXT NOT NULL,
                match_order INTEGER NOT NULL,
                external_id TEXT)""",
            """CREATE TABLE IF NOT EXISTS bets(
                user_id INTEGER NOT NULL,
                match_id INTEGER NOT NULL,
                prediction TEXT NOT NULL,
                PRIMARY KEY(user_id,match_id))"""
        ]

    for statement in statements:
        try:
            conn.execute(statement)
        except Exception:
            # Existing installations may already have the tables.
            pass

    # Existing installations from the previous version may not have external_id.
    try:
        conn.execute("ALTER TABLE matches ADD COLUMN external_id TEXT")
    except Exception:
        pass

    # Create the 11 accounts if they don't exist.
    for username in PARTICIPANTS:
        existing = sql(conn, "SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if existing is None:
            sql(conn, "INSERT INTO users(username,password,is_admin) VALUES(?,?,?)",
                (username, generate_password_hash(INITIAL_PASSWORD), username == ADMIN_USERNAME))

    # Guarantee that RFMF exists and can log in NOW. We only reset it when the
    # current password is the old default/unknown bootstrap password. This keeps
    # future admin password changes intact.
    admin = sql(conn, "SELECT * FROM users WHERE username=?", (ADMIN_USERNAME,)).fetchone()
    if admin is None:
        sql(conn, "INSERT INTO users(username,password,is_admin) VALUES(?,?,?)",
            (ADMIN_USERNAME, generate_password_hash(INITIAL_PASSWORD), True))
    else:
        try:
            ok = check_password_hash(admin["password"], INITIAL_PASSWORD)
        except Exception:
            ok = False
        if not ok:
            # One-time bootstrap reset is controlled by FORCE_ADMIN_RESET.
            # Default is TRUE so the broken previous deployment can be recovered.
            if os.environ.get("FORCE_ADMIN_RESET", "true").lower() == "true":
                sql(conn, "UPDATE users SET password=?, is_admin=? WHERE username=?",
                    (generate_password_hash(INITIAL_PASSWORD), True, ADMIN_USERNAME))
            else:
                sql(conn, "UPDATE users SET is_admin=? WHERE username=?", (True, ADMIN_USERNAME))

    # If the DB has no rounds, create all 38 so navigation and administration
    # work immediately. Matches are populated from ESPN on first access.
    # Ensure all 38 matchdays exist, including on databases created by older versions.
    for n in range(1, 39):
        exists = sql(conn, "SELECT id FROM rounds WHERE name=?", (f"Jornada {n}",)).fetchone()
        if exists is None:
            sql(conn, "INSERT INTO rounds(name,open) VALUES(?,?)",
                (f"Jornada {n}", True))

    # Repair the old demo installation: if there is a single Jornada 1 with
    # demo matches, keep it but let the live sync replace its matches.
    conn.commit()
    conn.close()


def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    conn = db()
    u = sql(conn, "SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    conn.close()
    return u


def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapped


def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        u = current_user()
        if not u or not u["is_admin"]:
            abort(403)
        return fn(*args, **kwargs)
    return wrapped


def normalize_team(name):
    replacements = {
        "Racing Club": "Racing de Santander",
        "Racing de Santander": "Racing de Santander",
        "R. Racing Club": "Racing de Santander",
        "Deportivo La Coruna": "Deportivo de A Coruña",
        "Deportivo de La Coruna": "Deportivo de A Coruña",
        "Deportivo": "Deportivo de A Coruña",
        "Málaga CF": "Málaga",
        "FC Barcelona": "Barcelona",
        "RCD Espanyol de Barcelona": "Espanyol",
        "RCD Espanyol": "Espanyol",
        "CA Osasuna": "Osasuna",
        "Real Betis": "Betis",
        "Real Sociedad": "Real Sociedad",
        "Atlético de Madrid": "Atlético de Madrid",
        "Rayo Vallecano": "Rayo Vallecano",
        "Athletic Club": "Athletic Club",
        "Elche CF": "Elche",
        "Sevilla FC": "Sevilla",
        "Valencia CF": "Valencia",
        "Real Madrid": "Real Madrid",
        "Villarreal CF": "Villarreal",
        "Getafe CF": "Getafe",
        "Levante UD": "Levante",
        "Celta": "Celta",
    }
    return replacements.get(name, name)


def outcome(home, away):
    if home is None or away is None:
        return None
    return "1" if home > away else ("2" if home < away else "X")


def round_window(round_no):
    # Exact windows for the currently relevant opening rounds. Later rounds use
    # a wider estimated window and ESPN's week number when available.
    exact = {
        1: ("20260815", "20260820"),
        2: ("20260822", "20260827"),
        3: ("20260828", "20260901"),
        4: ("20260904", "20260908"),
        5: ("20260911", "20260914"),
        6: ("20260915", "20260918"),
        7: ("20260918", "20260921"),
    }
    if round_no in exact:
        return exact[round_no]
    base = datetime.fromisoformat(ROUND_DATES.get(round_no, ROUND_DATES[1]))
    start = base - timedelta(days=4)
    end = base + timedelta(days=6)
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def parse_espn_event(event):
    comp = (event.get("competitions") or [{}])[0]
    competitors = comp.get("competitors") or []
    home = next((x for x in competitors if x.get("homeAway") == "home"), competitors[0] if competitors else {})
    away = next((x for x in competitors if x.get("homeAway") == "away"), competitors[1] if len(competitors) > 1 else {})
    hs = home.get("score")
    ass = away.get("score")
    try:
        hs = int(hs) if hs is not None and hs != "" else None
    except Exception:
        hs = None
    try:
        ass = int(ass) if ass is not None and ass != "" else None
    except Exception:
        ass = None

    status = (event.get("status") or {}).get("type") or {}
    state = status.get("state", "pre")
    status_name = status.get("name", "STATUS_SCHEDULED")
    completed = bool(status.get("completed")) or state == "post"
    live = state == "in"
    display_clock = (event.get("status") or {}).get("displayClock")
    period = (event.get("status") or {}).get("period")

    return {
        "external_id": str(event.get("id")),
        "home": normalize_team((home.get("team") or {}).get("displayName", "")),
        "away": normalize_team((away.get("team") or {}).get("displayName", "")),
        "home_logo": (home.get("team") or {}).get("logo"),
        "away_logo": (away.get("team") or {}).get("logo"),
        "date": event.get("date"),
        "home_goals": hs,
        "away_goals": ass,
        "completed": completed,
        "live": live,
        "status": status_name,
        "clock": display_clock,
        "period": period,
        "week": ((event.get("week") or {}).get("number")),
    }


FALLBACK_FIXTURES = {
    5: [
        ("Sevilla", "Valencia", "2026-09-11T21:00:00+02:00"),
        ("Racing de Santander", "Alavés", "2026-09-12T14:00:00+02:00"),
        ("Osasuna", "Espanyol", "2026-09-12T16:15:00+02:00"),
        ("Athletic Club", "Elche", "2026-09-12T18:30:00+02:00"),
        ("Real Madrid", "Rayo Vallecano", "2026-09-12T21:00:00+02:00"),
        ("Celta", "Málaga", "2026-09-13T14:00:00+02:00"),
        ("Levante", "Barcelona", "2026-09-13T16:15:00+02:00"),
        ("Getafe", "Deportivo de A Coruña", "2026-09-13T18:30:00+02:00"),
        ("Real Sociedad", "Atlético de Madrid", "2026-09-13T21:00:00+02:00"),
        ("Villarreal", "Betis", "2026-09-14T21:00:00+02:00"),
    ]
}

def fallback_round(round_no):
    return [{
        "external_id": f"manual-{round_no}-{i}", "home": h, "away": a, "home_logo": None,
        "away_logo": None, "date": d, "home_goals": None, "away_goals": None,
        "completed": False, "live": False, "status": "STATUS_SCHEDULED",
        "clock": None, "period": None, "week": round_no
    } for i,(h,a,d) in enumerate(FALLBACK_FIXTURES.get(round_no, []),1)]

def fetch_round(round_no):
    start, end = round_window(round_no)
    params = {
        "dates": f"{start}-{end}",
        "limit": 100,
        "seasontype": 2,
    }
    headers = {"User-Agent": "Quiniela-Mediamarkera/1.0"}
    errors = []

    for endpoint in (ESPN_URL, ESPN_URL.replace("site.api.", "site.web.api.")):
        try:
            r = requests.get(endpoint, params=params, headers=headers, timeout=12)
            r.raise_for_status()
            data = r.json()
            events = data.get("events") or []
            parsed = [parse_espn_event(e) for e in events]

            # Best case: ESPN tells us the matchday.
            exact = [m for m in parsed if m["week"] == round_no]
            if len(exact) >= 8:
                return sorted(exact, key=lambda x: x.get("date") or ""), None

            # Fallback: choose the 10 events closest to the nominal round date.
            target = datetime.fromisoformat(ROUND_DATES.get(round_no, ROUND_DATES[1])).replace(tzinfo=timezone.utc)
            parsed = [m for m in parsed if m["home"] and m["away"]]
            parsed.sort(key=lambda m: abs((datetime.fromisoformat(m["date"].replace("Z","+00:00")) - target).total_seconds())
                        if m.get("date") else 10**20)
            candidate = parsed[:10]
            candidate.sort(key=lambda x: x.get("date") or "")
            if candidate:
                return candidate, None
            errors.append("ESPN no devolvió partidos.")
        except Exception as exc:
            errors.append(str(exc))

    fallback = fallback_round(round_no)
    if fallback:
        return fallback, "Proveedor público temporalmente no disponible; calendario de respaldo activo."
    return [], "No se pudo consultar el marcador público: " + " | ".join(errors)


def sync_round(round_no):
    matches, err = fetch_round(round_no)
    if not matches:
        return [], err

    conn = db()
    rid_row = sql(conn, "SELECT id FROM rounds WHERE name=?", (f"Jornada {round_no}",)).fetchone()
    if not rid_row:
        sql(conn, "INSERT INTO rounds(name,open) VALUES(?,?)", (f"Jornada {round_no}", True))
        conn.commit()
        rid_row = sql(conn, "SELECT id FROM rounds WHERE name=?", (f"Jornada {round_no}",)).fetchone()
    rid = rid_row["id"]

    # Upsert by external_id where possible. We never delete existing bets.
    existing = sql(conn, "SELECT id,external_id FROM matches WHERE round_id=?", (rid,)).fetchall()
    by_external = {str(x["external_id"]): x["id"] for x in existing if x["external_id"]}
    by_pair = {}
    for x in existing:
        row = sql(conn, "SELECT home,away FROM matches WHERE id=?", (x["id"],)).fetchone()
        if row:
            by_pair[(row["home"], row["away"])] = x["id"]

    for idx, m in enumerate(matches, 1):
        mid = by_external.get(str(m["external_id"])) or by_pair.get((m["home"], m["away"]))
        if mid:
            sql(conn, "UPDATE matches SET home=?,away=?,match_order=?,external_id=? WHERE id=?",
                (m["home"], m["away"], idx, m["external_id"], mid))
        else:
            sql(conn, """INSERT INTO matches(round_id,home,away,match_order,external_id)
                         VALUES(?,?,?,?,?)""",
                (rid, m["home"], m["away"], idx, m["external_id"]))

    conn.commit()

    rows = sql(conn, "SELECT * FROM matches WHERE round_id=? ORDER BY match_order", (rid,)).fetchall()
    conn.close()
    return [dict(r) for r in rows], None


def live_data(round_no):
    fresh, err = fetch_round(round_no)
    by_ext = {m["external_id"]: m for m in fresh}
    by_pair = {(m["home"], m["away"]): m for m in fresh}

    conn = db()
    rid_row = sql(conn, "SELECT id FROM rounds WHERE name=?", (f"Jornada {round_no}",)).fetchone()
    if not rid_row:
        conn.close()
        return [], err
    ms = sql(conn, "SELECT * FROM matches WHERE round_id=? ORDER BY match_order", (rid_row["id"],)).fetchall()

    result = []
    for dbm in ms:
        m = dict(dbm)
        live = by_ext.get(str(m.get("external_id"))) or by_pair.get((m["home"], m["away"]))
        if live:
            m.update({
                "home_logo": live.get("home_logo"),
                "away_logo": live.get("away_logo"),
                "date": live.get("date"),
                "home_goals": live.get("home_goals"),
                "away_goals": live.get("away_goals"),
                "completed": live.get("completed"),
                "live": live.get("live"),
                "status": live.get("status"),
                "clock": live.get("clock"),
                "period": live.get("period"),
            })
        else:
            m.update({"home_goals": None, "away_goals": None, "completed": False, "live": False,
                      "status": "STATUS_SCHEDULED", "clock": None, "period": None})
        result.append(m)
    conn.close()
    return result, err


def current_bets_for_user(user_id, round_id):
    conn = db()
    rows = sql(conn, """SELECT b.match_id,b.prediction FROM bets b
                        JOIN matches m ON m.id=b.match_id
                        WHERE b.user_id=? AND m.round_id=?""", (user_id, round_id)).fetchall()
    conn.close()
    return {int(r["match_id"]): r["prediction"] for r in rows}


def calculate_user(round_no, user_id):
    matches, api_error = live_data(round_no)
    conn = db()
    rid = sql(conn, "SELECT id FROM rounds WHERE name=?", (f"Jornada {round_no}",)).fetchone()
    if not rid:
        conn.close()
        return {"hits": 0, "pending": 10, "errors": 0, "prize": 0, "matches": [], "api_error": api_error}
    bets = current_bets_for_user(user_id, rid["id"])
    conn.close()

    hits = pending = errors = 0
    out = []
    for m in matches:
        actual = outcome(m.get("home_goals"), m.get("away_goals")) if m.get("completed") else None
        pick = bets.get(int(m["id"]))
        if actual is None:
            pending += 1
        elif pick == actual:
            hits += 1
        else:
            errors += 1
        out.append({
            "id": int(m["id"]), "home": m["home"], "away": m["away"],
            "pick": pick, "actual": actual,
            "score": f'{m["home_goals"]} - {m["away_goals"]}' if actual else None,
            "live": bool(m.get("live")), "completed": bool(m.get("completed")),
            "clock": m.get("clock"), "status": m.get("status")
        })
    return {"hits": hits, "pending": pending, "errors": errors,
            "prize": hits * PRIZE_PER_HIT, "matches": out, "api_error": api_error}


BASE_CSS = """
<style>
:root{--bg:#080a0d;--panel:#14181e;--panel2:#20252d;--line:#303640;--text:#f5f7fa;--muted:#9ea7b3;--red:#ed0a16;--green:#21d18a;--yellow:#f5c542;--blue:#5da9ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif}
a{color:inherit}.app{max-width:900px;margin:auto;min-height:100vh;padding-bottom:95px}
header{position:sticky;top:0;z-index:20;background:#101318ee;backdrop-filter:blur(12px);border-bottom:1px solid var(--line);padding:14px 18px}
.top{display:flex;justify-content:space-between;align-items:center;gap:15px}.logo{font-size:20px;font-weight:950;letter-spacing:.3px}.logo b{color:var(--red)}
main{padding:18px}.hero{text-align:center;padding:12px 0}.hero h1{font-size:42px;margin:8px 0}.hero p{color:var(--muted);margin:0 0 18px;font-size:18px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:18px;margin:14px 0}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.stat{background:var(--panel2);border-radius:14px;padding:15px;text-align:center}.stat strong{display:block;font-size:28px}.stat span{color:var(--muted);font-size:11px;font-weight:800}
.btn{display:block;width:100%;border:0;border-radius:12px;background:var(--red);color:#fff;padding:13px;text-align:center;font-weight:900;text-decoration:none;margin-top:10px;cursor:pointer}.btn.secondary{background:var(--panel2)}.btn.green{background:#096b45}.btn.small{padding:9px;font-size:12px}
.badge{display:inline-block;border-radius:22px;padding:8px 13px;background:#073e2a;color:#70efb1;font-weight:900;font-size:12px}
.match{display:grid;grid-template-columns:34px 1fr 190px;gap:10px;align-items:center;padding:13px 5px;border-bottom:1px solid var(--line)}.match:last-child{border-bottom:0}
.teams{font-weight:750;line-height:1.55}.choices{display:flex;gap:6px;align-items:center;justify-content:flex-end}.choice{width:42px;height:42px;border:1px solid #454b55;border-radius:10px;display:grid;place-items:center;text-decoration:none;font-weight:950}.choice.sel{background:#fff;color:#111}
.status{grid-column:2/-1;font-size:11px;color:var(--muted);margin-top:-3px}.status.live{color:#4ff0aa}.status.hit{color:#4ff0aa;font-weight:900}.status.miss{color:#ff6871;font-weight:900}.status.pending{color:#f0c951}
.tablewrap{overflow:auto}table{border-collapse:collapse;width:100%;min-width:720px;font-size:12px}th,td{padding:10px 8px;border-bottom:1px solid var(--line);text-align:center}th{background:var(--panel2)}th:first-child,td:first-child{text-align:left;position:sticky;left:0;background:var(--panel);z-index:2;min-width:180px}.pick{font-size:16px;font-weight:950}
input,select{width:100%;padding:12px;border-radius:10px;background:#242932;color:#fff;border:1px solid #424955;margin:7px 0 12px;font-size:15px}label{font-size:12px;color:#cbd0d8;font-weight:700}
.alert{background:#3b1519;border:1px solid #743038;color:#ffb1b7;padding:11px;border-radius:10px;margin-bottom:12px}.ok{background:#0a3827;border:1px solid #176b4b;color:#85f2bd;padding:11px;border-radius:10px;margin-bottom:12px}
.nav{position:fixed;bottom:0;left:50%;transform:translateX(-50%);width:min(900px,100%);background:#11151aee;backdrop-filter:blur(12px);border-top:1px solid var(--line);display:flex;justify-content:space-around;padding:9px 3px calc(9px + env(safe-area-inset-bottom));z-index:30}.nav a{text-decoration:none;color:#aeb5bf;font-size:10px;text-align:center}.nav a b{display:block;font-size:19px;color:#fff;margin-bottom:2px}
.login{min-height:100vh;display:grid;place-items:center;padding:20px;background:radial-gradient(circle at 50% 15%,#321015,#080a0d 55%)}.login .card{width:100%;max-width:440px;padding:28px}.login h1{font-size:29px;text-align:center}.login h1 b{color:var(--red)}
.actions{display:grid;grid-template-columns:1fr 1fr;gap:10px}.danger{background:#65131a!important}.muted{color:var(--muted)}.right{text-align:right}
@media(max-width:650px){.app{max-width:100%}main{padding:14px}.hero h1{font-size:34px}.match{grid-template-columns:27px 1fr 145px}.choice{width:38px;height:38px}.grid{grid-template-columns:1fr 1fr 1fr}.nav a{font-size:9px}}
</style>
"""

LAYOUT = BASE_CSS + """
{% if user %}
<div class="app">
<header><div class="top"><div class="logo">QUINIELA <b>MEDIAMARKERA</b></div><div>{{ user["username"] }}</div></div></header>
<main>
{% with messages=get_flashed_messages(with_categories=true) %}
{% for cat,msg in messages %}<div class="{{'ok' if cat=='ok' else 'alert'}}">{{msg}}</div>{% endfor %}
{% endwith %}
{{ body|safe }}
</main>
<nav class="nav">
<a href="{{url_for('home')}}"><b>⚽</b>Jornada</a>
<a href="{{url_for('my_bet')}}"><b>📝</b>Mi apuesta</a>
<a href="{{url_for('summary')}}"><b>📊</b>Resumen</a>
{% if user["is_admin"] %}<a href="{{url_for('admin')}}"><b>⚙️</b>Admin</a>{% endif %}
<a href="{{url_for('logout')}}"><b>↪</b>Salir</a>
</nav>
</div>
{% else %}{{body|safe}}{% endif %}
"""


def page(body, user=None):
    return render_template_string(LAYOUT, body=body, user=user)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        name = request.form.get("username", "").strip()
        pw = request.form.get("password", "")
        conn = db()
        u = sql(conn, "SELECT * FROM users WHERE username=?", (name,)).fetchone()
        conn.close()
        if u:
            try:
                valid = check_password_hash(u["password"], pw)
            except Exception:
                valid = False
            if valid:
                session.clear()
                session["user_id"] = u["id"]
                return redirect(url_for("home"))
        flash("Usuario o contraseña incorrectos.", "error")
    body = """<div class="login"><div class="card">
<h1>QUINIELA <b>MEDIAMARKERA</b></h1>
<p class="muted" style="text-align:center">Acceso privado · 11 participantes</p>
<form method="post">
<label>Usuario</label><input name="username" placeholder="RFMF" autocomplete="username" required>
<label>Contraseña</label><input type="password" name="password" autocomplete="current-password" required>
<button class="btn" type="submit">Iniciar sesión</button>
</form>
<p class="muted" style="font-size:12px">El administrador puede restablecer cualquier contraseña.</p>
</div></div>"""
    return page(body)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def home():
    user = current_user()
    rn = max(1, min(38, int(request.args.get("round", 5))))
    matches, err = sync_round(rn)
    if not matches:
        # Do not block the app if the public provider is temporarily down.
        conn = db()
        rid = sql(conn, "SELECT id FROM rounds WHERE name=?", (f"Jornada {rn}",)).fetchone()
        matches = [dict(x) for x in sql(conn, "SELECT * FROM matches WHERE round_id=? ORDER BY match_order", (rid["id"],)).fetchall()] if rid else []
        conn.close()
    # Add live state.
    live, live_err = live_data(rn)
    live_by_id = {int(x["id"]): x for x in live}
    conn = db()
    rid = sql(conn, "SELECT id,open FROM rounds WHERE name=?", (f"Jornada {rn}",)).fetchone()
    bets = current_bets_for_user(user["id"], rid["id"]) if rid else {}
    conn.close()

    rows = ""
    for i, m in enumerate(matches, 1):
        lm = live_by_id.get(int(m["id"]), {})
        pick = bets.get(int(m["id"]), "")
        actual = outcome(lm.get("home_goals"), lm.get("away_goals")) if lm.get("completed") else None
        if lm.get("live"):
            status = f'<div class="status live">🔴 EN DIRECTO {lm.get("clock") or ""}</div>'
        elif actual:
            status = f'<div class="status {"hit" if pick==actual else "miss"}">{lm.get("home_goals")} - {lm.get("away_goals")} · {"✓ ACIERTO" if pick==actual else "✕ RESULTADO"}</div>'
        else:
            status = '<div class="status pending">PENDIENTE</div>'
        buttons = "".join(
            f'<a class="choice {"sel" if pick==p else ""}" href="{url_for("bet",match_id=m["id"],prediction=p)}">{p}</a>'
            for p in ("1","X","2")
        )
        rows += f'<div class="match"><div>{i}</div><div class="teams">{m["home"]}<br>{m["away"]}</div><div class="choices">{buttons}</div>{status}</div>'

    provider_note = "🟢 Resultados en directo · actualización automática" if not (err or live_err) else "🟡 Calendario/apuestas disponibles · el marcador se actualizará cuando el proveedor responda"
    is_open = bool(rid and rid["open"])
    admin_link = f"<a class='btn secondary' href='{url_for('admin')}'>⚙️ Administración</a>" if user["is_admin"] else ""
    nav = f"""<div class="hero"><h1>JORNADA {rn}</h1><p>LaLiga 2026/2027</p><span class="badge">● {'ABIERTA' if is_open else 'CERRADA'}</span></div>
<div class="card"><div class="muted">PREMIO POR ACIERTO</div><h2 style="font-size:34px;margin:6px 0">100.000 €</h2><div style="color:var(--green);font-weight:900;font-size:13px">{provider_note}</div></div>
<div class="actions"><a class="btn secondary" href="{url_for('home',round=max(1,rn-1))}" style="display:block">‹ Jornada anterior</a><a class="btn secondary" href="{url_for('home',round=min(38,rn+1))}" style="display:block">Jornada siguiente ›</a></div>
<div class="card"><h2>📝 Mi apuesta</h2>{rows}</div>
<a class="btn" href="{url_for('my_bet',round=rn)}">📝 Ver resumen de mi apuesta</a>
<a class="btn secondary" href="{url_for('summary',round=rn)}">📊 Ver todas las apuestas</a>
{admin_link}
<script>setTimeout(()=>location.reload(),15000)</script>"""
    return page(nav, user)


@app.route("/bet/<int:match_id>/<prediction>")
@login_required
def bet(match_id, prediction):
    if prediction not in ("1", "X", "2"):
        abort(400)
    user = current_user()
    conn = db()
    m = sql(conn, "SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()
    if not m:
        conn.close(); abort(404)
    r = sql(conn, "SELECT * FROM rounds WHERE id=?", (m["round_id"],)).fetchone()
    if not r["open"]:
        flash("La jornada está cerrada.", "error")
    else:
        if DATABASE_URL:
            sql(conn, """INSERT INTO bets(user_id,match_id,prediction) VALUES(?,?,?)
                         ON CONFLICT(user_id,match_id) DO UPDATE SET prediction=EXCLUDED.prediction""",
                (user["id"], match_id, prediction))
        else:
            sql(conn, "INSERT OR REPLACE INTO bets(user_id,match_id,prediction) VALUES(?,?,?)",
                (user["id"], match_id, prediction))
        conn.commit()
        flash("Apuesta guardada.", "ok")
    conn.close()
    return redirect(url_for("home", round=int(r["name"].split()[-1])))


@app.route("/mi-apuesta")
@login_required
def my_bet():
    user = current_user()
    rn = max(1, min(38, int(request.args.get("round", 5))))
    sync_round(rn)
    conn = db()
    rid = sql(conn, "SELECT * FROM rounds WHERE name=?", (f"Jornada {rn}",)).fetchone()
    ms = sql(conn, "SELECT * FROM matches WHERE round_id=? ORDER BY match_order", (rid["id"],)).fetchall() if rid else []
    bets = current_bets_for_user(user["id"], rid["id"]) if rid else {}
    conn.close()
    live, _ = live_data(rn)
    lb = {int(x["id"]): x for x in live}
    rows = ""
    hits = pending = errors = 0
    for m in ms:
        p = bets.get(int(m["id"]))
        x = lb.get(int(m["id"]), {})
        actual = outcome(x.get("home_goals"), x.get("away_goals")) if x.get("completed") else None
        if actual is None: pending += 1; state = "PENDIENTE"
        elif p == actual: hits += 1; state = "✓ ACIERTO · +100.000 €"
        else: errors += 1; state = "✕ FALLADO"
        score = f'{x.get("home_goals")} - {x.get("away_goals")} · ' if actual else ""
        rows += f"<tr><td>{m['match_order']}. {m['home']} - {m['away']}</td><td class='pick'>{p or '—'}</td><td>{score}{state}</td></tr>"
    prize = hits * PRIZE_PER_HIT
    body = f"""<h1>📝 Mi apuesta</h1><p class="muted">{rid['name'] if rid else 'Jornada '+str(rn)} · {user['username']}</p>
<div class="grid"><div class="stat"><strong>{hits}</strong><span>ACIERTOS</span></div><div class="stat"><strong>{pending}</strong><span>PENDIENTES</span></div><div class="stat"><strong>{errors}</strong><span>FALLOS</span></div></div>
<div class="card"><div class="muted">PREMIO ACUMULADO</div><strong style="font-size:32px;color:var(--yellow)">{prize:,} €</strong></div>
<div class="card tablewrap"><table><tr><th>Partido</th><th>Pronóstico</th><th>Estado</th></tr>{rows}</table></div>
<a class="btn" href="{url_for('home',round=rn)}">✏️ Editar apuesta</a>"""
    return page(body, user)


@app.route("/resumen")
@login_required
def summary():
    user = current_user()
    rn = max(1, min(38, int(request.args.get("round", 5))))
    sync_round(rn)
    conn = db()
    rid = sql(conn, "SELECT * FROM rounds WHERE name=?", (f"Jornada {rn}",)).fetchone()
    users = sql(conn, "SELECT * FROM users ORDER BY id").fetchall()
    ms = sql(conn, "SELECT * FROM matches WHERE round_id=? ORDER BY match_order", (rid["id"],)).fetchall() if rid else []
    bets = {}
    for u in users:
        bets[u["id"]] = current_bets_for_user(u["id"], rid["id"]) if rid else {}
    conn.close()

    headers = "".join(f"<th>{u['username']}</th>" for u in users)
    body = f"""<h1>📊 Todas las apuestas</h1><p class="muted">Jornada {rn} · {len(users)} participantes</p>
<div class="card tablewrap"><table><tr><th>Partido</th>{headers}<th>Reparto</th></tr>"""
    for m in ms:
        vals = []
        counts = {"1":0,"X":0,"2":0}
        for u in users:
            p = bets[u["id"]].get(int(m["id"]), "—")
            vals.append(f"<td class='pick'>{p}</td>")
            if p in counts: counts[p] += 1
        body += f"<tr><td>{m['match_order']}. {m['home']} - {m['away']}</td>{''.join(vals)}<td>1: {counts['1']} · X: {counts['X']} · 2: {counts['2']}</td></tr>"
    body += """</table></div>
<button class="btn secondary" onclick="navigator.clipboard.writeText(document.body.innerText);alert('Resumen copiado')">📋 Copiar resumen</button>
"""
    return page(body, user)


@app.route("/clasificacion")
@login_required
def ranking():
    user = current_user()
    rn = max(1, min(38, int(request.args.get("round", 5))))
    conn = db()
    users = sql(conn, "SELECT * FROM users ORDER BY username").fetchall()
    conn.close()
    rows = []
    for u in users:
        c = calculate_user(rn, u["id"])
        rows.append((u["username"], c["hits"], c["errors"], c["pending"], c["prize"]))
    rows.sort(key=lambda x: (-x[1], x[0]))
    body = f"<h1>🏆 Clasificación</h1><p class=muted>Jornada {rn}</p><div class=card>"
    for i, (name, hits, errors, pending, prize) in enumerate(rows, 1):
        body += f'<div class="match"><div><b>{i}º</b></div><div class="teams">{name}<br><span class="muted">{pending} pendientes · {errors} fallos</span></div><b>{hits} aciertos</b></div>'
    body += "</div>"
    return page(body, user)


@app.route("/admin", methods=["GET", "POST"])
@admin_required
def admin():
    user = current_user()
    conn = db()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "reset_password":
            uid = int(request.form["user_id"])
            new = request.form.get("new_password", "").strip() or INITIAL_PASSWORD
            sql(conn, "UPDATE users SET password=? WHERE id=?", (generate_password_hash(new), uid))
            conn.commit()
            flash("Contraseña restablecida.", "ok")
        elif action == "create_user":
            name = request.form.get("username", "").strip()
            if name:
                try:
                    sql(conn, "INSERT INTO users(username,password,is_admin) VALUES(?,?,?)",
                        (name, generate_password_hash(INITIAL_PASSWORD), False))
                    conn.commit(); flash(f"Usuario {name} creado.", "ok")
                except Exception:
                    conn.rollback(); flash("No se pudo crear: el usuario quizá ya existe.", "error")
        elif action == "delete_user":
            uid = int(request.form["user_id"])
            if uid != user["id"]:
                sql(conn, "DELETE FROM users WHERE id=?", (uid,)); conn.commit()
                flash("Usuario eliminado.", "ok")
        elif action == "toggle_round":
            rid = int(request.form["round_id"])
            rr = sql(conn, "SELECT open FROM rounds WHERE id=?", (rid,)).fetchone()
            if rr:
                sql(conn, "UPDATE rounds SET open=? WHERE id=?", (not bool(rr["open"]), rid)); conn.commit()
        elif action == "sync":
            rn = int(request.form["round"])
            ms, err = sync_round(rn)
            if ms: flash(f"Jornada {rn} sincronizada: {len(ms)} partidos.", "ok")
            else: flash(err or "No se pudo sincronizar.", "error")
        elif action == "set_bet":
            uid = int(request.form["user_id"]); mid = int(request.form["match_id"]); pred = request.form["prediction"]
            if pred in ("1","X","2"):
                if DATABASE_URL:
                    sql(conn, """INSERT INTO bets(user_id,match_id,prediction) VALUES(?,?,?)
                                 ON CONFLICT(user_id,match_id) DO UPDATE SET prediction=EXCLUDED.prediction""",(uid,mid,pred))
                else:
                    sql(conn, "INSERT OR REPLACE INTO bets(user_id,match_id,prediction) VALUES(?,?,?)",(uid,mid,pred))
                conn.commit()
                flash("Apuesta modificada.", "ok")
        elif action == "delete_bet":
            uid = int(request.form["user_id"]); mid = int(request.form["match_id"])
            sql(conn, "DELETE FROM bets WHERE user_id=? AND match_id=?", (uid,mid)); conn.commit()
            flash("Apuesta eliminada.", "ok")
        conn.close()
        return redirect(url_for("admin"))

    rounds = sql(conn, "SELECT * FROM rounds ORDER BY id").fetchall()
    users = sql(conn, "SELECT * FROM users ORDER BY username").fetchall()
    conn.close()

    selected = int(request.args.get("round", 5))
    selected = max(1,min(38,selected))
    sync_round(selected)
    conn = db()
    rid = sql(conn, "SELECT * FROM rounds WHERE name=?", (f"Jornada {selected}",)).fetchone()
    ms = sql(conn, "SELECT * FROM matches WHERE round_id=? ORDER BY match_order", (rid["id"],)).fetchall() if rid else []
    bets = {u["id"]: current_bets_for_user(u["id"], rid["id"]) for u in users} if rid else {}
    conn.close()

    users_html = ""
    for u in users:
        users_html += f"""<div class="card"><div class="top"><b>{u['username']}</b><span class="badge">{'ADMIN' if u['is_admin'] else 'USUARIO'}</span></div>
<form method=post><input type=hidden name=action value=reset_password><input type=hidden name=user_id value="{u['id']}">
<label>Nueva contraseña</label><input name=new_password value="{INITIAL_PASSWORD}">
<button class="btn secondary small">🔑 Restablecer contraseña</button></form>
{"<form method=post onsubmit='return confirm(\"¿Eliminar usuario?\")'><input type=hidden name=action value=delete_user><input type=hidden name=user_id value='"+str(u['id'])+"'><button class='btn danger small'>🗑️ Eliminar usuario</button></form>" if u["id"] != user["id"] else ""}</div>"""

    matrix = "<div class='card tablewrap'><h2>📝 Gestionar apuestas · Jornada %d</h2><table><tr><th>Partido</th>" % selected
    matrix += "".join(f"<th>{u['username']}</th>" for u in users) + "</tr>"
    for m in ms:
        matrix += f"<tr><td>{m['match_order']}. {m['home']} - {m['away']}</td>"
        for u in users:
            p = bets[u["id"]].get(int(m["id"]), "")
            opts = "".join(f'<option {"selected" if p==v else ""}>{v}</option>' for v in ("1","X","2"))
            matrix += f"""<td><form method=post>
<input type=hidden name=action value=set_bet><input type=hidden name=user_id value="{u['id']}"><input type=hidden name=match_id value="{m['id']}">
<select name=prediction onchange="this.form.submit()"><option value="">—</option>{opts}</select></form></td>"""
        matrix += "</tr>"
    matrix += "</table></div>"

    rounds_html = "<div class='card'><h2>🗓️ Jornadas</h2>"
    for r in rounds:
        rounds_html += f"""<div class="match"><div class="teams"><b>{r['name']}</b><br><span class="muted">{'ABIERTA' if r['open'] else 'CERRADA'}</span></div>
<form method=post><input type=hidden name=action value=toggle_round><input type=hidden name=round_id value="{r['id']}"><button class="btn secondary small">{"🔒 Cerrar" if r['open'] else "🔓 Abrir"}</button></form></div>"""
    rounds_html += "</div>"

    body = f"""<h1>⚙️ Administración</h1><p class="muted">Solo {ADMIN_USERNAME}. Gestión completa de usuarios, contraseñas, jornadas y apuestas.</p>
<div class="grid"><div class="stat"><strong>{len(users)}</strong><span>USUARIOS</span></div><div class="stat"><strong>{len(ms)}</strong><span>PARTIDOS</span></div><div class="stat"><strong>{selected}</strong><span>JORNADA</span></div></div>
<div class="card"><h2>🔄 Datos de fútbol</h2><form method=post><input type=hidden name=action value=sync><label>Jornada</label><select name=round>""" + "".join(f"<option value={i} {'selected' if i==selected else ''}>Jornada {i}</option>" for i in range(1,39)) + """</select><button class="btn green">Actualizar calendario y resultados</button></form></div>
<div class="card"><h2>👤 Crear usuario</h2><form method=post><input type=hidden name=action value=create_user><label>Nombre de usuario</label><input name=username required><button class=btn>➕ Crear usuario</button></form><p class=muted>Contraseña inicial: <b>biwenger2026</b></p></div>
""" + users_html + matrix + rounds_html
    return page(body, user)


@app.route("/api/status")
def api_status():
    return jsonify({"ok": True, "time": datetime.now(timezone.utc).isoformat(),
                    "provider": "ESPN public scoreboard", "requires_key": False})


@app.route("/health")
def health():
    try:
        conn = db()
        sql(conn, "SELECT 1").fetchone()
        conn.close()
        return "OK", 200
    except Exception as e:
        return "ERROR: " + str(e), 500


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
