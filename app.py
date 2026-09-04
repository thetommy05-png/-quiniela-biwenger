import os
import sqlite3
from datetime import datetime
from functools import wraps
from zoneinfo import ZoneInfo

try:
    from psycopg.rows import dict_row
except ImportError:
    dict_row = None

from flask import Flask, request, redirect, url_for, session, flash, render_template_string, abort
from werkzeug.security import generate_password_hash, check_password_hash

try:
    import psycopg
except ImportError:
    psycopg = None

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cambia-esta-clave-en-produccion")
DATABASE_URL = os.environ.get("DATABASE_URL")
TZ = ZoneInfo("Europe/Madrid")

DEFAULT_USERS = [
    ("Cablo Parmena", False), ("Ojeadores de rondos", False),
    ("AC Decza", False), ("MiCapitan FC", False),
    ("Real Funafuti FC", False), ("El Sin Nombre", False),
    ("CD Leganes", False), ("Quinta Buitre", False),
    ("Al Toque", False), ("Pepino Goya", False), ("RFMF", True)
]

DEFAULT_MATCHES = [
    ("Sevilla", "Valencia"),
    ("Racing de Santander", "Alavés"),
    ("Osasuna", "Espanyol"),
    ("Athletic Club", "Elche"),
    ("Real Madrid", "Rayo Vallecano"),
    ("Celta Vigo", "Málaga"),
    ("Levante", "Barcelona"),
    ("Getafe", "Deportivo de A Coruña"),
    ("Real Sociedad", "Atlético Madrid"),
    ("Villarreal", "Betis"),
]

BASE_CSS = r"""
<style>
:root{
  --bg:#07090b;--panel:#14171c;--panel2:#20242b;--line:#30353e;
  --text:#f4f5f7;--muted:#9da4ae;--red:#ed0b16;--green:#16c784;
  --yellow:#f4c842;--danger:#ff5d67;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
body{font-size:15px;-webkit-text-size-adjust:100%;text-size-adjust:100%}
a{color:inherit}
button,input,select{font:inherit}
.app{width:100%;max-width:820px;margin:0 auto;min-height:100vh;padding-bottom:92px}
header{background:#0e1115;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:20}
.top{height:64px;padding:0 20px;display:flex;align-items:center;justify-content:space-between}
.logo{font-weight:900;font-size:21px;letter-spacing:-.5px}.logo b{color:var(--red)}
.userpill{background:#20252c;border:1px solid #39404a;border-radius:22px;padding:9px 13px;font-weight:800}
main{padding:20px}
h1{font-size:34px;line-height:1.1;margin:0 0 5px;letter-spacing:-.7px}
h2{font-size:20px;margin:0 0 12px}
h3{font-size:16px;margin:0 0 10px}
.muted{color:var(--muted)}
.small{font-size:12px}.tiny{font-size:11px}
.hero{padding:10px 0 4px}
.roundnav{display:grid;grid-template-columns:54px 1fr 54px;gap:12px;align-items:center;text-align:center}
.roundnav button{height:54px;border:1px solid #3b424c;border-radius:14px;background:var(--panel2);color:#fff;font-size:36px;line-height:1;cursor:pointer}
.roundnav button:disabled{opacity:.35}
.roundnav p{margin:0;color:var(--muted);font-size:16px}
.badge{display:inline-flex;align-items:center;gap:7px;border-radius:22px;padding:8px 14px;font-size:12px;font-weight:900;background:#073b25;color:#67e7a9}
.badge.closed{background:#40151a;color:#ff8790}
.deadline{margin:12px 0 0;text-align:center;color:var(--yellow);font-weight:800;font-size:13px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:18px;margin:14px 0}
.prize{display:flex;justify-content:space-between;align-items:end;gap:20px}
.prize small{display:block;color:var(--muted);font-weight:800;letter-spacing:.9px}
.prize strong{font-size:34px;line-height:1}
.live{margin-top:12px;color:#55e3a1;font-weight:800;font-size:12px}
.flash{background:#3a2a05;border:1px solid #735800;padding:12px 14px;border-radius:10px;margin-bottom:14px}
.flash.error{background:#42151a;border-color:#79252d}
.actions{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:14px 0}
.btn{display:block;width:100%;border:0;border-radius:11px;background:var(--red);color:#fff;padding:13px 14px;text-align:center;font-weight:900;text-decoration:none;cursor:pointer}
.btn.secondary{background:#2a2f37}.btn.green{background:#0b6e40}.btn.danger{background:#6b1720}
.btn.smallbtn{padding:9px 10px;font-size:12px}
.matches{padding:0}
.match{display:grid;grid-template-columns:34px minmax(0,1fr) 132px;gap:10px;align-items:center;padding:15px 4px;border-bottom:1px solid var(--line)}
.match:last-child{border-bottom:0}
.num{color:var(--muted);font-weight:900;text-align:center}
.teams{font-weight:800;line-height:1.35}
.teams .sub{font-size:12px;color:var(--muted);font-weight:600;margin-top:4px}
.choices{display:flex;justify-content:flex-end;gap:6px}
.choice{width:38px;height:38px;border:1px solid #444b55;border-radius:9px;display:grid;place-items:center;text-decoration:none;font-weight:900}
.choice.sel{background:#f0f1f3;color:#101214}
.choice.disabled{opacity:.35;pointer-events:none}
.status{grid-column:2 / 4;margin-top:-3px;font-size:12px;font-weight:800}
.pending{color:var(--yellow)}.hit{color:#56e3a2}.miss{color:#ff6973}.result{color:#b9c0ca}
.savebar{position:sticky;bottom:78px;z-index:8;background:linear-gradient(transparent,var(--bg) 28%);padding:22px 0 6px}
.summarygrid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.stat{background:var(--panel2);border-radius:14px;padding:15px;text-align:center}
.stat strong{display:block;font-size:26px}.stat span{color:var(--muted);font-size:11px;font-weight:800}
.summarytitle{display:flex;justify-content:space-between;gap:15px;align-items:center}.summarytitle strong{font-size:28px;color:var(--yellow)}
.tablewrap{overflow-x:auto;border-radius:12px}
table{border-collapse:collapse;width:100%;min-width:680px;font-size:12px}
th,td{padding:10px 8px;border-bottom:1px solid var(--line);text-align:center;white-space:nowrap}
th{background:var(--panel2);position:sticky;top:64px;z-index:3}
th:first-child,td:first-child{text-align:left;position:sticky;left:0;background:var(--panel);z-index:2;min-width:190px}
.pick{font-size:16px;font-weight:900}
.formgrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
label{display:block;color:#cbd0d8;font-size:12px;font-weight:800;margin-bottom:6px}
input,select{width:100%;padding:12px;border-radius:10px;background:#252a31;color:#fff;border:1px solid #414852;outline:none}
input:focus,select:focus{border-color:#777f8a}
.formrow{margin-bottom:10px}
.adminnav{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:14px 0}
.adminnav a{padding:13px 10px;border-radius:11px;background:var(--panel2);text-decoration:none;text-align:center;font-weight:900;font-size:13px}
.adminlist{display:grid;gap:9px}
.adminitem{display:flex;justify-content:space-between;align-items:center;gap:12px;background:var(--panel2);padding:12px;border-radius:11px}
.inline{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.nav{position:fixed;bottom:0;left:50%;transform:translateX(-50%);width:min(820px,100%);background:#111419;border-top:1px solid var(--line);display:flex;justify-content:space-around;padding:9px 4px calc(9px + env(safe-area-inset-bottom));z-index:30}
.nav a{text-decoration:none;color:#aeb4bd;font-size:10px;text-align:center;min-width:60px}.nav a b{display:block;font-size:18px;color:#fff;margin-bottom:2px}.nav a.active{color:#fff}.nav a.active b{color:#fff}
.login{min-height:100vh;display:grid;place-items:center;padding:24px;background:radial-gradient(circle at 50% 15%,#321014,#07090b 55%)}
.login .card{width:min(460px,100%);padding:28px}
.loginlogo{text-align:center;font-size:29px;font-weight:900;margin-bottom:8px}.loginlogo b{color:var(--red)}
.center{text-align:center}
.help{font-size:12px;color:var(--muted);margin-top:12px}
.kpi{font-size:28px;font-weight:900}
.copy{background:#2a2f37;border:0;color:#fff;border-radius:10px;padding:10px 13px;font-weight:800;cursor:pointer}
@media(max-width:650px){
  .app{max-width:100%}
  main{padding:12px}
  .card{padding:14px;margin:11px 0}
  .top{height:54px}
  .logo{font-size:16px}
  .userpill{font-size:13px;padding:7px 10px}
  h1{font-size:29px}
  .top{height:58px;padding:0 14px}.logo{font-size:17px}
  .roundnav{grid-template-columns:46px 1fr 46px}.roundnav button{height:46px;font-size:30px}
  .match{grid-template-columns:26px minmax(0,1fr) 126px;gap:7px;padding:13px 2px}
  .teams{font-size:14px}.choice{width:36px;height:36px}
  .actions{grid-template-columns:1fr 1fr}
  .actions .adminonly{grid-column:1/-1}
  .adminnav{grid-template-columns:1fr 1fr}
  .formgrid{grid-template-columns:1fr}
  .savebar{bottom:70px}
}
</style>
"""

