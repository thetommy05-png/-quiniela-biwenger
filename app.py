
import os, sqlite3, threading, time, unicodedata
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from functools import wraps

import requests
from flask import Flask, request, redirect, url_for, session, flash, render_template_string

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:
    psycopg = None
    dict_row = None

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cambia-esta-clave-en-produccion")
TZ = ZoneInfo("Europe/Madrid")
DATABASE_URL = os.environ.get("DATABASE_URL")
ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/esp.1/scoreboard"
SYNC_SECONDS = 60
_last_sync = 0
_sync_lock = threading.Lock()

DEFAULT_USERS = [
    ("Cablo Parmena", False), ("Ojeadores de rondos", False),
    ("AC Decza", False), ("MiCapitan FC", False),
    ("Real Funafuti FC", False), ("El Sin Nombre", False),
    ("CD Leganes", False), ("Quinta Buitre", False),
    ("Al Toque", False), ("Pepino Goya", False), ("RFMF", True)
]
DEFAULT_MATCHES_R5 = [
    ("Sevilla", "Valencia"), ("Racing de Santander", "Alavés"),
    ("Osasuna", "Espanyol"), ("Athletic Club", "Elche"),
    ("Real Madrid", "Rayo Vallecano"), ("Celta Vigo", "Málaga"),
    ("Levante", "Barcelona"), ("Getafe", "Deportivo de A Coruña"),
    ("Real Sociedad", "Atlético Madrid"), ("Villarreal", "Betis")
]

