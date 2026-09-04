import os, sqlite3, hashlib
from datetime import datetime, timezone
from functools import wraps
import requests
from flask import Flask, request, redirect, url_for, session, jsonify, send_from_directory, render_template_string

app = Flask(__name__, static_folder=None)
app.secret_key = os.getenv('SECRET_KEY', 'cambia-esta-clave-en-produccion')
DB = os.getenv('DATABASE_PATH', 'quiniela.db')
START_ROUND = 5
PRIZE_PER_HIT = 100_000
ADMIN_USER = os.getenv('ADMIN_USER', 'RFM')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'biwenger2026')
ESPN_URL = 'https://site.api.espn.com/apis/site/v2/sports/soccer/esp.1/scoreboard'

# Round 5 is included as a guaranteed calendar fallback. Live scores are then
# refreshed from ESPN's public scoreboard (no paid API key required).
ROUND5 = [
 ('r5-1','Sevilla','Valencia','2026-09-11T21:00:00+02:00'),
 ('r5-2','Racing Santander','Alavés','2026-09-12T14:00:00+02:00'),
 ('r5-3','Osasuna','Espanyol','2026-09-12T16:15:00+02:00'),
 ('r5-4','Athletic Club','Elche','2026-09-12T18:30:00+02:00'),
 ('r5-5','Real Madrid','Rayo Vallecano','2026-09-12T21:00:00+02:00'),
 ('r5-6','Celta','Málaga','2026-09-13T14:00:00+02:00'),
 ('r5-7','Levante','Barcelona','2026-09-13T16:15:00+02:00'),
 ('r5-8','Getafe','Deportivo','2026-09-13T18:30:00+02:00'),
 ('r5-9','Real Sociedad','Atlético de Madrid','2026-09-13T21:00:00+02:00'),
 ('r5-10','Villarreal','Real Betis','2026-09-14T21:00:00+02:00'),
]

LOGIN_HTML='''<!doctype html><html lang="es"><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Quiniela Mediamarkera</title><style>body{margin:0;background:#07090b;color:#fff;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif}.box{max-width:430px;margin:12vh auto;padding:28px;background:#12161b;border:1px solid #30363d;border-radius:20px}h1{font-size:28px;margin:0 0 8px}h1 b{color:#e30613}.muted{color:#a8adb6}label{display:block;margin-top:18px}input{width:100%;box-sizing:border-box;padding:14px;border-radius:10px;border:1px solid #424850;background:#20252b;color:#fff;font-size:16px;margin-top:7px}button{width:100%;padding:14px;border:0;border-radius:10px;background:#e30613;color:#fff;font-size:16px;font-weight:800;margin-top:20px}.error{background:#3a1418;color:#ff9ca3;padding:10px;border-radius:10px;margin-top:15px}</style></head><body><div class="box"><h1>QUINIELA <b>MEDIAMARKERA</b></h1><p class="muted">Jornada 5 · 100.000 € por acierto</p>{% if error %}<div class="error">{{error}}</div>{% endif %}<form method="post"><label>Usuario</label><input name="username" required><label>Contraseña</label><input name="password" type="password" required><button>Iniciar sesión</button></form></div></body></html>'''

def db():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row
 c.execute('CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY,password TEXT NOT NULL,is_admin INTEGER DEFAULT 0,active INTEGER DEFAULT 1)')
 c.execute('CREATE TABLE IF NOT EXISTS bets(username TEXT,round INTEGER,match_id TEXT,pick TEXT,PRIMARY KEY(username,round,match_id))')
 c.execute('INSERT OR IGNORE INTO users(username,password,is_admin,active) VALUES(?,?,1,1)',(ADMIN_USER,ADMIN_PASSWORD))
 c.commit(); return c

def login_required(fn):
 @wraps(fn)
 def w(*a,**k):
  if 'user' not in session:return jsonify({'error':'No autenticado'}),401
  return fn(*a,**k)
 return w

