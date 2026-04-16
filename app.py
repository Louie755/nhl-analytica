import pandas as pd
from flask import Flask, render_template_string, jsonify, request
import requests
import os
from datetime import datetime

app = Flask(__name__)

# 팀 정보 및 색상 데이터
TEAM_MAP = {"ANA": "Anaheim Ducks", "BOS": "Boston Bruins", "BUF": "Buffalo Sabres", "CGY": "Calgary Flames", "CAR": "Carolina Hurricanes", "CHI": "Chicago Blackhawks", "COL": "Colorado Avalanche", "CBJ": "Columbus Blue Jackets", "DAL": "Dallas Stars", "DET": "Detroit Red Wings", "EDM": "Edmonton Oilers", "FLA": "Florida Panthers", "LAK": "Los Angeles Kings", "MIN": "Minnesota Wild", "MTL": "Montreal Canadiens", "NSH": "Nashville Predators", "NJD": "New Jersey Devils", "NYI": "New York Islanders", "NYR": "New York Rangers", "OTT": "Ottawa Senators", "PHI": "Philadelphia Flyers", "PIT": "Pittsburgh Penguins", "SJS": "San Jose Sharks", "SEA": "Seattle Kraken", "STL": "St Louis Blues", "TBL": "Tampa Bay Lightning", "TOR": "Toronto Maple Leafs", "UTA": "Utah Hockey Club", "VAN": "Vancouver Canucks", "VGK": "Vegas Golden Knights", "WSH": "Washington Capitals", "WPG": "Winnipeg Jets"}
TEAM_COLORS = {"ANA": "#F47A38", "BOS": "#FFB81C", "BUF": "#002654", "CGY": "#C8102E", "CAR": "#CE1126", "CHI": "#CF0A2C", "COL": "#6F263D", "CBJ": "#002654", "DAL": "#006847", "DET": "#CE1126", "EDM": "#FF4C00", "FLA": "#041E42", "LAK": "#111111", "MIN": "#154734", "MTL": "#AF1E2D", "NSH": "#FFB81C", "NJD": "#CE1126", "NYI": "#00539B", "NYR": "#0038A8", "OTT": "#C8102E", "PHI": "#F74902", "PIT": "#FCB514", "SJS": "#006D75", "SEA": "#001628", "STL": "#002F87", "TBL": "#002868", "TOR": "#00205B", "UTA": "#71AFE2", "VAN": "#00205B", "VGK": "#B4975A", "WSH": "#041E42", "WPG": "#004C97"}

def fetch_nhl_data(url, season, game_type, sort_prop):
    all_data = []
    start, limit = 0, 100
    while True:
        # 프로페셔널한 API 쿼리 구성
        cayenne_exp = f"seasonId={season} and gameTypeId={game_type}"
        params = {
            "isAggregate": "false",
            "isGame": "false",
            "sort": f'[{{"property":"{sort_prop}","direction":"DESC"}}]',
            "start": start,
            "limit": limit,
            "cayenneExp": cayenne_exp
        }
        try:
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
            data = r.json().get('data', [])
            if not data: break
            all_data.extend(data)
            if len(data) < limit: break
            start += limit
        except Exception as e:
            print(f"Error fetching data: {e}")
            break
    return all_data

@app.route('/api/data')
def get_nhl_data():
    season = request.args.get('season', '20242025')
    game_type = request.args.get('game_type', '2')
    
    # 데이터 호출
    s_raw = fetch_nhl_data("https://api.nhle.com/stats/rest/en/skater/summary", season, game_type, "points")
    g_raw = fetch_nhl_data("https://api.nhle.com/stats/rest/en/goalie/summary", season, game_type, "wins")
    
    # 스케이터 처리
    skaters = []
    for p in s_raw:
        gp = max(1, p.get('gamesPlayed', 0))
        pts = p.get('points', 0)
        ppg = round(pts / gp, 2)
        # Louie's IR Metric Logic
        ir = min(99.9, round((ppg * 40) + ((pts / max(1, p.get('shots', 0))) * 25) + (max(0, p.get('plusMinus', 0) + 10) / 2), 1))
        
        skaters.append({
            "id": p.get('playerId'),
            "name": p.get('skaterFullName'),
            "abbr": str(p.get('teamAbbrev', '')).upper(),
            "pos": p.get('positionCode'),
            "pts": pts, "g": p.get('goals', 0), "a": p.get('assists', 0),
            "ppg": ppg, "ir": ir,
            "col": TEAM_COLORS.get(p.get('teamAbbrev'), "#38bdf8")
        })

    # 골리 처리
    goalies = []
    for p in g_raw:
        gp = max(1, p.get('gamesPlayed', 0))
        sv_val = round(p.get('savePct', 0) * 100, 1)
        # Goalie IR Logic
        ir = min(99.9, round((p.get('wins', 0) / gp * 40) + (sv_val - 85) * 4, 1))
        
        goalies.append({
            "id": p.get('playerId'),
            "name": p.get('goalieFullName'),
            "abbr": str(p.get('teamAbbrev', '')).upper(),
            "w": p.get('wins', 0), "sv": sv_val, "gaa": round(p.get('goalsAgainstAverage', 0), 2),
            "ir": ir,
            "col": TEAM_COLORS.get(p.get('teamAbbrev'), "#38bdf8")
        })
        
    return jsonify({"skaters": skaters, "goalies": goalies})

