import os
import sqlite3
from datetime import datetime, timezone
from functools import wraps

import requests
from flask import Flask, request, redirect, url_for, session, flash, render_template_string, abort
from werkzeug.security import generate_password_hash, check_password_hash

try:
    import psycopg
except ImportError:
    psycopg = None

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "cambia-esta-clave-en-produccion")
DATABASE_URL = os.getenv("DATABASE_URL")
DEFAULT_PASSWORD = os.getenv("DEFAULT_PASSWORD", "biwenger2026")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "RFMF")
ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/esp.1/scoreboard"
SEASON_START = os.getenv("SEASON_START", "2026-08-01")
SEASON_END = os.getenv("SEASON_END", "2027-06-30")
PRIZE = 100000


J5_FIXTURES = [
    ("Sevilla FC", "Valencia CF", "2026-09-11T19:00:00+00:00"),
    ("R. Racing Club", "Deportivo Alavés", "2026-09-12T12:00:00+00:00"),
    ("CA Osasuna", "RCD Espanyol de Barcelona", "2026-09-12T14:15:00+00:00"),
    ("Athletic Club", "Elche CF", "2026-09-12T16:30:00+00:00"),
    ("Real Madrid", "Rayo Vallecano", "2026-09-12T19:00:00+00:00"),
    ("Celta", "Málaga CF", "2026-09-13T12:00:00+00:00"),
    ("Levante UD", "FC Barcelona", "2026-09-13T14:15:00+00:00"),
    ("Getafe CF", "RC Deportivo", "2026-09-13T16:30:00+00:00"),
    ("Real Sociedad", "Atlético de Madrid", "2026-09-13T19:00:00+00:00"),
    ("Villarreal CF", "Real Betis", "2026-09-14T19:00:00+00:00"),
]

def ensure_j5(c):
    rr = sql(c, "SELECT id FROM rounds WHERE number=?", (5,)).fetchone()
    if rr:
        rid = rr["id"] if hasattr(rr, "keys") else rr[0]
    else:
        cur = sql(
            c,
            "INSERT INTO rounds(number,name,open,synced_at,close_at) VALUES(?,?,?,?,?) RETURNING id",
            (5, "Jornada 5", True, datetime.now(timezone.utc).isoformat(), J5_FIXTURES[0][2]),
        )
        rid = cur.fetchone()[0]

    for no, (home, away, kickoff) in enumerate(J5_FIXTURES, 1):
        existing = sql(
            c,
            "SELECT id FROM matches WHERE round_id=? AND match_order=?",
            (rid, no),
        ).fetchone()
        if existing:
            sql(
                c,
                """UPDATE matches
                   SET home=?, away=?, kickoff=?
                   WHERE round_id=? AND match_order=?""",
                (home, away, kickoff, rid, no),
            )
        else:
            sql(
                c,
                """INSERT INTO matches
                   (round_id,match_order,home,away,kickoff,status)
                   VALUES(?,?,?,?,?,'STATUS_SCHEDULED')""",
                (rid, no, home, away, kickoff),
            )

    sql(
        c,
        "UPDATE rounds SET synced_at=?, close_at=? WHERE id=?",
        (datetime.now(timezone.utc).isoformat(), J5_FIXTURES[0][2], rid),
    )
    return rid

USERS = [
    ("Cablo Parmena", False), ("Ojeadores de rondos", False),
    ("AC Decza", False), ("MiCapitan FC", False),
    ("Real Funafuti FC", False), ("El Sin Nombre", False),
    ("CD Leganes", False), ("Quinta Buitre", False),
    ("Al Toque", False), ("Pepino Goya", False), ("RFMF", True)
]