def admin_required(fn):
 @wraps(fn)
 def w(*a,**k):
  if 'user' not in session:return jsonify({'error':'No autenticado'}),401
  c=db(); r=c.execute('SELECT is_admin,active FROM users WHERE username=?',(session['user'],)).fetchone()
  if not r or not r['active'] or not r['is_admin']:return jsonify({'error':'Acceso de administrador requerido'}),403
  return fn(*a,**k)
 return w

def outcome(h,a):
 if h is None or a is None:return None
 return '1' if h>a else ('2' if h<a else 'X')

def blank_round(rn):
 if rn==5:
  return [{'id':i,'home':h,'away':a,'date':d,'home_goals':None,'away_goals':None,'status':'NS','status_label':'Próximo','elapsed':None,'finished':False,'live':False,'home_logo':None,'away_logo':None} for i,h,a,d in ROUND5]
 return []

def normalize_espn(ev):
 c=(ev.get('competitions') or [{}])[0]; comps=c.get('competitors') or []
 home=next((x for x in comps if x.get('homeAway')=='home'),{})
 away=next((x for x in comps if x.get('homeAway')=='away'),{})
 st=c.get('status') or {}; typ=st.get('type') or {}; state=typ.get('state','pre'); detail=typ.get('detail','')
 status={'pre':'NS','in':'LIVE','post':'FT'}.get(state,state.upper())
 score_h=int(home.get('score')) if str(home.get('score','')).isdigit() else None
 score_a=int(away.get('score')) if str(away.get('score','')).isdigit() else None
 live=state=='in'; finished=state=='post'
 elapsed=None
 if live:
  clock=(st.get('displayClock') or '').replace(' ','')
  if clock:
   elapsed=clock.replace(':00','')
 return {'id':str(ev.get('id')),'home':(home.get('team') or {}).get('displayName',''),'away':(away.get('team') or {}).get('displayName',''),'date':ev.get('date'),'home_goals':score_h,'away_goals':score_a,'status':status,'status_label': 'EN DIRECTO' if live else ('Finalizado' if finished else detail or 'Próximo'),'elapsed':elapsed,'finished':finished,'live':live,'home_logo':(home.get('team') or {}).get('logo'),'away_logo':(away.get('team') or {}).get('logo')}

def espn_events_for_round(rn):
 if rn!=5:return [],None
 # Query each calendar day to avoid relying on a range endpoint.
 dates=['20260911','20260912','20260913','20260914']; out=[]
 try:
  for date in dates:
   r=requests.get(ESPN_URL,params={'dates':date,'limit':100},headers={'User-Agent':'Mozilla/5.0'},timeout=8)
   r.raise_for_status(); out.extend([normalize_espn(e) for e in r.json().get('events',[])])
  # Keep only fixtures belonging to LaLiga teams in this round.
  names={h for _,h,_,_ in ROUND5}|{a for _,_,a,_ in ROUND5}
  def close(n):
   n=n.lower().replace('cf','').replace('ud','').strip()
   return any(n in x.lower() or x.lower() in n for x in names)
  out=[x for x in out if close(x['home']) and close(x['away'])]
  return out,None
 except Exception as e:
  return [],f'Fuente de resultados temporalmente no disponible: {e}'

def fixture_matches(rn):
 base=blank_round(rn); live_events,err=espn_events_for_round(rn)
 if rn==5:
  # Map ESPN live/final events onto the guaranteed official calendar.
  for b in base:
   candidates=[e for e in live_events if e['home'].lower() in b['home'].lower() or b['home'].lower() in e['home'].lower()]
   candidates=[e for e in candidates if e['away'].lower() in b['away'].lower() or b['away'].lower() in e['away'].lower()]
   if candidates:
    e=candidates[0]; b.update(e); b['id']=b['id']
  return base,err
 return [],err or 'No hay calendario cargado para esta jornada.'

def bets_for(user,rn):
 c=db(); rows=c.execute('SELECT match_id,pick FROM bets WHERE username=? AND round=?',(user,rn)).fetchall(); return {r['match_id']:r['pick'] for r in rows}

