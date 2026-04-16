import pandas as pd
from flask import Flask, render_template_string, jsonify, request
import requests
import os
from datetime import datetime

app = Flask(__name__)

# [유지] 팀/색상 데이터
TEAM_MAP = {"ANA": "Anaheim Ducks", "BOS": "Boston Bruins", "BUF": "Buffalo Sabres", "CGY": "Calgary Flames", "CAR": "Carolina Hurricanes", "CHI": "Chicago Blackhawks", "COL": "Colorado Avalanche", "CBJ": "Columbus Blue Jackets", "DAL": "Dallas Stars", "DET": "Detroit Red Wings", "EDM": "Edmonton Oilers", "FLA": "Florida Panthers", "LAK": "Los Angeles Kings", "MIN": "Minnesota Wild", "MTL": "Montreal Canadiens", "NSH": "Nashville Predators", "NJD": "New Jersey Devils", "NYI": "New York Islanders", "NYR": "New York Rangers", "OTT": "Ottawa Senators", "PHI": "Philadelphia Flyers", "PIT": "Pittsburgh Penguins", "SJS": "San Jose Sharks", "SEA": "Seattle Kraken", "STL": "St Louis Blues", "TBL": "Tampa Bay Lightning", "TOR": "Toronto Maple Leafs", "UTA": "Utah Hockey Club", "VAN": "Vancouver Canucks", "VGK": "Vegas Golden Knights", "WSH": "Washington Capitals", "WPG": "Winnipeg Jets"}
TEAM_COLORS = {"ANA": "#F47A38", "BOS": "#FFB81C", "BUF": "#002654", "CGY": "#C8102E", "CAR": "#CE1126", "CHI": "#CF0A2C", "COL": "#6F263D", "CBJ": "#002654", "DAL": "#006847", "DET": "#CE1126", "EDM": "#FF4C00", "FLA": "#041E42", "LAK": "#111111", "MIN": "#154734", "MTL": "#AF1E2D", "NSH": "#FFB81C", "NJD": "#CE1126", "NYI": "#00539B", "NYR": "#0038A8", "OTT": "#C8102E", "PHI": "#F74902", "PIT": "#FCB514", "SJS": "#006D75", "SEA": "#001628", "STL": "#002F87", "TBL": "#002868", "TOR": "#00205B", "UTA": "#71AFE2", "VAN": "#00205B", "VGK": "#B4975A", "WSH": "#041E42", "WPG": "#004C97"}

def fetch_nhl_safe(url, season, game_type):
    all_data = []
    start, limit = 0, 100
    while True:
        params = {"isAggregate": "false", "isGame": "false", "sort": '[{"property":"points","direction":"DESC"}]', "start": start, "limit": limit, "cayenneExp": f"seasonId={season} and gameTypeId={game_type}"}
        try:
            r = requests.get(url, params=params, timeout=10)
            data = r.json().get('data', [])
            if not data: break
            all_data.extend(data)
            if len(data) < limit: break
            start += limit
        except: break
    return all_data

@app.route('/api/data')
def get_nhl_data():
    # Louie님 말씀대로 기본값은 25-26 시즌!
    season = request.args.get('season', '20252026')
    game_type = request.args.get('game_type', '2')
    
    # 1차 시도: 25-26 데이터 긁기
    s_raw = fetch_nhl_safe("https://api.nhle.com/stats/rest/en/skater/summary", season, game_type)
    
    # [핵심 로직] 만약 25-26 데이터가 없으면, 사진 속 그 데이터(24-25)를 자동으로 가져옴
    if not s_raw and season == '20252026':
        season = '20242025'
        s_raw = fetch_nhl_safe("https://api.nhle.com/stats/rest/en/skater/summary", season, game_type)
        g_raw = fetch_nhl_safe("https://api.nhle.com/stats/rest/en/goalie/summary", season, game_type)
    else:
        g_raw = fetch_nhl_safe("https://api.nhle.com/stats/rest/en/goalie/summary", season, game_type)

    skaters = []
    for p in s_raw:
        gp = max(1, p.get('gamesPlayed', 0)); pts = p.get('points', 0); ppg = round(pts/gp, 2)
        ir = min(99.9, round((ppg * 40) + ((pts/max(1, p.get('shots', 0)))*25) + (max(0, p.get('plusMinus', 0)+10)/2), 1))
        skaters.append({**p, "id": p.get('playerId'), "name": p.get('skaterFullName'), "abbr": str(p.get('teamAbbrev','')).upper(), "pos": p.get('positionCode'), "pts": pts, "ppg": ppg, "ir": ir, "col": TEAM_COLORS.get(p.get('teamAbbrev'), "#38bdf8")})

    goalies = []
    for p in g_raw:
        gp = max(1, p.get('gamesPlayed', 0)); sv = round(p.get('savePct', 0)*100, 1)
        ir = min(99.9, round((p.get('wins', 0)/gp * 40) + (sv - 85) * 4, 1))
        goalies.append({"id": p.get('playerId'), "name": p.get('goalieFullName'), "abbr": str(p.get('teamAbbrev','')).upper(), "w": p.get('wins', 0), "sv": sv, "ir": ir, "col": TEAM_COLORS.get(p.get('teamAbbrev'), "#38bdf8")})
        
    return jsonify({"skaters": skaters, "goalies": goalies})