CSS = r"""
:root{--bg:#07090b;--panel:#14171c;--panel2:#20252c;--line:#303640;--text:#f4f5f7;--muted:#9da4ae;--red:#ed0b16;--green:#16c784;--yellow:#f4c842}
*{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
body{font-size:15px;-webkit-text-size-adjust:100%}a{color:inherit}button,input,select{font:inherit}
.app{width:100%;max-width:820px;margin:auto;min-height:100vh;padding-bottom:82px}header{background:#0e1115;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:20}
.top{height:58px;padding:0 16px;display:flex;align-items:center;justify-content:space-between}.logo{font-weight:900;font-size:18px}.logo b{color:var(--red)}
.userpill{background:#20252c;border:1px solid #39404a;border-radius:22px;padding:8px 12px;font-weight:800;font-size:13px}
main{padding:14px}h1{font-size:30px;line-height:1.1;margin:0 0 5px;text-align:center}h2{font-size:20px;margin:0 0 12px}.muted{color:var(--muted)}.small{font-size:12px}
.center{text-align:center}.card{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:16px;margin:12px 0}
.roundnav{display:grid;grid-template-columns:46px 1fr 46px;gap:10px;align-items:center;text-align:center}.roundnav button{height:46px;border:1px solid #3b424c;border-radius:13px;background:var(--panel2);color:#fff;font-size:30px;line-height:1}
.badge{display:inline-flex;align-items:center;gap:6px;border-radius:22px;padding:7px 13px;font-size:12px;font-weight:900;background:#073b25;color:#67e7a9}.badge.closed{background:#40151a;color:#ff8790}
.notice{margin:10px 0;text-align:center;color:var(--yellow);font-weight:800;font-size:12px}.prize strong{display:block;font-size:38px;line-height:1}.prize small{display:block;color:var(--muted);font-weight:800;letter-spacing:.8px}
.live{margin-top:9px;color:#55e3a1;font-weight:800;font-size:12px}.actions{display:grid;grid-template-columns:repeat(3,1fr);gap:9px;margin:12px 0}
.btn{display:block;width:100%;border:0;border-radius:11px;background:var(--red);color:#fff;padding:12px;text-align:center;font-weight:900;text-decoration:none;cursor:pointer}.btn.secondary{background:#2a3038}.btn.green{background:#0b6e40}.btn.disabled{opacity:.45;pointer-events:none}
.flash{background:#3a2a05;border:1px solid #735800;padding:11px 13px;border-radius:10px;margin-bottom:12px}.flash.error{background:#42151a;border-color:#79252d}
.match{display:grid;grid-template-columns:28px minmax(0,1fr) 126px;gap:8px;align-items:center;padding:13px 2px;border-bottom:1px solid var(--line)}.match:last-child{border-bottom:0}
.num{color:var(--muted);font-weight:900;text-align:center}.teams{font-weight:800;line-height:1.3}.sub{font-size:11px;color:var(--muted);margin-top:4px}
.choices{display:flex;justify-content:flex-end;gap:5px}.choice{width:36px;height:36px;border:1px solid #444b55;border-radius:9px;display:grid;place-items:center;text-decoration:none;font-weight:900}.choice.sel{background:#f0f1f3;color:#101214}.choice.locked{opacity:.35;pointer-events:none}
.status{grid-column:2/4;font-size:11px;font-weight:800;margin-top:-2px}.pending{color:var(--yellow)}.hit{color:#56e3a2}.miss{color:#ff6973}.result{color:#b9c0ca}
.save{position:sticky;bottom:72px;background:linear-gradient(transparent,var(--bg) 25%);padding:18px 0 5px}.adminlist{display:grid;gap:8px}.adminitem{display:flex;justify-content:space-between;align-items:center;gap:10px;background:var(--panel2);padding:11px;border-radius:10px}
.formrow{margin-bottom:10px}label{display:block;color:#cbd0d8;font-size:12px;font-weight:800;margin-bottom:5px}input,select{width:100%;padding:12px;border-radius:10px;background:#252a31;color:#fff;border:1px solid #414852;outline:none}
.login{min-height:100vh;display:grid;place-items:center;padding:20px;background:radial-gradient(circle at 50% 15%,#321014,#07090b 55%)}.login .card{width:min(440px,100%);padding:24px}
.loginlogo{text-align:center;font-size:28px;font-weight:900;margin-bottom:7px}.loginlogo b{color:var(--red)}.help{text-align:center;color:var(--muted);font-size:11px;margin-top:10px}
.nav{position:fixed;bottom:0;left:50%;transform:translateX(-50%);width:min(820px,100%);background:#111419;border-top:1px solid var(--line);display:flex;justify-content:space-around;padding:8px 2px calc(8px + env(safe-area-inset-bottom));z-index:30}
.nav a{text-decoration:none;color:#aeb4bd;font-size:10px;text-align:center;min-width:55px}.nav a b{display:block;font-size:18px;color:#fff;margin-bottom:2px}
@media(max-width:650px){main{padding:11px}.card{padding:13px}.actions{grid-template-columns:1fr 1fr}.actions .wide{grid-column:1/-1}.match{grid-template-columns:24px minmax(0,1fr) 122px}.teams{font-size:14px}.choice{width:35px;height:35px}.logo{font-size:16px}}
"""

LAYOUT = """<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#07090b"><title>Quiniela Mediamarkera</title><style>""" + CSS + """</style></head><body>{% if user %}<div class="app"><header><div class="top"><div class="logo">QUINIELA <b>MEDIAMARKERA</b></div><div class="userpill">{{user["username"]}}</div></div></header><main>{% with messages=get_flashed_messages(with_categories=true) %}{% for c,m in messages %}<div class="flash {{c}}">{{m}}</div>{% endfor %}{% endwith %}{{body|safe}}</main><div class="nav"><a href="{{url_for('home')}}"><b>⚽</b>Jornada</a><a href="{{url_for('my_bet')}}"><b>📝</b>Mi apuesta</a><a href="{{url_for('summary')}}"><b>📊</b>Resumen</a><a href="{{url_for('ranking')}}"><b>🏆</b>Clasificación</a>{% if user["is_admin"] %}<a href="{{url_for('admin')}}"><b>⚙️</b>Admin</a>{% endif %}<a href="{{url_for('logout')}}"><b>↪</b>Salir</a></div></div>{% else %}{{body|safe}}{% endif %}</body></html>"""