def summary_data(user):
 c=db(); rounds=[r[0] for r in c.execute('SELECT DISTINCT round FROM bets WHERE username=? ORDER BY round',(user,)).fetchall()]
 total=pending=errors=0; out=[]
 for rn in rounds:
  ms,_=fixture_matches(rn); bs=bets_for(user,rn); h=p=e=0
  for m in ms:
   a=outcome(m['home_goals'],m['away_goals']) if m['finished'] else None
   if a is None:p+=1
   elif bs.get(m['id'])==a:h+=1
   else:e+=1
  total+=h;pending+=p;errors+=e;out.append({'round':rn,'hits':h,'pending':p,'errors':e,'prize':h*PRIZE_PER_HIT})
 return {'username':user,'hits':total,'pending':pending,'errors':errors,'prize':total*PRIZE_PER_HIT,'rounds':out}

@app.route('/')
def home():
 if 'user' not in session:return redirect(url_for('login'))
 return send_from_directory('.', 'index.html')
@app.route('/style.css')
def css():return send_from_directory('.','style.css')
@app.route('/rfmf_logo.svg')
def logo():return send_from_directory('.','rfmf_logo.svg')
@app.route('/login',methods=['GET','POST'])
def login():
 db()
 if request.method=='POST':
  u=request.form.get('username','').strip();p=request.form.get('password','');c=db();r=c.execute('SELECT * FROM users WHERE username=?',(u,)).fetchone()
  if r and r['active'] and r['password']==p:session['user']=u;return redirect(url_for('home'))
  return render_template_string(LOGIN_HTML,error='Usuario o contraseña incorrectos.')
 return render_template_string(LOGIN_HTML,error=None)
@app.route('/logout')
def logout():session.clear();return redirect(url_for('login'))
@app.route('/api/me')
@login_required
def me():
 r=db().execute('SELECT username,is_admin,active FROM users WHERE username=?',(session['user'],)).fetchone();return jsonify(dict(r))
@app.route('/api/matches')
@login_required
def api_matches():
 rn=max(START_ROUND,min(38,int(request.args.get('round',START_ROUND))));ms,err=fixture_matches(rn);bs=bets_for(session['user'],rn)
 for m in ms:
  a=outcome(m['home_goals'],m['away_goals']) if m['finished'] else None;m['pick']=bs.get(m['id']);m['actual']=a;m['score']=f"{m['home_goals']} - {m['away_goals']}" if m['home_goals'] is not None and m['away_goals'] is not None else None;m['correct']=bool(a and m['pick']==a)
 return jsonify({'jornada':rn,'matches':ms,'prize_per_hit':PRIZE_PER_HIT,'api_error':err,'source':'ESPN público + calendario oficial de respaldo','updated_at':datetime.now(timezone.utc).isoformat()})
@app.route('/api/save',methods=['POST'])
@login_required
def save():
 d=request.get_json(silent=True) or {};rn=max(START_ROUND,min(38,int(d.get('round',START_ROUND))));pred=d.get('predictions') or {};c=db();saved=0
 valid={m['id'] for m in blank_round(rn)}
 # Also accept existing database IDs when an external source is available.
 ms,_=fixture_matches(rn);valid|={m['id'] for m in ms}
 for mid,pick in pred.items():
  if pick in {'1','X','2'} and str(mid) in valid:c.execute('INSERT OR REPLACE INTO bets(username,round,match_id,pick) VALUES(?,?,?,?)',(session['user'],rn,str(mid),pick));saved+=1
 c.commit();return jsonify({'ok':True,'saved':saved})