CSS = """
<style>
:root{--bg:#08090b;--panel:#15171b;--panel2:#202329;--line:#30343b;--txt:#f5f5f5;--muted:#9ca3af;--red:#e30613;--green:#19b965}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif}
a{color:#fff}.app{max-width:760px;margin:auto;min-height:100vh;padding-bottom:88px}
header{position:sticky;top:0;z-index:10;background:#101114;border-bottom:1px solid var(--line);padding:14px 18px}
.top{display:flex;justify-content:space-between;align-items:center}.logo{font-weight:900;font-size:20px}.logo b{color:var(--red)}
main{padding:18px}.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:15px;margin:12px 0}
h1{font-size:28px;margin:0 0 5px}h2{font-size:18px}.muted{color:var(--muted);font-size:13px}
.badge{display:inline-block;border-radius:20px;padding:6px 10px;font-size:11px;font-weight:900;background:#083d24;color:#72efaa}
.badge.closed{background:#461318;color:#ff9ca3}.btn{display:block;width:100%;border:0;border-radius:10px;background:var(--red);color:#fff;padding:13px;text-align:center;font-weight:900;text-decoration:none;margin-top:10px;cursor:pointer}
.btn.secondary{background:#292d33}.btn.green{background:#08733d}
input,select{width:100%;padding:13px;border-radius:9px;background:#25282e;color:#fff;border:1px solid #424750;margin:7px 0 13px;font-size:15px}
label{font-size:12px;color:#c9cdd4}.match{display:grid;grid-template-columns:30px 1fr 128px;gap:8px;align-items:center;padding:12px 3px;border-bottom:1px solid var(--line)}
.match:last-child{border-bottom:0}.teams{font-size:13px;line-height:1.45}.choices{display:flex;gap:5px}.choice{width:37px;height:37px;border:1px solid #474c55;border-radius:8px;display:grid;place-items:center;text-decoration:none;font-weight:900}.choice.sel{background:#eee;color:#111}
.locked .choice{opacity:.45;pointer-events:none}.status{font-size:10px;color:var(--muted);margin-top:4px}.live{color:#ff5b64}.hit{color:#65e59b}.miss{color:#ff6870}
.nav{position:fixed;bottom:0;left:50%;transform:translateX(-50%);width:min(760px,100%);background:#15171b;border-top:1px solid var(--line);display:flex;justify-content:space-around;padding:9px 3px calc(9px + env(safe-area-inset-bottom));z-index:20}
.nav a{text-decoration:none;color:#aaa;font-size:10px;text-align:center}.nav a b{display:block;font-size:18px;color:#fff}
table{border-collapse:collapse;width:100%;font-size:11px}th,td{padding:9px 7px;border-bottom:1px solid var(--line);text-align:center}th{background:var(--panel2)}th:first-child,td:first-child{text-align:left}
.scroll{overflow:auto}.statgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.stat{text-align:center;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px}.stat strong{font-size:22px;display:block}.stat span{font-size:10px;color:var(--muted)}
.flash{background:#3a2a05;border:1px solid #735800;padding:10px;border-radius:9px;font-size:12px;margin-bottom:10px}
.login{min-height:100vh;display:grid;place-items:center;padding:22px;background:radial-gradient(circle at 50% 20%,#2b1113,#08090b 55%)}.login .card{width:100%;max-width:430px;padding:24px}
@media(max-width:600px){main{padding:12px}.match{grid-template-columns:25px 1fr 116px}.choice{width:34px;height:34px}.teams{font-size:12px}.app{max-width:100%}}
</style>
"""

def db():
    if DATABASE_URL:
        if not psycopg:
            raise RuntimeError("Falta psycopg[binary].")
        return psycopg.connect(DATABASE_URL)
    c = sqlite3.connect(os.getenv("SQLITE_PATH","quiniela.db"))
    c.row_factory = sqlite3.Row
    return c

def sql(c,q,p=()):
    return c.execute(q.replace("?","%s") if DATABASE_URL else q,p)

