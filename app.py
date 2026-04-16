import pandas as pd
from flask import Flask, render_template_string, jsonify, request
import requests
import os
from datetime import datetime

app = Flask(__name__)

# [데이터 맵 및 컬러 - 기존 설정 유지]
TEAM_MAP = {"ANA": "Anaheim Ducks", "BOS": "Boston Bruins", "BUF": "Buffalo Sabres", "CGY": "Calgary Flames", "CAR": "Carolina Hurricanes", "CHI": "Chicago Blackhawks", "COL": "Colorado Avalanche", "CBJ": "Columbus Blue Jackets", "DAL": "Dallas Stars", "DET": "Detroit Red Wings", "EDM": "Edmonton Oilers", "FLA": "Florida Panthers", "LAK": "Los Angeles Kings", "MIN": "Minnesota Wild", "MTL": "Montreal Canadiens", "NSH": "Nashville Predators", "NJD": "New Jersey Devils", "NYI": "New York Islanders", "NYR": "New York Rangers", "OTT": "Ottawa Senators", "PHI": "Philadelphia Flyers", "PIT": "Pittsburgh Penguins", "SJS": "San Jose Sharks", "SEA": "Seattle Kraken", "STL": "St Louis Blues", "TBL": "Tampa Bay Lightning", "TOR": "Toronto Maple Leafs", "UTA": "Utah Hockey Club", "VAN": "Vancouver Canucks", "VGK": "Vegas Golden Knights", "WSH": "Washington Capitals", "WPG": "Winnipeg Jets"}
TEAM_COLORS = {"ANA": "#F47A38", "BOS": "#FFB81C", "BUF": "#002654", "CGY": "#C8102E", "CAR": "#CE1126", "CHI": "#CF0A2C", "COL": "#6F263D", "CBJ": "#002654", "DAL": "#006847", "DET": "#CE1126", "EDM": "#FF4C00", "FLA": "#041E42", "LAK": "#111111", "MIN": "#154734", "MTL": "#AF1E2D", "NSH": "#FFB81C", "NJD": "#CE1126", "NYI": "#00539B", "NYR": "#0038A8", "OTT": "#C8102E", "PHI": "#F74902", "PIT": "#FCB514", "SJS": "#006D75", "SEA": "#001628", "STL": "#002F87", "TBL": "#002868", "TOR": "#00205B", "UTA": "#71AFE2", "VAN": "#00205B", "VGK": "#B4975A", "WSH": "#041E42", "WPG": "#004C97"}

