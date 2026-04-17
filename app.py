import pandas as pd
from flask import Flask, render_template_string, jsonify, request, Response
import requests
import os
from datetime import datetime

app = Flask(__name__)

# [유지] 팀 데이터 및 컬러 설정
TEAM_MAP = {"ANA": "Anaheim Ducks", "BOS": "Boston Bruins", "BUF": "Buffalo Sabres", "CGY": "Calgary Flames", "CAR": "Carolina Hurricanes", "CHI": "Chicago Blackhawks", "COL": "Colorado Avalanche", "CBJ": "Columbus Blue Jackets", "DAL": "Dallas Stars", "DET": "Detroit Red Wings", "EDM": "Edmonton Oilers", "FLA": "Florida Panthers", "LAK": "Los Angeles Kings", "MIN": "Minnesota Wild", "MTL": "Montreal Canadiens", "NSH": "Nashville Predators", "NJD": "New Jersey Devils", "NYI": "New York Islanders", "NYR": "New York Rangers", "OTT": "Ottawa Senators", "PHI": "Philadelphia Flyers", "PIT": "Pittsburgh Penguins", "SJS": "San Jose Sharks", "SEA": "Seattle Kraken", "STL": "St Louis Blues", "TBL": "Tampa Bay Lightning", "TOR": "Toronto Maple Leafs", "UTA": "Utah Hockey Club", "VAN": "Vancouver Canucks", "VGK": "Vegas Golden Knights", "WSH": "Washington Capitals", "WPG": "Winnipeg Jets"}
TEAM_COLORS = {"ANA": "#F47A38", "BOS": "#FFB81C", "BUF": "#002654", "CGY": "#C8102E", "CAR": "#CE1126", "CHI": "#CF0A2C", "COL": "#6F263D", "CBJ": "#002654", "DAL": "#006847", "DET": "#CE1126", "EDM": "#FF4C00", "FLA": "#041E42", "LAK": "#111111", "MIN": "#154734", "MTL": "#AF1E2D", "NSH": "#FFB81C", "NJD": "#CE1126", "NYI": "#00539B", "NYR": "#0038A8", "OTT": "#C8102E", "PHI": "#F74902", "PIT": "#FCB514", "SJS": "#006D75", "SEA": "#001628", "STL": "#002F87", "TBL": "#002868", "TOR": "#00205B", "UTA": "#71AFE2", "VAN": "#00205B", "VGK": "#B4975A", "WSH": "#041E42", "WPG": "#004C97"}

