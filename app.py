import os
from flask import Flask, jsonify, render_template, request
import requests

app = Flask(__name__)

API_KEY = os.getenv("API_FOOTBALL_KEY", "")
LEAGUE_ID = 140
SEASON = int(os.getenv("FOOTBALL_SEASON", "2026"))
ROUND = os.getenv("FOOTBALL_ROUND", "Regular Season - 5")
PRIZE_PER_HIT = 100000

FALLBACK_MATCHES = [
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

def api_get(path, params):
    if not API_KEY:
        return None
    try:
        r = requests.get(
            f"https://v3.football.api-sports.io/{path}",
            headers={"x-apisports-key": API_KEY},
            params=params,
            timeout=8,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def load_matches():
    data = api_get("fixtures", {
        "league": LEAGUE_ID,
        "season": SEASON,
        "round": ROUND,
    })
    if data and data.get("response"):
        out = []
        for item in data["response"]:
            f = item["fixture"]
            h = item["teams"]["home"]
            a = item["teams"]["away"]
            out.append({
                "id": f["id"],
                "home": h["name"],
                "away": a["name"],
                "home_logo": h.get("logo"),
                "away_logo": a.get("logo"),
                "date": f["date"],
                "status": f["status"]["short"],
                "home_goals": item["goals"]["home"],
                "away_goals": item["goals"]["away"],
            })
        return out

    return [
        {
            "id": i + 1, "home": h, "away": a,
            "home_logo": None, "away_logo": None,
            "date": None, "status": "NS",
            "home_goals": None, "away_goals": None,
        }
        for i, (h, a) in enumerate(FALLBACK_MATCHES)
    ]

@app.get("/")
def index():
    return render_template("index.html", prize=PRIZE_PER_HIT)

@app.get("/api/matches")
def matches():
    return jsonify({
        "jornada": 5,
        "prize_per_hit": PRIZE_PER_HIT,
        "matches": load_matches(),
    })

@app.post("/api/check")
def check():
    payload = request.get_json(silent=True) or {}
    predictions = payload.get("predictions", {})
    matches = load_matches()
    results = []
    hits = 0

    for i, m in enumerate(matches):
        prediction = predictions.get(str(i + 1))
        actual = None
        if m["home_goals"] is not None and m["away_goals"] is not None:
            actual = (
                "1" if m["home_goals"] > m["away_goals"]
                else "2" if m["home_goals"] < m["away_goals"]
                else "X"
            )
        hit = actual is not None and prediction == actual
        if hit:
            hits += 1
        results.append({
            "number": i + 1,
            "prediction": prediction,
            "actual": actual,
            "hit": hit if actual else None,
        })

    return jsonify({
        "hits": hits,
        "prize": hits * PRIZE_PER_HIT,
        "results": results,
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