LAYOUT = BASE_CSS + r"""
{% if user %}
<div class="app">
<header><div class="top">
  <div class="logo">QUINIELA <b>MEDIAMARKERA</b></div>
  <div class="userpill">{{ user["username"] }}</div>
</div></header>
<main>
{% with messages=get_flashed_messages(with_categories=true) %}
  {% for category, message in messages %}<div class="flash {{category}}">{{message}}</div>{% endfor %}
{% endwith %}
{{ body|safe }}
</main>
<div class="nav">
  <a href="{{url_for('home')}}"><b>⚽</b>Jornada</a>
  <a href="{{url_for('my_bet')}}"><b>📝</b>Mi apuesta</a>
  <a href="{{url_for('summary')}}"><b>📊</b>Resumen</a>
  <a href="{{url_for('ranking')}}"><b>🏆</b>Clasificación</a>
  {% if user["is_admin"] %}<a href="{{url_for('admin')}}"><b>⚙️</b>Admin</a>{% endif %}
  <a href="{{url_for('logout')}}"><b>↪</b>Salir</a>
</div>
</div>
{% else %}{{body|safe}}{% endif %}
"""

def page(body, user=None):
    return render_template_string(LAYOUT, body=body, user=user)

def db():
    if DATABASE_URL:
        if not psycopg:
            raise RuntimeError("Falta psycopg. Revisa requirements.txt.")
        conn = psycopg.connect(DATABASE_URL, row_factory=dict_row) if dict_row else psycopg.connect(DATABASE_URL)
        return conn
    conn = sqlite3.connect(os.environ.get("SQLITE_PATH", "quiniela.db"))
    conn.row_factory = sqlite3.Row
    return conn

