import os
import sqlite3
from datetime import datetime, timezone
from functools import wraps
import requests
from flask import Flask, request, redirect, url_for, session, jsonify, send_from_directory, render_template_string

app = Flask(__name__, static_folder=None)
app.secret_key = os.getenv("SECRET_KEY", "cambia-esta-clave-en-produccion")
DB = os.getenv("DATABASE_PATH", "quiniela.db")

SOFASCORE_URL = "https://www.sofascore.com/api/v1"
TOURNAMENT_ID = 8
SEASON_ID = 97268
START_ROUND = 5
PRIZE_PER_HIT = 100_000

ADMIN_USER = os.getenv("ADMIN_USER", "RFM")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "biwenger2026")

LOGIN_HTML = """<!doctype html><html lang="es"><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Quiniela Mediamarkera</title><style>
body{margin:0;background:#07090b;color:#fff;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif}.box{max-width:430px;margin:15vh auto;padding:28px;background:#12161b;border:1px solid #30363d;border-radius:20px}h1{font-size:30px;margin:0 0 8px}b{color:#e30613}.muted{color:#a8adb6}label{display:block;margin-top:18px}input{width:100%;box-sizing:border-box;padding:14px;border-radius:10px;border:1px solid #424850;background:#20252b;color:#fff;font-size:16px;margin-top:7px}button{width:100%;padding:14px;border:0;border-radius:10px;background:#e30613;color:#fff;font-size:16px;font-weight:800;margin-top:20px}.error{background:#3a1418;color:#ff9ca3;padding:10px;border-radius:10px;margin-top:15px}</style></head><body><div class="box"><h1>QUINIELA <b>MEDIAMARKERA</b></h1><p class="muted">Jornada 5 · 100.000 € por acierto</p>{% if error %}<div class="error">{{error}}</div>{% endif %}<form method="post"><label>Usuario</label><input name="username" value="RFM" required><label>Contraseña</label><input name="password" type="password" required><button>Iniciar sesión</button></form></div></body></html>"""