def init_db():
    c=db()
    if DATABASE_URL:
        sts=[
            """CREATE TABLE IF NOT EXISTS users(id SERIAL PRIMARY KEY,username TEXT UNIQUE NOT NULL,password TEXT NOT NULL,is_admin BOOLEAN NOT NULL DEFAULT FALSE)""",
            """CREATE TABLE IF NOT EXISTS rounds(id SERIAL PRIMARY KEY,number INTEGER UNIQUE NOT NULL,name TEXT NOT NULL,open BOOLEAN NOT NULL DEFAULT TRUE,synced_at TEXT,close_at TEXT)""",
            """CREATE TABLE IF NOT EXISTS matches(id SERIAL PRIMARY KEY,round_id INTEGER NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,match_order INTEGER NOT NULL,home TEXT NOT NULL,away TEXT NOT NULL,kickoff TEXT,status TEXT DEFAULT 'NS',home_score INTEGER,away_score INTEGER,external_id TEXT UNIQUE,UNIQUE(round_id,match_order))""",
            """CREATE TABLE IF NOT EXISTS bets(user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,prediction TEXT NOT NULL CHECK(prediction IN ('1','X','2')),PRIMARY KEY(user_id,match_id))"""
        ]
    else:
        sts=[
            "CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT UNIQUE NOT NULL,password TEXT NOT NULL,is_admin INTEGER NOT NULL DEFAULT 0)",
            "CREATE TABLE IF NOT EXISTS rounds(id INTEGER PRIMARY KEY AUTOINCREMENT,number INTEGER UNIQUE NOT NULL,name TEXT NOT NULL,open INTEGER NOT NULL DEFAULT 1,synced_at TEXT,close_at TEXT)",
            "CREATE TABLE IF NOT EXISTS matches(id INTEGER PRIMARY KEY AUTOINCREMENT,round_id INTEGER NOT NULL,match_order INTEGER NOT NULL,home TEXT NOT NULL,away TEXT NOT NULL,kickoff TEXT,status TEXT DEFAULT 'NS',home_score INTEGER,away_score INTEGER,external_id TEXT UNIQUE,UNIQUE(round_id,match_order))",
            "CREATE TABLE IF NOT EXISTS bets(user_id INTEGER NOT NULL,match_id INTEGER NOT NULL,prediction TEXT NOT NULL,PRIMARY KEY(user_id,match_id))"
        ]
    for st in sts: c.execute(st)
    for name,admin in USERS:
        if not sql(c,"SELECT id FROM users WHERE username=?",(name,)).fetchone():
            sql(c,"INSERT INTO users(username,password,is_admin) VALUES(?,?,?)",(name,generate_password_hash(DEFAULT_PASSWORD),admin))
    ensure_j5(c)
    c.commit(); c.close()

def current_user():
    if "uid" not in session: return None
    c=db(); u=sql(c,"SELECT * FROM users WHERE id=?",(session["uid"],)).fetchone(); c.close(); return u

def login_required(fn):
    @wraps(fn)
    def w(*a,**k):
        if not current_user(): return redirect(url_for("login"))
        return fn(*a,**k)
    return w

def admin_required(fn):
    @wraps(fn)
    def w(*a,**k):
        u=current_user()
        if not u or not u["is_admin"]: abort(403)
        return fn(*a,**k)
    return w

def page(body,u=None):
    layout=CSS+""" {% if user %}<div class=app><header><div class=top><div class=logo>BIWENGER <b>QUINIELA</b></div><div>{{user["username"]}}</div></div></header><main>{% with messages=get_flashed_messages() %}{% for m in messages %}<div class=flash>{{m}}</div>{% endfor %}{% endwith %}{{body|safe}}</main><div class=nav><a href="{{url_for('home')}}">⚽<b>Jornada</b></a><a href="{{url_for('my_bet')}}">📝<b>Mi apuesta</b></a><a href="{{url_for('summary')}}">📊<b>Resumen</b></a><a href="{{url_for('ranking')}}">🏆<b>Clasificación</b></a>{% if user["is_admin"] %}<a href="{{url_for('admin')}}">⚙️<b>Admin</b></a>{% endif %}<a href="{{url_for('logout')}}">↪<b>Salir</b></a></div></div>{% else %}{{body|safe}}{% endif %}"""
    return render_template_string(layout,body=body,user=u)