@app.route('/')
def nhl_dashboard_main():
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8"><title>NHL ANALYTICA</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&family=Syncopate:wght@700&display=swap" rel="stylesheet">
        <style>
            :root { --accent: #38bdf8; --bg: #030712; --card: rgba(31, 41, 55, 0.45); }
            body { background: #030712; color: white; font-family: 'Inter', sans-serif; margin: 0; }
            header { padding: 20px 5%; background: rgba(3,7,18,0.95); border-bottom: 1px solid rgba(255,255,255,0.1); display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 1000; backdrop-filter: blur(10px); }
            .logo { font-family: 'Syncopate'; color: var(--accent); font-size: 1.5rem; text-decoration: none; }
            .header-right { display: flex; align-items: center; gap: 12px; }
            .select-style { background: rgba(255,255,255,0.05); color: white; border: 1px solid rgba(255,255,255,0.2); border-radius: 8px; padding: 10px; font-size: 0.8rem; cursor: pointer; }
            .search-box { background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2); padding: 10px 15px; border-radius: 12px; color: white; width: 180px; }
            .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px; padding: 30px 5%; }
            .card { background: var(--card); border-radius: 20px; padding: 20px; border: 1px solid rgba(255,255,255,0.05); display: flex; align-items: center; gap: 15px; position: relative; }
            .card::before { content: ""; position: absolute; left: 0; width: 4px; height: 60%; background: var(--t-color); border-radius: 0 4px 4px 0; }
            #loading { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: #030712; display: flex; justify-content: center; align-items: center; z-index: 9999; color: var(--accent); font-family: 'Syncopate'; }
        </style>
    </head>
    <body>
        <div id="loading"><h1>SYNCING 2025-2026 DATA...</h1></div>
        <header>
            <a href="/" class="logo">NHL ANALYTICA</a>
            <div class="header-right">
                <select id="seasonSelect" class="select-style" onchange="init()">
                    <option value="20252026">Current Season (25-26)</option>
                    <option value="20242025">2024-2025</option>
                    <option value="20232024">2023-2024</option>
                </select>
                <select id="typeSelect" class="select-style" onchange="init()">
                    <option value="2">Regular Season</option>
                    <option value="3">Playoffs 🏆</option>
                </select>
                <input type="text" id="pSearch" class="search-box" placeholder="Search..." oninput="render()">
            </div>
        </header>
        <div class="grid" id="main-grid"></div>
        <script>
            let skaters = [];
            async function init() {
                document.getElementById('loading').style.display = 'flex';
                const s = document.getElementById('seasonSelect').value;
                const g = document.getElementById('typeSelect').value;
                const res = await fetch(`/api/data?season=${s}&game_type=${g}`);
                const data = await res.json();
                skaters = data.skaters;
                document.getElementById('loading').style.display = 'none';
                render();
            }
            function render() {
                const grid = document.getElementById('main-grid');
                const query = document.getElementById('pSearch').value.toLowerCase();
                grid.innerHTML = skaters.filter(p => p.name.toLowerCase().includes(query)).map(p => `
                    <div class="card" style="--t-color:${p.col}">
                        <img src="https://assets.nhle.com/mugs/nhl/latest/${p.id}.png" style="width:60px; border-radius:50%;" onerror="this.src='https://assets.nhle.com/logos/nhl/svg/${p.abbr}_light.svg'">
                        <div><h3 style="margin:0;">${p.name}</h3><small>${p.abbr} • ${p.pos} • PPG ${p.ppg}</small></div>
                        <div style="margin-left:auto; text-align:right;"><b style="color:var(--accent); font-size:1.2rem;">${p.pts}</b><br><small>PTS</small></div>
                    </div>
                `).join('');
            }
            init();
        </script>
    </body>
    </html>
    """)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
