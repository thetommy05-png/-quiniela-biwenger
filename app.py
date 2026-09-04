import os
import sqlite3
from functools import wraps
from datetime import datetime

import requests
from flask import Flask, request, redirect, url_for, session, render_template_string, jsonify

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "cambia-esta-clave-en-produccion")

DB = os.getenv("DATABASE_PATH", "quiniela.db")
API_KEY = os.getenv("API_FOOTBALL_KEY") or os.getenv("API_FOOTBALL")
API_URL = "https://v3.football.api-sports.io"
LEAGUE_ID = 140  # LaLiga
SEASON = int(os.getenv("FOOTBALL_SEASON", "2026"))
START_ROUND = 5
PRIZE_PER_HIT = 100_000

TEAMS_FALLBACK = [
    ("Real Madrid", "Real Sociedad"),
    ("Barcelona", "Valencia"),
    ("Atlético de Madrid", "Villarreal"),
    ("Betis", "Sevilla"),
    ("Athletic Club", "Getafe"),
    ("Celta", "Osasuna"),
    ("Rayo Vallecano", "Espanyol"),
    ("Mallorca", "Alavés"),
    ("Girona", "Las Palmas"),
    ("Levante", "Elche"),
]

HTML = r"""
<!doctype html>
<html lang="es">
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Quiniela Mediamarkera</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#080a0d;color:#f4f4f5;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif}
header{height:76px;background:#101317;border-bottom:1px solid #292d33;display:flex;align-items:center;justify-content:space-between;padding:0 18px;position:sticky;top:0;z-index:10}
.brand{display:flex;align-items:center;gap:12px;font-weight:900;font-size:22px}.brand b{color:#e30613}.brand span{color:#fff}
.logo{width:46px;height:46px;border-radius:50%;object-fit:contain;background:#fff;border:2px solid #e30613}
.user{background:#272c31;border:1px solid #41474e;border-radius:50%;width:44px;height:44px;display:flex;align-items:center;justify-content:center;font-weight:800}
main{max-width:760px;margin:0 auto;padding:24px 14px 100px}.hero{text-align:center;padding:8px 0 20px}
h1{font-size:34px;margin:8px 0}.sub{color:#a9adb5;font-size:16px}.pill{display:inline-block;margin-top:14px;background:#063d27;border:1px solid #10b981;color:#5ee7ad;padding:8px 18px;border-radius:24px;font-weight:800}
.card{background:#12161a;border:1px solid #30363d;border-radius:16px;padding:8px 14px;margin-top:15px;box-shadow:0 8px 25px #0005}
.match{display:grid;grid-template-columns:35px 1fr 180px;align-items:center;gap:8px;padding:14px 4px;border-bottom:1px solid #292d33}.match:last-child{border-bottom:0}
.num{color:#aeb3bb;font-size:14px}.teams{font-size:16px;line-height:1.35}.teams small{display:block;color:#aeb3bb}.buttons{display:flex;justify-content:flex-end;gap:7px}
button,.btn{border:1px solid #424850;background:#20252b;color:white;border-radius:9px;min-width:48px;padding:11px 10px;font-weight:800;font-size:15px;text-decoration:none;cursor:pointer}
button.active{background:#f1f3f5;color:#101317;border-color:#fff}.red{background:#e30613;border-color:#e30613;width:100%;padding:14px;border-radius:10px}.nav{display:flex;gap:8px;margin:16px 0;flex-wrap:wrap}.nav .btn{flex:1;text-align:center;min-width:120px}
.result{font-weight:800;text-align:right}.ok{color:#35d58a}.bad{color:#ff5c67}.pending{color:#f4c95d}
.scorebox{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:16px 0}.stat{background:#151a1f;border:1px solid #30363d;border-radius:14px;padding:16px}.stat strong{display:block;font-size:25px;margin-top:4px}
.notice{padding:12px;border-radius:10px;background:#24200d;color:#f5d66a;margin:12px 0}.error{background:#351317;color:#ff8990}.login{max-width:480px;margin:60px auto}
input,select{width:100%;padding:14px;border-radius:10px;border:1px solid #3b4148;background:#1d2126;color:#fff;margin:8px 0 14px;font-size:16px}
footer{position:fixed;bottom:0;left:0;right:0;background:#101317;border-top:1px solid #292d33;display:flex;justify-content:center;gap:25px;padding:12px}
footer a{color:#aeb3bb;text-decoration:none;font-weight:700}.muted{color:#858b94}
@media(max-width:620px){.match{grid-template-columns:25px 1fr 150px}.buttons{gap:4px}.buttons button{min-width:42px;padding:10px 7px}h1{font-size:29px}}
</style>
</head>
<body>
<header>
  <div class="brand">
    <img class="logo" src="/logo.svg" alt="RFMF">
    <span>QUINIELA <b>MEDIAMARKERA</b></span>
  </div>
  <div class="user">{{ session.get('user','RFM') }}</div>
</header>

<main>
{% if page == 'login' %}
  <div class="card login">
    <div class="hero"><h1>QUINIELA <b style="color:#e30613">MEDIAMARKERA</b></h1><div class="sub">Desde la Jornada 5 · 100.000 € por acierto</div></div>
    {% if error %}<div class="notice error">{{error}}</div>{% endif %}
    <form method="post">
      <label>Usuario</label><input name="username" value="RFM" required>
      <label>Contraseña</label><input name="password" type="password" required>
      <button class="red">Iniciar sesión</button>
    </form>
    <p class="muted">Contraseña inicial: <b>biwenger2026</b></p>
  </div>
{% else %}
  <div class="hero">
    <h1>Jornada {{round}}</h1>
    <div class="sub">Selecciona tu pronóstico · apuesta privada</div>
    <div class="pill">{{status}}</div>
  </div>

  {% if notice %}<div class="notice">{{notice}}</div>{% endif %}

  <div class="nav">
    {% if round > START_ROUND %}<a class="btn" href="?round={{round-1}}">← Jornada {{round-1}}</a>{% endif %}
    {% if round < 38 %}<a class="btn" href="?round={{round+1}}">Jornada {{round+1}} →</a>{% endif %}
    <a class="btn" href="{{url_for('my_bet')}}">📝 Mi apuesta</a>
    <a class="btn" href="{{url_for('summary')}}">📊 Resultados</a>
  </div>

  <form method="post" action="{{url_for('save_bet')}}">
  <input type="hidden" name="round" value="{{round}}">
  <div class="card">
  {% for m in matches %}
    <div class="match">
      <div class="num">{{loop.index}}</div>
      <div class="teams">{{m.home}}<small>{{m.away}}</small></div>
      <div>
        <div class="buttons">
          {% for p in ['1','X','2'] %}
          <button type="submit" name="pick_{{m.id}}" value="{{p}}" class="{{'active' if bets.get(m.id)==p else ''}}">{{p}}</button>
          {% endfor %}
        </div>
        {% if m.finished %}
          <div class="result {{'ok' if m.correct else 'bad'}}">
            {{m.score}} · {{'✓ Acierto' if m.correct else '✕ Fallo'}}
          </div>
        {% else %}
          <div class="result pending">{{m.score or 'Pendiente'}}</div>
        {% endif %}
      </div>
    </div>
  {% endfor %}
  </div>
  <p class="muted">Cada partido acertado suma <b>100.000 €</b> al premio acumulado.</p>
  </form>
{% endif %}
</main>

{% if page != 'login' %}
<footer>
<a href="{{url_for('home')}}">⚽ Jornada</a>
<a href="{{url_for('my_bet')}}">📝 Mi apuesta</a>
<a href="{{url_for('summary')}}">📊 Resumen</a>
<a href="{{url_for('logout')}}">↪ Salir</a>
</footer>
{% endif %}
</body></html>
"""

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
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def outcome(home, away):
    if home is None or away is None: return None
    if home > away: return "1"
    if home < away: return "2"
    return "X"

