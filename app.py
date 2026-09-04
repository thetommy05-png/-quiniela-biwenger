import os, sqlite3
from functools import wraps
from flask import Flask, request, redirect, url_for, session, flash, render_template_string, abort
from werkzeug.security import generate_password_hash, check_password_hash
try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'cambia-esta-clave-en-produccion')
DATABASE_URL = os.environ.get('DATABASE_URL')

USERS = [
    ('Cablo Parmena', False), ('Ojeadores de rondos', False), ('AC Decza', False),
    ('MiCapitan FC', False), ('Real Funafuti FC', False), ('El Sin Nombre', False),
    ('CD Leganes', False), ('Quinta Buitre', False), ('Al Toque', False),
    ('Pepino Goya', False), ('RFMF', True)
]

CSS = r'''
:root{--bg:#07090b;--panel:#12161a;--panel2:#1b2025;--line:#2a3036;--text:#f4f5f6;--muted:#9ca3aa;--red:#ef1018;--red2:#b90c13;--green:#20c878;--gold:#f0c94b}
*{box-sizing:border-box}html{background:#07090b}body{margin:0;background:radial-gradient(circle at 50% -10%,#251013 0,#0b0d10 35%,#07090b 75%);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;min-height:100vh}a{color:inherit;text-decoration:none}.app{width:min(100%,560px);margin:auto;min-height:100vh;padding-bottom:88px}
.topbar{height:76px;background:rgba(10,12,15,.94);border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:8px 16px;position:sticky;top:0;z-index:20;backdrop-filter:blur(12px)}.brand{text-align:center;line-height:.9;font-weight:1000;letter-spacing:-1px;font-size:18px}.stars{color:#e31a22;font-size:10px;letter-spacing:4px;display:block;margin-bottom:4px}.brand b{color:#ef1018}.avatar{width:38px;height:38px;border-radius:50%;display:grid;place-items:center;background:#252a2f;border:1px solid #3b4248;font-size:10px;font-weight:900}.menu{font-size:24px;color:#ddd}
main{padding:18px 14px}.hero{text-align:center;margin:4px 0 18px}.hero h1{font-size:24px;margin:0}.hero p{margin:6px 0;color:var(--muted);font-size:13px}.status{display:inline-flex;align-items:center;gap:5px;border-radius:99px;padding:6px 10px;background:#063c24;color:#6df0ad;font-size:11px;font-weight:900;border:1px solid #116d45}.status.closed{background:#3c1013;color:#ff8085;border-color:#76252a}
.card{background:linear-gradient(180deg,#14181c,#101316);border:1px solid var(--line);border-radius:14px;box-shadow:0 10px 30px #0005;overflow:hidden}.matches{padding:4px 10px}.match{display:grid;grid-template-columns:28px 1fr 126px;gap:8px;align-items:center;min-height:58px;padding:9px 2px;border-bottom:1px solid #252a2f}.match:last-child{border-bottom:0}.num{color:#cbd0d5;font-size:12px;text-align:center}.teams{font-size:13px;line-height:1.25}.teams span{display:block}.choices{display:flex;gap:5px;justify-content:flex-end}.choice{width:36px;height:34px;border:1px solid #41484f;border-radius:8px;background:#20252a;display:grid;place-items:center;font-weight:950;font-size:13px;transition:.15s}.choice.sel{background:#f0f1f2;color:#111;border-color:#fff;box-shadow:0 0 0 1px #fff3 inset}.choice:hover{border-color:#eee}
.btn{width:100%;display:block;border:0;border-radius:10px;padding:13px 15px;text-align:center;font-weight:950;margin-top:12px;background:linear-gradient(180deg,#f5121a,#dc0d14);color:white;box-shadow:0 7px 18px #ed101c33}.btn.secondary{background:#24292e;border:1px solid #3b4248;box-shadow:none}.btn.small{width:auto;display:inline-block;padding:9px 12px;margin:0;font-size:12px}.flash{padding:12px;border-radius:11px;background:#063d27;border:1px solid #15965b;color:#9bf2c5;margin-bottom:14px;font-size:13px}.muted{color:var(--muted)}
.bet-table{width:100%;border-collapse:collapse}.bet-table td,.bet-table th{padding:10px 8px;border-bottom:1px solid var(--line);font-size:12px}.bet-table th{text-align:left;background:#1a1f24;color:#cfd3d7}.bet-table td:last-child,.bet-table th:last-child{text-align:center;width:70px}.pick{font-weight:1000;font-size:17px}.pick.one{color:#fff}.pick.x{color:#f3d15b}.pick.two{color:#ff7b80}.summary-scroll{overflow:auto;border-radius:14px}.summary-scroll table{min-width:780px}.summary-scroll th,.summary-scroll td{text-align:center}.summary-scroll th:first-child,.summary-scroll td:first-child{text-align:left;position:sticky;left:0;background:#12161a;z-index:2;min-width:190px}.summary-scroll .pick{font-size:14px}.sharebox{width:100%;min-height:210px;background:#0e1114;border:1px solid var(--line);color:#ddd;border-radius:11px;padding:12px;font:12px/1.5 monospace}
.statgrid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.stat{background:#161b1f;border:1px solid var(--line);border-radius:12px;padding:14px;text-align:center}.stat strong{font-size:23px;display:block}.stat span{font-size:11px;color:var(--muted)}.admin-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.admin-tile{background:#171c20;border:1px solid var(--line);border-radius:12px;padding:18px 8px;text-align:center;font-size:12px;font-weight:800}.admin-tile b{display:block;font-size:23px;margin-bottom:7px}
.nav{position:fixed;bottom:0;left:50%;transform:translateX(-50%);width:min(560px,100%);background:rgba(14,17,20,.97);border-top:1px solid var(--line);display:flex;justify-content:space-around;padding:9px 3px calc(9px + env(safe-area-inset-bottom));z-index:30;backdrop-filter:blur(14px)}.nav a{width:25%;text-align:center;color:#8f969c;font-size:10px;font-weight:700}.nav b{display:block;color:#cbd0d4;font-size:18px;height:22px}.nav a.active,.nav a.active b{color:#f1121a}
.login{min-height:100vh;display:grid;place-items:center;padding:18px;background:linear-gradient(#0b0d10cc,#07090bdd),url('/static/stadium.jpg') center/cover}.login-card{width:min(100%,420px);padding:26px 20px;background:#12161acc;border:1px solid #353b40;border-radius:18px;box-shadow:0 25px 80px #0008}.login-brand{text-align:center;font-weight:1000;font-size:28px;letter-spacing:-1.5px}.login-brand b{color:#ef1018}.login-sub{text-align:center;color:#aeb5bb;font-size:13px;margin:8px 0 22px}.field{display:flex;align-items:center;gap:10px;background:#292e33;border:1px solid #3b4147;border-radius:10px;padding:0 12px;margin:10px 0}.field span{font-size:20px}.field select,.field input{background:transparent;border:0;color:#fff;outline:0;width:100%;padding:14px 0;font-size:15px}.field option{background:#20242a;color:#fff}.tiny{font-size:11px;color:#899197;text-align:center;margin-top:15px}
@media(max-width:430px){.match{grid-template-columns:25px 1fr 120px}.choice{width:35px}.teams{font-size:12px}}
@media print{.topbar,.nav,.btn,.sharebox+h2{display:none!important}body{background:#fff;color:#111}.card{box-shadow:none;border:1px solid #ccc}.summary-scroll th:first-child,.summary-scroll td:first-child{background:#fff;color:#111}}
'''