def outcome(h,a):
    if h is None or a is None:return None
    return "1" if h>a else ("2" if h<a else "X")

def parse_events(data):
    events=data.get("events",[]) if isinstance(data,dict) else []
    out=[]
    for e in events:
        comp=(e.get("competitions") or [{}])[0]
        teams=comp.get("competitors") or []
        if len(teams)!=2: continue
        home=next((x for x in teams if x.get("homeAway")=="home"),teams[0])
        away=next((x for x in teams if x.get("homeAway")=="away"),teams[1])
        st=e.get("status") or {}
        typ=st.get("type") or {}
        hs=home.get("score"); a=away.get("score")
        try: hs=int(hs) if hs is not None else None
        except: hs=None
        try: a=int(a) if a is not None else None
        except: a=None
        week = e.get("week") or {}
        round_number = week.get("number")
        try:
            round_number = int(round_number) if round_number is not None else None
        except Exception:
            round_number = None
        out.append({
            "id": str(e.get("id")),
            "home": (home.get("team") or {}).get("displayName",""),
            "away": (away.get("team") or {}).get("displayName",""),
            "kickoff": e.get("date"),
            "status": typ.get("name","STATUS_SCHEDULED"),
            "home_score": hs,
            "away_score": a,
            "round_number": round_number
        })
    return out

def sync_rounds():
    """Synchronize Jornada 5 without mixing other jornadas.
    The fixture list and kickoff times come from the official LaLiga schedule;
    ESPN is used only to update scores/statuses by matching teams.
    """
    c = db()
    try:
        ensure_j5(c)
        r = requests.get(
            ESPN_URL,
            params={
                "limit": 100,
                "dates": "20260911-20260914",
                "region": "es",
                "lang": "es",
            },
            timeout=20,
        )
        r.raise_for_status()
        events = parse_events(r.json())
    except Exception as e:
        c.commit()
        c.close()
        return str(e)

    def norm(s):
        return "".join(ch.lower() for ch in (s or "") if ch.isalnum())

    def same_team(a, b):
        a, b = norm(a), norm(b)
        aliases = {
            "sevillafc": "sevillafc",
            "valenciacf": "valenciacf",
            "rracingclub": "rracingclub",
            "deportivoalaves": "deportivoalaves",
            "caosasuna": "caosasuna",
            "rcdespanoldbarcelona": "rcdespanoldbarcelona",
            "athleticclub": "athleticclub",
            "elchecf": "elchecf",
            "realmadrid": "realmadrid",
            "rayovallecano": "rayovallecano",
            "rcelta": "rcelta",
            "celta": "rcelta",
            "malagacf": "malagacf",
            "levanteud": "levanteud",
            "fcbarcelona": "fcbarcelona",
            "getafecf": "getafecf",
            "rcdeportivo": "rcdeportivo",
            "realsociedad": "realsociedad",
            "atleticodemadrid": "atleticodemadrid",
            "villarrealcf": "villarrealcf",
            "realbetis": "realbetis",
            "betis": "realbetis",
        }
        return aliases.get(a, a) == aliases.get(b, b)

    sql(c, "SELECT id FROM rounds WHERE number=?", (5,))
    rr = sql(c, "SELECT id FROM rounds WHERE number=?", (5,)).fetchone()
    rid = rr["id"] if hasattr(rr, "keys") else rr[0]

    for e in events:
        target = None
        for no, (home, away, _kickoff) in enumerate(J5_FIXTURES, 1):
            if same_team(home, e["home"]) and same_team(away, e["away"]):
                target = no
                break
        if not target:
            continue
        sql(
            c,
            """UPDATE matches
               SET home=?, away=?, kickoff=?, status=?, home_score=?, away_score=?, external_id=?
               WHERE round_id=? AND match_order=?""",
            (
                e["home"], e["away"], e["kickoff"], e["status"],
                e["home_score"], e["away_score"], e["id"], rid, target
            ),
        )

    c.commit()
    c.close()
    return None

