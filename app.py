import pandas as pd
from flask import Flask, render_template_string, jsonify, request
import requests
import os
from datetime import datetime

app = Flask(__name__)

# [유지] 기존 팀 데이터 및 컬러 설정 그대로
TEAM_MAP = {"ANA": "Anaheim Ducks", "BOS": "Boston Bruins", "BUF": "Buffalo Sabres", "CGY": "Calgary Flames", "CAR": "Carolina Hurricanes", "CHI": "Chicago Blackhawks", "COL": "Colorado Avalanche", "CBJ": "Columbus Blue Jackets", "DAL": "Dallas Stars", "DET": "Detroit Red Wings", "EDM": "Edmonton Oilers", "FLA": "Florida Panthers", "LAK": "Los Angeles Kings", "MIN": "Minnesota Wild", "MTL": "Montreal Canadiens", "NSH": "Nashville Predators", "NJD": "New Jersey Devils", "NYI": "New York Islanders", "NYR": "New York Rangers", "OTT": "Ottawa Senators", "PHI": "Philadelphia Flyers", "PIT": "Pittsburgh Penguins", "SJS": "San Jose Sharks", "SEA": "Seattle Kraken", "STL": "St Louis Blues", "TBL": "Tampa Bay Lightning", "TOR": "Toronto Maple Leafs", "UTA": "Utah Hockey Club", "VAN": "Vancouver Canucks", "VGK": "Vegas Golden Knights", "WSH": "Washington Capitals", "WPG": "Winnipeg Jets"}
TEAM_COLORS = {"ANA": "#F47A38", "BOS": "#FFB81C", "BUF": "#002654", "CGY": "#C8102E", "CAR": "#CE1126", "CHI": "#CF0A2C", "COL": "#6F263D", "CBJ": "#002654", "DAL": "#006847", "DET": "#CE1126", "EDM": "#FF4C00", "FLA": "#041E42", "LAK": "#111111", "MIN": "#154734", "MTL": "#AF1E2D", "NSH": "#FFB81C", "NJD": "#CE1126", "NYI": "#00539B", "NYR": "#0038A8", "OTT": "#C8102E", "PHI": "#F74902", "PIT": "#FCB514", "SJS": "#006D75", "SEA": "#001628", "STL": "#002F87", "TBL": "#002868", "TOR": "#00205B", "UTA": "#71AFE2", "VAN": "#00205B", "VGK": "#B4975A", "WSH": "#041E42", "WPG": "#004C97"}