LAYOUT = '''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#07090b"><title>Biwenger Quiniela</title><style>'''+CSS+'''</style></head><body>{{ body|safe }}</body></html>'''

def db():
    if DATABASE_URL:
        if not psycopg: raise RuntimeError('Falta psycopg')
        return psycopg.connect(DATABASE_URL, row_factory=dict_row)
    c=sqlite3.connect(os.environ.get('SQLITE_PATH','quiniela.db'))
    c.row_factory=sqlite3.Row
    return c

def q(conn, query, params=()):
    return conn.execute(query.replace('?', '%s') if DATABASE_URL else query, params)

def init_db():
    c=db()
    sts=(['''CREATE TABLE IF NOT EXISTS users(id SERIAL PRIMARY KEY,username TEXT UNIQUE NOT NULL,password TEXT NOT NULL,is_admin BOOLEAN NOT NULL DEFAULT FALSE)''','''CREATE TABLE IF NOT EXISTS rounds(id SERIAL PRIMARY KEY,name TEXT NOT NULL,open BOOLEAN NOT NULL DEFAULT TRUE)''','''CREATE TABLE IF NOT EXISTS matches(id SERIAL PRIMARY KEY,round_id INTEGER NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,home TEXT NOT NULL,away TEXT NOT NULL,match_order INTEGER NOT NULL)''','''CREATE TABLE IF NOT EXISTS bets(user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,prediction TEXT NOT NULL CHECK(prediction IN ('1','X','2')),PRIMARY KEY(user_id,match_id))'''] if DATABASE_URL else ['''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT UNIQUE NOT NULL,password TEXT NOT NULL,is_admin INTEGER NOT NULL DEFAULT 0)''','''CREATE TABLE IF NOT EXISTS rounds(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,open INTEGER NOT NULL DEFAULT 1)''','''CREATE TABLE IF NOT EXISTS matches(id INTEGER PRIMARY KEY AUTOINCREMENT,round_id INTEGER NOT NULL,home TEXT NOT NULL,away TEXT NOT NULL,match_order INTEGER NOT NULL)''','''CREATE TABLE IF NOT EXISTS bets(user_id INTEGER NOT NULL,match_id INTEGER NOT NULL,prediction TEXT NOT NULL,PRIMARY KEY(user_id,match_id))'''])
    for st in sts:c.execute(st)
    for name,admin in USERS:
        if q(c,'SELECT id FROM users WHERE username=?',(name,)).fetchone() is None:q(c,'INSERT INTO users(username,password,is_admin) VALUES(?,?,?)',(name,generate_password_hash('biwenger2026'),admin))
    if q(c,'SELECT id FROM rounds ORDER BY id DESC LIMIT 1').fetchone() is None:
        q(c,'INSERT INTO rounds(name,open) VALUES(?,?)',('Jornada 1',True));c.commit();rid=q(c,'SELECT id FROM rounds ORDER BY id DESC LIMIT 1').fetchone()['id']
        for i,(h,a) in enumerate([('Real Madrid','Real Sociedad'),('Barcelona','Valencia'),('Atlético de Madrid','Villarreal'),('Betis','Sevilla'),('Athletic Club','Getafe'),('Celta','Osasuna'),('Rayo Vallecano','Espanyol'),('Mallorca','Alavés'),('Girona','Las Palmas'),('Levante','Elche')],1):q(c,'INSERT INTO matches(round_id,home,away,match_order) VALUES(?,?,?,?)',(rid,h,a,i))
    c.commit();c.close()

