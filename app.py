import pandas as pd
from flask import Flask, render_template_string, jsonify, request, Response
import requests
import os
from datetime import datetime

app = Flask(__name__)

# [기본 데이터 로직 및 팀 컬러 보존]
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
    ts = int(now.timestamp())
    season = "20252026"
    s_reg = fetch_nhl_safe(f"https://api.nhle.com/stats/rest/en/skater/summary?t={ts}", season, "points", 2)
    s_ply = fetch_nhl_safe(f"https://api.nhle.com/stats/rest/en/skater/summary?t={ts}", season, "points", 3)
    g_reg = fetch_nhl_safe(f"https://api.nhle.com/stats/rest/en/goalie/summary?t={ts}", season, "wins", 2)
    g_ply = fetch_nhl_safe(f"https://api.nhle.com/stats/rest/en/goalie/summary?t={ts}", season, "wins", 3)
    today_scorers = get_today_scorers()

    def process_skaters(raw, min_gp):
        if not raw: return []
        processed = []
        for p in raw:
            gp = p.get('gamesPlayed', 0)
            if gp < min_gp: continue
            pts, sh, pm = p.get('points', 0), max(1, p.get('shots', 0)), p.get('plusMinus', 0)
            ppg = round(pts/gp, 2); ir = min(99.9, round((ppg * 40) + ((pts/sh)*25) + (max(0, pm+10)/2) + (gp/10), 1))
            raw_abbr = p.get('teamAbbrevs', p.get('teamAbbrev', ''))
            teams_list = [t.strip().upper() for t in str(raw_abbr).split(',') if t.strip()]
            main_abbr = teams_list[-1] if teams_list else ""
            processed.append({
                "id": str(p.get('playerId')), "name": p.get('skaterFullName'), "type": "skater", 
                "abbr": main_abbr, "pos": p.get('positionCode'), "gp": gp, "pts": pts, "ppg": ppg, "ir": ir, 
                "g": p.get('goals', 0), "a": p.get('assists', 0), "sh": sh, "pm": pm, 
                "team": TEAM_MAP.get(main_abbr, main_abbr), 
                "prob": min(round(((p.get('goals', 0)/gp)*50 + (sh/gp)*10), 1), 95.0), 
                "trending": str(p.get('playerId')) in today_scorers, 
                "col": TEAM_COLORS.get(main_abbr, "#38bdf8")
            })
        processed.sort(key=lambda x: (-x['pts'], x['gp']))
        for i, p in enumerate(processed): p['rank'] = i + 1
        return processed

    def process_goalies(raw, min_gp):
        if not raw: return []
        processed = []
        for p in raw:
            gp = p.get('gamesPlayed', 0)
            if gp < min_gp: continue
            ga, sa, wins = p.get('goalsAgainst', 0), max(1, p.get('shotsAgainst', 0)), p.get('wins', 0)
            sv_val = round((1 - (ga/sa)) * 100, 2) if sa > 0 else 0.0
            gaa = round(ga/gp, 2); ir = min(99.9, round((wins/gp * 40) + (sv_val - 85) * 4 + (5 - gaa) * 2, 1))
            raw_abbr = p.get('teamAbbrevs', p.get('teamAbbrev', ''))
            teams_list = [t.strip().upper() for t in str(raw_abbr).split(',') if t.strip()]
            main_abbr = teams_list[-1] if teams_list else ""
            processed.append({
                "id": str(p.get('playerId')), "name": p.get('goalieFullName'), "type": "goalie", 
                "abbr": main_abbr, "pos": "G", "gp": gp, "w": wins, "sv": sv_val, "gaa": gaa, "ir": ir, 
                "so": p.get('shutouts', 0), "sa": sa, "ga": ga, 
                "team": TEAM_MAP.get(main_abbr, main_abbr), 
                "trending": str(p.get('playerId')) in today_scorers, 
                "col": TEAM_COLORS.get(main_abbr, "#38bdf8")
            })
        processed.sort(key=lambda x: (-x['w'], x['gp']))
        for i, p in enumerate(processed): p['rank'] = i + 1
        return processed

    return jsonify({
        "regular": {"skaters": process_skaters(s_reg, 1), "goalies": process_goalies(g_reg, 1)}, 
        "playoff": {"skaters": process_skaters(s_ply, 1), "goalies": process_goalies(g_ply, 1)}
    })