def db():
    c=sqlite3.connect(DB)
    c.row_factory=sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS users(
        username TEXT PRIMARY KEY, password TEXT NOT NULL, is_admin INTEGER DEFAULT 0, active INTEGER DEFAULT 1)""")
    c.execute("""CREATE TABLE IF NOT EXISTS bets(
        username TEXT, round INTEGER, match_id TEXT, pick TEXT,
        PRIMARY KEY(username,round,match_id))""")
    c.execute("INSERT OR IGNORE INTO users(username,password,is_admin,active) VALUES(?,?,?,?,?)",
              (ADMIN_USER, ADMIN_PASSWORD, 1, 1))
    c.commit(); return c

def login_required(fn):
    @wraps(fn)
    def wrapper(*args,**kwargs):
        if "user" not in session: return jsonify({"error":"No autenticado"}),401
        return fn(*args,**kwargs)
    return wrapper

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args,**kwargs):
        if "user" not in session: return jsonify({"error":"No autenticado"}),401
        c=db(); row=c.execute("SELECT is_admin,active FROM users WHERE username=?",(session["user"],)).fetchone()
        if not row or not row["active"] or not row["is_admin"]: return jsonify({"error":"Acceso de administrador requerido"}),403
        return fn(*args,**kwargs)
    return wrapper

def outcome(home,away):
    if home is None or away is None:return None
    return "1" if home>away else ("2" if home<away else "X")

def fixture_matches(round_no):
    try:
        r=requests.get(f"{SOFASCORE_URL}/unique-tournament/{TOURNAMENT_ID}/season/{SEASON_ID}/events/round/{round_no}",
                       headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"},timeout=15)
        r.raise_for_status()
        out=[]
        for e in r.json().get("events",[]):
            h=e.get("homeTeam") or {}; a=e.get("awayTeam") or {}
            s=e.get("status") or {}; hs=e.get("homeScore") or {}; aws=e.get("awayScore") or {}
            st=s.get("type",""); finished=st=="finished"; live=st in {"inprogress","in_progress"}
            label="Finalizado" if finished else ("EN DIRECTO" if live else ("Aplazado" if st=="postponed" else ("Cancelado" if st=="canceled" else "Próximo")))
            t=e.get("time") or {}; elapsed=t.get("current") or t.get("played")
            ts=e.get("startTimestamp")
            out.append({"id":str(e.get("id")),"home":h.get("name",""),"away":a.get("name",""),
                        "home_logo":f"https://api.sofascore.com/api/v1/team/{h.get('id')}/image" if h.get("id") else None,
                        "away_logo":f"https://api.sofascore.com/api/v1/team/{a.get('id')}/image" if a.get("id") else None,
                        "date":datetime.fromtimestamp(ts,tz=timezone.utc).isoformat() if ts else None,
                        "timestamp":ts,"home_goals":hs.get("current"),"away_goals":aws.get("current"),
                        "status":st,"status_label":label,"elapsed":elapsed,"finished":finished,"live":live})
        out.sort(key=lambda x:x.get("timestamp") or 0); return out,None
    except Exception as e:
        app.logger.warning("SofaScore: %s",e); return [],str(e)

def get_matches(r): return fixture_matches(r)

def bets_for(username,r):
    c=db(); rows=c.execute("SELECT match_id,pick FROM bets WHERE username=? AND round=?",(username,r)).fetchall()
    return {x["match_id"]:x["pick"] for x in rows}

@app.route("/")
def home():
    if "user" not in session:return redirect(url_for("login"))
    return send_from_directory(".","index.html")

@app.route("/style.css")
def css_file(): return send_from_directory(".","style.css")
@app.route("/rfmf_logo.svg")
def logo_file(): return send_from_directory(".","rfmf_logo.svg")

@app.route("/login",methods=["GET","POST"])
def login():
    db()
    if request.method=="POST":
        u=request.form.get("username","").strip(); p=request.form.get("password","")
        c=db(); row=c.execute("SELECT * FROM users WHERE username=?",(u,)).fetchone()
        if row and row["active"] and row["password"]==p:
            session["user"]=u; return redirect(url_for("home"))
        return render_template_string(LOGIN_HTML,error="Usuario o contraseña incorrectos.")
    return render_template_string(LOGIN_HTML,error=None)

@app.route("/logout")
def logout(): session.clear(); return redirect(url_for("login"))

@app.route("/api/me")
@login_required
def me():
    c=db(); row=c.execute("SELECT username,is_admin,active FROM users WHERE username=?",(session["user"],)).fetchone()
    return jsonify({"username":row["username"],"is_admin":bool(row["is_admin"]),"active":bool(row["active"])})

@app.route("/api/matches")
@login_required
def api_matches():
    rn=max(START_ROUND,min(38,int(request.args.get("round",START_ROUND))))
    matches,err=get_matches(rn); bets=bets_for(session["user"],rn)
    for m in matches:
        actual=outcome(m["home_goals"],m["away_goals"]) if m["finished"] else None
        m["pick"]=bets.get(m["id"]); m["actual"]=actual
        m["score"]=f'{m["home_goals"]} - {m["away_goals"]}' if m["home_goals"] is not None and m["away_goals"] is not None else None
        m["correct"]=bool(actual and m["pick"]==actual)
    return jsonify({"jornada":rn,"matches":matches,"prize_per_hit":PRIZE_PER_HIT,"api_error":err,"updated_at":datetime.now(timezone.utc).isoformat()})

@app.route("/api/save",methods=["POST"])
@login_required
def api_save():
    data=request.get_json(silent=True) or {}; rn=max(START_ROUND,min(38,int(data.get("round",START_ROUND))))
    predictions=data.get("predictions",{}); matches,_=get_matches(rn); valid={m["id"] for m in matches}
    if not valid: valid={str(k) for k in predictions}
    c=db(); saved=0
    for mid,pick in predictions.items():
        if str(mid) in valid and pick in {"1","X","2"}:
            c.execute("INSERT OR REPLACE INTO bets(username,round,match_id,pick) VALUES(?,?,?,?)",(session["user"],rn,str(mid),pick)); saved+=1
    c.commit(); return jsonify({"ok":saved>0,"saved":saved})

@app.route("/api/check")
@login_required
def api_check():
    rn=max(START_ROUND,min(38,int(request.args.get("round",START_ROUND))))
    matches,err=get_matches(rn); bets=bets_for(session["user"],rn); results=[]; hits=pending=errors=0
    for m in matches:
        actual=outcome(m["home_goals"],m["away_goals"]) if m["finished"] else None; pick=bets.get(m["id"]); hit=bool(actual and pick==actual)
        if actual:hits+=int(hit); errors+=int(not hit)
        else:pending+=1
        results.append({"id":m["id"],"home":m["home"],"away":m["away"],"pick":pick,"actual":actual,
                        "score":f'{m["home_goals"]} - {m["away_goals"]}' if actual else None,"hit":hit,
                        "status":m["status"],"status_label":m["status_label"],"elapsed":m["elapsed"],"live":m["live"],"finished":m["finished"]})
    return jsonify({"round":rn,"hits":hits,"pending":pending,"errors":errors,"prize":hits*PRIZE_PER_HIT,"results":results,"api_error":err})

@app.route("/api/summary")
@login_required
def api_summary():
    return summary_for(session["user"])

def summary_for(username):
    c=db(); rounds=[r[0] for r in c.execute("SELECT DISTINCT round FROM bets WHERE username=? AND round>=? ORDER BY round",(username,START_ROUND)).fetchall()]
    total=pend=0; out=[]
    for rn in rounds:
        ms,_=get_matches(rn); bs=bets_for(username,rn); h=p=e=0
        for m in ms:
            a=outcome(m["home_goals"],m["away_goals"]) if m["finished"] else None
            if a is None:p+=1
            elif bs.get(m["id"])==a:h+=1
            else:e+=1
        total+=h; pend+=p; out.append({"round":rn,"hits":h,"pending":p,"errors":e,"prize":h*PRIZE_PER_HIT})
    return jsonify({"username":username,"hits":total,"prize":total*PRIZE_PER_HIT,"pending":pend,"rounds":out})

# ---------------- ADMIN ----------------
@app.route("/api/admin/users")
@admin_required
def admin_users():
    c=db(); rows=c.execute("SELECT username,is_admin,active FROM users ORDER BY username").fetchall()
    return jsonify({"users":[{"username":r["username"],"is_admin":bool(r["is_admin"]),"active":bool(r["active"])} for r in rows]})

@app.route("/api/admin/users",methods=["POST"])
@admin_required
def admin_create_user():
    d=request.get_json(silent=True) or {}; u=str(d.get("username","")).strip(); p=str(d.get("password",""))
    if not u or not p:return jsonify({"error":"Usuario y contraseña obligatorios"}),400
    c=db()
    try:c.execute("INSERT INTO users(username,password,is_admin,active) VALUES(?,?,0,1)",(u,p)); c.commit()
    except sqlite3.IntegrityError:return jsonify({"error":"El usuario ya existe"}),409
    return jsonify({"ok":True})

@app.route("/api/admin/users/<username>",methods=["POST"])
@admin_required
def admin_update_user(username):
    d=request.get_json(silent=True) or {}; c=db()
    if username==ADMIN_USER and d.get("active") is False:return jsonify({"error":"No puedes desactivar al administrador principal"}),400
    if "password" in d and d["password"]:
        c.execute("UPDATE users SET password=? WHERE username=?",(str(d["password"]),username))
    if "active" in d:c.execute("UPDATE users SET active=? WHERE username=?",(1 if d["active"] else 0,username))
    c.commit(); return jsonify({"ok":True})

@app.route("/api/admin/users/<username>",methods=["DELETE"])
@admin_required
def admin_delete_user(username):
    if username==ADMIN_USER:return jsonify({"error":"No puedes eliminar al administrador principal"}),400
    c=db(); c.execute("DELETE FROM bets WHERE username=?",(username,)); c.execute("DELETE FROM users WHERE username=?",(username,)); c.commit()
    return jsonify({"ok":True})

@app.route("/api/admin/bets")
@admin_required
def admin_bets():
    rn=max(START_ROUND,min(38,int(request.args.get("round",START_ROUND)))); user=request.args.get("username")
    c=db(); q="SELECT username,round,match_id,pick FROM bets WHERE round=?"; args=[rn]
    if user:q+=" AND username=?"; args.append(user)
    rows=c.execute(q,args).fetchall()
    return jsonify({"round":rn,"bets":[dict(r) for r in rows]})

@app.route("/api/admin/bets/<username>/<int:rn>",methods=["GET","POST"])
@admin_required
def admin_user_bets(username,rn):
    if request.method=="POST":
        d=request.get_json(silent=True) or {}; c=db()
        for mid,pick in (d.get("predictions") or {}).items():
            if pick in {"1","X","2"}:c.execute("INSERT OR REPLACE INTO bets(username,round,match_id,pick) VALUES(?,?,?,?)",(username,rn,str(mid),pick))
        c.commit()
    return summary_for(username)

@app.route("/api/admin/overview")
@admin_required
def admin_overview():
    c=db(); users=[r["username"] for r in c.execute("SELECT username FROM users WHERE active=1 ORDER BY username").fetchall()]
    data=[]
    for u in users:
        s=summary_for(u).get_json(); data.append(s)
    return jsonify({"users":data})

if __name__=="__main__":
    db(); app.run(host="0.0.0.0",port=int(os.getenv("PORT","8080")))