def user():
    if 'user_id' not in session:return None
    c=db();u=q(c,'SELECT * FROM users WHERE id=?',(session['user_id'],)).fetchone();c.close();return u

def login_required(fn):
    @wraps(fn)
    def w(*a,**kw):
        if not user():return redirect(url_for('login'))
        return fn(*a,**kw)
    return w

def admin_required(fn):
    @wraps(fn)
    def w(*a,**kw):
        u=user()
        if not u or not u['is_admin']:abort(403)
        return fn(*a,**kw)
    return w

def page(inner, u=None, active='jornada'):
    if u:
        nav=''.join(f'<a class="{"active" if active==x else ""}" href="{url_for(route)}"><b>{ico}</b>{label}</a>' for x,route,ico,label in [('jornada','home','⚽','Jornada'),('apuesta','my_bet','📝','Mi apuesta'),('resumen','summary','📊','Resumen'),('mas','admin' if u['is_admin'] else 'ranking','☰','Más')])
        body=f'''<div class="app"><div class="topbar"><div class="menu">☰</div><div class="brand"><span class="stars">★★★★★</span>BIWENGER <b>QUINIELA</b></div><div class="avatar">{u['username'][:3].upper()}</div></div><main>{''.join(f'<div class="flash">{m}</div>' for m in flash_messages())}{inner}</main><div class="nav">{nav}</div></div>'''
    else:body=inner
    return render_template_string(LAYOUT,body=body)

def flash_messages():return session.pop('_flashes',[]) and []

@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        c=db();u=q(c,'SELECT * FROM users WHERE username=?',(request.form['username'],)).fetchone();c.close()
        if u and check_password_hash(u['password'],request.form['password']):session['user_id']=u['id'];return redirect(url_for('home'))
        flash('Usuario o contraseña incorrectos.')
    opts=''.join(f'<option>{x[0]}</option>' for x in USERS)
    inner=f'''<div class="login"><div class="login-card"><div class="login-brand">BIWENGER <b>QUINIELA</b></div><div class="login-sub">11 amigos · 1 quiniela · ¿Quién será el ganador?</div><form method="post"><div class="field"><span>👤</span><select name="username">{opts}</select></div><div class="field"><span>🔒</span><input name="password" type="password" placeholder="Contraseña" required></div><button class="btn">Iniciar sesión</button></form><div class="tiny">Contraseña inicial: <b>biwenger2026</b></div></div></div>'''
    return page(inner)