def auto_close():
    c=db()
    rs=sql(c,"SELECT * FROM rounds WHERE open=1 AND close_at IS NOT NULL").fetchall()
    now=datetime.now(timezone.utc)
    for r in rs:
        try:
            dt=datetime.fromisoformat(str(r["close_at"]).replace("Z","+00:00"))
            if dt<=now: sql(c,"UPDATE rounds SET open=0 WHERE id=?",(r["id"],))
        except: pass
    c.commit(); c.close()

# NUEVO: devuelve la jornada que está actualmente en juego o, si ya terminó,
# la siguiente jornada futura. Así nunca se muestra automáticamente la última
# jornada de la temporada.
def get_current_round(c):
    """Start the quiniela at Jornada 5 and, once it has closed, advance to
    the next scheduled round if one exists. Never choose the last round just
    because it has the highest number.
    """
    r = sql(c, "SELECT * FROM rounds WHERE number=5 LIMIT 1").fetchone()
    if not r:
        ensure_j5(c)
        c.commit()
        r = sql(c, "SELECT * FROM rounds WHERE number=5 LIMIT 1").fetchone()

    now = datetime.now(timezone.utc)
    if r:
        try:
            close_at = r["close_at"]
            if close_at:
                dt = datetime.fromisoformat(str(close_at).replace("Z", "+00:00"))
                if dt > now:
                    return r
        except Exception:
            return r

    nxt = sql(
        c,
        """SELECT * FROM rounds
           WHERE number > 5 AND close_at IS NOT NULL
           ORDER BY number ASC
           LIMIT 1""",
    ).fetchone()
    return nxt or r

@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        name=request.form.get("username","").strip(); pw=request.form.get("password","")
        c=db(); u=sql(c,"SELECT * FROM users WHERE username=?",(name,)).fetchone(); c.close()
        if u and check_password_hash(u["password"],pw):
            session["uid"]=u["id"]; return redirect(url_for("home"))
        flash("Usuario o contraseña incorrectos.")
    opts="".join(f"<option value='{n}'>{n}</option>" for n,_ in USERS)
    body=f"""<div class=login><div class=card><div class=logo style='text-align:center;font-size:25px'>BIWENGER <b>QUINIELA</b></div><p class=muted style='text-align:center'>11 participantes · acceso privado</p><form method=post><label>Usuario</label><select name=username required>{opts}</select><label>Contraseña</label><input type=password name=password required autocomplete=current-password><button class=btn>Iniciar sesión</button></form><p class=muted>Contraseña inicial: <b>{DEFAULT_PASSWORD}</b></p></div></div>"""
    return page(body)

@app.route("/logout")
def logout(): session.clear(); return redirect(url_for("login"))

@app.route("/")
@login_required
def home():
    auto_close(); sync_rounds(); u=current_user(); c=db()
    r=get_current_round(c)
    if not r: c.close(); return page("<h1>No hay jornadas</h1>",u)
    ms=sql(c,"SELECT * FROM matches WHERE round_id=? ORDER BY match_order",(r["id"],)).fetchall()
    bets={x["match_id"]:x["prediction"] for x in sql(c,"SELECT match_id,prediction FROM bets WHERE user_id=?",(u["id"],)).fetchall()}
    c.close()
    rows=""
    for m in ms:
        actual=outcome(m["home_score"],m["away_score"])
        locked=not r["open"]
        st="CERRADA" if locked else (m["status"] if m["status"]!="STATUS_SCHEDULED" else "Pendiente")
        choices="".join(f'<a class="choice {"sel" if bets.get(m["id"])==p else ""}" href="{url_for("bet",match_id=m["id"],prediction=p)}">{p}</a>' for p in ("1","X","2"))
        rows+=f'<div class="match {"locked" if locked else ""}"><div>{m["match_order"]}</div><div class=teams>{m["home"]}<br>{m["away"]}<div class="status">{m["kickoff"] or ""} · {st}'+(f' · {m["home_score"]}-{m["away_score"]}' if actual else "")+f'</div></div><div class=choices>{choices}</div></div>'
    body=f"<h1>{r['name']}</h1><p class=muted>{len(ms)} partidos · calendario y resultados automáticos · cierre automático al comenzar la jornada.</p><span class='badge {'closed' if not r['open'] else ''}'>{'CERRADA' if not r['open'] else 'ABIERTA'}</span><div class=card>{rows}</div><a class=btn href='{url_for('my_bet')}'>📝 Mi apuesta</a><a class='btn secondary' href='{url_for('summary')}'>📊 Resumen</a>"
    return page(body,u)

