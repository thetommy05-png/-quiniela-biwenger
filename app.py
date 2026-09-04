import os
import sqlite3
from functools import wraps
from flask import Flask, request, redirect, url_for, session, flash, render_template_string, abort
from werkzeug.security import generate_password_hash, check_password_hash

try:
    import psycopg
except ImportError:
    psycopg = None

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cambia-esta-clave-en-produccion")
DATABASE_URL = os.environ.get("DATABASE_URL")

USERS = [
    ("Cablo Parmena", False), ("Ojeadores de rondos", False),
    ("AC Decza", False), ("MiCapitan FC", False),
    ("Real Funafuti FC", False), ("El Sin Nombre", False),
    ("CD Leganes", False), ("Quinta Buitre", False),
    ("Al Toque", False), ("Pepino Goya", False), ("RFMF", True)
]

BASE_CSS = """
<style>
:root{--bg:#090a0c;--panel:#15171b;--panel2:#202329;--line:#2d3037;--text:#f5f5f5;--muted:#9ca3af;--red:#e50914;--green:#18b964}
*{box-sizing:border-box}body{margin:0;background:#090a0c;color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
a{color:#fff}.app{max-width:620px;margin:auto;min-height:100vh;padding-bottom:90px}
header{background:#101114;border-bottom:1px solid var(--line);padding:15px 18px;position:sticky;top:0;z-index:5}
.top{display:flex;justify-content:space-between;align-items:center}.logo{font-weight:900;font-size:20px}.logo b{color:var(--red)}
main{padding:18px}.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px;margin:12px 0}
h1{margin:0 0 5px;font-size:27px}h2{font-size:18px}.muted{color:var(--muted);font-size:13px}
.badge{display:inline-block;border-radius:20px;padding:6px 10px;font-size:11px;font-weight:800;background:#083d24;color:#72efaa}
.btn{display:block;width:100%;border:0;border-radius:10px;background:var(--red);color:#fff;padding:13px;text-align:center;font-weight:900;text-decoration:none;margin-top:10px}
.btn.secondary{background:#2a2d33}.btn.green{background:#0c6b3b}
input,select{width:100%;padding:13px;border-radius:9px;background:#25282e;color:#fff;border:1px solid #3b3e45;margin:7px 0 13px;font-size:15px}
label{font-size:12px;color:#c9cdd4}.match{display:grid;grid-template-columns:28px 1fr 126px;gap:8px;align-items:center;padding:12px 4px;border-bottom:1px solid var(--line)}
.match:last-child{border-bottom:0}.teams{font-size:13px;line-height:1.35}.choices{display:flex;gap:5px}.choice{width:36px;height:36px;border:1px solid #444850;border-radius:8px;display:grid;place-items:center;text-decoration:none;font-weight:900}
.choice.sel{background:#eee;color:#111}.flash{background:#3a2a05;border:1px solid #735800;padding:10px;border-radius:9px;font-size:12px;margin-bottom:10px}
.scroll{overflow:auto}table{border-collapse:collapse;width:100%;min-width:900px;font-size:11px}th,td{padding:9px 7px;border-bottom:1px solid var(--line);text-align:center}th{background:var(--panel2)}
th:first-child,td:first-child{text-align:left;position:sticky;left:0;background:var(--panel);z-index:2;min-width:190px}.pick{font-size:15px;font-weight:900}
.nav{position:fixed;bottom:0;left:50%;transform:translateX(-50%);width:min(620px,100%);background:#15171b;border-top:1px solid var(--line);display:flex;justify-content:space-around;padding:10px 4px calc(10px + env(safe-area-inset-bottom));z-index:10}
.nav a{text-decoration:none;color:#aaa;font-size:11px;text-align:center}.nav a b{display:block;font-size:18px;color:#fff;margin-bottom:2px}
.statgrid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.stat{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px;text-align:center}.stat strong{font-size:22px;display:block}.stat span{font-size:11px;color:var(--muted)}
.login{min-height:100vh;display:grid;place-items:center;padding:22px;background:radial-gradient(circle at 50% 20%,#2b1113,#08090b 55%)}.login .card{width:100%;max-width:430px;padding:24px}
</style>
"""

def db():
    if DATABASE_URL:
        if not psycopg:
            raise RuntimeError("Falta psycopg. Ejecuta pip install -r requirements.txt")
        return psycopg.connect(DATABASE_URL)
    conn = sqlite3.connect(os.environ.get("SQLITE_PATH", "quiniela.db"))
    conn.row_factory = sqlite3.Row
    return conn