def now_local(): return datetime.now(TZ)
def db():
    if DATABASE_URL:
        if not psycopg: raise RuntimeError("Falta psycopg.")
        return psycopg.connect(DATABASE_URL, row_factory=dict_row)
    c=sqlite3.connect(os.environ.get("SQLITE_PATH","quiniela.db")); c.row_factory=sqlite3.Row; return c
def q(c,s,p=()):
    if DATABASE_URL: s=s.replace("?","%s")
    return c.execute(s,p)
def commit(c): c.commit()

def init_db():
    c=db()
    idtype = "BIGINT GENERATED BY DEFAULT AS IDENTITY" if DATABASE_URL else "INTEGER"
    q(c,f"""CREATE TABLE IF NOT EXISTS qm_users(
        id {idtype} PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, is_admin INTEGER NOT NULL DEFAULT 0)""")
    q(c,f"""CREATE TABLE IF NOT EXISTS qm_rounds(
        id {idtype} PRIMARY KEY, number INTEGER UNIQUE NOT NULL, season TEXT NOT NULL, synced_at TEXT)""")
    q(c,f"""CREATE TABLE IF NOT EXISTS qm_matches(
        id {idtype} PRIMARY KEY, round_id INTEGER NOT NULL, match_no INTEGER NOT NULL,
        home TEXT NOT NULL, away TEXT NOT NULL, kickoff TEXT, status TEXT DEFAULT 'scheduled',
        home_score INTEGER, away_score INTEGER, espn_id TEXT UNIQUE,
        UNIQUE(round_id,match_no))""")
    q(c,f"""CREATE TABLE IF NOT EXISTS qm_bets(
        id {idtype} PRIMARY KEY, user_id INTEGER NOT NULL, match_id INTEGER NOT NULL,
        pick TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(user_id,match_id))""")
    for n in range(1,39):
        q(c,"INSERT INTO qm_rounds(number,season) VALUES(?,?) ON CONFLICT(number) DO NOTHING",
          (n,"2026/2027"))
    # First-run fallback only. The automatic sync will replace dates/results when ESPN is available.
    rid=q(c,"SELECT id FROM qm_rounds WHERE number=5").fetchone()["id"]
    for i,(h,a) in enumerate(DEFAULT_MATCHES_R5,1):
        q(c,"INSERT INTO qm_matches(round_id,match_no,home,away) VALUES(?,?,?,?) ON CONFLICT(round_id,match_no) DO NOTHING",(rid,i,h,a))
    from werkzeug.security import generate_password_hash
    pwd=os.environ.get("DEFAULT_PASSWORD","1234")
    for name,admin in DEFAULT_USERS:
        q(c,"INSERT INTO qm_users(username,password_hash,is_admin) VALUES(?,?,?) ON CONFLICT(username) DO NOTHING",
          (name,generate_password_hash(pwd),1 if admin else 0))
    commit(c); c.close()

def norm(s):
    return unicodedata.normalize("NFKD",s or "").encode("ascii","ignore").decode().lower().strip()
ALIASES={
    "athletic bilbao":"athletic club","athletic club":"athletic club","rcd espanyol":"espanyol",
    "espanyol barcelona":"espanyol","real betis":"betis","betis sevilla":"betis",
    "cd alaves":"alaves","alaves":"alaves","atletico":"atletico madrid",
    "atletico de madrid":"atletico madrid","racing":"racing de santander",
    "racing santander":"racing de santander","rc celta":"celta vigo","celta de vigo":"celta vigo",
    "deportivo":"deportivo de a coruna","deportivo la coruna":"deportivo de a coruna",
    "rcd deportivo":"deportivo de a coruna","deportivo de la coruna":"deportivo de a coruna",
    "rcd mallorca":"mallorca","real sociedad san sebastian":"real sociedad"
}
def teamkey(s): return ALIASES.get(norm(s),norm(s))