# [수정] game_type 파라미터 추가
def fetch_nhl_safe(url, season, game_type, sort_prop):
    all_data = []
    start, limit = 0, 100
    while True:
        params = {"isAggregate": "false", "isGame": "false", "sort": f'[{{"property":"{sort_prop}","direction":"DESC"}}]', "start": start, "limit": limit, "cayenneExp": f"seasonId={season} and gameTypeId={game_type}"}
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
    # [자동화] 매 시즌 알아서 연도 계산
    auto_season = f"{now.year}{now.year + 1}" if now.month >= 9 else f"{now.year - 1}{now.year}"
    
    # [추가] 드랍다운 선택값 받기
    season = request.args.get('season', auto_season)
    game_type = request.args.get('game_type', '2')
    
    ts = int(now.timestamp())
    s_raw = fetch_nhl_safe(f"https://api.nhle.com/stats/rest/en/skater/summary?t={ts}", season, game_type, "points")
    g_raw = fetch_nhl_safe(f"https://api.nhle.com/stats/rest/en/goalie/summary?t={ts}", season, game_type, "wins")
    today_scorers = get_today_scorers()
    
    # [유지] 기존 스케이터/골리 데이터 가공 로직 그대로
    skater_dict = {}
    for p in s_raw:
        pid = str(p.get('playerId'))
        if pid not in skater_dict:
            skater_dict[pid] = {"id": pid, "name": p.get('skaterFullName'), "type": "skater", "abbr": str(p.get('teamAbbrev', '')).upper(), "pos": p.get('positionCode'), "gp": 0, "g": 0, "a": 0, "pts": 0, "sh": 0, "pm": 0}
        t = skater_dict[pid]
        t["gp"] += p.get('gamesPlayed', 0); t["g"] += p.get('goals', 0); t["a"] += p.get('assists', 0); t["pts"] += p.get('points', 0); t["sh"] += p.get('shots', 0); t["pm"] += p.get('plusMinus', 0)

    skaters = []
    for pid, p in skater_dict.items():
        gp = max(1, p["gp"]); ppg = round(p["pts"]/gp, 2)
        ir = min(99.9, round((ppg * 40) + ((p["pts"]/max(1, p["sh"]))*25) + (max(0, p["pm"]+10)/2) + (gp/10), 1))
        skaters.append({**p, "ppg": ppg, "ir": ir, "team": TEAM_MAP.get(p["abbr"], p["abbr"]), "prob": min(round(((p["g"]/gp)*50 + (p["sh"]/gp)*10), 1), 95.0), "trending": pid in today_scorers, "col": TEAM_COLORS.get(p["abbr"], "#38bdf8")})

    goalie_dict = {}
    for p in g_raw:
        pid = str(p.get('playerId'))
        if pid not in goalie_dict:
            goalie_dict[pid] = {"id": pid, "name": p.get('goalieFullName'), "type": "goalie", "abbr": str(p.get('teamAbbrev', '')).upper(), "pos": "G", "gp": 0, "w": 0, "so": 0, "ga": 0, "sa": 0}
        t = goalie_dict[pid]
        t["gp"] += p.get('gamesPlayed', 0); t["w"] += p.get('wins', 0); t["so"] += p.get('shutouts', 0); t["ga"] += p.get('goalsAgainst', 0); t["sa"] += p.get('shotsAgainst', 0)

    goalies = []
    for pid, p in goalie_dict.items():
        gp = max(1, p["gp"]); sv_val = round((1 - (p["ga"]/max(1, p["sa"]))) * 100, 1) if p["sa"] > 0 else 0.0
        gaa = round(p["ga"]/gp, 2); ir = min(99.9, round((p["w"]/gp * 40) + (sv_val - 85) * 4 + (5 - gaa) * 2, 1))
        goalies.append({**p, "sv": sv_val, "gaa": gaa, "ir": ir, "team": TEAM_MAP.get(p["abbr"], p["abbr"]), "trending": pid in today_scorers, "col": TEAM_COLORS.get(p["abbr"], "#38bdf8")})
        
    return jsonify({"skaters": skaters, "goalies": goalies})