@app.route("/bet/<int:match_id>/<prediction>")
@login_required
def bet(match_id,prediction):
    if prediction not in ("1","X","2"): abort(400)
    auto_close(); u=current_user(); c=db(); m=sql(c,"SELECT * FROM matches WHERE id=?",(match_id,)).fetchone()
    if not m: c.close(); abort(404)
    r=sql(c,"SELECT * FROM rounds WHERE id=?",(m["round_id"],)).fetchone()
    if not r["open"]: flash("La jornada ya está cerrada. No se puede modificar ninguna apuesta.")
    else:
        if m["kickoff"]:
            try:
                if datetime.fromisoformat(str(m["kickoff"]).replace("Z","+00:00"))<=datetime.now(timezone.utc):
                    sql(c,"UPDATE rounds SET open=0 WHERE id=?",(r["id"],)); flash("El partido ya ha comenzado. Apuesta bloqueada.")
                else:
                    sql(c,"INSERT INTO bets(user_id,match_id,prediction) VALUES(?,?,?) ON CONFLICT(user_id,match_id) DO UPDATE SET prediction=EXCLUDED.prediction" if DATABASE_URL else "INSERT OR REPLACE INTO bets(user_id,match_id,prediction) VALUES(?,?,?)",(u["id"],match_id,prediction))
                    c.commit()
            except Exception: pass
        else:
            sql(c,"INSERT INTO bets(user_id,match_id,prediction) VALUES(?,?,?) ON CONFLICT(user_id,match_id) DO UPDATE SET prediction=EXCLUDED.prediction" if DATABASE_URL else "INSERT OR REPLACE INTO bets(user_id,match_id,prediction) VALUES(?,?,?)",(u["id"],match_id,prediction)); c.commit()
    c.close(); return redirect(url_for("home"))

@app.route("/mi-apuesta")
@login_required
def my_bet():
    u=current_user(); c=db(); r=get_current_round(c)
    if not r:
        c.close(); return page("<h1>No hay jornadas</h1>",u)
    ms=sql(c,"SELECT * FROM matches WHERE round_id=? ORDER BY match_order",(r["id"],)).fetchall()
    rows=""
    for m in ms:
        b=sql(c,"SELECT prediction FROM bets WHERE user_id=? AND match_id=?",(u["id"],m["id"])).fetchone()
        rows+=f"<tr><td>{m['match_order']}. {m['home']} - {m['away']}</td><td class=pick>{b['prediction'] if b else '—'}</td></tr>"
    c.close()
    return page(f"<h1>Mi apuesta</h1><p class=muted>{r['name']} · {u['username']}</p><div class='card scroll'><table><tr><th>Partido</th><th>Pronóstico</th></tr>{rows}</table></div>{'' if not r['open'] else f'<a class=btn href=\"{url_for("home")}\">✏️ Editar apuesta</a>'}",u)