def fetch_nhl_safe(url, season, sort_prop):
    all_data = []
    start, limit = 0, 100
    while True:
        params = {"isAggregate": "false", "isGame": "false", "sort": f'[{{"property":"{sort_prop}","direction":"DESC"}}]', "start": start, "limit": limit, "cayenneExp": f"seasonId={season} and gameTypeId=2"}
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
    ts, season = int(now.timestamp()), f"{now.year}{now.year + 1}" if now.month >= 9 else f"{now.year - 1}{now.year}"
    s_raw = fetch_nhl_safe(f"https://api.nhle.com/stats/rest/en/skater/summary?t={ts}", season, "points")
    g_raw = fetch_nhl_safe(f"https://api.nhle.com/stats/rest/en/goalie/summary?t={ts}", season, "wins")
    today_scorers = get_today_scorers()
    
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
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>NHL ANALYTICA | Insights</title>
        <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'><path d='M21,16.5C21,16.88 20.79,17.21 20.47,17.38L12.57,21.82C12.41,21.94 12.21,22 12,22C11.79,22 11.59,21.94 11.43,21.82L3.53,17.38C3.21,17.21 3,16.88 3,16.5V7.5C3,7.12 3.21,6.79 3.53,6.62L11.43,2.18C11.59,2.06 11.79,2 12,2C12.21,2 12.41,2.06 12.57,2.18L20.47,6.62C20.79,6.79 21,7.12 21,7.5V16.5Z' fill='none' stroke='%2338bdf8' stroke-width='1.5'/><path d='M12,22V12 L20.47,7.38 M12,12L3.53,7.38' stroke='%2338bdf8' stroke-width='1.2'/><path d='M18,15V11.5' stroke='%23fff' stroke-width='1.8' stroke-linecap='round'/><path d='M15,15V13' stroke='%23fff' stroke-width='1.8' stroke-linecap='round'/><path d='M12,15V12.5' stroke='%23fff' stroke-width='1.8' stroke-linecap='round'/></svg>" type="image/svg+xml">
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800;900&family=Syncopate:wght@700&display=swap" rel="stylesheet">
        <style>
            :root { --accent: #38bdf8; --bg: #020617; --card: rgba(15, 23, 42, 0.7); }
            body { 
                background: var(--bg); color: white; font-family: 'Inter', sans-serif; margin: 0; 
                background-image: radial-gradient(circle at 50% 0%, #1e1b4b1a 0%, #020617 100%);
                min-height: 100vh; overflow-x: hidden;
            }
            header { 
                padding: 15px 5%; background: rgba(2, 6, 23, 0.8); border-bottom: 1px solid rgba(255,255,255,0.08); 
                display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 1000; backdrop-filter: blur(20px); 
            }
            .logo { display: flex; align-items: center; gap: 12px; font-family: 'Syncopate'; color: var(--accent); font-size: 1.3rem; text-decoration: none; }
            .logo svg { width: 34px; height: 34px; filter: drop-shadow(0 0 5px var(--accent)); }
            .search-box { 
                background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); padding: 12px 25px; 
                border-radius: 50px; color: white; width: 280px; outline: none; transition: 0.4s;
            }
            .search-box:focus { width: 350px; border-color: var(--accent); background: rgba(255,255,255,0.1); }

            .nav-tabs { display: flex; justify-content: center; gap: 40px; padding: 25px 0; }
            .tab-btn { font-family: 'Syncopate'; font-size: 0.8rem; cursor: pointer; color: #475569; border: none; background: none; transition: 0.3s; padding-bottom: 8px; }
            .tab-btn.active { color: var(--accent); border-bottom: 2px solid var(--accent); }

            .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 20px; padding: 0 5% 50px; }
            .card { 
                background: var(--card); border-radius: 20px; padding: 22px; cursor: pointer; border: 1px solid rgba(255,255,255,0.03); 
                transition: 0.3s cubic-bezier(0.4, 0, 0.2, 1); position: relative; overflow: hidden; backdrop-filter: blur(10px);
            }
            .card:hover { transform: translateY(-5px); border-color: var(--accent); background: rgba(30, 41, 59, 0.8); }
            .card::before { content: ""; position: absolute; top: 0; left: 0; width: 4px; height: 100%; background: var(--t-color); }

            .modal { display:none; position:fixed; z-index:2000; left:0; top:0; width:100%; height:100%; background:rgba(2, 6, 23, 0.95); backdrop-filter:blur(15px); }
            .modal-box { 
                background: #0f172a; width: 1000px; max-width: 95%; margin: 5vh auto; border-radius: 30px; 
                border: 1px solid rgba(255,255,255,0.1); display: grid; grid-template-columns: 1fr 1.2fr; overflow: hidden;
            }
            .m-left { padding: 45px; border-right: 1px solid rgba(255,255,255,0.05); text-align: center; }
            .m-right { padding: 45px; display: flex; align-items: center; justify-content: center; background: rgba(0,0,0,0.2); }

            .stat-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 25px 0; }
            .stat-box { background: rgba(255,255,255,0.03); padding: 15px; border-radius: 16px; border: 1px solid rgba(255,255,255,0.02); }
            .stat-box small { color: #64748b; font-size: 0.65rem; font-weight: 800; text-transform: uppercase; }
            .stat-box b { font-size: 1.3rem; display: block; margin-top: 5px; }

            .kf-container { background: rgba(0,0,0,0.3); border-radius: 16px; padding: 20px; text-align: left; margin-bottom: 20px; border: 1px solid rgba(255,255,255,0.05); }
            .kf-title { color: var(--accent); font-size: 0.75rem; font-weight: 900; margin-bottom: 15px; letter-spacing: 1.5px; }
            .kf-item { display: flex; justify-content: space-between; margin-bottom: 10px; font-size: 0.9rem; border-bottom: 1px solid rgba(255,255,255,0.03); padding-bottom: 5px; }
            .kf-label { color: #94a3b8; }
            .kf-val { font-weight: 800; }

            .prob-box { background: linear-gradient(135deg, #1e1b4b, #312e81); border-radius: 16px; padding: 20px; text-align: center; border: 1px solid #4338ca; }
            .prob-box b { color: #fbbf24; font-size: 2.2rem; display: block; }

            #loading { position: fixed; inset: 0; background: #020617; display: flex; flex-direction: column; justify-content: center; align-items: center; z-index: 9999; }
            .spinner { width: 50px; height: 50px; border: 3px solid rgba(56, 189, 248, 0.1); border-top-color: var(--accent); border-radius: 50%; animation: spin 1s linear infinite; }
            @keyframes spin { to { transform: rotate(360deg); } }

            @media (max-width: 900px) {
                .modal-box { grid-template-columns: 1fr; margin: 2vh auto; max-height: 95vh; overflow-y: auto; }
                .m-left { border-right: none; border-bottom: 1px solid rgba(255,255,255,0.05); }
            }
        </style>
    </head>
    <body>
        <div id="loading"><div class="spinner"></div><h2 style="font-family:'Syncopate'; font-size:0.7rem; margin-top:20px; letter-spacing:4px;">ANALYZING LEAGUE DATA</h2></div>
        
        <header>
            <a href="/" class="logo">
                <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M21 16.5V7.5C21 7.12 20.79 6.79 20.47 6.62L12.57 2.18C12.41 2.06 12.21 2 12 2C11.79 2 11.59 2.06 11.43 2.18L3.53 6.62C3.21 6.79 3 7.12 3 7.5V16.5C3 16.88 3.21 17.21 3.53 17.38L11.43 21.82C11.59 21.94 11.79 22 12 22C12.21 22 12.41 21.94 12.57 21.82L20.47 17.38C20.79 17.21 21 16.88 21 16.5Z" stroke="currentColor" stroke-width="1.5"/>
                    <path d="M12 22V12L20.5 7.5M12 12L3.5 7.5" stroke="currentColor" stroke-width="1.2"/>
                </svg>
                <span>NHL ANALYTICA</span>
            </a>
            <input type="text" id="pSearch" class="search-box" placeholder="Search Player Name..." oninput="render()">
        </header>

        <div class="nav-tabs">
            <button class="tab-btn active" id="skater-tab" onclick="switchTab('skater')">SKATERS</button>
            <button class="tab-btn" id="goalie-tab" onclick="switchTab('goalie')">GOALIES</button>
        </div>

        <div class="grid" id="main-grid"></div>

        <div id="modal" class="modal" onclick="this.style.display='none'">
            <div class="modal-box" onclick="event.stopPropagation()">
                <div class="m-left" id="mInfo"></div>
                <div class="m-right"><div style="width:100%; max-width:480px;"><canvas id="radar"></canvas></div></div>
            </div>
        </div>

        <script>
            let skaters = []; let goalies = [];
            let currentTab = 'skater'; let chartInstance = null;

            async function init() {
                try {
                    const res = await fetch('/api/data?t=' + Date.now());
                    const data = await res.json();
                    skaters = data.skaters; goalies = data.goalies;
                    document.getElementById('loading').style.display = 'none';
                    render();
                } catch (e) {
                    document.getElementById('loading').innerHTML = "<h2>LOAD ERROR</h2>";
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
                
                let idx = 0;
                function draw() {
                    const chunk = filtered.slice(idx, idx + 30);
                    const html = chunk.map(p => {
                        const trend = p.trending ? '<span style="color:#10b981; margin-left:8px; font-size:0.7rem;">● HOT</span>' : '';
                        const val = currentTab === 'skater' ? p.pts : p.w;
                        const label = currentTab === 'skater' ? 'PTS' : 'WINS';
                        return `
                        <div class="card" onclick="openModal('${p.id}', '${p.type}')" style="--t-color:${p.col}">
                            <div style="display:flex; align-items:center; gap:18px;">
                                <img src="https://assets.nhle.com/mugs/nhl/latest/${p.id}.png" style="width:65px; height:65px; border-radius:50%; background:rgba(0,0,0,0.2);" onerror="this.src='https://assets.nhle.com/logos/nhl/svg/${p.abbr}_light.svg'">
                                <div style="flex:1">
                                    <h3 style="margin:0; font-size:1.1rem; letter-spacing:-0.5px;">${p.name}${trend}</h3>
                                    <small style="color:#64748b; font-weight:800;">${p.abbr} • ${currentTab==='skater' ? p.pos : 'G'} • IR ${p.ir}</small>
                                </div>
                                <div style="text-align:right">
                                    <b style="color:var(--accent); font-size:1.5rem;">${val}</b>
                                    <div style="font-size:0.6rem; color:#475569; font-weight:900;">${label}</div>
                                </div>
                            </div>
                        </div>`;
                    }).join('');
                    grid.insertAdjacentHTML('beforeend', html);
                    idx += 30;
                    if(idx < filtered.length) setTimeout(draw, 5);
                }
                draw();
            }

            function openModal(id, type) {
                const data = type === 'skater' ? skaters : goalies;
                const p = data.find(x => x.id === id);
                const gp = Math.max(1, p.gp);
                
                // --- 정확한 Key Factors 로직 ---
                let kf = [];
                if(type === 'skater') {
                    const shotEff = (p.pts / Math.max(1, p.sh)) * 100;
                    if(p.ppg >= 1.0) kf.push({l: 'Impact Tier', v: 'Elite', c: '#f87171'});
                    else if(p.ppg >= 0.7) kf.push({l: 'Impact Tier', v: 'Core', c: '#fbbf24'});
                    else kf.push({l: 'Impact Tier', v: 'Support', c: '#94a3b8'});
                    
                    if(shotEff > 25) kf.push({l: 'Finishing', v: 'Deadly', c: '#f87171'});
                    else if(shotEff > 15) kf.push({l: 'Finishing', v: 'Precise', c: var(--accent)});
                    else kf.push({l: 'Finishing', v: 'Standard', c: '#94a3b8'});

                    kf.push({l: 'Team Value', v: p.pm >= 0 ? 'Positive' : 'Low', c: p.pm >= 0 ? '#22c55e' : '#f87171'});
                } else {
                    const winRate = (p.w / gp) * 100;
                    kf.push({l: 'Reliability', v: p.sv >= 91 ? 'Wall' : 'Stable', c: p.sv >= 91 ? '#f87171' : '#38bdf8'});
                    kf.push({l: 'Win Contribution', v: winRate > 50 ? 'High' : 'Normal', c: winRate > 50 ? '#fbbf24' : '#94a3b8'});
                    kf.push({l: 'Net Mind', v: p.gaa < 2.8 ? 'Elite' : 'Tested', c: p.gaa < 2.8 ? '#22c55e' : '#fbbf24'});
                }

                const kfHtml = kf.map(i => `<div class="kf-item"><span class="kf-label">${i.l}</span><span class="kf-val" style="color:${i.c}">${i.v}</span></div>`).join('');
                
                let statsHtml = type === 'skater' ? 
                    `<div class="stat-box"><small>GP</small><b>${p.gp}</b></div><div class="stat-box"><small>G</small><b>${p.g}</b></div><div class="stat-box"><small>A</small><b>${p.a}</b></div><div class="stat-box"><small>+/-</small><b>${p.pm}</b></div><div class="stat-box"><small>PPG</small><b>${p.ppg}</b></div><div class="stat-box"><small>IR</small><b style="color:var(--accent)">${p.ir}</b></div>` : 
                    `<div class="stat-box"><small>GP</small><b>${p.gp}</b></div><div class="stat-box"><small>W</small><b>${p.w}</b></div><div class="stat-box"><small>SV%</small><b>${p.sv}</b></div><div class="stat-box"><small>GAA</small><b>${p.gaa}</b></div><div class="stat-box"><small>SO</small><b>${p.so}</b></div><div class="stat-box"><small>IR</small><b style="color:var(--accent)">${p.ir}</b></div>`;

                document.getElementById('mInfo').innerHTML = `
                    <img src="https://assets.nhle.com/mugs/nhl/latest/${p.id}.png" style="width:160px; height:160px; border-radius:50%; border:3px solid ${p.col}; padding:5px; background:rgba(0,0,0,0.3);">
                    <h2 style="font-family:'Syncopate'; margin:25px 0 5px; font-size:1.8rem;">${p.name.toUpperCase()}</h2>
                    <div style="color:${p.col}; font-weight:900; font-size:1rem; letter-spacing:2px; margin-bottom:25px;">${p.team.toUpperCase()}</div>
                    <div class="stat-grid">${statsHtml}</div>
                    <div class="kf-container"><div class="kf-title">ADVANCED INSIGHTS</div>${kfHtml}</div>
                    <div class="prob-box"><small style="color:rgba(255,255,255,0.6); font-weight:800; font-size:0.7rem; letter-spacing:2px;">ANALYTICA PROBABILITY</small><b>${type === 'skater' ? p.prob + '%' : (p.sv * 0.95).toFixed(1) + '%'}</b></div>
                `;
                document.getElementById('modal').style.display = 'block';
                setTimeout(() => drawRadar(p), 50);
            }

            function drawRadar(p) {
                const ctx = document.getElementById('radar').getContext('2d');
                if(chartInstance) chartInstance.destroy();
                
                let chartData = [], labels = [];
                const gp = Math.max(1, p.gp);

                if(p.type === 'skater') {
                    labels = ['Scoring', 'Playmaking', 'Efficiency', 'Shot Vol.', 'Defense'];
                    // 정규화 가중치 세밀화
                    chartData = [
                        Math.min(100, (p.g / gp) * 280),           
                        Math.min(100, (p.a / gp) * 220),           
                        Math.min(100, (p.pts / Math.max(1, p.sh)) * 650), 
                        Math.min(100, (p.sh / gp) * 30),           
                        Math.max(20, Math.min(100, 50 + (p.pm * 6))) 
                    ];
                } else {
                    labels = ['Wins', 'Save %', 'GAA', 'Shutouts', 'Reliability'];
                    chartData = [
                        Math.min(100, (p.w / gp) * 190),
                        Math.max(20, Math.min(100, (p.sv - 87) * 18)),
                        Math.max(20, Math.min(100, (4.5 - p.gaa) * 30)),
                        Math.min(100, (p.so * 55) + 5),
                        Math.min(100, gp * 2.5)
                    ];
                }

                chartInstance = new Chart(ctx, {
                    type: 'radar',
                    data: {
                        labels: labels,
                        datasets: [{
                            data: chartData,
                            backgroundColor: 'rgba(56, 189, 248, 0.15)',
                            borderColor: p.col,
                            borderWidth: 3,
                            pointBackgroundColor: p.col,
                            pointRadius: 4,
                            pointHoverRadius: 6,
                            lineTension: 0.15
                        }]
                    },
                    options: {
                        scales: {
                            r: {
                                min: 0, max: 100,
                                grid: { color: 'rgba(255,255,255,0.05)' },
                                angleLines: { color: 'rgba(255,255,255,0.1)' },
                                ticks: { display: false, stepSize: 20 },
                                pointLabels: { color: '#64748b', font: { size: 12, weight: '700' } }
                            }
                        },
                        plugins: { legend: { display: false } },
                        animation: { duration: 1200, easing: 'easeOutQuart' }
                    }
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