@app.route('/')
def nhl_dashboard_main():
    now = datetime.now()
    auto_season = f"{now.year}{now.year + 1}" if now.month >= 9 else f"{now.year - 1}{now.year}"
    # [유지] 기존 HTML 스타일 및 레이아웃 그대로, 드랍다운만 헤더에 추가
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8"><title>NHL ANALYTICA</title>
        <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'><path d='M21,16.5C21,16.88 20.79,17.21 20.47,17.38L12.57,21.82C12.41,21.94 12.21,22 12,22C11.79,22 11.59,21.94 11.43,21.82L3.53,17.38C3.21,17.21 3,16.88 3,16.5V7.5C3,7.12 3.21,6.79 3.53,6.62L11.43,2.18C11.59,2.06 11.79,2 12,2C12.21,2 12.41,2.06 12.57,2.18L20.47,6.62C20.79,6.79 21,7.12 21,7.5V16.5Z' fill='none' stroke='%2338bdf8' stroke-width='1.5'/><path d='M12,22V12 L20.47,7.38 M12,12L3.53,7.38' stroke='%2338bdf8' stroke-width='1.2'/><path d='M18,15V11.5' stroke='%23fff' stroke-width='1.8' stroke-linecap='round'/><path d='M15,15V13' stroke='%23fff' stroke-width='1.8' stroke-linecap='round'/><path d='M12,15V12.5' stroke='%23fff' stroke-width='1.8' stroke-linecap='round'/></svg>" type="image/svg+xml">
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&family=Syncopate:wght@700&display=swap" rel="stylesheet">
        <style>
            :root { --accent: #38bdf8; --bg: #030712; --card: rgba(31, 41, 55, 0.45); }
            body { background: #030712; color: white; font-family: 'Inter', sans-serif; margin: 0; overflow-x: hidden; }
            header { padding: 20px 5%; background: rgba(3,7,18,0.95); border-bottom: 1px solid rgba(255,255,255,0.1); display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 1000; backdrop-filter: blur(10px); }
            .logo { display: flex; align-items: center; gap: 12px; font-family: 'Syncopate'; color: var(--accent); font-size: 1.5rem; text-decoration: none; }
            .logo svg { width: 38px; height: 38px; }
            
            /* [유지] 기존 스타일들 */
            .search-box { background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2); padding: 12px 20px; border-radius: 12px; color: white; width: 250px; outline: none; }
            .nav-tabs { display: flex; justify-content: center; gap: 40px; padding: 20px 0; background: rgba(255,255,255,0.02); }
            .tab-btn { font-family: 'Syncopate'; font-size: 0.9rem; cursor: pointer; color: #64748b; border: none; background: none; outline:none; padding-bottom: 8px; transition: 0.3s; }
            .tab-btn.active { color: var(--accent); border-bottom: 2px solid var(--accent); }
            .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px; padding: 30px 5%; min-height: 80vh; }
            .card { background: var(--card); border-radius: 20px; padding: 20px; cursor: pointer; border: 1px solid rgba(255,255,255,0.05); transition: 0.3s; position: relative; }
            .card:hover { transform: translateY(-5px); border-color: var(--accent); }
            .card::before { content: ""; position: absolute; top: 0; left: 0; width: 4px; height: 100%; background: var(--t-color); border-radius: 20px 0 0 20px; }
            
            /* [추가] 드랍다운 전용 스타일 (Glassmorphism 유지) */
            .dropdown-group { display: flex; gap: 10px; margin-right: 20px; }
            .select-style { background: rgba(255,255,255,0.05); color: white; border: 1px solid rgba(255,255,255,0.2); border-radius: 8px; padding: 8px; outline: none; cursor: pointer; font-size: 0.8rem; }
            
            .modal { display:none; position:fixed; z-index:2000; left:0; top:0; width:100%; height:100%; background:rgba(2, 6, 23, 0.95); backdrop-filter:blur(10px); }
            .modal-box { background: #0b1426; width: 950px; max-width: 95%; margin: 8vh auto; border-radius: 25px; border: 1px solid #1f3a52; display: grid; grid-template-columns: 1fr 1.2fr; overflow: hidden; }
            .m-left { padding: 40px; border-right: 1px solid rgba(255,255,255,0.05); text-align: center; }
            .m-right { padding: 40px; display: flex; align-items: center; justify-content: center; }
            .stat-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 10px; margin: 25px 0; }
            .stat-box { background: #16253d; padding: 15px; border-radius: 12px; text-align: left; }
            .stat-box small { color: #637381; font-size: 0.65rem; font-weight: 800; text-transform: uppercase; }
            .stat-box b { font-size: 1.3rem; display: block; margin-top: 4px; }
            .kf-container { background: #16253d; border: 1.5px solid #1f3a52; border-radius: 12px; padding: 20px; text-align: left; }
            .kf-title { color: var(--accent); font-size: 0.8rem; font-weight: 900; margin-bottom: 12px; text-transform: uppercase; }
            .kf-item { display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 0.95rem; }
            .kf-label { color: #aab4be; }
            .kf-val { font-weight: 800; }
            .prob-box { background: #1c1c1c; border: 1px solid #5e4d2b; border-radius: 12px; padding: 18px; margin-top: 15px; text-align: center; }
            .prob-box b { color: #fbbf24; font-size: 2.2rem; display: block; }
            .trend-up { color: #2ecc71; font-size: 0.8rem; margin-left: 4px; vertical-align: middle; }
            #loading { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: #030712; display: flex; flex-direction: column; justify-content: center; align-items: center; z-index: 9999; color: var(--accent); }
        </style>
    </head>
    <body>
        <div id="loading"><h1>DEFINING PERFORMANCE GRADES...</h1><p>Syncing Impact Tiers. Please wait.</p></div>
        
        <header>
            <a href="/" class="logo">
                <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                    <path d="M21,16.5C21,16.88 20.79,17.21 20.47,17.38L12.57,21.82C12.41,21.94 12.21,22 12,22C11.79,22 11.59,21.94 11.43,21.82L3.53,17.38C3.21,17.21 3,16.88 3,16.5V7.5C3,7.12 3.21,6.79 3.53,6.62L11.43,2.18C11.59,2.06 11.79,2 12,2C12.21,2 12.41,2.06 12.57,2.18L20.47,6.62C20.79,6.79 21,7.12 21,7.5V16.5Z" fill="none" stroke="currentColor" stroke-width="1.5"/>
                    <path d="M12,22V12 L20.47,7.38 M12,12L3.53,7.38" stroke="currentColor" stroke-width="1.2"/>
                    <path d="M18,15V11.5" stroke="#fff" stroke-width="1.8" stroke-linecap.round"/>
                    <path d="M15,15V13" stroke="#fff" stroke-width="1.8" stroke-linecap.round"/>
                    <path d="M12,15V12.5" stroke="#fff" stroke-width="1.8" stroke-linecap.round"/>
                </svg>
                <span>NHL ANALYTICA</span>
            </a>
            <div style="display:flex; align-items:center;">
                <div class="dropdown-group">
                    <select id="seasonSelect" class="select-style" onchange="init()">
                        <option value="{{auto_season}}">Current Season</option>
                        <option value="20242025">2024-2025</option>
                        <option value="20232024">2023-2024</option>
                    </select>
                    <select id="typeSelect" class="select-style" onchange="init()">
                        <option value="2">Regular Season</option>
                        <option value="3">Playoffs 🏆</option>
                    </select>
                </div>
                <input type="text" id="pSearch" class="search-box" placeholder="Search Player Name..." oninput="render()">
            </div>
        </header>

        <div class="nav-tabs"><button class="tab-btn active" id="skater-tab" onclick="switchTab('skater')">SKATERS</button><button class="tab-btn" id="goalie-tab" onclick="switchTab('goalie')">GOALIES</button></div>
        <div class="grid" id="main-grid"></div>
        <div id="modal" class="modal" onclick="this.style.display='none'"><div class="modal-box" onclick="event.stopPropagation()"><div class="m-left" id="mInfo"></div><div class="m-right"><canvas id="radar"></canvas></div></div></div>
        
        <script>
            let skaters = []; let goalies = [];
            let currentTab = 'skater'; let chartInstance = null;

            async function init() {
                document.getElementById('loading').style.display = 'flex';
                const s = document.getElementById('seasonSelect').value;
                const g = document.getElementById('typeSelect').value;
                try {
                    // [수정] API 호출 시 선택된 시즌과 타입 전달
                    const res = await fetch(`/api/data?season=${s}&game_type=${g}&t=${Date.now()}`);
                    const data = await res.json();
                    skaters = data.skaters; goalies = data.goalies;
                    document.getElementById('loading').style.display = 'none';
                    render();
                } catch (e) {
                    document.getElementById('loading').innerHTML = "<h1>LOAD ERROR</h1><p>Check API response.</p>";
                }
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
                grid.innerHTML = '';
                const filtered = data.filter(p => p.name.toLowerCase().includes(query));
                
                // [유지] 기존 렌더링 로직 그대로
                grid.innerHTML = filtered.slice(0, 100).map(p => {
                    const trend = p.trending ? '<span class="trend-up">▲</span>' : '';
                    const subInfo = currentTab === 'skater' ? `${p.abbr} • ${p.pos} • PPG ${p.ppg}` : `${p.abbr} • G • SV% ${p.sv}`;
                    return `
                    <div class="card" onclick="openModal('${p.id}', '${p.type}')" style="--t-color:${p.col}">
                        <div style="display:flex; align-items:center; gap:15px;">
                            <img src="https://assets.nhle.com/mugs/nhl/latest/${p.id}.png" style="width:60px; border-radius:50%; background:#000;" onerror="this.src='https://assets.nhle.com/logos/nhl/svg/${p.abbr}_light.svg'">
                            <div><h3 style="margin:0; font-size:1.1rem;">${p.name}</h3><small>${subInfo}</small></div>
                            <div style="margin-left:auto; text-align:right;"><b style="color:var(--accent); font-size:1.3rem;">${currentTab==='skater'?p.pts:p.w}${trend}</b><br><small style="font-size:0.6rem;">${currentTab==='skater'?'PTS':'WINS'}</small></div>
                        </div>
                    </div>`;
                }).join('');
            }

            // [유지] 기존 모달 및 차트 로직 그대로
            function openModal(id, type) {
                const data = type === 'skater' ? skaters : goalies;
                const p = data.find(x => x.id === id);
                let irGrade = p.ir >= 90 ? "Elite" : p.ir >= 75 ? "Above Average" : p.ir >= 60 ? "Average" : "Below Average";
                let statsHtml = type === 'skater' ? 
                    `<div class="stat-box"><small>GP</small><b>${p.gp}</b></div><div class="stat-box"><small>PPG</small><b>${p.ppg}</b></div><div class="stat-box"><small>IR SCORE</small><b style="color:var(--accent)">${p.ir}</b></div><div class="stat-box"><small>+/-</small><b>${p.pm}</b></div><div class="stat-box"><small>GOALS</small><b>${p.g}</b></div>` : 
                    `<div class="stat-box"><small>GP</small><b>${p.gp}</b></div><div class="stat-box"><small>WINS</small><b>${p.w}</b></div><div class="stat-box"><small>IR SCORE</small><b style="color:var(--accent)">${p.ir}</b></div><div class="stat-box"><small>SV%</small><b>${p.sv}%</b></div><div class="stat-box"><small>GAA</small><b>${p.gaa}</b></div>`;
                
                document.getElementById('mInfo').innerHTML = `<img src="https://assets.nhle.com/mugs/nhl/latest/${p.id}.png" style="width:150px; border-radius:50%; border:4px solid ${p.col};"><h2 style="font-family:'Syncopate'; margin:20px 0 5px; font-size:1.8rem;">${p.name.toUpperCase()}</h2><div style="color:${p.col}; font-weight:800; font-size:1.2rem; margin-bottom:20px;">${p.team}</div><div class="stat-grid">${statsHtml}</div><div class="kf-container"><div class="kf-title">Key Factors</div><div class="kf-item"><span class="kf-label">Impact Rating</span><span class="kf-val">${irGrade}</span></div></div><div class="prob-box"><small style="color:#fbbf24; font-weight:800;">${type==='skater'?'GOAL PROBABILITY':'SHUTOUTS'}</small><b>${type==='skater'?p.prob+'%':p.so}</b></div>`;
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
                    data: { labels: ['Scoring', 'Playmaking', 'Efficiency', 'Shot Vol.', 'Def.'], datasets: [{ data: chartData, backgroundColor: 'rgba(56, 189, 248, 0.2)', borderColor: '#38bdf8', borderWidth: 2, pointRadius: 0 }] },
                    options: { scales: { r: { grid: { color: '#1f2d44' }, angleLines: { color: '#1f2d44' }, ticks: { display: false }, pointLabels: { color: '#aab4be' } } }, plugins: { legend: { display: false } } }
                });
            }
            init();
        </script>
    </body>
    </html>
    """)

# [유지] 기존 엔드포인트 그대로
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