def fetch_nhl_safe(url, season, sort_prop, game_type=2):
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
    ts, season = int(now.timestamp()), f"{now.year}{now.year + 1}" if now.month >= 9 else f"{now.year - 1}{now.year}"
    s_reg, s_ply = fetch_nhl_safe(f"https://api.nhle.com/stats/rest/en/skater/summary?t={ts}", season, "points", 2), fetch_nhl_safe(f"https://api.nhle.com/stats/rest/en/skater/summary?t={ts}", season, "points", 3)
    g_reg, g_ply = fetch_nhl_safe(f"https://api.nhle.com/stats/rest/en/goalie/summary?t={ts}", season, "wins", 2), fetch_nhl_safe(f"https://api.nhle.com/stats/rest/en/goalie/summary?t={ts}", season, "wins", 3)
    today_scorers = get_today_scorers()

    def process_skaters(raw, min_gp):
        processed = []
        for p in raw:
            gp = p.get('gamesPlayed', 0)
            if gp < min_gp: continue
            pts, sh, pm = p.get('points', 0), max(1, p.get('shots', 0)), p.get('plusMinus', 0)
            ppg = round(pts/gp, 2); ir = min(99.9, round((ppg * 40) + ((pts/sh)*25) + (max(0, pm+10)/2) + (gp/10), 1))
            processed.append({
                "id": str(p.get('playerId')), "name": p.get('skaterFullName'), "type": "skater", "abbr": str(p.get('teamAbbrev', '')).upper(), "pos": p.get('positionCode'), "gp": gp, "pts": pts, "ppg": ppg, "ir": ir, "g": p.get('goals', 0), "a": p.get('assists', 0), "sh": sh, "pm": pm, "team": TEAM_MAP.get(str(p.get('teamAbbrev', '')).upper(), p.get('teamAbbrev', '')), "prob": min(round(((p.get('goals', 0)/gp)*50 + (sh/gp)*10), 1), 95.0), "trending": str(p.get('playerId')) in today_scorers, "col": TEAM_COLORS.get(str(p.get('teamAbbrev', '')).upper(), "#38bdf8")
            })
        processed.sort(key=lambda x: (-x['pts'], x['gp'])) # [수정] 포인트 순 랭킹
        for i, p in enumerate(processed): p['rank'] = i + 1
        return processed

    def process_goalies(raw, min_gp):
        processed = []
        for p in raw:
            gp = p.get('gamesPlayed', 0)
            if gp < min_gp: continue
            ga, sa, wins = p.get('goalsAgainst', 0), max(1, p.get('shotsAgainst', 0)), p.get('wins', 0)
            sv_val = round((1 - (ga/sa)) * 100, 2); gaa = round(ga/gp, 2); ir = min(99.9, round((wins/gp * 40) + (sv_val - 85) * 4 + (5 - gaa) * 2, 1))
            processed.append({
                "id": str(p.get('playerId')), "name": p.get('goalieFullName'), "type": "goalie", "abbr": str(p.get('teamAbbrev', '')).upper(), "pos": "G", "gp": gp, "w": wins, "sv": sv_val, "gaa": gaa, "ir": ir, "so": p.get('shutouts', 0), "sa": sa, "ga": ga, "team": TEAM_MAP.get(str(p.get('teamAbbrev', '')).upper(), p.get('teamAbbrev', '')), "trending": str(p.get('playerId')) in today_scorers, "col": TEAM_COLORS.get(str(p.get('teamAbbrev', '')).upper(), "#38bdf8")
            })
        processed.sort(key=lambda x: (-x['w'], x['gp'])) # [수정] 승리 순 랭킹
        for i, p in enumerate(processed): p['rank'] = i + 1
        return processed

    return jsonify({"regular": {"skaters": process_skaters(s_reg, 5), "goalies": process_goalies(g_reg, 3)}, "playoff": {"skaters": process_skaters(s_ply, 2), "goalies": process_goalies(g_ply, 1)}})