@app.route('/api/check')
@login_required
def check():
 rn=max(START_ROUND,min(38,int(request.args.get('round',START_ROUND))));ms,err=fixture_matches(rn);bs=bets_for(session['user'],rn);res=[];h=p=e=0
 for m in ms:
  a=outcome(m['home_goals'],m['away_goals']) if m['finished'] else None;pick=bs.get(m['id']);hit=bool(a and pick==a)
  if a:h+=hit;e+=not hit
  else:p+=1
  res.append({'id':m['id'],'home':m['home'],'away':m['away'],'pick':pick,'actual':a,'score':m['score'] if 'score' in m else (f"{m['home_goals']} - {m['away_goals']}" if a else None),'hit':hit,'status':m['status'],'status_label':m['status_label'],'elapsed':m['elapsed'],'live':m['live'],'finished':m['finished']})
 return jsonify({'round':rn,'hits':h,'pending':p,'errors':e,'prize':h*PRIZE_PER_HIT,'results':res,'api_error':err})
@app.route('/api/summary')
@login_required
def summary():return jsonify(summary_data(session['user']))

# Admin
@app.route('/api/admin/users')
@admin_required
def users():
 rows=db().execute('SELECT username,is_admin,active FROM users ORDER BY is_admin DESC,username').fetchall();return jsonify({'users':[dict(r) for r in rows]})
@app.route('/api/admin/users',methods=['POST'])
@admin_required
def create_user():
 d=request.get_json(silent=True) or {};u=str(d.get('username','')).strip();p=str(d.get('password','')).strip()
 if not u or not p:return jsonify({'error':'Usuario y contraseña son obligatorios'}),400
 try:
  c=db();c.execute('INSERT INTO users(username,password,is_admin,active) VALUES(?,?,0,1)',(u,p));c.commit();return jsonify({'ok':True})
 except sqlite3.IntegrityError:return jsonify({'error':'Ese usuario ya existe'}),409
@app.route('/api/admin/users/<path:u>',methods=['POST'])
@admin_required
def update_user(u):
 d=request.get_json(silent=True) or {};c=db();r=c.execute('SELECT * FROM users WHERE username=?',(u,)).fetchone()
 if not r:return jsonify({'error':'Usuario no encontrado'}),404
 if 'password' in d and str(d['password']).strip():c.execute('UPDATE users SET password=? WHERE username=?',(str(d['password']).strip(),u))
 if 'active' in d and u!=ADMIN_USER:c.execute('UPDATE users SET active=? WHERE username=?',(1 if d['active'] else 0,u))
 c.commit();return jsonify({'ok':True})
@app.route('/api/admin/users/<path:u>',methods=['DELETE'])
@admin_required
def delete_user(u):
 if u==ADMIN_USER:return jsonify({'error':'No se puede eliminar el administrador principal'}),400
 c=db();c.execute('DELETE FROM bets WHERE username=?',(u,));c.execute('DELETE FROM users WHERE username=?',(u,));c.commit();return jsonify({'ok':True})
@app.route('/api/admin/user-summary/<path:u>')
@admin_required
def user_summary(u):return jsonify(summary_data(u))
@app.route('/api/admin/overview')
@admin_required
def overview():
 rows=db().execute('SELECT username FROM users WHERE active=1 ORDER BY username').fetchall();return jsonify({'users':[summary_data(r['username']) for r in rows]})
@app.route('/api/admin/bets',methods=['GET','POST'])
@admin_required
def admin_bets():
 if request.method=='GET':
  rn=int(request.args.get('round',START_ROUND));u=request.args.get('username');q='SELECT username,round,match_id,pick FROM bets WHERE round=?';args=[rn]
  if u:q+=' AND username=?';args.append(u)
  return jsonify({'bets':[dict(r) for r in db().execute(q,args).fetchall()]})
 d=request.get_json(silent=True) or {};u=str(d.get('username',''));rn=int(d.get('round',START_ROUND));pred=d.get('predictions') or {};c=db()
 for mid,pick in pred.items():
  if pick in {'1','X','2'}:c.execute('INSERT OR REPLACE INTO bets(username,round,match_id,pick) VALUES(?,?,?,?)',(u,rn,str(mid),pick))
 c.commit();return jsonify({'ok':True})

if __name__=='__main__':db();app.run(host='0.0.0.0',port=int(os.getenv('PORT','8080')))