def api_fixtures(round_no):
    if not API_KEY:
        return []
    headers = {"x-apisports-key": API_KEY}
    params = {"league": LEAGUE_ID, "season": SEASON, "round": f"Regular Season - {round_no}"}
    try:
        r = requests.get(f"{API_URL}/fixtures", headers=headers, params=params, timeout=8)
        r.raise_for_status()
        data = r.json().get("response", [])
        matches = []
        for x in data:
            g = x["fixture"]
            h, a = x["teams"]["home"]["name"], x["teams"]["away"]["name"]
            hg = x["goals"]["home"]; ag = x["goals"]["away"]
            finished = x["fixture"]["status"]["short"] in {"FT","AET","PEN"}
            matches.append({
                "id": str(g["id"]), "home": h, "away": a,
                "home_goals": hg, "away_goals": ag, "finished": finished,
                "score": f"{hg}-{ag}" if hg is not None and ag is not None else "Pendiente",
                "correct": False
            })
        return matches
    except Exception:
        return []

def get_matches(round_no, bets):
    matches = api_fixtures(round_no)
    if not matches:
        # Fallback para que la interfaz siga funcionando mientras se configura la API.
        matches = [{"id": f"f{round_no}_{i}", "home": h, "away": a,
                    "home_goals": None, "away_goals": None, "finished": False,
                    "score": "Pendiente", "correct": False}
                   for i,(h,a) in enumerate(TEAMS_FALLBACK, 1)]
    for m in matches:
        m["correct"] = bool(m["finished"] and bets.get(m["id"]) == outcome(m["home_goals"], m["away_goals"]))
    return matches