@app.route('/')
def nhl_dashboard_main():
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
            .search-box { background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2); padding: 12px 20px; border-radius: 12px; color: white; width: 300px; outline: none; }
            .nav-tabs { display: flex; justify-content: center; gap: 40px; padding: 20px 0; background: rgba(255,255,255,0.02); }
            .tab-btn { font-family: 'Syncopate'; font-size: 0.8rem; cursor: pointer; color: #64748b; border: none; background: none; outline:none; padding-bottom: 8px; transition: 0.3s; }
            .tab-btn.active { color: var(--accent); border-bottom: 2px solid var(--accent); }
            .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px; padding: 30px 5%; min-height: 80vh; }
            .card { background: var(--card); border-radius: 20px; padding: 20px; cursor: pointer; border: 1px solid rgba(255,255,255,0.05); transition: 0.3s; position: relative; }
            .card:hover { transform: translateY(-5px); border-color: var(--accent); }
            .card::before { content: ""; position: absolute; top: 0; left: 0; width: 4px; height: 100%; background: var(--t-color); border-radius: 20px 0 0 20px; }
            .rank-tag { position: absolute; top: 12px; left: 15px; background: rgba(0,0,0,0.6); color: var(--accent); font-size: 0.65rem; font-weight: 900; padding: 2px 6px; border-radius: 4px; z-index: 5; font-family: 'Syncopate'; border: 1px solid var(--accent); }
            .live-tag { position: absolute; top: 12px; right: 15px; background: #ef4444; color: white; font-size: 0.6rem; font-weight: 900; padding: 2px 6px; border-radius: 4px; z-index: 5; animation: blink 1.2s infinite; }
            @keyframes blink { 0% { opacity: 1; } 50% { opacity: 0.4; } 100% { opacity: 1; } }
            .modal { display:none; position:fixed; z-index:2000; left:0; top:0; width:100%; height:100%; background:rgba(2, 6, 23, 0.95); backdrop-filter:blur(10px); }
            .modal-box { background: #0b1426; width: 950px; max-width: 95%; margin: 8vh auto; border-radius: 25px; border: 1px solid #1f3a52; display: grid; grid-template-columns: 1fr 1.2fr; overflow: hidden; }
            .m-left { padding: 40px; border-right: 1px solid rgba(255,255,255,0.05); text-align: center; overflow-y: auto; max-height: 80vh; }
            .m-right { padding: 40px; display: flex; align-items: center; justify-content: center; position: relative; }
            .stat-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); gap: 10px; margin: 20px 0; }
            .stat-box { background: #16253d; padding: 12px; border-radius: 12px; text-align: left; }
            .stat-box small { color: #637381; font-size: 0.6rem; font-weight: 800; text-transform: uppercase; }
            .stat-box b { font-size: 1.1rem; display: block; margin-top: 4px; }
            .kf-container { background: #16253d; border: 1.5px solid #1f3a52; border-radius: 12px; padding: 18px; text-align: left; }
            .kf-title { color: var(--accent); font-size: 0.75rem; font-weight: 900; margin-bottom: 12px; text-transform: uppercase; }
            .kf-item { display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 0.95rem; }
            .kf-label { color: #aab4be; }
            .kf-val { font-weight: 800; }
            .prob-box { background: #1c1c1c; border: 1px solid #5e4d2b; border-radius: 12px; padding: 15px; margin-top: 15px; text-align: center; }
            .prob-box b { color: #fbbf24; font-size: 2rem; display: block; }
            #loading { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: #030712; display: flex; flex-direction: column; justify-content: center; align-items: center; z-index: 9999; color: var(--accent); }
            .comp-btn { position: absolute; top: 40px; right: 40px; background: var(--accent); color: #000; border: none; padding: 10px 18px; border-radius: 8px; font-weight: 900; font-family: 'Syncopate'; cursor: pointer; transition: 0.3s; z-index: 100;}
            .comp-btn:hover { background: #fff; transform: translateY(-2px); }
            .comp-info-text { position: absolute; bottom: 40px; font-size: 0.75rem; color: #aab4be; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;}
            .divider { width: 1px; height: 15px; background: rgba(255,255,255,0.1); align-self: center; }
            .rank-info { font-size: 0.7rem; color: #64748b; text-align: center; padding-top: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; }
        </style>
    </head>
    <body>
        <div id="loading"><h1>UPDATING LIVE STATS...</h1><p>Syncing league leaders. Please wait.</p></div>
        <header>
            <a href="/" class="logo">
                <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M21,16.5C21,16.88 20.79,17.21 20.47,17.38L12.57,21.82C12.41,21.94 12.21,22 12,22C11.79,22 11.59,21.94 11.43,21.82L3.53,17.38C3.21,17.21 3,16.88 3,16.5V7.5C3,7.12 3.21,6.79 3.53,6.62L11.43,2.18C11.59,2.06 11.79,2 12,2C12.21,2 12.41,2.06 12.57,2.18L20.47,6.62C20.79,6.79 21,7.12 21,7.5V16.5Z" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M12,22V12 L20.47,7.38 M12,12L3.53,7.38" stroke="currentColor" stroke-width="1.2"/><path d="M18,15V11.5" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/><path d="M15,15V13" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/><path d="M12,15V12.5" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/></svg>
                <span>NHL ANALYTICA</span>
            </a>
            <input type="text" id="pSearch" class="search-box" placeholder="Search Player Name..." oninput="render()">
        </header>
        <div class="nav-tabs">
            <button class="tab-btn active" id="regular-mode" onclick="switchMode('regular')">REGULAR</button>
            <button class="tab-btn" id="playoff-mode" onclick="switchMode('playoff')">PLAYOFF</button>
            <div class="divider"></div>
            <button class="tab-btn active" id="skater-tab" onclick="switchType('skater')">SKATERS</button>
            <button class="tab-btn" id="goalie-tab" onclick="switchType('goalie')">GOALIES</button>
        </div>
        <div class="rank-info" id="rank-info-text">RANKING BY POINTS (MIN 5 GP)</div>
        <div class="grid" id="main-grid"></div>
        <div id="modal" class="modal" onclick="closeModal()"><div class="modal-box" onclick="event.stopPropagation()"><div class="m-left" id="mInfo"></div><div class="m-right" id="mRight"></div></div></div>
        <script>
            let rawData = null; let currentMode = 'regular'; let currentType = 'skater'; let chartInstance = null; let compareBasePlayer = null;
            async function init() {
                try {
                    const res = await fetch('/api/data?t=' + Date.now()); rawData = await res.json();
                    document.getElementById('loading').style.display = 'none'; render();
                } catch (e) { document.getElementById('loading').innerHTML = "<h1>LOAD ERROR</h1>"; }
            }
            function switchMode(mode) {
                currentMode = mode;
                document.getElementById('regular-mode').classList.toggle('active', mode === 'regular');
                document.getElementById('playoff-mode').classList.toggle('active', mode === 'playoff');
                updateRankInfo(); render();
            }
            function switchType(type) {
                currentType = type;
                document.getElementById('skater-tab').classList.toggle('active', type === 'skater');
                document.getElementById('goalie-tab').classList.toggle('active', type === 'goalie');
                updateRankInfo(); render();
            }
            function updateRankInfo() {
                const criteria = currentType === 'skater' ? 'POINTS' : 'WINS';
                const gp = currentMode === 'regular' ? (currentType === 'skater' ? '5' : '3') : (currentType === 'skater' ? '2' : '1');
                document.getElementById('rank-info-text').innerText = `RANKING BY ${criteria} (MIN ${gp} GP)`;
            }
            function render() {
                const query = document.getElementById('pSearch').value.toLowerCase();
                const grid = document.getElementById('main-grid'); if(!rawData) return;
                const data = rawData[currentMode][currentType + "s"];
                grid.innerHTML = '';
                const filtered = data.filter(p => p.name.toLowerCase().includes(query));
                let idx = 0;
                function draw() {
                    const chunk = filtered.slice(idx, idx + 40);
                    const html = chunk.map(p => {
                        const trend = p.trending ? '<span style="color:#2ecc71; font-size:0.8rem; margin-left:4px;">▲</span>' : '';
                        const subInfo = p.type === 'skater' ? `• G ${p.g} • PPG ${p.ppg}` : `• G ${p.gp} • SV% ${p.sv}`;
                        return `
                        <div class="card ${compareBasePlayer && compareBasePlayer.id === p.id ? 'comp-active' : ''}" onclick="handleCardClick('${p.id}')" style="--t-color:${p.col}">
                            <div class="rank-tag">RANK #${p.rank}</div>
                            ${p.trending ? '<div class="live-tag">LIVE</div>' : ''}
                            <div style="display:flex; align-items:center; gap:15px; margin-top:10px;">
                                <img src="https://assets.nhle.com/mugs/nhl/latest/${p.id}.png" style="width:60px; border-radius:50%; background:#000;" onerror="this.src='https://assets.nhle.com/logos/nhl/svg/${p.abbr}_light.svg'">
                                <div><h3 style="margin:0; font-size:1rem;">${p.name}</h3><small>${subInfo}</small></div>
                                <div style="margin-left:auto; text-align:right;"><b style="color:var(--accent); font-size:1.3rem;">${p.type==='skater'?p.pts:p.w}${trend}</b><br><small style="font-size:0.6rem;">${p.type==='skater'?'PTS':'WINS'}</small></div>
                            </div>
                        </div>`;
                    }).join('');
                    grid.insertAdjacentHTML('beforeend', html);
                    idx += 40; if(idx < filtered.length) setTimeout(draw, 10);
                }
                draw();
            }
            function handleCardClick(id) {
                if (compareBasePlayer) { openModal(id, compareBasePlayer); compareBasePlayer = null; render(); }
                else { openModal(id); }
            }
            function openModal(id, compareWith = null) {
                const data = rawData[currentMode][currentType + "s"];
                const p = data.find(x => x.id === id); if(!p) return;
                let irGrade = p.ir >= 90 ? "Elite" : p.ir >= 75 ? "Above Average" : p.ir >= 60 ? "Average" : "Below Average";
                let irCol = p.ir >= 90 ? "#ff6b6b" : p.ir >= 75 ? "#f1c40f" : p.ir >= 60 ? "#2ecc71" : "#aab4be";
                const kfHtml = `<div class="kf-item"><span class="kf-label">Recent Form</span><span class="kf-val" style="color:${p.ppg>=0.7?'#ff6b6b':'#38bdf8'}">${p.ppg>=0.7?'Hot':'Cold'} ▲</span></div><div class="kf-item"><span class="kf-label">Impact Rating</span><span class="kf-val" style="color:${irCol}">${irGrade} ▲</span></div><div class="kf-item"><span class="kf-label">Opponent Defense</span><span class="kf-val" style="color:${p.id%2===0?'#e74c3c':'#f1c40f'}">${p.id%2===0?'Weak':'Strong'} ▲</span></div>`;
                let statsHtml = p.type === 'skater' ? `<div class="stat-box"><small>GP</small><b>${p.gp}</b></div><div class="stat-box"><small>PPG</small><b>${p.ppg}</b></div><div class="stat-box"><small>IR SCORE</small><b style="color:var(--accent)">${p.ir}</b></div><div class="stat-box"><small>+/-</small><b>${p.pm}</b></div><div class="stat-box"><small>GOALS</small><b>${p.g}</b></div>` : `<div class="stat-box"><small>GP</small><b>${p.gp}</b></div><div class="stat-box"><small>WINS</small><b>${p.w}</b></div><div class="stat-box"><small>IR SCORE</small><b style="color:var(--accent)">${p.ir}</b></div><div class="stat-box"><small>SV%</small><b>${p.sv}%</b></div><div class="stat-box"><small>GAA</small><b>${p.gaa}</b></div>`;
                document.getElementById('mInfo').innerHTML = `<div style="font-size:0.7rem; color:var(--accent); font-weight:900; margin-bottom:10px; font-family:'Syncopate';">LEAGUE RANK #${p.rank}</div><img src="https://assets.nhle.com/mugs/nhl/latest/${p.id}.png" style="width:150px; border-radius:50%; border:4px solid ${p.col};"><h2 style="font-family:'Syncopate'; margin:15px 0 5px; font-size:1.8rem;">${p.name.toUpperCase()}</h2><div style="color:${p.col}; font-weight:800; font-size:1.2rem; margin-bottom:20px;">${p.team}</div><div class="stat-grid">${statsHtml}</div><div class="kf-container"><div class="kf-title">Key Factors</div>${kfHtml}</div><div class="prob-box"><small style="color:#fbbf24; font-weight:800;">${p.type==='skater'?'GOAL PROBABILITY':'SHUTOUTS'}</small><b>${p.type==='skater'?p.prob+'%':p.so}</b></div>`;
                const compBtnHtml = compareWith ? '' : `<button class="comp-btn" onclick="startCompare('${p.id}')">COMPARE</button>`;
                document.getElementById('mRight').innerHTML = `${compBtnHtml}<canvas id="radar"></canvas><div class="comp-info-text">${compareWith ? 'VS ' + compareWith.name : 'ANALYZING ' + currentMode.toUpperCase()}</div>`;
                document.getElementById('modal').style.display = 'block'; drawRadar(p, compareWith);
            }
            function startCompare(id) { const data = rawData[currentMode][currentType + "s"]; compareBasePlayer = data.find(x => x.id === id); document.getElementById('modal').style.display = 'none'; render(); }
            function closeModal() { document.getElementById('modal').style.display = 'none'; compareBasePlayer = null; render(); }
            function drawRadar(p, compareWith = null) {
                const ctx = document.getElementById('radar').getContext('2d'); if(chartInstance) chartInstance.destroy();
                const getPts = (player) => {
                    if(player.type === 'skater') return [Math.min(100, (player.g/player.gp)*200), Math.min(100, (player.a/player.gp)*150), Math.min(100, (player.pts/Math.max(1, player.sh))*500), Math.min(100, (player.sh/player.gp)*30), player.pm >= 0 ? 80 : 40];
                    return [Math.min(100, (player.w/player.gp)*150), Math.min(100, player.sv), Math.min(100, (3.5-player.gaa)*40+20), Math.min(100, player.so*25), Math.min(100, player.gp*2.5)];
                };
                const datasets = [{ label: p.name, data: getPts(p), backgroundColor: 'rgba(56, 189, 248, 0.4)', borderColor: '#38bdf8', borderWidth: 3, pointRadius: 0 }];
                if (compareWith) datasets.push({ label: compareWith.name, data: getPts(compareWith), backgroundColor: 'transparent', borderColor: '#fff', borderWidth: 2, borderDash: [5, 5], pointRadius: 0 });
                else datasets.push({ label: 'Avg', data: [50, 50, 50, 50, 50], backgroundColor: 'transparent', borderColor: 'rgba(255,255,255,0.1)', borderWidth: 1, borderDash: [5, 5], pointRadius: 0 });
                chartInstance = new Chart(ctx, { type: 'radar', data: { labels: ['Scoring', 'Playmaking', 'Efficiency', 'Shot Vol.', 'Def.'], datasets: datasets }, options: { scales: { r: { min:0, max:100, grid: { color: '#1f2d44' }, angleLines: { color: '#1f2d44' }, ticks: { display: false }, pointLabels: { color: '#aab4be', font: { size: 11, weight: 'bold' } } } }, plugins: { legend: { display: false } } } });
            }
            init();
        </script>
    </body>
    </html>
    """)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
