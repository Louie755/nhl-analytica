import pandas as pd
from flask import Flask, render_template_string, jsonify, request, Response
import requests
import os
from datetime import datetime

app = Flask(__name__)

# 팀 데이터 및 컬러 설정
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

@app.route('/sitemap.xml')
def sitemap_xml_route():
    host_root = request.host_url
    now_date = datetime.now().strftime('%Y-%m-%d')
    sitemap_data = f"""<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <url><loc>{host_root}</loc><lastmod>{now_date}</lastmod><priority>1.0</priority></url>
    </urlset>"""
    return Response(sitemap_data, mimetype='application/xml')

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
        <meta name="description" content="NHL Analytica: 최첨단 Impact Rating(IR) 지표로 분석하는 실시간 NHL 선수 통계 및 데이터 시각화 플랫폼.">
        <title>NHL ANALYTICA</title>
        
        <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'><rect width='24' height='24' rx='5' fill='%23030712'/><path d='M12,2L22,7V17L12,22L2,17V7L12,2Z' fill='none' stroke='%2338bdf8' stroke-width='1.5'/><circle cx='12' cy='12' r='3' fill='%2338bdf8'/><path d='M12,8V16M8,12H16' stroke='white' stroke-width='1' stroke-linecap='round'/></svg>" type="image/svg+xml">
        <link rel="apple-touch-icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'><rect width='24' height='24' rx='5' fill='%23030712'/><path d='M12,2L22,7V17L12,22L2,17V7L12,2Z' fill='none' stroke='%2338bdf8' stroke-width='1.5'/><circle cx='12' cy='12' r='3' fill='%2338bdf8'/></svg>">

        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&family=Syncopate:wght@700&display=swap" rel="stylesheet">
        
        <style>
            :root { --accent: #38bdf8; --bg: #030712; --card: rgba(15, 23, 42, 0.75); }
            body { background: #030712; color: white; font-family: 'Inter', sans-serif; margin: 0; overflow-x: hidden; }
            
            /* [성능 최적화: Blur 연산 제거 및 GPU 가속] */
            header { padding: 20px 5%; background: #030712; border-bottom: 1px solid rgba(255,255,255,0.1); display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 1000; transform: translateZ(0); }
            .logo { display: flex; align-items: center; gap: 12px; font-family: 'Syncopate'; color: var(--accent); font-size: 1.5rem; text-decoration: none; }
            .logo svg { width: 38px; height: 38px; }
            
            .search-box { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); padding: 12px 20px; border-radius: 12px; color: white; width: 300px; outline: none; transition: 0.3s; }
            .search-box:focus { border-color: var(--accent); background: rgba(255,255,255,0.1); }
            
            .team-bar { display: flex; gap: 15px; padding: 15px 5%; overflow-x: auto; background: #030712; border-bottom: 1px solid rgba(255,255,255,0.05); scrollbar-width: none; }
            .team-logo-btn { width: 45px; height: 45px; cursor: pointer; transition: 0.2s; opacity: 0.3; filter: grayscale(1); flex-shrink: 0; }
            .team-logo-btn:hover, .team-logo-btn.active { opacity: 1; filter: grayscale(0); transform: scale(1.1); }
            
            .nav-tabs { display: flex; justify(content: center; gap: 40px; padding: 20px 0; background: #030712; }
            .tab-btn { font-family: 'Syncopate'; font-size: 0.8rem; cursor: pointer; color: #475569; border: none; background: none; transition: 0.3s; }
            .tab-btn.active { color: var(--accent); border-bottom: 2px solid var(--accent); }
            
            /* [2. UI 업그레이드: Glassmorphism & S-TIER 레이아웃] */
            .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px; padding: 30px 5%; min-height: 80vh; contain: content; }
            .card { 
                background: var(--card); 
                border-radius: 20px; 
                padding: 20px; 
                cursor: pointer; 
                border: 1px solid rgba(255,255,255,0.05); 
                transition: 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275); 
                position: relative; 
                transform: translateZ(0); 
                will-change: transform;
                contain: layout paint;
            }
            .card:hover { transform: translateY(-5px); border-color: var(--accent); background: rgba(30, 41, 59, 0.9); }
            .card::before { content: ""; position: absolute; top: 0; left: 0; width: 4px; height: 100%; background: var(--t-color); border-radius: 20px 0 0 20px; }
            
            /* [전문가형 레이아웃: 이름과 뱃지가 겹치지 않음] */
            .p-header { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 5px; }
            .p-name { margin: 0; font-size: 1rem; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 140px; }
            .s-tier-badge { background: rgba(251, 191, 36, 0.1); color: #fbbf24; border: 1px solid #fbbf24; font-size: 0.6rem; font-weight: 900; padding: 2px 6px; border-radius: 4px; white-space: nowrap; flex-shrink: 0; }

            .rank-tag { position: absolute; top: 12px; left: 15px; background: #000; color: var(--accent); font-size: 0.65rem; font-weight: 900; padding: 2px 6px; border-radius: 4px; z-index: 5; font-family: 'Syncopate'; border: 1px solid var(--accent); }
            .live-tag { position: absolute; top: 12px; right: 15px; background: #ef4444; color: white; font-size: 0.6rem; font-weight: 900; padding: 2px 6px; border-radius: 4px; z-index: 5; animation: blink 1.2s infinite; }
            @keyframes blink { 0% { opacity: 1; } 50% { opacity: 0.4; } 100% { opacity: 1; } }
            
            /* [3. 전문적 모달: 박스 형태 및 시각화 강화] */
            .modal { display:none; position:fixed; z-index:2000; left:0; top:0; width:100%; height:100%; background:rgba(0,0,0,0.92); }
            .modal-box { background: #0b1426; width: 950px; max-width: 95%; margin: 6vh auto; border-radius: 25px; border: 1px solid #1f3a52; display: grid; grid-template-columns: 1fr 1.2fr; overflow: hidden; box-shadow: 0 0 50px rgba(0,0,0,0.8); }
            .m-left { padding: 40px; border-right: 1px solid rgba(255,255,255,0.05); text-align: center; overflow-y: auto; max-height: 80vh; }
            .m-right { padding: 40px; display: flex; align-items: center; justify-content: center; position: relative; }
            
            .stat-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 20px 0; }
            .stat-box { background: #16253d; padding: 12px; border-radius: 12px; text-align: left; border: 1px solid rgba(255,255,255,0.03); }
            .stat-box small { color: #64748b; font-size: 0.55rem; font-weight: 800; text-transform: uppercase; display: block; margin-bottom: 4px; }
            .stat-box b { font-size: 1.2rem; color: #fff; }
            
            /* Key Factors: 이미지 기반으로 구현한 전문가형 박스 */
            .kf-box { background: #16253d; border-radius: 12px; padding: 20px; text-align: left; margin-bottom: 15px; border: 1px solid #1f3a52; }
            .kf-title { font-family: 'Syncopate'; font-size: 0.7rem; color: var(--accent); margin-bottom: 15px; display: block; }
            .kf-row { display: flex; justify-content: space-between; margin-bottom: 10px; font-size: 0.9rem; }
            .kf-label { color: #aab4be; font-weight: 500; }
            .kf-val { font-weight: 800; }

            .prob-box { background: #0f172a; border: 1px solid #fbbf24; border-radius: 12px; padding: 20px; margin-top: 15px; text-align: center; }
            .prob-box b { color: #fbbf24; font-size: 2.5rem; display: block; font-family: 'Syncopate'; }
            
            #loading { position: fixed; inset: 0; background: #030712; display: flex; justify-content: center; align-items: center; z-index: 9999; color: var(--accent); font-family: 'Syncopate'; font-size: 1.2rem; }
            .yt-hook-btn { position: fixed; bottom: 20px; right: 20px; background: var(--accent); color: #000; border: none; padding: 12px 24px; border-radius: 30px; font-weight: 900; font-family: 'Syncopate'; font-size: 10px; cursor: pointer; z-index: 5000; }
        </style>
    </head>
    <body>
        <div id="loading">SYNCING_DATA...</div>
        <header>
            <a href="/" class="logo">
                <svg viewBox="0 0 24 24"><path d="M21,16.5L12,21.5L3,16.5V7.5L12,2.5L21,7.5V16.5Z" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M12,22V12 L21,7.5 M12,12L3,7.5" stroke="currentColor" stroke-width="1"/></svg>
                <span>NHL ANALYTICA</span>
            </a>
            <input type="text" id="pSearch" class="search-box" placeholder="Search Player Name..." oninput="render()">
        </header>
        <div class="team-bar" id="team-bar"></div>
        <div class="nav-tabs">
            <button class="tab-btn active" id="regular-mode" onclick="switchMode('regular')">REGULAR</button>
            <button class="tab-btn" id="playoff-mode" onclick="switchMode('playoff')">PLAYOFF</button>
            <span style="color:rgba(255,255,255,0.1)">|</span>
            <button class="tab-btn active" id="skater-tab" onclick="switchType('skater')">SKATERS</button>
            <button class="tab-btn" id="goalie-tab" onclick="switchType('goalie')">GOALIES</button>
        </div>
        <div class="grid" id="main-grid"></div>
        <div id="modal" class="modal" onclick="this.style.display='none'"><div class="modal-box" onclick="event.stopPropagation()"><div class="m-left" id="mInfo"></div><div class="m-right" id="mRight"></div></div></div>
        
        <button class="yt-hook-btn" onclick="generateHook()">GET YT HOOK</button>

        <script>
            let rawData = null; let currentMode = 'regular'; let currentType = 'skater'; 
            let currentTeam = null; let chartInstance = null;
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
                const bar = document.getElementById('team-bar');
                bar.innerHTML = teams.map(t => `<img src="https://assets.nhle.com/logos/nhl/svg/${t}_light.svg" class="team-logo-btn" id="btn-${t}" onclick="filterByTeam('${t}')">`).join('');
            }

            function filterByTeam(team) {
                document.querySelectorAll('.team-logo-btn').forEach(b => b.classList.remove('active'));
                if (currentTeam === team) { currentTeam = null; } 
                else { currentTeam = team; document.getElementById('btn-' + team).classList.add('active'); }
                render();
            }

            function switchMode(mode) {
                currentMode = mode;
                document.getElementById('regular-mode').classList.toggle('active', mode === 'regular');
                document.getElementById('playoff-mode').classList.toggle('active', mode === 'playoff');
                render();
            }

            function switchType(type) {
                currentType = type;
                document.getElementById('skater-tab').classList.toggle('active', type === 'skater');
                document.getElementById('goalie-tab').classList.toggle('active', type === 'goalie');
                render();
            }

            // [성능 최적화: Chunked 렌더링으로 랙 원천 차단]
            function render() {
                const query = document.getElementById('pSearch').value.toLowerCase();
                const grid = document.getElementById('main-grid'); if(!rawData) return;
                let data = rawData[currentMode][currentType + "s"];
                
                if (currentTeam) data = data.filter(p => p.abbr === currentTeam);
                const filtered = data.filter(p => p.name.toLowerCase().includes(query));

                grid.innerHTML = '';
                let idx = 0;
                function draw() {
                    const chunk = filtered.slice(idx, idx + 40);
                    const html = chunk.map(p => {
                        const trend = p.trending ? '▲' : '';
                        const subInfo = p.type === 'skater' ? `• G ${p.g} • PPG ${p.ppg}` : `• G ${p.gp} • SV% ${p.sv}`;
                        const sTier = p.ir >= 90 ? '<span class="s-tier-badge">S-TIER</span>' : '';

                        return `
                        <div class="card" onclick="openModal('${p.id}')" style="--t-color:${p.col}">
                            <div class="rank-tag">#${p.rank}</div>
                            ${p.trending ? '<div class="live-tag">LIVE</div>' : ''}
                            <div style="display:flex; align-items:center; gap:15px; margin-top:10px;">
                                <img src="https://assets.nhle.com/mugs/nhl/latest/${p.id}.png" style="width:60px; border-radius:50%; background:#000;" onerror="this.src='https://assets.nhle.com/logos/nhl/svg/${p.abbr}_light.svg'">
                                <div style="flex:1; min-width:0;">
                                    <div class="p-header">
                                        <h3 class="p-name">${p.name}</h3>
                                        ${sTier}
                                    </div>
                                    <small style="color:#64748b; font-size:0.7rem;">${subInfo}</small>
                                </div>
                                <div style="text-align:right;"><b style="color:var(--accent); font-size:1.3rem;">${p.type==='skater'?p.pts:p.w}</b><br><small style="font-size:0.5rem; color:#475569;">${p.type==='skater'?'PTS':'WINS'}</small></div>
                            </div>
                        </div>`;
                    }).join('');
                    grid.insertAdjacentHTML('beforeend', html);
                    idx += 40; if(idx < filtered.length) requestAnimationFrame(draw);
                }
                draw();
            }

            function openModal(id) {
                const p = rawData[currentMode][currentType + "s"].find(x => x.id === id);
                if(!p) return;
                
                let irGrade = p.ir >= 90 ? "Elite" : p.ir >= 75 ? "Above Average" : p.ir >= 60 ? "Average" : "Below Average";
                let irCol = p.ir >= 90 ? "#fbbf24" : p.ir >= 75 ? "#f1c40f" : p.ir >= 60 ? "#2ecc71" : "#aab4be";

                const stats = p.type === 'skater' ? 
                    `<div class="stat-box"><small>GP</small><b>${p.gp}</b></div><div class="stat-box"><small>PTS</small><b>${p.pts}</b></div><div class="stat-box"><small>PPG</small><b>${p.ppg}</b></div><div class="stat-box"><small>G</small><b>${p.g}</b></div><div class="stat-box"><small>A</small><b>${p.a}</b></div><div class="stat-box"><small>+/-</small><b>${p.pm}</b></div>` :
                    `<div class="stat-box"><small>GP</small><b>${p.gp}</b></div><div class="stat-box"><small>WINS</small><b>${p.w}</b></div><div class="stat-box"><small>SV%</small><b>${p.sv}</b></div><div class="stat-box"><small>GAA</small><b>${p.gaa}</b></div><div class="stat-box"><small>SO</small><b>${p.so}</b></div><div class="stat-box"><small>SA</small><b>${p.sa}</b></div>`;

                document.getElementById('mInfo').innerHTML = `
                    <img src="https://assets.nhle.com/mugs/nhl/latest/${p.id}.png" style="width:140px; border-radius:50%; border:4px solid ${p.col};">
                    <h2 style="font-family:'Syncopate'; margin:15px 0 10px;">${p.name.toUpperCase()}</h2>
                    <div style="background:${p.col}; padding:6px 14px; border-radius:8px; font-weight:800; font-size:0.85rem; margin-bottom:20px; display:inline-block;">${p.team}</div>
                    
                    <div class="kf-box">
                        <span class="kf-title">Key Factors</span>
                        <div class="kf-row"><span class="kf-label">Recent Form</span><span class="kf-val" style="color:${p.ppg>=0.7?'#ff6b6b':'#38bdf8'}">${p.ppg>=0.7?'Hot':'Cold'} ▲</span></div>
                        <div class="kf-row"><span class="kf-label">Impact Rating</span><span class="kf-val" style="color:${irCol}">${irGrade} ▲</span></div>
                        <div class="kf-row"><span class="kf-label">Opponent Defense</span><span class="kf-val" style="color:${p.rank%2===0?'#e74c3c':'#f1c40f'}">${p.rank%2===0?'Weak':'Strong'} ▲</span></div>
                    </div>

                    <div class="stat-grid">${stats}</div>
                    <div class="prob-box"><small style="font-weight:900; color:#fbbf24;">IMPACT PROBABILITY</small><b>${p.prob || p.so || 0}%</b></div>`;
                
                document.getElementById('mRight').innerHTML = `<canvas id="radar"></canvas>`;
                document.getElementById('modal').style.display = 'block';
                drawRadar(p);
            }

            function drawRadar(p) {
                const ctx = document.getElementById('radar').getContext('2d');
                if(chartInstance) chartInstance.destroy();
                const data = p.type==='skater' ? [p.g*5, p.pts, p.ppg*50, 70, p.ir] : [p.w*5, p.sv, 70, 50, p.ir];
                chartInstance = new Chart(ctx, {
                    type: 'radar',
                    data: { labels: ['Scoring', 'Points', 'PPG', 'Defensive', 'Impact'], datasets: [{ data, backgroundColor: 'rgba(56, 189, 248, 0.2)', borderColor: '#38bdf8', borderWidth: 2, pointRadius: 0 }] },
                    options: { scales: { r: { min: 0, max: 100, grid: { color: '#1e293b' }, angleLines: { color: '#1e293b' }, ticks: { display: false }, pointLabels: { color: '#64748b', font: { weight: 'bold' } } } }, plugins: { legend: { display: false } } }
                });
            }

            function generateHook() {
                const first = document.querySelector('.p-name');
                const ir = document.querySelector('.card b').innerText;
                alert(`[Ice Analytics Hook]\\n"현재 IR 지표 ${ir}점, ${first.innerText}가 이번 시즌 왜 '언터처블'인지 숫자로 증명합니다."`);
            }

            init();

            // [성능 최적화: 스크롤 시 포인터 이벤트 제어]
            let isScrolling;
            window.addEventListener('scroll', () => {
                window.clearTimeout(isScrolling);
                document.body.style.pointerEvents = 'none';
                isScrolling = setTimeout(() => {
                    document.body.style.pointerEvents = 'auto';
                }, 100);
            }, { passive: true });
        </script>
    </body>
    </html>
    """)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