@app.route("/logo.svg")
def logo():
    # Logo RFMF reproducido como SVG para no necesitar otro archivo.
    return """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
    <circle cx="50" cy="50" r="47" fill="white" stroke="#e30613" stroke-width="3"/>
    <text x="50" y="27" text-anchor="middle" font-family="Arial" font-size="8" font-weight="bold" fill="#e30613">REAL FEDERACIÓN</text>
    <text x="50" y="45" text-anchor="middle" font-family="Arial" font-size="24" font-weight="900" fill="#e30613">RF</text>
    <text x="50" y="67" text-anchor="middle" font-family="Arial" font-size="24" font-weight="900" fill="#e30613">MF</text>
    <text x="50" y="83" text-anchor="middle" font-family="Arial" font-size="7" font-weight="bold" fill="#e30613">MEDIAMARKERA DE FÚTBOL</text>
    </svg>"""

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username","RFM").strip()
        p = request.form.get("password","")
        if p == os.getenv("ADMIN_PASSWORD", "biwenger2026"):
            session["user"] = u
            return redirect(url_for("home"))
        return render_template_string(HTML,page="login",error="Contraseña incorrecta.")
    return render_template_string(HTML,page="login",error=None)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def home():
    round_no = max(START_ROUND, min(38, int(request.args.get("round", START_ROUND))))
    c=db()
    rows=c.execute("SELECT match_id,pick FROM bets WHERE username=? AND round=?",(session["user"],round_no)).fetchall()
    bets={r["match_id"]:r["pick"] for r in rows}
    matches=get_matches(round_no,bets)
    return render_template_string(HTML,page="home",round=round_no,matches=matches,bets=bets,
                                  status="ABIERTA",START_ROUND=START_ROUND,notice=None)

@app.route("/save", methods=["POST"])
@login_required
def save_bet():
    round_no=max(START_ROUND,min(38,int(request.form.get("round",START_ROUND))))
    c=db()
    for k,v in request.form.items():
        if k.startswith("pick_") and v in {"1","X","2"}:
            mid=k[5:]
            c.execute("INSERT OR REPLACE INTO bets(username,round,match_id,pick) VALUES(?,?,?,?)",
                      (session["user"],round_no,mid,v))
    c.commit()
    return redirect(url_for("home",round=round_no))

@app.route("/my-bet")
@login_required
def my_bet():
    return redirect(url_for("home",round=max(START_ROUND,int(request.args.get("round",START_ROUND)))))

@app.route("/summary")
@login_required
def summary():
    c=db()
    rows=c.execute("SELECT round,match_id,pick FROM bets WHERE username=? AND round>=? ORDER BY round,match_id",
                   (session["user"],START_ROUND)).fetchall()
    by_round={}
    for r in rows: by_round.setdefault(r["round"],{})[r["match_id"]]=r["pick"]
    total_hits=0; rounds=[]
    for rn,bets in by_round.items():
        ms=get_matches(rn,bets)
        hits=sum(1 for m in ms if m["correct"])
        total_hits+=hits
        rounds.append((rn,hits,hits*PRIZE_PER_HIT))
    total=total_hits*PRIZE_PER_HIT
    return render_template_string(HTML.replace(
        '{% else %}<div class="hero">','{% else %}<div class="hero">',1),
        page="summary",round=START_ROUND,matches=[],bets={},status="EN DIRECT",
        START_ROUND=START_ROUND,notice=f"Premio acumulado: {total:,} € · Aciertos: {total_hits}".replace(",", "."),
        session=session, rounds=rounds, total=total, total_hits=total_hits)

@app.route("/api/results")
@login_required
def results_api():
    rn=max(START_ROUND,min(38,int(request.args.get("round",START_ROUND))))
    c=db()
    rows=c.execute("SELECT match_id,pick FROM bets WHERE username=? AND round=?",(session["user"],rn)).fetchall()
    bets={r["match_id"]:r["pick"] for r in rows}
    matches=get_matches(rn,bets)
    hits=sum(1 for m in matches if m["correct"])
    return jsonify({"round":rn,"prize":hits*PRIZE_PER_HIT,"hits":hits,"matches":matches,
                    "updated_at":datetime.utcnow().isoformat()+"Z"})

if __name__ == "__main__":
    db()
    app.run(host="0.0.0.0",port=int(os.getenv("PORT","8080")))