def parse_event(ev):
    comp=(ev.get("competitions") or [{}])[0]
    cs=comp.get("competitors") or []
    home=next((x for x in cs if x.get("homeAway")=="home"),{})
    away=next((x for x in cs if x.get("homeAway")=="away"),{})
    ht=(home.get("team") or {}).get("displayName") or home.get("team",{}).get("shortDisplayName")
    at=(away.get("team") or {}).get("displayName") or away.get("team",{}).get("shortDisplayName")
    status=((comp.get("status") or {}).get("type") or {})
    st=status.get("name") or status.get("state") or "scheduled"
    hs=home.get("score"); aws=away.get("score")
    try: hs=int(hs) if hs is not None else None
    except: hs=None
    try: aws=int(aws) if aws is not None else None
    except: aws=None
    kickoff=ev.get("date") or comp.get("date")
    week=(ev.get("week") or {}).get("number") or (comp.get("week") or {}).get("number")
    if not week:
        week=((ev.get("season") or {}).get("type") or {}).get("week")
    return ht,at,kickoff,st,hs,aws,week,str(ev.get("id") or "")

def sync_fixtures(force=False):
    global _last_sync
    if not force and time.time()-_last_sync<SYNC_SECONDS: return
    if not _sync_lock.acquire(blocking=False): return
    try:
        _last_sync=time.time()
        r=requests.get(ESPN_URL,params={"dates":"20260801-20270601","limit":500},timeout=(4,10))
        r.raise_for_status(); events=r.json().get("events") or []
        if not events: return
        c=db()
        for ev in events:
            ht,at,kickoff,st,hs,aws,week,eid=parse_event(ev)
            if not ht or not at: continue
            # ESPN may omit week; match against existing fallback fixtures, otherwise skip.
            rnd=week
            if not rnd:
                rows=q(c,"SELECT r.number,m.id,m.home,m.away FROM qm_rounds r JOIN qm_matches m ON m.round_id=r.id WHERE m.kickoff IS NULL").fetchall()
                for rr in rows:
                    if teamkey(rr["home"])==teamkey(ht) and teamkey(rr["away"])==teamkey(at):
                        rnd=rr["number"]; break
            if not rnd or not (1<=int(rnd)<=38): continue
            rr=q(c,"SELECT id FROM qm_rounds WHERE number=?",(int(rnd),)).fetchone()
            if not rr: continue
            row=q(c,"SELECT id FROM qm_matches WHERE espn_id=?",(eid,)).fetchone() if eid else None
            if row:
                q(c,"UPDATE qm_matches SET home=?,away=?,kickoff=?,status=?,home_score=?,away_score=? WHERE id=?",(ht,at,kickoff,st,hs,aws,row["id"]))
            else:
                existing=q(c,"SELECT id FROM qm_matches WHERE round_id=? AND teamkey(home)=? AND teamkey(away)=?",(rr["id"],teamkey(ht),teamkey(at))).fetchone() if False else None
                # SQLite/Postgres cannot use Python teamkey in SQL; compare in Python.
                candidates=q(c,"SELECT id,home,away FROM qm_matches WHERE round_id=?",(rr["id"],)).fetchall()
                found=next((x for x in candidates if teamkey(x["home"])==teamkey(ht) and teamkey(x["away"])==teamkey(at)),None)
                if found:
                    q(c,"UPDATE qm_matches SET home=?,away=?,kickoff=?,status=?,home_score=?,away_score=?,espn_id=? WHERE id=?",(ht,at,kickoff,st,hs,aws,eid or None,found["id"]))
                else:
                    nextno=(q(c,"SELECT COALESCE(MAX(match_no),0)+1 AS n FROM qm_matches WHERE round_id=?",(rr["id"],)).fetchone()["n"])
                    q(c,"INSERT INTO qm_matches(round_id,match_no,home,away,kickoff,status,home_score,away_score,espn_id) VALUES(?,?,?,?,?,?,?,?,?)",(rr["id"],nextno,ht,at,kickoff,st,hs,aws,eid or None))
        q(c,"UPDATE qm_rounds SET synced_at=?",(now_local().isoformat(),))
        commit(c); c.close()
    except Exception:
        return
    finally: _sync_lock.release()