@app.route('/')
def nhl_dashboard_main():
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>NHL ANALYTICA</title>
        
        <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'><rect width='24' height='24' rx='6' fill='%23030712'/><path d='M12,2L22,7V17L12,22L2,17V7L12,2Z' fill='none' stroke='%2338bdf8' stroke-width='1.5'/><circle cx='12' cy='12' r='3' fill='%2338bdf8'/></svg>" type="image/svg+xml">
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&family=Syncopate:wght@700&display=swap" rel="stylesheet">
        
        <style>
            :root { --accent: #38bdf8; --bg: #030712; --card-bg: rgba(15, 23, 42, 0.7); }
            body { background: var(--bg); color: white; font-family: 'Inter', sans-serif; margin: 0; overflow-x: hidden; }

            header { 
                padding: 15px 5%; background: rgba(3, 7, 18, 0.95); border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 1000;
            }
            .logo { display: flex; align-items: center; gap: 12px; font-family: 'Syncopate'; color: var(--accent); font-size: 1.3rem; text-decoration: none; }
            .logo svg { width: 34px; height: 34px; }
            .search-box { 
                background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); 
                padding: 10px 18px; border-radius: 10px; color: white; width: 280px; outline: none;
            }

            .team-bar { display: flex; gap: 12px; padding: 12px 5%; overflow-x: auto; scrollbar-width: none; }
            .team-logo-btn { width: 40px; height: 40px; cursor: pointer; transition: 0.2s; opacity: 0.3; filter: grayscale(1); flex-shrink: 0; }
            .team-logo-btn.active, .team-logo-btn:hover { opacity: 1; filter: grayscale(0); transform: scale(1.1); }

            .nav-tabs { display: flex; justify-content: center; gap: 40px; padding: 15px 0; }
            .tab-btn { font-family: 'Syncopate'; font-size: 0.75rem; cursor: pointer; color: #475569; border: none; background: none; transition: 0.3s; }
            .tab-btn.active { color: var(--accent); border-bottom: 2px solid var(--accent); }

            /* [사용자 요청 포맷 그대로 유지] */
            .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; padding: 20px 5% 50px; contain: content; }
            .card { 
                background: var(--card-bg); border-radius: 20px; padding: 20px; cursor: pointer;
                border: 1px solid rgba(255, 255, 255, 0.05); position: relative; 
                transform: translateZ(0); will-change: transform; transition: 0.3s;
            }
            .card:hover { transform: translateY(-5px); border-color: var(--accent); background: rgba(30, 41, 59, 0.9); }
            .card::before { content: ""; position: absolute; top: 0; left: 0; width: 4px; height: 100%; background: var(--t-color); border-radius: 20px 0 0 20px; }
            
            .p-header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
            .p-mug { width: 55px; height: 55px; border-radius: 50%; background: #000; border: 1.5px solid rgba(255,255,255,0.05); }
            .p-info-wrap { flex: 1; min-width: 0; }
            .p-name { margin: 0; font-size: 0.95rem; font-weight: 800; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
            .s-tier-badge { background: #fbbf24; color: #000; font-size: 0.55rem; font-weight: 900; padding: 2px 5px; border-radius: 3px; display: inline-block; margin-top: 3px; }

            .rank-tag { position: absolute; top: 12px; left: 15px; background: #000; color: var(--accent); font-size: 0.6rem; font-weight: 900; padding: 2px 6px; border-radius: 4px; border: 1px solid var(--accent); font-family: 'Syncopate'; }
            .live-tag { position: absolute; top: 12px; right: 15px; background: #ef4444; color: white; font-size: 0.55rem; font-weight: 900; padding: 2px 6px; border-radius: 4px; animation: blink 1.2s infinite; }
            @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }

            .ir-display { text-align: right; }
            .ir-display b { font-size: 1.4rem; color: var(--accent); font-family: 'Syncopate'; display: block; line-height: 1; }
            .ir-display small { font-size: 0.5rem; color: #64748b; font-weight: 800; }

            /* [사용자 요청 포맷 그대로 유지: 모달 레이아웃] */
            .modal { display:none; position:fixed; inset:0; background:rgba(0,0,0,0.95); z-index: 2000; align-items: center; justify-content: center; backdrop-filter: blur(10px); }
            .modal-box { 
                background: #0b1426; width: 950px; max-width: 95%; border-radius: 28px; border: 1px solid rgba(255,255,255,0.1);
                display: grid; grid-template-columns: 1fr 1.2fr; overflow: hidden;
            }
            .m-left { padding: 40px; border-right: 1px solid rgba(255,255,255,0.05); text-align: center; }
            .m-right { padding: 40px; background: rgba(0,0,0,0.2); display: flex; align-items: center; justify-content: center; }
            
            .kf-container { background: rgba(56, 189, 248, 0.05); border-radius: 16px; padding: 20px; text-align: left; margin: 20px 0; border: 1px solid rgba(56, 189, 248, 0.1); }
            .kf-title { font-family: 'Syncopate'; font-size: 0.65rem; color: var(--accent); margin-bottom: 15px; display: block; opacity: 0.7; }
            .kf-row { display: flex; justify-content: space-between; margin-bottom: 10px; font-size: 0.9rem; }
            .kf-label { color: #94a3b8; }
            .kf-val { font-weight: 900; }

            .stat-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
            .stat-box { background: #16253d; padding: 12px; border-radius: 12px; text-align: left; border: 1px solid rgba(255,255,255,0.03); }
            .stat-box small { color: #64748b; font-size: 0.55rem; font-weight: 800; display: block; }
            .stat-box b { font-size: 1.1rem; color: #fff; }

            .prob-box { background: #0f172a; border: 1px solid #fbbf24; border-radius: 12px; padding: 20px; margin-top: 15px; text-align: center; }
            .prob-box b { color: #fbbf24; font-size: 2rem; display: block; font-family: 'Syncopate'; }

            #loading { position: fixed; inset: 0; background: #030712; display: flex; justify-content: center; align-items: center; z-index: 9999; color: var(--accent); font-family: 'Syncopate'; font-size: 1rem; }
            canvas#radar { width: 100% !important; height: auto !important; max-width: 400px; }
        </style>
    </head>
    <body>
        <div id="loading">SYNCING_DATA...</div>
        
        <header>
            <a href="/" class="logo">
                <svg viewBox="0 0 24 24"><path d="M21,16.5L12,21.5L3,16.5V7.5L12,2.5L21,7.5V16.5Z" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12,22V12 L21,7.5 M12,12L3,7.5" stroke="currentColor" stroke-width="1.5"/></svg>
                <span>NHL ANALYTICA</span>
            </a>
            <input type="text" id="pSearch" class="search-box" placeholder="Search Player Name..." oninput="render()">
        </header>

        <div class="team-bar" id="team-bar"></div>

        <div class="nav-tabs">
            <button class="tab-btn active" id="reg-tab" onclick="switchMode('regular')">REGULAR</button>
            <button class="tab-btn" id="ply-tab" onclick="switchMode('playoff')">PLAYOFF</button>
            <span style="color:rgba(255,255,255,0.1)">|</span>
            <button class="tab-btn active" id="sk-tab" onclick="switchType('skater')">SKATERS</button>
            <button class="tab-btn" id="go-tab" onclick="switchType('goalie')">GOALIES</button>
        </div>

        <div class="grid" id="main-grid"></div>

        <div id="modal" class="modal" onclick="this.style.display='none'"><div class="modal-box" onclick="event.stopPropagation()"><div class="m-left" id="mInfo"></div><div class="m-right" id="mRight"></div></div></div>

        <script>
            let rawData = null; let mode = 'regular'; let type = 'skater'; let team = null; let chart = null;
            const teams = ["ANA", "BOS", "BUF", "CGY", "CAR", "CHI", "COL", "CBJ", "DAL", "DET", "EDM", "FLA", "LAK", "MIN", "MTL", "NSH", "NJD", "NYI", "NYR", "OTT", "PHI", "PIT", "SJS", "SEA", "STL", "TBL", "TOR", "UTA", "VAN", "VGK", "WSH", "WPG"];

            async function init() {
                try {
                    const res = await fetch('/api/data?t=' + Date.now()); 
                    rawData = await res.json();
                    document.getElementById('loading').style.display = 'none';
                    buildTeamBar(); render();
                } catch (e) { document.getElementById('loading').innerText = "LOAD_ERROR"; }
            }

            function buildTeamBar() {
                document.getElementById('team-bar').innerHTML = teams.map(t => `<img src="https://assets.nhle.com/logos/nhl/svg/${t}_light.svg" class="team-logo-btn" id="btn-${t}" onclick="filterTeam('${t}')">`).join('');
            }

            function filterTeam(t) {
                document.querySelectorAll('.team-logo-btn').forEach(b => b.classList.remove('active'));
                if (team === t) { team = null; } 
                else { team = t; document.getElementById('btn-' + t).classList.add('active'); }
                render();
            }

            function switchMode(m) {
                mode = m;
                document.getElementById('reg-tab').classList.toggle('active', m==='regular');
                document.getElementById('ply-tab').classList.toggle('active', m==='playoff');
                render();
            }

            function switchType(t) {
                type = t;
                document.getElementById('sk-tab').classList.toggle('active', t==='skater');
                document.getElementById('go-tab').classList.toggle('active', t==='goalie');
                render();
            }

            // [성능 최적화: 가상 렌더링으로 랙 제거]
            function render() {
                const query = document.getElementById('pSearch').value.toLowerCase();
                const grid = document.getElementById('main-grid');
                if(!rawData) return;
                
                let data = rawData[mode][type + "s"];
                if (team) data = data.filter(p => p.abbr === team);
                const filtered = data.filter(p => p.name.toLowerCase().includes(query));

                grid.innerHTML = '';
                let idx = 0;
                function draw() {
                    const chunk = filtered.slice(idx, idx + 40);
                    const html = chunk.map(p => `
                        <div class="card" onclick="openModal('${p.id}')" style="--t-color:${p.col}">
                            <div class="rank-tag">#${p.rank}</div>
                            ${p.trending ? '<div class="live-tag">LIVE</div>' : ''}
                            <div class="p-header">
                                <img src="https://assets.nhle.com/mugs/nhl/latest/${p.id}.png" class="p-mug" onerror="this.src='https://assets.nhle.com/logos/nhl/svg/${p.abbr}_light.svg'">
                                <div class="p-info-wrap">
                                    <h3 class="p-name">${p.name}</h3>
                                    ${p.ir >= 90 ? '<span class="s-tier-badge">S-TIER</span>' : ''}
                                </div>
                            </div>
                            <div style="display:flex; justify-content:space-between; align-items:flex-end;">
                                <small style="color:#64748b; font-size:0.7rem; font-weight:700;">${p.type==='skater'?'PTS '+p.pts:'WINS '+p.w}</small>
                                <div class="ir-display"><b>${p.ir}</b><small>IR SCORE</small></div>
                            </div>
                        </div>
                    `).join('');
                    grid.insertAdjacentHTML('beforeend', html);
                    idx += 40; if(idx < filtered.length) requestAnimationFrame(draw);
                }
                draw();
            }

            function openModal(id) {
                const p = rawData[mode][type + "s"].find(x => x.id === id);
                if(!p) return;
                
                let irGrade = p.ir >= 90 ? "ELITE IMPACT" : p.ir >= 75 ? "CORE ASSET" : "AVERAGE";
                let irCol = p.ir >= 90 ? "#fbbf24" : p.ir >= 75 ? "#38bdf8" : "#94a3b8";

                const stats = p.type === 'skater' ? 
                    `<div class="stat-box"><small>GP</small><b>${p.gp}</b></div><div class="stat-box"><small>PPG</small><b>${p.ppg}</b></div><div class="stat-box"><small>G</small><b>${p.g}</b></div><div class="stat-box"><small>A</small><b>${p.a}</b></div><div class="stat-box"><small>+/-</small><b>${p.pm}</b></div><div class="stat-box"><small>SHOTS</small><b>${p.sh}</b></div>` :
                    `<div class="stat-box"><small>GP</small><b>${p.gp}</b></div><div class="stat-box"><small>WINS</small><b>${p.w}</b></div><div class="stat-box"><small>SV%</small><b>${p.sv}</b></div><div class="stat-box"><small>GAA</small><b>${p.gaa}</b></div><div class="stat-box"><small>SO</small><b>${p.so}</b></div><div class="stat-box"><small>SA</small><b>${p.sa}</b></div>`;

                document.getElementById('mInfo').innerHTML = `
                    <div style="font-size:0.7rem; color:var(--accent); font-weight:900; margin-bottom:10px; font-family:'Syncopate';">RANK #${p.rank}</div>
                    <img src="https://assets.nhle.com/mugs/nhl/latest/${p.id}.png" style="width:140px; border-radius:50%; border:4px solid ${p.col}; background:#000;">
                    <h2 style="font-family:'Syncopate'; margin:15px 0 10px; font-size:1.6rem; letter-spacing:-1px;">${p.name.toUpperCase()}</h2>
                    <div style="background:${p.col}; padding:5px 14px; border-radius:8px; font-weight:900; font-size:0.8rem; display:inline-block; margin-bottom:20px;">${p.team.toUpperCase()}</div>
                    
                    <div class="kf-container">
                        <span class="kf-title">KEY ANALYTICS</span>
                        <div class="kf-row"><span class="kf-label">Impact Assessment</span><span class="kf-val" style="color:${irCol}">${irGrade}</span></div>
                        <div class="kf-row"><span class="kf-label">Recent Scoring</span><span class="kf-val" style="color:${p.ppg>=0.8?'#ef4444':'#38bdf8'}">${p.ppg>=0.8?'HOT':'STABLE'}</span></div>
                    </div>

                    <div class="stat-grid">${stats}</div>
                    <div class="prob-box"><small style="font-weight:900; color:#fbbf24;">EXPECTED IMPACT PROBABILITY</small><b>${p.prob || p.so || 0}%</b></div>`;
                
                document.getElementById('mRight').innerHTML = `<canvas id="radar"></canvas>`;
                document.getElementById('modal').style.display = 'flex';
                drawRadar(p);
            }

            // [그래프 수정: 튀어나가지 않도록 정규화 및 고정 눈금 적용]
            function drawRadar(p) {
                const ctx = document.getElementById('radar').getContext('2d');
                if(chart) chart.destroy();

                const normalize = (val, max) => Math.min(100, Math.max(0, (val / max) * 100));
                const labels = p.type === 'skater' ? ['GOALS', 'POINTS', 'PPG', 'DEFENSE', 'IMPACT'] : ['WINS', 'SV%', 'GAA', 'SHUTOUT', 'IMPACT'];
                
                const skaterVals = [
                    normalize(p.g, 60), normalize(p.pts, 140), normalize(p.ppg, 1.8), normalize(p.pm + 30, 60), p.ir
                ];
                const goalieVals = [
                    normalize(p.w, 45), normalize(p.sv - 85, 10), normalize(4.5 - p.gaa, 2.5), normalize(p.so, 8), p.ir
                ];

                chart = new Chart(ctx, {
                    type: 'radar',
                    data: {
                        labels,
                        datasets: [{
                            data: p.type === 'skater' ? skaterVals : goalieVals,
                            backgroundColor: 'rgba(56, 189, 248, 0.25)',
                            borderColor: '#38bdf8',
                            borderWidth: 3,
                            pointRadius: 0
                        }]
                    },
                    options: {
                        scales: {
                            r: {
                                min: 0,
                                max: 100, // 눈금을 100으로 고정하여 튀어나가기 원천 방지
                                beginAtZero: true,
                                grid: { color: 'rgba(255,255,255,0.05)' },
                                angleLines: { color: 'rgba(255,255,255,0.05)' },
                                ticks: { display: false },
                                pointLabels: { color: '#64748b', font: { family: 'Syncopate', size: 9, weight: 'bold' } }
                            }
                        },
                        plugins: { legend: { display: false } }
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