def sql(conn, query, params=()):
    # PostgreSQL uses %s, SQLite uses ?
    if DATABASE_URL:
        query = query.replace("?", "%s")
    return conn.execute(query, params)

def init_db():
    conn = db()
    if DATABASE_URL:
        statements = [
            """CREATE TABLE IF NOT EXISTS users(
                id SERIAL PRIMARY KEY, username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL, is_admin BOOLEAN NOT NULL DEFAULT FALSE)""",
            """CREATE TABLE IF NOT EXISTS rounds(
                id SERIAL PRIMARY KEY, name TEXT NOT NULL, open BOOLEAN NOT NULL DEFAULT TRUE)""",
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
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, open INTEGER NOT NULL DEFAULT 1)""",
            """CREATE TABLE IF NOT EXISTS matches(
                id INTEGER PRIMARY KEY AUTOINCREMENT, round_id INTEGER NOT NULL,
                home TEXT NOT NULL, away TEXT NOT NULL, match_order INTEGER NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS bets(
                user_id INTEGER NOT NULL, match_id INTEGER NOT NULL, prediction TEXT NOT NULL,
                PRIMARY KEY(user_id,match_id))"""
        ]
    for st in statements: conn.execute(st)
    for name, admin in USERS:
        cur = sql(conn, "SELECT id FROM users WHERE username=?", (name,))
        if cur.fetchone() is None:
            sql(conn, "INSERT INTO users(username,password,is_admin) VALUES(?,?,?)",
                (name, generate_password_hash("biwenger2026"), admin))
    cur = sql(conn, "SELECT id FROM rounds ORDER BY id DESC LIMIT 1")
    if cur.fetchone() is None:
        sql(conn, "INSERT INTO rounds(name,open) VALUES(?,?)", ("Jornada 1", True))
        conn.commit()
        rid = sql(conn, "SELECT id FROM rounds ORDER BY id DESC LIMIT 1").fetchone()[0]
        demo = [
            ("Real Madrid","Real Sociedad"),("Barcelona","Valencia"),
            ("Atlético de Madrid","Villarreal"),("Betis","Sevilla"),
            ("Athletic Club","Getafe"),("Celta","Osasuna"),
            ("Rayo Vallecano","Espanyol"),("Mallorca","Alavés"),
            ("Girona","Las Palmas"),("Levante","Elche")
        ]
        for i,(h,a) in enumerate(demo,1):
            sql(conn,"INSERT INTO matches(round_id,home,away,match_order) VALUES(?,?,?,?)",(rid,h,a,i))
    conn.commit(); conn.close()

def current_user():
    if "user_id" not in session: return None
    conn=db(); u=sql(conn,"SELECT * FROM users WHERE id=?",(session["user_id"],)).fetchone(); conn.close()
    return u

def login_required(fn):
    @wraps(fn)
    def wrapped(*a,**kw):
        if not current_user(): return redirect(url_for("login"))
        return fn(*a,**kw)
    return wrapped

def admin_required(fn):
    @wraps(fn)
    def wrapped(*a,**kw):
        u=current_user()
        if not u or not u["is_admin"]: abort(403)
        return fn(*a,**kw)
    return wrapped

LAYOUT = BASE_CSS + """
{% if user %}<div class=app><header><div class=top><div class=logo>BIWENGER <b>QUINIELA</b></div><div>{{ user["username"] }}</div></div></header>
<main>{% with messages=get_flashed_messages() %}{% for m in messages %}<div class=flash>{{m}}</div>{% endfor %}{% endwith %}{{ body|safe }}</main>
<div class=nav><a href="{{url_for('home')}}"><b>⚽</b>Jornada</a><a href="{{url_for('my_bet')}}"><b>📝</b>Mi apuesta</a><a href="{{url_for('summary')}}"><b>📊</b>Resumen</a><a href="{{url_for('ranking')}}"><b>🏆</b>Clasificación{% if user["is_admin"] %}</a><a href="{{url_for('admin')}}"><b>⚙️</b>Admin{% endif %}</a><a href="{{url_for('logout')}}"><b>↪</b>Salir</a></div></div>
{% else %}{{body|safe}}{% endif %}
"""

def page(body, user=None):
    return render_template_string(LAYOUT, body=body, user=user)

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        name=request.form["username"]; pw=request.form["password"]
        conn=db(); u=sql(conn,"SELECT * FROM users WHERE username=?",(name,)).fetchone(); conn.close()
        if u and check_password_hash(u["password"],pw):
            session["user_id"]=u["id"]; return redirect(url_for("home"))
        flash("Usuario o contraseña incorrectos.")
    body="""<div class=login><div class=card><div class=logo style="text-align:center;font-size:25px">BIWENGER <b>QUINIELA</b></div>
    <p class=muted style=text-align:center>11 participantes · quiniela privada</p><form method=post>
    <label>Usuario</label><select name=username>""" + "".join(f"<option>{x[0]}</option>" for x in USERS) + """</select>
    <label>Contraseña</label><input type=password name=password placeholder="Contraseña" required>
    <button class=btn type=submit>Iniciar sesión</button></form>
    <p class=muted>Contraseña inicial para esta primera versión: <b>biwenger2026</b></p></div></div>"""
    return page(body)

@app.route("/logout")
def logout():
    session.clear(); return redirect(url_for("login"))

@app.route("/")
@login_required
def home():
    u=current_user(); conn=db()
    r=sql(conn,"SELECT * FROM rounds ORDER BY id DESC LIMIT 1").fetchone()
    ms=sql(conn,"SELECT * FROM matches WHERE round_id=? ORDER BY match_order",(r["id"],)).fetchall()
    bets={}
    for m in ms:
        b=sql(conn,"SELECT prediction FROM bets WHERE user_id=? AND match_id=?",(u["id"],m["id"])).fetchone()
        bets[m["id"]]=b["prediction"] if b else ""
    conn.close()
    rows=""
    for m in ms:
        rows += f"""<div class=match><div>{m["match_order"]}</div><div class=teams>{m["home"]}<br>{m["away"]}</div><div class=choices>"""
        for p in ("1","X","2"):
            sel="sel" if bets[m["id"]]==p else ""
            rows += f'<a class="choice {sel}" href="{url_for("bet",match_id=m["id"],prediction=p)}">{p}</a>'
        rows+="</div></div>"
    body=f"""<div><h1>{r["name"]}</h1><p class=muted>Selecciona 1 / X / 2. Tus apuestas son privadas.</p>
    <span class=badge>{'ABIERTA' if r['open'] else 'CERRADA'}</span></div>
    <div class=card>{rows}</div><a class="btn" href="{url_for('my_bet')}">💾 Ver mi apuesta</a>
    <a class="btn secondary" href="{url_for('summary')}">📊 Ver resumen</a>"""
    return page(body,u)

@app.route("/bet/<int:match_id>/<prediction>")
@login_required
def bet(match_id,prediction):
    if prediction not in ("1","X","2"): abort(400)
    u=current_user(); conn=db()
    m=sql(conn,"SELECT * FROM matches WHERE id=?",(match_id,)).fetchone()
    r=sql(conn,"SELECT * FROM rounds WHERE id=?",(m["round_id"],)).fetchone()
    if not r["open"]: flash("La jornada está cerrada.")
    else:
        if DATABASE_URL:
            sql(conn,"INSERT INTO bets(user_id,match_id,prediction) VALUES(?,?,?) ON CONFLICT(user_id,match_id) DO UPDATE SET prediction=EXCLUDED.prediction",(u["id"],match_id,prediction))
        else:
            sql(conn,"INSERT OR REPLACE INTO bets(user_id,match_id,prediction) VALUES(?,?,?)",(u["id"],match_id,prediction))
        conn.commit()
    conn.close(); return redirect(url_for("home"))

@app.route("/mi-apuesta")
@login_required
def my_bet():
    u=current_user(); conn=db(); r=sql(conn,"SELECT * FROM rounds ORDER BY id DESC LIMIT 1").fetchone()
    ms=sql(conn,"SELECT * FROM matches WHERE round_id=? ORDER BY match_order",(r["id"],)).fetchall()
    rows=""
    for m in ms:
        b=sql(conn,"SELECT prediction FROM bets WHERE user_id=? AND match_id=?",(u["id"],m["id"])).fetchone()
        rows+=f"<tr><td>{m['match_order']}. {m['home']} - {m['away']}</td><td class=pick>{b['prediction'] if b else '—'}</td></tr>"
    conn.close()
    body=f"<h1>Mi apuesta</h1><p class=muted>{r['name']} · {u['username']}</p><div class='card scroll'><table><tr><th>Partido</th><th>Pronóstico</th></tr>{rows}</table></div><a class=btn href='{url_for('home')}'>✏️ Editar</a>"
    return page(body,u)

@app.route("/resumen")
@login_required
def summary():
    u=current_user(); conn=db(); r=sql(conn,"SELECT * FROM rounds ORDER BY id DESC LIMIT 1").fetchone()
    users=sql(conn,"SELECT * FROM users ORDER BY id").fetchall(); ms=sql(conn,"SELECT * FROM matches WHERE round_id=? ORDER BY match_order",(r["id"],)).fetchall()
    heads="".join(f"<th>{x['username'][:7]}</th>" for x in users)
    body=f"<h1>Resumen</h1><p class=muted>{r['name']} · {len(users)} participantes</p><div class='card scroll'><table><tr><th>Partido</th>{heads}<th>Reparto</th></tr>"
    for m in ms:
        vals=[]; counts={"1":0,"X":0,"2":0}
        for x in users:
            b=sql(conn,"SELECT prediction FROM bets WHERE user_id=? AND match_id=?",(x["id"],m["id"])).fetchone()
            p=b["prediction"] if b else "—"; vals.append(p)
            if p in counts: counts[p]+=1
        body+=f"<tr><td>{m['match_order']}. {m['home']} - {m['away']}</td>"+ "".join(f"<td class=pick>{p}</td>" for p in vals)+f"<td>1: {counts['1']} · X: {counts['X']} · 2: {counts['2']}</td></tr>"
    conn.close(); body+="</table></div><button class=btn onclick='navigator.clipboard.writeText(document.body.innerText);alert(\"Resumen copiado\")'>📋 Copiar resumen</button>"
    return page(body,u)

@app.route("/clasificacion")
@login_required
def ranking():
    u=current_user(); conn=db(); users=sql(conn,"SELECT * FROM users ORDER BY id").fetchall()
    body="<h1>Clasificación</h1><p class=muted>Preparada para calcular puntos con los resultados reales.</p><div class=card>"
    for i,x in enumerate(users,1): body+=f"<div class=match><b>{i}º</b><div class=teams>{x['username']}</div><b>— pts</b></div>"
    conn.close(); body+="</div>"; return page(body,u)

@app.route("/admin", methods=["GET","POST"])
@admin_required
def admin():
    u=current_user(); conn=db()
    if request.method=="POST":
        action=request.form.get("action")
        if action=="new":
            name=request.form.get("name","Nueva jornada").strip() or "Nueva jornada"
            sql(conn,"INSERT INTO rounds(name,open) VALUES(?,?)",(name,True)); conn.commit()
        elif action=="close":
            sql(conn,"UPDATE rounds SET open=? WHERE id=?",(False,int(request.form["id"]))); conn.commit()
        elif action=="open":
            sql(conn,"UPDATE rounds SET open=? WHERE id=?",(True,int(request.form["id"]))); conn.commit()
        return redirect(url_for("admin"))
    rounds=sql(conn,"SELECT * FROM rounds ORDER BY id DESC").fetchall()
    r=rounds[0]; n=sql(conn,"SELECT COUNT(*) FROM matches WHERE round_id=?",(r["id"],)).fetchone()[0]
    conn.close()
    body=f"""<h1>Administración</h1><p class=muted>Solo RFMF</p>
    <div class=statgrid><div class=stat><strong>11</strong><span>Participantes</span></div><div class=stat><strong>{n}</strong><span>Partidos</span></div></div>
    <div class=card><h2>Crear jornada</h2><form method=post><input type=hidden name=action value=new><input name=name placeholder="Ej. Jornada 2" required><button class=btn>➕ Crear</button></form></div>
    <div class=card><h2>Jornadas</h2>"""
    for rr in rounds:
        action="close" if rr["open"] else "open"; label="🔒 Cerrar" if rr["open"] else "🔓 Abrir"
        body+=f"<div class=match><div class=teams><b>{rr['name']}</b><br><span class=muted>{'ABIERTA' if rr['open'] else 'CERRADA'}</span></div><form method=post><input type=hidden name=action value={action}><input type=hidden name=id value={rr['id']}><button class='btn secondary' style='margin:0;padding:9px'>{label}</button></form></div>"
    body+="</div><a class='btn secondary' href='"+url_for("summary")+"'>📊 Ver tabla completa</a>"
    return page(body,u)

@app.route("/health")
def health(): return "OK",200

init_db()

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)))