def round_info(number):
    c=db(); rr=q(c,"SELECT * FROM qm_rounds WHERE number=?",(number,)).fetchone()
    matches=q(c,"SELECT * FROM qm_matches WHERE round_id=? ORDER BY match_no",(rr["id"],)).fetchall() if rr else []
    c.close()
    first=None
    for m in matches:
        if m["kickoff"]:
            try:
                d=datetime.fromisoformat(m["kickoff"].replace("Z","+00:00"))
                if d.tzinfo is None:d=d.replace(tzinfo=timezone.utc)
                d=d.astimezone(TZ)
                first=d if first is None or d<first else first
            except: pass
    closed=bool(first and now_local()>=first)
    return rr,matches,first,closed

def current_round():
    # The first round whose opening kickoff has not passed; otherwise the last round with matches.
    for n in range(1,39):
        rr,ms,first,closed=round_info(n)
        if ms and not closed: return n
    for n in range(38,0,-1):
        rr,ms,first,closed=round_info(n)
        if ms:return n
    return 5

def get_user():
    if "uid" not in session:return None
    c=db(); u=q(c,"SELECT * FROM qm_users WHERE id=?",(session["uid"],)).fetchone(); c.close(); return u

def login_required(fn):
    @wraps(fn)
    def w(*a,**kw):
        u=get_user()
        if not u:return redirect(url_for("login",next=request.path))
        return fn(*a,**kw)
    return w

def admin_required(fn):
    @wraps(fn)
    @login_required
    def w(*a,**kw):
        u=get_user()
        if not u["is_admin"]: return ("No autorizado",403)
        return fn(*a,**kw)
    return w

def page(body,user=None): return render_template_string(LAYOUT,body=body,user=user)

@app.route("/login",methods=["GET","POST"])
def login():
    init_db()
    c=db(); users=q(c,"SELECT id,username,is_admin FROM qm_users ORDER BY is_admin DESC,username").fetchall()
    if request.method=="POST":
        username=request.form.get("username","").strip(); password=request.form.get("password","")
        u=q(c,"SELECT * FROM qm_users WHERE username=?",(username,)).fetchone()
        from werkzeug.security import check_password_hash
        if u and check_password_hash(u["password_hash"],password):
            session["uid"]=u["id"]; return redirect(request.args.get("next") or url_for("home"))
        flash("Usuario o contraseña incorrectos.","error")
    c.close()
    body='<div class="login"><div class="card"><div class="loginlogo">QUINIELA <b>MEDIAMARKERA</b></div><div class="muted center">LaLiga 2026/2027</div><form method="post">'
    body+='<div class="formrow"><label>Usuario</label><select name="username" required><option value="">Selecciona tu usuario…</option>'
    body+=''.join(f'<option value="{u["username"]}">{u["username"]}</option>' for u in users)
    body+='</select></div><div class="formrow"><label>Contraseña</label><input type="password" name="password" required autocomplete="current-password"></div><button class="btn" type="submit">Iniciar sesión</button></form><div class="help">Selecciona tu usuario del desplegable. La contraseña se mantiene privada.</div></div></div>'
    return page(body)

@app.route("/logout")
def logout(): session.clear(); return redirect(url_for("login"))