@app.route('/')
def index():
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>NHL ANALYTICA | Professional Dashboard</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&family=Syncopate:wght@700&display=swap" rel="stylesheet">
        <style>
            :root { --accent: #38bdf8; --bg: #030712; --glass: rgba(17, 24, 39, 0.7); }
            body { background: var(--bg); color: white; font-family: 'Inter', sans-serif; margin: 0; }
            
            /* 프로페셔널 네비게이션 바 */
            nav { 
                background: var(--glass); backdrop-filter: blur(12px);
                border-bottom: 1px solid rgba(255,255,255,0.1);
                padding: 15px 5%; display: flex; justify-content: space-between; align-items: center;
                position: sticky; top: 0; z-index: 9999;
            }
            .logo { font-family: 'Syncopate'; font-size: 1.2rem; color: var(--accent); text-decoration: none; }
            
            /* 컨트롤 패널 (드랍다운 영역) */
            .controls { display: flex; gap: 12px; align-items: center; }
            .select-box { 
                background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.2);
                color: white; padding: 8px 12px; border-radius: 8px; cursor: pointer; font-size: 0.85rem;
            }
            .search-input {
                background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2);
                padding: 8px 15px; border-radius: 8px; color: white; width: 180px;
            }

            /* 탭 디자인 */
            .tabs { display: flex; justify-content: center; gap: 30px; margin: 20px 0; }
            .tab-btn { 
                background: none; border: none; color: #64748b; font-family: 'Syncopate';
                font-size: 0.8rem; cursor: pointer; padding-bottom: 5px; transition: 0.3s;
            }
            .tab-btn.active { color: var(--accent); border-bottom: 2px solid var(--accent); }

            /* 그리드 시스템 */
            .grid { 
                display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
                gap: 20px; padding: 0 5% 50px;
            }
            .card { 
                background: var(--glass); border-radius: 16px; padding: 20px;
                border: 1px solid rgba(255,255,255,0.05); transition: 0.3s;
                display: flex; align-items: center; gap: 15px; position: relative;
            }
            .card:hover { transform: translateY(-5px); border-color: var(--accent); }
            .card-border { position: absolute; left: 0; top: 20%; width: 4px; height: 60%; border-radius: 0 4px 4px 0; }

            .player-img { width: 60px; height: 60px; border-radius: 50%; background: #000; border: 2px solid rgba(255,255,255,0.1); }
            .player-info h3 { margin: 0; font-size: 1rem; letter-spacing: -0.5px; }
            .player-info small { color: #94a3b8; font-size: 0.75rem; }
            .ir-badge { margin-left: auto; text-align: right; }
            .ir-val { font-size: 1.2rem; font-weight: 900; color: var(--accent); display: block; }
            .ir-label { font-size: 0.6rem; color: #64748b; font-weight: 800; }

            #loading { 
                position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: var(--bg);
                display: flex; justify-content: center; align-items: center; z-index: 10000;
                font-family: 'Syncopate'; color: var(--accent);
            }
        </style>
    </head>
    <body>
        <div id="loading">LOADING ANALYTICS...</div>

        <nav>
            <a href="#" class="logo">NHL ANALYTICA</a>
            <div class="controls">
                <select id="seasonSelect" class="select-box" onchange="loadData()">
                    <option value="20242025">2024-2025</option>
                    <option value="20232024">2023-2024</option>
                    <option value="20222023">2022-2023</option>
                </select>
                <select id="typeSelect" class="select-box" onchange="loadData()">
                    <option value="2">Regular Season</option>
                    <option value="3">Playoffs 🏆</option>
                </select>
                <input type="text" id="pSearch" class="search-input" placeholder="Search Player..." oninput="render()">
            </div>
        </nav>

        <div class="tabs">
            <button class="tab-btn active" id="tab-skater" onclick="setTab('skater')">SKATERS</button>
            <button class="tab-btn" id="tab-goalie" onclick="setTab('goalie')">GOALIES</button>
        </div>

        <div class="grid" id="main-grid"></div>

        <script>
            let allData = { skaters: [], goalies: [] };
            let currentTab = 'skater';

            async function loadData() {
                const loader = document.getElementById('loading');
                loader.style.display = 'flex';
                
                const s = document.getElementById('seasonSelect').value;
                const t = document.getElementById('typeSelect').value;
                
                try {
                    const res = await fetch(`/api/data?season=${s}&game_type=${t}`);
                    allData = await res.json();
                    render();
                } catch (e) {
                    console.error("Fetch error:", e);
                } finally {
                    loader.style.display = 'none';
                }
            }

            function setTab(tab) {
                currentTab = tab;
                document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
                document.getElementById('tab-' + tab).classList.add('active');
                render();
            }

            function render() {
                const grid = document.getElementById('main-grid');
                const query = document.getElementById('pSearch').value.toLowerCase();
                const data = currentTab === 'skater' ? allData.skaters : allData.goalies;
                
                grid.innerHTML = data.filter(p => p.name.toLowerCase().includes(query)).map(p => `
                    <div class="card">
                        <div class="card-border" style="background: ${p.col}"></div>
                        <img src="https://assets.nhle.com/mugs/nhl/latest/${p.id}.png" class="player-img" onerror="this.src='https://assets.nhle.com/logos/nhl/svg/${p.abbr}_light.svg'">
                        <div class="player-info">
                            <h3>${p.name}</h3>
                            <small>${p.abbr} • ${currentTab === 'skater' ? p.pos : 'Goalie'}</small>
                        </div>
                        <div class="ir-badge">
                            <span class="ir-val">${p.ir}</span>
                            <span class="ir-label">IR SCORE</span>
                        </div>
                    </div>
                `).join('');
            }

            // 초기 로드
            loadData();
        </script>
    </body>
    </html>
    """)

if __name__ == "__main__":
    # Render 및 로컬 호스팅 대응
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