def sql(conn, query, params=()):
    if DATABASE_URL:
        query = query.replace("?", "%s")
    return conn.execute(query, params)

def columns(conn, table):
    if DATABASE_URL:
        rows = sql(conn, """SELECT column_name FROM information_schema.columns
                            WHERE table_name=?""", (table,)).fetchall()
        return {r["column_name"] for r in rows}
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}

def add_column_if_missing(conn, table, name, definition):
    if name not in columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

def init_db():
    conn = db()
    if DATABASE_URL:
        statements = [
            """CREATE TABLE IF NOT EXISTS users(
                id SERIAL PRIMARY KEY, username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL, is_admin BOOLEAN NOT NULL DEFAULT FALSE)""",
            """CREATE TABLE IF NOT EXISTS rounds(
                id SERIAL PRIMARY KEY, name TEXT NOT NULL,
                open BOOLEAN NOT NULL DEFAULT TRUE)""",
            """CREATE TABLE IF NOT EXISTS matches(
                id SERIAL PRIMARY KEY, round_id INTEGER NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
                home TEXT NOT NULL, away TEXT NOT NULL, match_order INTEGER NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS bets(
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
                prediction TEXT NOT NULL CHECK(prediction IN ('1','X','2')),
                PRIMARY KEY(user_id,match_id))"""
        ]
    else:
        statements = [
            """CREATE TABLE IF NOT EXISTS users(
                id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL, is_admin INTEGER NOT NULL DEFAULT 0)""",
            """CREATE TABLE IF NOT EXISTS rounds(
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
                open INTEGER NOT NULL DEFAULT 1)""",
            """CREATE TABLE IF NOT EXISTS matches(
                id INTEGER PRIMARY KEY AUTOINCREMENT, round_id INTEGER NOT NULL,
                home TEXT NOT NULL, away TEXT NOT NULL, match_order INTEGER NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS bets(
                user_id INTEGER NOT NULL, match_id INTEGER NOT NULL, prediction TEXT NOT NULL,
                PRIMARY KEY(user_id,match_id))"""
        ]
    for st in statements:
        conn.execute(st)

    # Safe migrations for previous versions.
    add_column_if_missing(conn, "matches", "kickoff", "TEXT")
    add_column_if_missing(conn, "matches", "actual", "TEXT")
    add_column_if_missing(conn, "matches", "score", "TEXT")
    add_column_if_missing(conn, "rounds", "description", "TEXT")

    for name, admin in DEFAULT_USERS:
        cur = sql(conn, "SELECT id FROM users WHERE username=?", (name,))
        if cur.fetchone() is None:
            sql(conn, "INSERT INTO users(username,password,is_admin) VALUES(?,?,?)",
                (name, generate_password_hash("biwenger2026"), admin))

    # First install: create the requested current Jornada 5.
    cur = sql(conn, "SELECT id FROM rounds ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    if row is None:
        sql(conn, "INSERT INTO rounds(name,open,description) VALUES(?,?,?)",
            ("Jornada 5", True, "LaLiga 2026/2027"))
        conn.commit()
        rid = sql(conn, "SELECT id FROM rounds ORDER BY id DESC LIMIT 1").fetchone()["id"]
        for i, (home, away) in enumerate(DEFAULT_MATCHES, 1):
            sql(conn, """INSERT INTO matches(round_id,home,away,match_order)
                         VALUES(?,?,?,?)""", (rid, home, away, i))

    conn.commit()
    conn.close()

def now_local():
    return datetime.now(TZ)

def parse_local(s):
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)
        return dt.astimezone(TZ)
    except ValueError:
        return None

def round_deadline(conn, round_id):
    rows = sql(conn, """SELECT kickoff FROM matches
                        WHERE round_id=? AND kickoff IS NOT NULL AND kickoff<>''
                        ORDER BY kickoff ASC LIMIT 1""", (round_id,)).fetchall()
    return parse_local(rows[0][0]) if rows else None

def round_is_open(conn, r):
    """Public betting is open only until the FIRST kickoff of the jornada.
    Once that first match starts, NO match in that jornada can be edited by players.
    Admin tools remain available separately for management/results.
    """
    if not r["open"]:
        return False
    deadline = round_deadline(conn, r["id"])
    if deadline is not None and now_local() >= deadline:
        return False
    return True