@app.route('/logout')
def logout():session.clear();return redirect(url_for('login'))

@app.route('/')
@login_required
def home():
    u=user();c=db();r=q(c,'SELECT * FROM rounds ORDER BY id DESC LIMIT 1').fetchone();ms=q(c,'SELECT * FROM matches WHERE round_id=? ORDER BY match_order',(r['id'],)).fetchall();bets={}
    for m in ms:
        b=q(c,'SELECT prediction FROM bets WHERE user_id=? AND match_id=?',(u['id'],m['id'])).fetchone();bets[m['id']]=b['prediction'] if b else ''
    c.close();rows=''
    for m in ms:
        rows+=f'<div class="match"><div class="num">{m["match_order"]}</div><div class="teams"><span>{m["home"]}</span><span>{m["away"]}</span></div><div class="choices">'+''.join(f'<a class="choice {"sel" if bets[m["id"]]==p else ""}" href="{url_for("bet",match_id=m["id"],prediction=p)}">{p}</a>' for p in ('1','X','2'))+'</div></div>'
    inner=f'''<div class="hero"><h1>{r['name']}</h1><p>Selecciona tu pronóstico. Tu apuesta es privada.</p><span class="status {'closed' if not r['open'] else ''}">{'🔒 CERRADA' if not r['open'] else '● ABIERTA'}</span></div><div class="card matches">{rows}</div><a class="btn" href="{url_for('my_bet')}">Guardar y ver mi apuesta</a><a class="btn secondary" href="{url_for('summary')}">📊 Ver resumen</a>'''
    return page(inner,u,'jornada')

@app.route('/bet/<int:match_id>/<prediction>')
@login_required
def bet(match_id,prediction):
    if prediction not in ('1','X','2'):abort(400)
    u=user();c=db();m=q(c,'SELECT * FROM matches WHERE id=?',(match_id,)).fetchone();r=q(c,'SELECT * FROM rounds WHERE id=?',(m['round_id'],)).fetchone()
    if r['open']:
        if DATABASE_URL:q(c,'INSERT INTO bets(user_id,match_id,prediction) VALUES(?,?,?) ON CONFLICT(user_id,match_id) DO UPDATE SET prediction=EXCLUDED.prediction',(u['id'],match_id,prediction))
        else:q(c,'INSERT OR REPLACE INTO bets(user_id,match_id,prediction) VALUES(?,?,?)',(u['id'],match_id,prediction))
        c.commit()
    c.close();return redirect(url_for('home'))

@app.route('/mi-apuesta')
@login_required
def my_bet():
    u=user();c=db();r=q(c,'SELECT * FROM rounds ORDER BY id DESC LIMIT 1').fetchone();ms=q(c,'SELECT * FROM matches WHERE round_id=? ORDER BY match_order',(r['id'],)).fetchall();rows='';complete=True
    for m in ms:
        b=q(c,'SELECT prediction FROM bets WHERE user_id=? AND match_id=?',(u['id'],m['id'])).fetchone();p=b['prediction'] if b else '—';complete &= bool(b);cls={'1':'one','X':'x','2':'two'}.get(p,'')
        rows+=f'<tr><td><b>{m["match_order"]}</b> &nbsp; {m["home"]} - {m["away"]}</td><td class="pick {cls}">{p}</td></tr>'
    c.close();notice='✅ Apuesta guardada · puedes modificarla hasta el cierre.' if complete else '⚠️ Te faltan partidos por pronosticar.'
    inner=f'''<div class="hero"><h1>Mi apuesta</h1><p>{r['name']} · {u['username']}</p><span class="status {'closed' if not r['open'] else ''}">{'🔒 CERRADA' if not r['open'] else '● ABIERTA'}</span></div><div class="flash">{notice}</div><div class="card"><table class="bet-table"><tr><th>Partido</th><th>Pronóstico</th></tr>{rows}</table></div><a class="btn secondary" href="{url_for('home')}">✏️ Editar apuesta</a>'''
    return page(inner,u,'apuesta')