@app.route("/")
@login_required
def home():
    sync_fixtures()
    u=get_user(); n=int(request.args.get("jornada",current_round())); n=max(1,min(38,n))
    rr,ms,first,closed=round_info(n)
    c=db(); bets={r["match_id"]:r["pick"] for r in q(c,"SELECT match_id,pick FROM qm_bets WHERE user_id=?",(u["id"],)).fetchall()}; c.close()
    badge='<span class="badge closed">🔒 CERRADA</span>' if closed else '<span class="badge">● ABIERTA</span>'
    notice="" if first else '<div class="notice">🕐 Horarios y resultados se sincronizan automáticamente. No tienes que introducirlos.</div>'
    firsttxt=f"🔒 Cierre automático: {first.strftime('%d/%m/%Y %H:%M')}" if first else ""
    body=f'<div class="roundnav"><a class="btn secondary" href="?jornada={max(1,n-1)}">‹</a><div><h1>Jornada {n}</h1><div class="muted">LaLiga 2026/2027</div><div style="margin-top:9px">{badge}</div></div><a class="btn secondary" href="?jornada={min(38,n+1)}">›</a></div>{notice}'
    body+=f'<div class="card prize"><small>PREMIO POR ACIERTO</small><strong>100.000 €</strong><div class="live">● RESULTADOS Y CIERRE AUTOMÁTICOS</div>{f"<div class=\"small muted\">{firsttxt}</div>" if firsttxt else ""}</div>'
    body+='<div class="actions"><a class="btn secondary" href="'+url_for("my_bet",jornada=n)+'">📝 Mi apuesta</a><a class="btn secondary" href="'+url_for("summary",jornada=n)+'">📊 Resumen</a><a class="btn secondary wide" href="'+url_for("admin")+'">⚙️ Administración</a></div>' if u["is_admin"] else '<div class="actions"><a class="btn secondary" href="'+url_for("my_bet",jornada=n)+'">📝 Mi apuesta</a><a class="btn secondary" href="'+url_for("summary",jornada=n)+'">📊 Resumen</a><a class="btn secondary wide" href="'+url_for("ranking")+'">🏆 Clasificación</a></div>'
    body+='<div class="card"><h2>📝 Mi apuesta</h2><div class="matches">'
    if not ms: body+='<div class="muted center">Esta jornada todavía no tiene partidos cargados. La aplicación intentará sincronizarlos automáticamente.</div>'
    for m in ms:
        pick=bets.get(m["id"]); lock=closed
        sub="CERRADA: ya ha comenzado la jornada" if lock else (datetime.fromisoformat(m["kickoff"].replace("Z","+00:00")).astimezone(TZ).strftime("%d/%m %H:%M") if m["kickoff"] else "Horario pendiente de sincronización")
        choices=''.join(f'<a class="choice {"sel" if pick==x else ""} {"locked" if lock else ""}" href="{url_for("pick",match_id=m["id"],value=x,jornada=n)}">{x}</a>' for x in ("1","X","2"))
        result=f'{m["home_score"]} - {m["away_score"]}' if m["home_score"] is not None and m["away_score"] is not None else "PENDIENTE"
        body+=f'<div class="match"><div class="num">{m["match_no"]}</div><div class="teams">{m["home"]}<br>{m["away"]}<div class="sub">🕐 {sub}</div></div><div class="choices">{choices}</div><div class="status {"result" if result!="PENDIENTE" else "pending"}">{result}</div></div>'
    body+='</div></div>'
    body += '<script>setTimeout(function(){location.reload()},60000);</script>'
    return page(body,u)

@app.route("/pick/<int:match_id>/<value>")
@login_required
def pick(match_id,value):
    if value not in ("1","X","2"): return ("Selección inválida",400)
    sync_fixtures()
    u=get_user(); c=db(); m=q(c,"SELECT m.*,r.number FROM qm_matches m JOIN qm_rounds r ON r.id=m.round_id WHERE m.id=?",(match_id,)).fetchone()
    if not m: c.close(); return ("Partido no encontrado",404)
    rr,ms,first,closed=round_info(m["number"])
    if closed:
        c.close(); flash("La jornada ya ha comenzado. No se puede modificar ningún partido.","error"); return redirect(url_for("home",jornada=m["number"]))
    q(c,"INSERT INTO qm_bets(user_id,match_id,pick,updated_at) VALUES(?,?,?,?) ON CONFLICT(user_id,match_id) DO UPDATE SET pick=excluded.pick,updated_at=excluded.updated_at",(u["id"],match_id,value,now_local().isoformat()))
    commit(c); c.close(); return redirect(url_for("home",jornada=m["number"]))

