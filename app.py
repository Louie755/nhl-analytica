import pandas as pd
from flask import Flask, render_template_string, jsonify, request
import requests
import os
from datetime import datetime

app = Flask(__name__)

# [유지] 팀 데이터 및 컬러 설정
TEAM_MAP = {"ANA": "Anaheim Ducks", "BOS": "Boston Bruins", "BUF": "Buffalo Sabres", "CGY": "Calgary Flames", "CAR": "Carolina Hurricanes", "CHI": "Chicago Blackhawks", "COL": "Colorado Avalanche", "CBJ": "Columbus Blue Jackets", "DAL": "Dallas Stars", "DET": "Detroit Red Wings", "EDM": "Edmonton Oilers", "FLA": "Florida Panthers", "LAK": "Los Angeles Kings", "MIN": "Minnesota Wild", "MTL": "Montreal Canadiens", "NSH": "Nashville Predators", "NJD": "New Jersey Devils", "NYI": "New York Islanders", "NYR": "New York Rangers", "OTT": "Ottawa Senators", "PHI": "Philadelphia Flyers", "PIT": "Pittsburgh Penguins", "SJS": "San Jose Sharks", "SEA": "Seattle Kraken", "STL": "St Louis Blues", "TBL": "Tampa Bay Lightning", "TOR": "Toronto Maple Leafs", "UTA": "Utah Hockey Club", "VAN": "Vancouver Canucks", "VGK": "Vegas Golden Knights", "WSH": "Washington Capitals", "WPG": "Winnipeg Jets"}
TEAM_COLORS = {"ANA": "#F47A38", "BOS": "#FFB81C", "BUF": "#002654", "CGY": "#C8102E", "CAR": "#CE1126", "CHI": "#CF0A2C", "COL": "#6F263D", "CBJ": "#002654", "DAL": "#006847", "DET": "#CE1126", "EDM": "#FF4C00", "FLA": "#041E42", "LAK": "#111111", "MIN": "#154734", "MTL": "#AF1E2D", "NSH": "#FFB81C", "NJD": "#CE1126", "NYI": "#00539B", "NYR": "#0038A8", "OTT": "#C8102E", "PHI": "#F74902", "PIT": "#FCB514", "SJS": "#006D75", "SEA": "#001628", "STL": "#002F87", "TBL": "#002868", "TOR": "#00205B", "UTA": "#71AFE2", "VAN": "#00205B", "VGK": "#B4975A", "WSH": "#041E42", "WPG": "#004C97"}

def fetch_nhl_safe(url, season, game_type, sort_prop):
    all_data = []
    start, limit = 0, 100
    while True:
        # game_type: 2(Regular), 3(Playoffs)
        params = {
            "isAggregate": "false", 
            "isGame": "false", 
            "sort": f'[{{"property":"{sort_prop}","direction":"DESC"}}]', 
            "start": start, 
            "limit": limit, 
            "cayenneExp": f"seasonId={season} and gameTypeId={game_type}"
        }
        try:
            r = requests.get(url, params=params, timeout=10)
            data = r.json().get('data', [])
            if not data: break
            all_data.extend(data)
            if len(data) < limit: break
            start += limit
        except: break
    return all_data

def get_today_scorers():
    scorer_ids = set()
    try:
        r = requests.get("https://api-web.nhle.com/v1/score/now", timeout=10)
        games = r.json().get('games', [])
        for game in games:
            for goal in game.get('goals', []):
                sid = goal.get('playerId')
                if sid: scorer_ids.add(str(sid))
    except: pass
    return scorer_ids