@app.route('/resumen')
@login_required
def summary():
    u=user();c=db();r=q(c,'SELECT * FROM rounds ORDER BY id DESC LIMIT 1').fetchone();users=q(c,'SELECT * FROM users ORDER BY id').fetchall();ms=q(c,'SELECT * FROM matches WHERE round_id=? ORDER BY match_order',(r['id'],)).fetchall();heads=''.join(f'<th>{x["username"][:7]}</th>' for x in users);body=f'<div class="hero"><h1>Resumen</h1><p>{r["name"]} · {len(users)} participantes</p></div><div class="card summary-scroll"><table class="bet-table"><tr><th>Partido</th>{heads}<th>Reparto</th></tr>'
    share=[]
    for m in ms:
        vals=[];counts={'1':0,'X':0,'2':0}
        for x in users:
            b=q(c,'SELECT prediction FROM bets WHERE user_id=? AND match_id=?',(x['id'],m['id'])).fetchone();p=b['prediction'] if b else '—';vals.append(p)
            if p in counts:counts[p]+=1
        body+=f'<tr><td>{m["match_order"]}. {m["home"]} - {m["away"]}</td>'+''.join(f'<td class="pick">{p}</td>' for p in vals)+f'<td>{counts["1"]} · {counts["X"]} · {counts["2"]}</td></tr>'
        share.append(f'{m["match_order"]}. {m["home"]} - {m["away"]}\n'+' | '.join(f'{x["username"]}: {vals[i]}' for i,x in enumerate(users)))
    c.close();body+=f'''</table></div><h2 style="margin-top:20px">Compartir con el grupo</h2><textarea class="sharebox" readonly>{'\n'.join(share)}</textarea><button class="btn" onclick="navigator.clipboard.writeText(document.querySelector('.sharebox').value);this.innerText='✅ Copiado'">📋 Copiar resumen</button>'''
    return page(body,u,'resumen')

@app.route('/clasificacion')
@login_required
def ranking():
    u=user();c=db();users=q(c,'SELECT * FROM users ORDER BY id').fetchall();body='<div class="hero"><h1>Clasificación</h1><p>Tabla general de la liga</p></div><div class="card">'
    for i,x in enumerate(users,1):body+=f'<div class="match"><div class="num">{i}</div><div class="teams">{x["username"]}</div><b>— pts</b></div>'
    c.close();body+='</div>';return page(body,u,'mas')

@app.route('/admin',methods=['GET','POST'])
@admin_required
def admin():
    u=user();c=db()
    if request.method=='POST':
        a=request.form.get('action')
        if a=='new':q(c,'INSERT INTO rounds(name,open) VALUES(?,?)',(request.form.get('name','Nueva jornada'),True));c.commit()
        elif a in ('close','open'):q(c,'UPDATE rounds SET open=? WHERE id=?',(a=='open',int(request.form['id'])));c.commit()
        return redirect(url_for('admin'))
    rounds=q(c,'SELECT * FROM rounds ORDER BY id DESC').fetchall();r=rounds[0];n=q(c,'SELECT COUNT(*) FROM matches WHERE round_id=?',(r['id'],)).fetchone()['count']
    c.close();items=''.join(f'<div class="match"><div class="teams"><b>{x["name"]}</b><span class="muted">{"ABIERTA" if x["open"] else "CERRADA"}</span></div><form method="post"><input type="hidden" name="action" value="{"close" if x["open"] else "open"}"><input type="hidden" name="id" value="{x["id"]}"><button class="btn small secondary">{"🔒 Cerrar" if x["open"] else "🔓 Abrir"}</button></form></div>' for x in rounds)
    body=f'''<div class="hero"><h1>⚙️ Administración</h1><p>Solo RFMF</p></div><div class="statgrid"><div class="stat"><strong>{len(USERS)}</strong><span>Participantes</span></div><div class="stat"><strong>{n}</strong><span>Partidos</span></div></div><div class="admin-grid" style="margin-top:12px"><a class="admin-tile" href="{url_for('summary')}"><b>📋</b>Ver apuestas</a><a class="admin-tile" href="{url_for('home')}"><b>⚽</b>Jornada actual</a></div><div class="card" style="margin-top:12px;padding:14px"><h2>Nueva jornada</h2><form method="post"><input type="hidden" name="action" value="new"><div class="field"><input name="name" placeholder="Ej. Jornada 2" required></div><button class="btn">➕ Crear jornada</button></form></div><div class="card" style="margin-top:12px;padding:10px"><h2 style="padding:0 6px">Jornadas</h2>{items}</div>'''
    return page(body,u,'mas')

@app.route('/health')
def health():return 'OK',200

init_db()
if __name__=='__main__':app.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)))