@app.route("/resumen")
@login_required
def summary():
    u=current_user(); c=db(); r=get_current_round(c)
    if not r:
        c.close(); return page("<h1>No hay jornadas</h1>",u)
    users=sql(c,"SELECT * FROM users ORDER BY id").fetchall(); ms=sql(c,"SELECT * FROM matches WHERE round_id=? ORDER BY match_order",(r["id"],)).fetchall()
    heads="".join(f"<th>{x['username'][:7]}</th>" for x in users); body=f"<h1>Resumen</h1><p class=muted>{r['name']} · {len(users)} participantes</p><div class='card scroll'><table><tr><th>Partido</th>{heads}<th>Reparto</th></tr>"
    for m in ms:
        vals=[]; cnt={"1":0,"X":0,"2":0}
        for x in users:
            b=sql(c,"SELECT prediction FROM bets WHERE user_id=? AND match_id=?",(x["id"],m["id"])).fetchone(); p=b["prediction"] if b else "—"; vals.append(p)
            if p in cnt: cnt[p]+=1
        body+=f"<tr><td>{m['match_order']}. {m['home']} - {m['away']}</td>"+''.join(f"<td class=pick>{p}</td>" for p in vals)+f"<td>1:{cnt['1']} · X:{cnt['X']} · 2:{cnt['2']}</td></tr>"
    c.close(); body+="</table></div><button class=btn onclick='navigator.clipboard.writeText(document.body.innerText);alert(\"Resumen copiado\")'>📋 Copiar resumen</button>"; return page(body,u)

@app.route("/clasificacion")
@login_required
def ranking():
    u=current_user(); c=db(); users=sql(c,"SELECT * FROM users ORDER BY id").fetchall()
    body="<h1>Clasificación</h1><div class=card>"
    for i,x in enumerate(users,1):
        body+=f"<div class=match><div>{i}º</div><div class=teams>{x['username']}</div><b>— pts</b></div>"
    c.close(); body+="</div>"; return page(body,u)

@app.route("/admin",methods=["GET","POST"])
@admin_required
def admin():
    u=current_user(); c=db()
    if request.method=="POST":
        action=request.form.get("action")
        if action=="reset":
            uid=int(request.form["id"]); new=request.form.get("password") or DEFAULT_PASSWORD
            sql(c,"UPDATE users SET password=? WHERE id=?",(generate_password_hash(new),uid)); c.commit(); flash("Contraseña actualizada.")
        elif action=="close":
            sql(c,"UPDATE rounds SET open=0 WHERE id=?",(int(request.form["id"]),)); c.commit(); flash("Jornada cerrada.")
        elif action=="open":
            sql(c,"UPDATE rounds SET open=1 WHERE id=?",(int(request.form["id"]),)); c.commit(); flash("Jornada abierta.")
        elif action=="sync":
            c.close(); err=sync_rounds(); flash("Calendario sincronizado." if not err else "Error de sincronización: "+err); return redirect(url_for("admin"))
        c.close(); return redirect(url_for("admin"))
    users=sql(c,"SELECT * FROM users ORDER BY id").fetchall(); rounds=sql(c,"SELECT * FROM rounds ORDER BY number DESC").fetchall(); c.close()
    users_html="".join(f"<div class=card><b>{x['username']}</b>{' · ADMIN' if x['is_admin'] else ''}<form method=post><input type=hidden name=action value=reset><input type=hidden name=id value='{x['id']}'><input name=password placeholder='Nueva contraseña (vacío = inicial)'><button class='btn secondary'>🔑 Restablecer contraseña</button></form></div>" for x in users)
    rounds_html="".join(f"<div class=card><b>{r['name']}</b> · {'ABIERTA' if r['open'] else 'CERRADA'}<form method=post><input type=hidden name=id value='{r['id']}'><input type=hidden name=action value='{'close' if r['open'] else 'open'}'><button class='btn secondary'>{'🔒 Cerrar' if r['open'] else '🔓 Abrir'}</button></form></div>" for r in rounds)
    body=f"<h1>Administración</h1><p class=muted>Solo {ADMIN_USERNAME}. El calendario no requiere horarios manuales.</p><form method=post><input type=hidden name=action value=sync><button class='btn green'>🔄 Sincronizar calendario/resultados</button></form><h2>Usuarios y contraseñas</h2>{users_html}<h2>Jornadas</h2>{rounds_html}"
    return page(body,u)

@app.route("/health")
def health(): return "OK",200

init_db()
if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.getenv("PORT","8080")))