@app.route('/api/data')
def get_nhl_data():
    now = datetime.now()
    # [자동화] 현재 날짜 기준으로 시즌 자동 계산
    auto_season = f"{now.year}{now.year + 1}" if now.month >= 9 else f"{now.year - 1}{now.year}"
    
    # 유저 선택값 가져오기 (없으면 자동 계산된 시즌과 정규시즌)
    season = request.args.get('season', auto_season)
    game_type = request.args.get('game_type', '2') 
    
    ts = int(now.timestamp())
    s_raw = fetch_nhl_safe(f"https://api.nhle.com/stats/rest/en/skater/summary?t={ts}", season, game_type, "points")
    g_raw = fetch_nhl_safe(f"https://api.nhle.com/stats/rest/en/goalie/summary?t={ts}", season, game_type, "wins")
    today_scorers = get_today_scorers()
    
    # 스케이터/골리 처리 로직 (기존 IR 계산 유지)
    skaters = []
    skater_dict = {}
    for p in s_raw:
        pid = str(p.get('playerId'))
        if pid not in skater_dict:
            skater_dict[pid] = {"id": pid, "name": p.get('skaterFullName'), "abbr": str(p.get('teamAbbrev', '')).upper(), "pos": p.get('positionCode'), "gp": 0, "g": 0, "a": 0, "pts": 0, "sh": 0, "pm": 0}
        t = skater_dict[pid]
        t["gp"] += p.get('gamesPlayed', 0); t["g"] += p.get('goals', 0); t["a"] += p.get('assists', 0); t["pts"] += p.get('points', 0); t["sh"] += p.get('shots', 0); t["pm"] += p.get('plusMinus', 0)

    for pid, p in skater_dict.items():
        gp = max(1, p["gp"]); ppg = round(p["pts"]/gp, 2)
        ir = min(99.9, round((ppg * 40) + ((p["pts"]/max(1, p["sh"]))*25) + (max(0, p["pm"]+10)/2) + (gp/10), 1))
        skaters.append({**p, "type": "skater", "ppg": ppg, "ir": ir, "team": TEAM_MAP.get(p["abbr"], p["abbr"]), "prob": min(round(((p["g"]/gp)*50 + (p["sh"]/gp)*10), 1), 95.0), "trending": pid in today_scorers, "col": TEAM_COLORS.get(p["abbr"], "#38bdf8")})

    goalies = []
    goalie_dict = {}
    for p in g_raw:
        pid = str(p.get('playerId'))
        if pid not in goalie_dict:
            goalie_dict[pid] = {"id": pid, "name": p.get('goalieFullName'), "abbr": str(p.get('teamAbbrev', '')).upper(), "pos": "G", "gp": 0, "w": 0, "so": 0, "ga": 0, "sa": 0}
        t = goalie_dict[pid]
        t["gp"] += p.get('gamesPlayed', 0); t["w"] += p.get('wins', 0); t["so"] += p.get('shutouts', 0); t["ga"] += p.get('goalsAgainst', 0); t["sa"] += p.get('shotsAgainst', 0)

    for pid, p in goalie_dict.items():
        gp = max(1, p["gp"]); sv_val = round((1 - (p["ga"]/max(1, p["sa"]))) * 100, 1) if p["sa"] > 0 else 0.0
        gaa = round(p["ga"]/gp, 2); ir = min(99.9, round((p["w"]/gp * 40) + (sv_val - 85) * 4 + (5 - gaa) * 2, 1))
        goalies.append({**p, "type": "goalie", "sv": sv_val, "gaa": gaa, "ir": ir, "team": TEAM_MAP.get(p["abbr"], p["abbr"]), "trending": pid in today_scorers, "col": TEAM_COLORS.get(p["abbr"], "#38bdf8")})
        
    return jsonify({"skaters": skaters, "goalies": goalies})