def current_user():
    if "user_id" not in session:
        return None
    conn = db()
    u = sql(conn, "SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    conn.close()
    return u

def login_required(fn):
    @wraps(fn)
    def wrapped(*a, **kw):
        if not current_user():
            return redirect(url_for("login"))
        return fn(*a, **kw)
    return wrapped

def admin_required(fn):
    @wraps(fn)
    def wrapped(*a, **kw):
        u = current_user()
        if not u or not u["is_admin"]:
            abort(403)
        return fn(*a, **kw)
    return wrapped

def get_round(conn, round_id=None):
    if round_id is not None:
        return sql(conn, "SELECT * FROM rounds WHERE id=?", (round_id,)).fetchone()
    return sql(conn, "SELECT * FROM rounds ORDER BY id DESC LIMIT 1").fetchone()

def bet_map(conn, user_id, round_id):
    rows = sql(conn, """SELECT b.match_id,b.prediction FROM bets b
                        JOIN matches m ON m.id=b.match_id
                        WHERE b.user_id=? AND m.round_id=?""", (user_id, round_id)).fetchall()
    return {r["match_id"]: r["prediction"] for r in rows}

def render_matches(conn, r, user_id, editable=True):
    ms = sql(conn, "SELECT * FROM matches WHERE round_id=? ORDER BY match_order", (r["id"],)).fetchall()
    bets = bet_map(conn, user_id, r["id"])
    can_edit = editable and round_is_open(conn, r)
    deadline = round_deadline(conn, r["id"])
    rows = []
    for m in ms:
        p = bets.get(m["id"], "")
        actual = m["actual"]
        if actual:
            if p == actual:
                status = f"✓ ACIERTO · +100.000 €"
                cls = "hit"
            elif p:
                status = "✕ FALLADO"
                cls = "miss"
            else:
                status = "RESULTADO"
                cls = "result"
        else:
            status = "PENDIENTE"
            cls = "pending"
        if m["kickoff"]:
            dt = parse_local(m["kickoff"])
            date_text = dt.strftime("%d/%m · %H:%M") if dt else m["kickoff"]
        else:
            date_text = "Fecha por definir"
        choices = []
        for choice in ("1", "X", "2"):
            selected = "sel" if p == choice else ""
            disabled = "" if can_edit else "disabled"
            if can_edit:
                href = url_for("bet", match_id=m["id"], prediction=choice)
            else:
                href = "#"
            choices.append(f'<a class="choice {selected} {disabled}" href="{href}">{choice}</a>')
        score = f" · {m['score']}" if m["score"] else ""
        rows.append(f"""
        <div class="match">
          <div class="num">{m['match_order']}</div>
          <div class="teams">{m['home']}<br>{m['away']}
            <div class="sub">🕒 {date_text}</div>
          </div>
          <div class="choices">{''.join(choices)}</div>
          <div class="status {cls}">{status}{score}</div>
        </div>""")
    if deadline and can_edit:
        deadline_text = deadline.strftime("%d/%m/%Y a las %H:%M")
        deadline_html = f'<div class="deadline">⏱ Puedes modificar la apuesta hasta el {deadline_text}</div>'
    elif deadline and not can_edit:
        deadline_text = deadline.strftime("%d/%m/%Y a las %H:%M")
        deadline_html = f'<div class="deadline">🔒 Toda la jornada está bloqueada desde el {deadline_text}. Ya no se puede modificar ningún pronóstico.</div>'
    else:
        deadline_html = '<div class="deadline">⚠️ El administrador aún debe introducir el horario de los partidos.</div>'
    return "".join(rows), can_edit, deadline_html

@app.route("/login", methods=["GET", "POST"])
def login():
    conn = db()
    users = sql(conn, "SELECT username FROM users ORDER BY LOWER(username)").fetchall()
    conn.close()
    if request.method == "POST":
        name = request.form.get("username", "").strip()
        pw = request.form.get("password", "")
        conn = db()
        u = sql(conn, "SELECT * FROM users WHERE username=?", (name,)).fetchone()
        conn.close()
        if u and check_password_hash(u["password"], pw):
            session["user_id"] = u["id"]
            return redirect(url_for("home"))
        flash("Usuario o contraseña incorrectos.", "error")
    options = "".join(f'<option value="{u["username"]}">{u["username"]}</option>' for u in users)
    body = f"""
    <div class="login"><div class="card">
      <div class="loginlogo">QUINIELA <b>MEDIAMARKERA</b></div>
      <p class="muted center">Jornada 5 · 100.000 € por acierto</p>
      <form method="post">
        <div class="formrow"><label>USUARIO</label>
          <select name="username" required><option value="">Selecciona tu usuario</option>{options}</select>
        </div>
        <div class="formrow"><label>CONTRASEÑA</label>
          <input type="password" name="password" placeholder="Contraseña" required autocomplete="current-password">
        </div>
        <button class="btn" type="submit">Iniciar sesión</button>
      </form>
      <div class="help">El usuario se selecciona del desplegable. El administrador puede restablecer contraseñas.</div>
    </div></div>"""
    return page(body)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def home():
    u = current_user()
    conn = db()
    r = get_round(conn)
    if not r:
        conn.close()
        return "No hay jornadas creadas.", 500
    rows, can_edit, deadline_html = render_matches(conn, r, u["id"])
    deadline = round_deadline(conn, r["id"])
    status = "ABIERTA" if can_edit else "CERRADA"
    badge = '<span class="badge">● ABIERTA</span>' if can_edit else '<span class="badge closed">🔒 CERRADA</span>'
    desc = r["description"] or "LaLiga 2026/2027"
    conn.close()
    body = f"""
    <section class="hero">
      <div class="roundnav">
        <button onclick="location.href='{url_for('change_round',direction='prev',current=r['id'])}'">‹</button>
        <div><h1>{r['name']}</h1><p>{desc}</p></div>
        <button onclick="location.href='{url_for('change_round',direction='next',current=r['id'])}'">›</button>
      </div>
      <div class="center" style="margin-top:14px">{badge}</div>
      {deadline_html}
    </section>
    <section class="card">
      <div class="prize"><div><small>PREMIO POR ACIERTO</small><strong>100.000 €</strong></div></div>
      <div class="live">● RESULTADOS Y CIERRE AUTOMÁTICOS</div>
    </section>
    <div class="actions">
      <a class="btn secondary" href="{url_for('my_bet')}">📝 Mi apuesta</a>
      <a class="btn secondary" href="{url_for('summary')}">📊 Resumen</a>
      {'<a class="btn secondary adminonly" href="'+url_for('admin')+'">⚙️ Administración</a>' if u['is_admin'] else ''}
    </div>
    <section class="card">
      <h2>📝 Mi apuesta</h2>
      <div class="matches">{rows}</div>
    </section>
    {'<div class="savebar"><a class="btn" href="'+url_for('my_bet')+'">💾 Ver / revisar mi apuesta</a></div>' if can_edit else ''}
    """
    return page(body, u)

@app.route("/round/<direction>")
@login_required
def change_round(direction):
    conn = db()
    try:
        base_id = int(request.args.get("current", 0))
    except ValueError:
        base_id = 0
    r = get_round(conn, base_id) if base_id else get_round(conn)
    if not r:
        conn.close()
        return redirect(url_for("home"))
    op = "<" if direction == "prev" else ">"
    order = "DESC" if direction == "prev" else "ASC"
    nxt = sql(conn, f"SELECT id FROM rounds WHERE id {op} ? ORDER BY id {order} LIMIT 1", (r["id"],)).fetchone()
    target = nxt["id"] if nxt else r["id"]
    conn.close()
    return redirect(url_for("round_view", round_id=target))

@app.route("/jornada/<int:round_id>")
@login_required
def round_view(round_id):
    u = current_user()
    conn = db()
    r = get_round(conn, round_id)
    if not r:
        conn.close(); abort(404)
    rows, can_edit, deadline_html = render_matches(conn, r, u["id"])
    desc = r["description"] or "LaLiga 2026/2027"
    conn.close()
    body = f"""
    <div class="hero">
      <div class="roundnav">
        <button onclick="location.href='{url_for('change_round',direction='prev',current=r['id'])}'">‹</button>
        <div><h1>{r['name']}</h1><p>{desc}</p></div>
        <button onclick="location.href='{url_for('change_round',direction='next',current=r['id'])}'">›</button>
      </div>
      <div class="center" style="margin-top:14px">{'<span class="badge">● ABIERTA</span>' if can_edit else '<span class="badge closed">🔒 CERRADA</span>'}</div>
      {deadline_html}
    </div>
    <section class="card"><div class="matches">{rows}</div></section>
    """
    return page(body, u)

@app.route("/bet/<int:match_id>/<prediction>")
@login_required
def bet(match_id, prediction):
    if prediction not in ("1", "X", "2"):
        abort(400)
    u = current_user()
    conn = db()
    m = sql(conn, "SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()
    if not m:
        conn.close(); abort(404)
    r = get_round(conn, m["round_id"])
    # HARD RULE FOR PLAYERS: the moment the first match of the jornada starts,
    # every prediction in that jornada is locked. This is enforced server-side.
    if not round_is_open(conn, r):
        flash("La jornada está cerrada: no se puede modificar ningún partido desde el inicio del primer encuentro.", "error")
    else:
        # Extra protection in case a single match has a kickoff earlier than the
        # calculated jornada deadline (e.g. data was corrected by the admin).
        ko = parse_local(m["kickoff"])
        if ko and now_local() >= ko:
            flash("Este partido ya ha comenzado y no se puede modificar.", "error")
        else:
            if DATABASE_URL:
                sql(conn, """INSERT INTO bets(user_id,match_id,prediction)
                             VALUES(?,?,?)
                             ON CONFLICT(user_id,match_id)
                             DO UPDATE SET prediction=EXCLUDED.prediction""",
                    (u["id"], match_id, prediction))
            else:
                sql(conn, """INSERT OR REPLACE INTO bets(user_id,match_id,prediction)
                             VALUES(?,?,?)""", (u["id"], match_id, prediction))
            conn.commit()
            flash("Apuesta actualizada.", "success")
    conn.close()
    return redirect(url_for("round_view", round_id=r["id"]))

@app.route("/mi-apuesta")
@login_required
def my_bet():
    u = current_user()
    conn = db()
    r = get_round(conn)
    if not r:
        conn.close(); abort(404)
    ms = sql(conn, "SELECT * FROM matches WHERE round_id=? ORDER BY match_order", (r["id"],)).fetchall()
    bets = bet_map(conn, u["id"], r["id"])
    hits = pending = errors = 0
    rows = []
    for m in ms:
        p = bets.get(m["id"], "—")
        if m["actual"]:
            if p == m["actual"]: hits += 1
            elif p != "—": errors += 1
        else:
            pending += 1
        rows.append(f"<tr><td>{m['match_order']}. {m['home']} - {m['away']}</td><td class='pick'>{p}</td><td>{m['score'] or '—'}</td></tr>")
    can_edit = round_is_open(conn, r)
    deadline = round_deadline(conn, r["id"])
    prize = hits * 100000
    conn.close()
    deadline_text = deadline.strftime("%d/%m/%Y %H:%M") if deadline else "horario aún no configurado"
    body = f"""
    <h1>Mi apuesta</h1>
    <p class="muted">{r['name']} · {u['username']}</p>
    <section class="card">
      <div class="summarytitle"><span>🏆 RESUMEN DE MI APUESTA</span><strong>{prize:,} €</strong></div>
      <div class="summarygrid" style="margin-top:14px">
        <div class="stat"><strong>{hits}</strong><span>ACIERTOS</span></div>
        <div class="stat"><strong>{pending}</strong><span>PENDIENTES</span></div>
        <div class="stat"><strong>{errors}</strong><span>FALLOS</span></div>
      </div>
      <p class="muted small">{'Puedes modificarla hasta el '+deadline_text+'.' if can_edit and deadline else ('Las apuestas están cerradas.' if not can_edit else 'El administrador debe introducir el horario.')}</p>
    </section>
    <section class="card tablewrap"><table>
      <tr><th>Partido</th><th>Pronóstico</th><th>Resultado</th></tr>{''.join(rows)}
    </table></section>
    {'<a class="btn" href="'+url_for('home')+'">✏️ Editar apuesta</a>' if can_edit else ''}
    """
    return page(body, u)

@app.route("/resumen")
@login_required
def summary():
    u = current_user()
    conn = db()
    r = get_round(conn)
    users = sql(conn, "SELECT * FROM users ORDER BY LOWER(username)").fetchall()
    ms = sql(conn, "SELECT * FROM matches WHERE round_id=? ORDER BY match_order", (r["id"],)).fetchall()
    # Matrix of all bets.
    heads = "".join(f"<th>{x['username'][:8]}</th>" for x in users)
    body = f"""<h1>Resumen</h1><p class="muted">{r['name']} · {len(users)} participantes</p>
    <section class="card tablewrap"><table><tr><th>Partido</th>{heads}<th>Recuento</th></tr>"""
    totals = {"1": 0, "X": 0, "2": 0}
    for m in ms:
        vals = []
        counts = {"1": 0, "X": 0, "2": 0}
        for x in users:
            b = sql(conn, "SELECT prediction FROM bets WHERE user_id=? AND match_id=?", (x["id"], m["id"])).fetchone()
            p = b["prediction"] if b else "—"
            vals.append(p)
            if p in counts: counts[p] += 1; totals[p] += 1
        body += f"<tr><td>{m['match_order']}. {m['home']} - {m['away']}</td>" + "".join(f"<td class='pick'>{p}</td>" for p in vals) + f"<td>1: {counts['1']} · X: {counts['X']} · 2: {counts['2']}</td></tr>"
    body += f"""</table></section>
    <section class="card">
      <h2>Recuento de apuestas</h2>
      <div class="summarygrid">
        <div class="stat"><strong>{totals['1']}</strong><span>PRONÓSTICOS 1</span></div>
        <div class="stat"><strong>{totals['X']}</strong><span>PRONÓSTICOS X</span></div>
        <div class="stat"><strong>{totals['2']}</strong><span>PRONÓSTICOS 2</span></div>
      </div>
      <button class="btn secondary" style="margin-top:12px" onclick="navigator.clipboard.writeText(document.body.innerText).then(()=>alert('Resumen copiado'))">📋 Copiar resumen para WhatsApp</button>
    </section>"""
    conn.close()
    return page(body, u)

@app.route("/clasificacion")
@login_required
def ranking():
    u = current_user()
    conn = db()
    rounds = sql(conn, "SELECT * FROM rounds ORDER BY id").fetchall()
    users = sql(conn, "SELECT * FROM users ORDER BY LOWER(username)").fetchall()
    scores = {x["id"]: {"hits": 0, "pending": 0, "points": 0} for x in users}
    for r in rounds:
        ms = sql(conn, "SELECT * FROM matches WHERE round_id=?", (r["id"],)).fetchall()
        for m in ms:
            for x in users:
                b = sql(conn, "SELECT prediction FROM bets WHERE user_id=? AND match_id=?", (x["id"], m["id"])).fetchone()
                if b and m["actual"]:
                    if b["prediction"] == m["actual"]:
                        scores[x["id"]]["hits"] += 1
                        scores[x["id"]]["points"] += 1
                elif b:
                    scores[x["id"]]["pending"] += 1
    ordered = sorted(users, key=lambda x: (-scores[x["id"]]["points"], -scores[x["id"]]["hits"], x["username"].lower()))
    rows = []
    for i, x in enumerate(ordered, 1):
        s = scores[x["id"]]
        rows.append(f"<div class='match'><div class='num'>{i}º</div><div class='teams'>{x['username']}</div><div><b>{s['points']}</b> pts<br><span class='muted'>{s['hits']} aciertos</span></div></div>")
    body = f"""<h1>Clasificación</h1><p class="muted">1 punto por acierto · todas las jornadas</p>
    <section class="card">{''.join(rows)}</section>"""
    conn.close()
    return page(body, u)

@app.route("/admin", methods=["GET", "POST"])
@admin_required
def admin():
    u = current_user()
    conn = db()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "new_round":
            name = request.form.get("name", "").strip() or "Nueva jornada"
            desc = request.form.get("description", "").strip() or "LaLiga 2026/2027"
            sql(conn, "INSERT INTO rounds(name,open,description) VALUES(?,?,?)", (name, True, desc))
            conn.commit()
        elif action == "toggle_round":
            rid = int(request.form["id"])
            r = get_round(conn, rid)
            if r:
                sql(conn, "UPDATE rounds SET open=? WHERE id=?", (not bool(r["open"]), rid))
                conn.commit()
        elif action == "add_match":
            rid = int(request.form["round_id"])
            order = int(request.form["match_order"])
            home = request.form.get("home","").strip()
            away = request.form.get("away","").strip()
            kickoff = request.form.get("kickoff","").strip() or None
            if home and away:
                sql(conn, """INSERT INTO matches(round_id,home,away,match_order,kickoff)
                             VALUES(?,?,?,?,?)""", (rid,home,away,order,kickoff))
                conn.commit()
        elif action == "edit_match":
            mid = int(request.form["id"])
            kickoff = request.form.get("kickoff","").strip() or None
            actual = request.form.get("actual","").strip().upper() or None
            score = request.form.get("score","").strip() or None
            if actual not in (None, "1", "X", "2"):
                actual = None
            sql(conn, """UPDATE matches SET home=?,away=?,match_order=?,kickoff=?,actual=?,score=?
                         WHERE id=?""",
                (request.form["home"].strip(), request.form["away"].strip(),
                 int(request.form["match_order"]), kickoff, actual, score, mid))
            conn.commit()
        elif action == "reset_password":
            uid = int(request.form["id"])
            pw = request.form.get("password","").strip()
            if pw:
                sql(conn, "UPDATE users SET password=? WHERE id=?", (generate_password_hash(pw), uid))
                conn.commit()
                flash("Contraseña restablecida.", "success")
        elif action == "add_user":
            username = request.form.get("username","").strip()
            password = request.form.get("password","").strip() or "biwenger2026"
            is_admin = 1 if request.form.get("is_admin") == "1" else 0
            if username:
                try:
                    sql(conn, "INSERT INTO users(username,password,is_admin) VALUES(?,?,?)",
                        (username, generate_password_hash(password), is_admin))
                    conn.commit()
                except Exception:
                    conn.rollback()
                    flash("No se pudo crear el usuario. Comprueba que el nombre no exista.", "error")
        elif action == "delete_user":
            uid = int(request.form["id"])
            if uid != u["id"]:
                sql(conn, "DELETE FROM users WHERE id=?", (uid,))
                conn.commit()
        return redirect(url_for("admin"))

    rounds = sql(conn, "SELECT * FROM rounds ORDER BY id DESC").fetchall()
    users = sql(conn, "SELECT * FROM users ORDER BY LOWER(username)").fetchall()
    current = rounds[0] if rounds else None
    body = f"""
    <h1>Administración</h1><p class="muted">Solo RFMF · gestión completa</p>
    <div class="adminnav">
      <a href="#jornadas">📅 Jornadas</a><a href="#partidos">⚽ Partidos</a><a href="#usuarios">👥 Usuarios</a>
      <a href="{url_for('admin_bets')}">📊 Apuestas</a><a href="#resultados">🏆 Resultados</a><a href="#seguridad">🔐 Contraseñas</a>
    </div>

    <section class="card" id="jornadas"><h2>Crear jornada</h2>
      <form method="post"><input type="hidden" name="action" value="new_round">
      <div class="formgrid"><div class="formrow"><label>NOMBRE</label><input name="name" placeholder="Jornada 6" required></div>
      <div class="formrow"><label>COMPETICIÓN</label><input name="description" value="LaLiga 2026/2027"></div></div>
      <button class="btn">➕ Crear jornada</button></form>
    </section>

    <section class="card"><h2>Jornadas existentes</h2><div class="adminlist">"""
    for rr in rounds:
        deadline = round_deadline(conn, rr["id"])
        automatic = round_is_open(conn, rr)
        deadline_text = deadline.strftime("%d/%m/%Y %H:%M") if deadline else "Sin horario"
        body += f"""<div class="adminitem"><div><b>{rr['name']}</b><br><span class="muted small">{rr['description'] or ''} · {'ABIERTA' if automatic else 'CERRADA'} · cierre automático: {deadline_text}</span></div>
        <form method="post"><input type="hidden" name="action" value="toggle_round"><input type="hidden" name="id" value="{rr['id']}"><button class="btn secondary smallbtn">{'🔒 Cerrar' if rr['open'] else '🔓 Abrir manualmente'}</button></form></div>"""
    body += """</div></section>

    <section class="card" id="partidos"><h2>Gestionar partidos</h2>"""
    for rr in rounds:
        body += f"<h3>{rr['name']}</h3>"
        ms = sql(conn, "SELECT * FROM matches WHERE round_id=? ORDER BY match_order", (rr["id"],)).fetchall()
        for m in ms:
            kickoff_val = (m["kickoff"] or "").replace(" ", "T")
            body += f"""<form method="post" class="card" style="margin:9px 0;background:var(--panel2)">
              <input type="hidden" name="action" value="edit_match"><input type="hidden" name="id" value="{m['id']}">
              <div class="formgrid">
                <div class="formrow"><label>PARTIDO Nº</label><input type="number" name="match_order" value="{m['match_order']}" min="1"></div>
                <div class="formrow"><label>FECHA Y HORA (MADRID)</label><input type="datetime-local" name="kickoff" value="{kickoff_val}"></div>
                <div class="formrow"><label>LOCAL</label><input name="home" value="{m['home']}" required></div>
                <div class="formrow"><label>VISITANTE</label><input name="away" value="{m['away']}" required></div>
                <div class="formrow"><label>RESULTADO (1/X/2)</label><select name="actual"><option value="">Pendiente</option>{''.join(f'<option {"selected" if m["actual"]==v else ""}>{v}</option>' for v in ("1","X","2"))}</select></div>
                <div class="formrow"><label>MARCADOR</label><input name="score" value="{m['score'] or ''}" placeholder="2-1"></div>
              </div><button class="btn smallbtn">💾 Guardar partido</button></form>"""
        body += f"""<form method="post" class="card" style="margin:9px 0;background:#101318">
          <input type="hidden" name="action" value="add_match"><input type="hidden" name="round_id" value="{rr['id']}">
          <div class="formgrid"><input name="match_order" type="number" placeholder="Nº" required>
          <input name="kickoff" type="datetime-local"><input name="home" placeholder="Local" required><input name="away" placeholder="Visitante" required></div>
          <button class="btn secondary smallbtn" style="margin-top:8px">➕ Añadir partido</button></form>"""
    body += """</section>

    <section class="card" id="usuarios"><h2>Gestionar usuarios</h2>
      <form method="post"><input type="hidden" name="action" value="add_user">
      <div class="formgrid"><input name="username" placeholder="Nuevo usuario" required><input name="password" placeholder="Contraseña inicial" required></div>
      <label style="margin-top:8px"><input type="checkbox" name="is_admin" value="1" style="width:auto"> Administrador</label>
      <button class="btn" style="margin-top:10px">➕ Crear usuario</button></form>
      <div class="adminlist" style="margin-top:14px">"""
    for x in users:
        body += f"""<div class="adminitem"><div><b>{x['username']}</b> {'· ADMIN' if x['is_admin'] else ''}</div>
        <div class="inline" id="seguridad">
          <form method="post"><input type="hidden" name="action" value="reset_password"><input type="hidden" name="id" value="{x['id']}">
          <input name="password" placeholder="Nueva contraseña" required style="width:145px;padding:8px"><button class="btn secondary smallbtn">🔑 Restablecer</button></form>
          {'<form method="post"><input type="hidden" name="action" value="delete_user"><input type="hidden" name="id" value="'+str(x['id'])+'"><button class="btn danger smallbtn">🗑️</button></form>' if x['id'] != u['id'] else ''}</div></div>"""
    body += """</div></section>
    <section class="card" id="resultados"><h2>Resultados</h2><p class="muted">Introduce el resultado 1/X/2 y el marcador desde “Gestionar partidos”. Los aciertos y la clasificación se recalculan automáticamente.</p></section>
    """
    conn.close()
    return page(body, u)

@app.route('/admin/apuestas', methods=['GET', 'POST'])
@admin_required
def admin_bets():
    u = current_user()
    conn = db()
    if request.method == 'POST':
        action = request.form.get('action')
        uid = int(request.form.get('user_id', 0))
        mid = int(request.form.get('match_id', 0))
        if action == 'set_bet':
            prediction = request.form.get('prediction', '')
            if prediction in ('1', 'X', '2'):
                if DATABASE_URL:
                    sql(conn, """INSERT INTO bets(user_id,match_id,prediction) VALUES(?,?,?)
                                ON CONFLICT(user_id,match_id) DO UPDATE SET prediction=EXCLUDED.prediction""", (uid, mid, prediction))
                else:
                    sql(conn, 'INSERT OR REPLACE INTO bets(user_id,match_id,prediction) VALUES(?,?,?)', (uid, mid, prediction))
                conn.commit()
                flash('Apuesta modificada por administración.', 'success')
        elif action == 'delete_bet':
            sql(conn, 'DELETE FROM bets WHERE user_id=? AND match_id=?', (uid, mid))
            conn.commit()
            flash('Apuesta eliminada.', 'success')
        conn.close()
        return redirect(url_for('admin_bets', round_id=request.form.get('round_id')))
    rounds = sql(conn, 'SELECT * FROM rounds ORDER BY id DESC').fetchall()
    if not rounds:
        conn.close(); abort(404)
    try:
        selected_id = int(request.args.get('round_id', rounds[0]['id']))
    except ValueError:
        selected_id = rounds[0]['id']
    r = get_round(conn, selected_id) or rounds[0]
    users = sql(conn, 'SELECT * FROM users ORDER BY LOWER(username)').fetchall()
    ms = sql(conn, 'SELECT * FROM matches WHERE round_id=? ORDER BY match_order', (r['id'],)).fetchall()
    deadline = round_deadline(conn, r['id'])
    deadline_text = deadline.strftime('%d/%m/%Y %H:%M') if deadline else 'sin configurar'
    options = ''.join(f'<option value="{rr["id"]}"{" selected" if rr["id"] == r["id"] else ""}>{rr["name"]}</option>' for rr in rounds)
    body = f"""
    <h1>Gestión de apuestas</h1>
    <p class="muted">Administración · {r['name']} · cierre automático: {deadline_text}</p>
    <form method="get" class="card"><label>JORNADA</label>
      <select name="round_id" onchange="this.form.submit()">{options}</select></form>
    <section class="card tablewrap"><table><tr><th>Jugador</th><th>Partido</th><th>Actual</th><th>Modificar</th></tr>"""
    for x in users:
        for m in ms:
            b = sql(conn, 'SELECT prediction FROM bets WHERE user_id=? AND match_id=?', (x['id'], m['id'])).fetchone()
            current = b['prediction'] if b else '—'
            opts = ''.join(f'<option value="{v}"{" selected" if current == v else ""}>{v}</option>' for v in ('1','X','2'))
            body += f"""<tr><td>{x['username']}</td><td>{m['match_order']}. {m['home']} - {m['away']}</td><td class="pick">{current}</td><td>
              <form method="post" class="inline"><input type="hidden" name="action" value="set_bet"><input type="hidden" name="user_id" value="{x['id']}"><input type="hidden" name="match_id" value="{m['id']}"><input type="hidden" name="round_id" value="{r['id']}"><select name="prediction" style="width:65px;padding:7px">{opts}</select><button class="btn secondary smallbtn">Guardar</button></form>
              <form method="post" class="inline" style="margin-top:4px"><input type="hidden" name="action" value="delete_bet"><input type="hidden" name="user_id" value="{x['id']}"><input type="hidden" name="match_id" value="{m['id']}"><input type="hidden" name="round_id" value="{r['id']}"><button class="btn danger smallbtn">Borrar</button></form>
            </td></tr>"""
    body += """</table></section><a class="btn secondary" href="/admin">← Volver a Administración</a>"""
    conn.close()
    return page(body, u)

@app.route("/health")
def health():
    return "OK", 200

init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