@app.route("/my-bet")
@login_required
def my_bet():
    return redirect(url_for("home",jornada=request.args.get("jornada",current_round())))

@app.route("/summary")
@login_required
def summary():
    sync_fixtures(); u=get_user(); n=int(request.args.get("jornada",current_round())); rr,ms,first,closed=round_info(n)
    c=db(); users=q(c,"SELECT * FROM qm_users ORDER BY username").fetchall()
    rows=[]
    for usr in users:
        bets=q(c,"SELECT b.pick,m.home,m.away,m.home_score,m.away_score FROM qm_bets b JOIN qm_matches m ON m.id=b.match_id JOIN qm_rounds r ON r.id=m.round_id WHERE b.user_id=? AND r.number=?",(usr["id"],n)).fetchall()
        hits=sum(1 for b in bets if b["home_score"] is not None and b["away_score"] is not None and ((b["pick"]=="1" and b["home_score"]>b["away_score"]) or (b["pick"]=="X" and b["home_score"]==b["away_score"]) or (b["pick"]=="2" and b["home_score"]<b["away_score"])))
        rows.append((usr["username"],len(bets),hits))
    c.close()
    body=f'<h1>Resumen · Jornada {n}</h1><div class="card"><div class="muted">Resultados y puntuaciones se actualizan automáticamente.</div></div><div class="card"><div class="adminlist">'
    for name,total,hits in sorted(rows,key=lambda x:(-x[2],x[0])): body+=f'<div class="adminitem"><b>{name}</b><span>{hits} aciertos · {total} apuestas</span></div>'
    body+='</div></div>'; return page(body,u)

@app.route("/ranking")
@login_required
def ranking():
    sync_fixtures(); u=get_user(); c=db()
    users=q(c,"SELECT * FROM qm_users ORDER BY username").fetchall(); scores=[]
    for usr in users:
        rows=q(c,"SELECT b.pick,m.home_score,m.away_score FROM qm_bets b JOIN qm_matches m ON m.id=b.match_id WHERE b.user_id=?",(usr["id"],)).fetchall()
        hits=sum(1 for b in rows if b["home_score"] is not None and ((b["pick"]=="1" and b["home_score"]>b["away_score"]) or (b["pick"]=="X" and b["home_score"]==b["away_score"]) or (b["pick"]=="2" and b["home_score"]<b["away_score"])))
        scores.append((usr["username"],hits))
    c.close(); scores.sort(key=lambda x:(-x[1],x[0]))
    body='<h1>🏆 Clasificación</h1><div class="card"><div class="adminlist">'
    for i,(name,hits) in enumerate(scores,1): body+=f'<div class="adminitem"><b>#{i} {name}</b><strong>{hits} aciertos</strong></div>'
    body+='</div></div>'; return page(body,u)

@app.route("/admin")
@admin_required
def admin():
    sync_fixtures(); u=get_user(); c=db(); users=q(c,"SELECT id,username,is_admin FROM qm_users ORDER BY username").fetchall(); c.close()
    body='<h1>⚙️ Administración</h1><div class="card"><h2>Sincronización automática</h2><div class="muted">Calendario, horarios, resultados y cierre se gestionan automáticamente. No introduzcas horarios manualmente.</div><p class="small">Regla de cierre: cuando comienza el primer partido de una jornada, quedan bloqueados los 10 partidos para todos los usuarios.</p></div><div class="card"><h2>Usuarios</h2><div class="adminlist">'
    for x in users: body+=f'<div class="adminitem"><span>{x["username"]} {"👑" if x["is_admin"] else ""}</span><span class="small">Activo</span></div>'
    body+='</div></div>'; return page(body,u)

@app.route("/health")
def health(): return {"ok":True,"time":now_local().isoformat()}

@app.before_request
def boot():
    # Initialize safely and try synchronization on normal requests.
    try:init_db()
    except Exception: pass

if __name__=="__main__":
    init_db()
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT","8080")))