@app.route('/')
def nhl_dashboard_main():
    now = datetime.now()
    auto_season = f"{now.year}{now.year + 1}" if now.month >= 9 else f"{now.year - 1}{now.year}"
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8"><title>NHL ANALYTICA | Data Insights</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&family=Syncopate:wght@700&display=swap" rel="stylesheet">
        <style>
            :root { --accent: #38bdf8; --bg: #030712; --card: rgba(31, 41, 55, 0.45); }
            body { background: var(--bg); color: white; font-family: 'Inter', sans-serif; margin: 0; }
            header { padding: 15px 5%; background: rgba(3,7,18,0.9); border-bottom: 1px solid rgba(255,255,255,0.1); display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 1000; backdrop-filter: blur(15px); }
            .logo { font-family: 'Syncopate'; color: var(--accent); font-size: 1.3rem; text-decoration: none; display: flex; align-items: center; gap: 10px; }
            
            /* Glassmorphism 필터 섹션 */
            .filter-bar { display: flex; gap: 15px; align-items: center; background: rgba(255,255,255,0.05); padding: 10px 20px; border-radius: 50px; border: 1px solid rgba(255,255,255,0.1); }
            select { background: transparent; color: white; border: none; outline: none; cursor: pointer; font-weight: 700; font-size: 0.85rem; }
            select option { background: #0f172a; color: white; }

            .nav-tabs { display: flex; justify-content: center; gap: 40px; padding: 20px 0; background: rgba(255,255,255,0.02); }
            .tab-btn { font-family: 'Syncopate'; font-size: 0.8rem; cursor: pointer; color: #64748b; border: none; background: none; transition: 0.3s; padding-bottom: 5px; }
            .tab-btn.active { color: var(--accent); border-bottom: 2px solid var(--accent); }
            
            .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px; padding: 20px 5%; }
            .card { background: var(--card); border-radius: 15px; padding: 15px; cursor: pointer; border: 1px solid rgba(255,255,255,0.05); transition: 0.3s; position: relative; overflow: hidden; }
            .card:hover { transform: translateY(-5px); border-color: var(--accent); background: rgba(31, 41, 55, 0.6); }
            .card::before { content: ""; position: absolute; top: 0; left: 0; width: 4px; height: 100%; background: var(--t-color); }

            .modal { display:none; position:fixed; z-index:2000; left:0; top:0; width:100%; height:100%; background:rgba(2, 6, 23, 0.98); backdrop-filter:blur(20px); }
            .modal-box { background: #0b1426; width: 900px; max-width: 95%; margin: 5vh auto; border-radius: 20px; border: 1px solid #1f3a52; display: grid; grid-template-columns: 1fr 1fr; overflow: hidden; }
            .m-left { padding: 30px; border-right: 1px solid rgba(255,255,255,0.05); text-align: center; }
            .m-right { padding: 30px; display: flex; align-items: center; justify-content: center; background: rgba(0,0,0,0.2); }
            
            .stat-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 20px 0; }
            .stat-box { background: rgba(255,255,255,0.05); padding: 12px; border-radius: 10px; }
            .stat-box small { font-size: 0.6rem; color: #94a3b8; display: block; margin-bottom: 5px; }
            .stat-box b { font-size: 1.1rem; color: var(--accent); }
            
            #loading { position: fixed; inset: 0; background: var(--bg); display: flex; flex-direction: column; justify-content: center; align-items: center; z-index: 9999; }
            .trend-up { color: #10b981; margin-left: 5px; font-size: 0.8rem; }
            .search-input { background: transparent; border: none; color: white; width: 150px; outline: none; font-size: 0.9rem; }
        </style>
    </head>
    <body>
        <div id="loading"><h2 style="font-family:'Syncopate'; letter-spacing:4px;">SYNCING LIVE DATA...</h2></div>
        
        <header>
            <a href="/" class="logo">NHL ANALYTICA</a>
            <div class="filter-bar">
                <input type="text" id="pSearch" class="search-input" placeholder="Search Player..." oninput="render()">
                <div style="width:1px; height:20px; background:rgba(255,255,255,0.2);"></div>
                <select id="seasonSelect" onchange="init()">
                    <option value="{{auto_season}}">CURRENT SEASON</option>
                    <option value="20242025">2024-2025</option>
                    <option value="20232024">2023-2024</option>
                </select>
                <select id="typeSelect" onchange="init()">
                    <option value="2">REGULAR SEASON</option>
                    <option value="3">PLAYOFFS 🏆</option>
                </select>
            </div>
        </header>

        <div class="nav-tabs">
            <button class="tab-btn active" id="skater-tab" onclick="switchTab('skater')">SKATERS</button>
            <button class="tab-btn" id="goalie-tab" onclick="switchTab('goalie')">GOALIES</button>
        </div>

        <div class="grid" id="main-grid"></div>

        <div id="modal" class="modal" onclick="this.style.display='none'">
            <div class="modal-box" onclick="event.stopPropagation()">
                <div class="m-left" id="mInfo"></div>
                <div class="m-right"><canvas id="radar"></canvas></div>
            </div>
        </div>

        <script>
            let skaters = []; let goalies = [];
            let currentTab = 'skater'; let chartInstance = null;

            async function init() {
                document.getElementById('loading').style.display = 'flex';
                const s = document.getElementById('seasonSelect').value;
                const g = document.getElementById('typeSelect').value;
                try {
                    const res = await fetch(`/api/data?season=${s}&game_type=${g}&t=${Date.now()}`);
                    const data = await res.json();
                    skaters = data.skaters; goalies = data.goalies;
                    document.getElementById('loading').style.display = 'none';
                    render();
                } catch (e) { console.error(e); }
            }

            function switchTab(tab) {
                currentTab = tab;
                document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
                document.getElementById(tab + '-tab').classList.add('active');
                render();
            }

            function render() {
                const query = document.getElementById('pSearch').value.toLowerCase();
                const grid = document.getElementById('main-grid');
                const data = currentTab === 'skater' ? skaters : goalies;
                const filtered = data.filter(p => p.name.toLowerCase().includes(query));
                
                grid.innerHTML = filtered.slice(0, 50).map(p => `
                    <div class="card" onclick="openModal('${p.id}', '${p.type}')" style="--t-color:${p.col}">
                        <div style="display:flex; align-items:center; gap:12px;">
                            <img src="https://assets.nhle.com/mugs/nhl/latest/${p.id}.png" style="width:50px; border-radius:50%; background:#000;" onerror="this.src='https://assets.nhle.com/logos/nhl/svg/${p.abbr}_light.svg'">
                            <div>
                                <div style="font-weight:900; font-size:0.95rem;">${p.name}</div>
                                <small style="color:#64748b; font-size:0.75rem;">${p.abbr} • ${p.pos}</small>
                            </div>
                            <div style="margin-left:auto; text-align:right;">
                                <div style="color:var(--accent); font-weight:900;">${currentTab==='skater'?p.pts:p.w}${p.trending?'<span class="trend-up">▲</span>':''}</div>
                                <small style="font-size:0.6rem; color:#475569;">${currentTab==='skater'?'PTS':'WINS'}</small>
                            </div>
                        </div>
                    </div>
                `).join('');
            }

            function openModal(id, type) {
                const data = type === 'skater' ? skaters : goalies;
                const p = data.find(x => x.id === id);
                
                let statsHtml = type === 'skater' ? 
                    `<div class="stat-box"><small>GP</small><b>${p.gp}</b></div><div class="stat-box"><small>PPG</small><b>${p.ppg}</b></div><div class="stat-box"><small>IR</small><b>${p.ir}</b></div>` :
                    `<div class="stat-box"><small>GP</small><b>${p.gp}</b></div><div class="stat-box"><small>SV%</small><b>${p.sv}%</b></div><div class="stat-box"><small>IR</small><b>${p.ir}</b></div>`;

                document.getElementById('mInfo').innerHTML = `
                    <img src="https://assets.nhle.com/mugs/nhl/latest/${p.id}.png" style="width:120px; border-radius:50%; border:3px solid ${p.col};">
                    <h2 style="font-family:'Syncopate'; margin:15px 0 5px;">${p.name}</h2>
                    <div style="color:${p.col}; font-weight:800; font-size:0.9rem; margin-bottom:20px;">${p.team}</div>
                    <div class="stat-grid">${statsHtml}</div>
                    <div style="background:rgba(255,255,255,0.03); padding:15px; border-radius:10px; margin-top:15px;">
                        <small style="color:#94a3b8; font-weight:800; font-size:0.6rem;">${type==='skater'?'GOAL PROBABILITY':'SHUTOUTS'}</small>
                        <div style="font-size:1.5rem; font-weight:900; color:#fbbf24;">${type==='skater'?p.prob+'%':p.so}</div>
                    </div>
                `;
                document.getElementById('modal').style.display = 'block';
                drawRadar(p);
            }

            function drawRadar(p) {
                const ctx = document.getElementById('radar').getContext('2d');
                if(chartInstance) chartInstance.destroy();
                let chartData = p.type === 'skater' ? 
                    [Math.min(100, (p.g/(p.gp||1))*200), Math.min(100, (p.a/(p.gp||1))*150), Math.min(100, (p.pts/Math.max(1, p.sh))*500), Math.min(100, (p.sh/(p.gp||1))*30), 80] :
                    [Math.min(100, (p.w/Math.max(1, p.gp))*150), Math.min(100, (p.sv/100)*105), Math.min(100, (3.5-p.gaa)*40+20), Math.min(100, p.so*25), 50];
                
                chartInstance = new Chart(ctx, {
                    type: 'radar',
                    data: {
                        labels: ['Scoring', 'Playmaking', 'Efficiency', 'Shot Vol.', 'Def.'],
                        datasets: [{ data: chartData, backgroundColor: 'rgba(56, 189, 248, 0.2)', borderColor: '#38bdf8', borderWidth: 2, pointRadius: 0 }]
                    },
                    options: { scales: { r: { grid: { color: '#1e293b' }, angleLines: { color: '#1e293b' }, ticks: { display: false }, pointLabels: { color: '#94a3b8' } } }, plugins: { legend: { display: false } } }
                });
            }
            init();
        </script>
    </body>
    </html>
    """)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
