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
        <meta name="description" content="NHL Analytica: 최첨단 Impact Rating(IR) 지표로 분석하는 실시간 NHL 선수 통계 및 데이터 시각화 플랫폼.">
        <title>NHL ANALYTICA</title>
        <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'><path d='M21,16.5C21,16.88 20.79,17.21 20.47,17.38L12.57,21.82C12.41,21.94 12.21,22 12,22C11.79,22 11.59,21.94 11.43,21.82L3.53,17.38C3.21,17.21 3,16.88 3,16.5V7.5C3,7.12 3.21,6.79 3.53,6.62L11.43,2.18C11.59,2.06 11.79,2 12,2C12.21,2 12.41,2.06 12.57,2.18L20.47,6.62C20.79,6.79 21,7.12 21,7.5V16.5Z' fill='none' stroke='%2338bdf8' stroke-width='1.5'/><path d='M12,22V12 L20.47,7.38 M12,12L3.53,7.38' stroke='%2338bdf8' stroke-width='1.2'/><path d='M18,15V11.5' stroke='%23fff' stroke-width='1.8' stroke-linecap='round'/><path d='M15,15V13' stroke='%23fff' stroke-width='1.8' stroke-linecap='round'/><path d='M12,15V12.5' stroke='%23fff' stroke-width='1.8' stroke-linecap='round'/></svg>" type="image/svg+xml">
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&family=Syncopate:wght@700&display=swap" rel="stylesheet">
        <style>
            :root { --accent: #38bdf8; --bg: #030712; --card: rgba(15, 23, 42, 0.8); }
            body { background: #030712; color: white; font-family: 'Inter', sans-serif; margin: 0; overflow-x: hidden; }
            header { padding: 20px 5%; background: rgba(3,7,18,0.98); border-bottom: 1px solid rgba(255,255,255,0.1); display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 1000; }
            .logo { display: flex; align-items: center; gap: 12px; font-family: 'Syncopate'; color: var(--accent); font-size: 1.5rem; text-decoration: none; }
            .logo svg { width: 38px; height: 38px; }
            .search-box { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); padding: 12px 20px; border-radius: 12px; color: white; width: 300px; outline: none; transition: 0.3s; }
            .search-box:focus { border-color: var(--accent); background: rgba(255,255,255,0.1); }
            .team-bar { display: flex; gap: 12px; padding: 12px 5%; overflow-x: auto; background: #030712; border-bottom: 1px solid rgba(255,255,255,0.05); scrollbar-width: none; }
            .team-bar::-webkit-scrollbar { display: none; }
            .team-logo-btn { width: 40px; height: 40px; cursor: pointer; transition: 0.2s; opacity: 0.3; filter: grayscale(1); flex-shrink: 0; }
            .team-logo-btn:hover, .team-logo-btn.active { opacity: 1; filter: grayscale(0); transform: scale(1.1); }
            .nav-tabs { display: flex; justify-content: center; gap: 40px; padding: 20px 0; background: #030712; }
            .tab-btn { font-family: 'Syncopate'; font-size: 0.75rem; cursor: pointer; color: #475569; border: none; background: none; transition: 0.3s; }
            .tab-btn.active { color: var(--accent); border-bottom: 2px solid var(--accent); }
            
            /* [성능 최적화] 레이아웃 격리 및 GPU 가속 */
            .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px; padding: 30px 5%; contain: content; }
            .card { 
                background: var(--card); 
                border-radius: 16px; 
                padding: 16px; 
                cursor: pointer; 
                border: 1px solid rgba(255,255,255,0.05); 
                position: relative; 
                transform: translateZ(0); /* GPU 가속 강제 */
                will-change: transform;
                contain: layout paint;
                transition: 0.2s;
            }
            .card:hover { transform: translateY(-4px); border-color: var(--accent); background: rgba(31, 41, 55, 0.9); }
            .card::before { content: ""; position: absolute; top: 0; left: 0; width: 4px; height: 100%; background: var(--t-color); border-radius: 16px 0 0 16px; }
            
            .rank-tag { position: absolute; top: 12px; left: 15px; background: #000; color: var(--accent); font-size: 0.6rem; font-weight: 900; padding: 2px 6px; border-radius: 4px; border: 1px solid var(--accent); font-family: 'Syncopate'; }
            .live-tag { position: absolute; top: 12px; right: 15px; background: #ef4444; color: white; font-size: 0.55rem; font-weight: 900; padding: 2px 6px; border-radius: 4px; animation: blink 1.2s infinite; }
            @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
            
            .modal { display:none; position:fixed; z-index:2000; left:0; top:0; width:100%; height:100%; background:rgba(0,0,0,0.9); }
            .modal-box { background: #0b1426; width: 900px; max-width: 95%; margin: 6vh auto; border-radius: 25px; border: 1px solid #1f3a52; display: grid; grid-template-columns: 1fr 1.2fr; overflow: hidden; }
            .m-left { padding: 40px; border-right: 1px solid rgba(255,255,255,0.05); text-align: center; overflow-y: auto; max-height: 85vh; }
            .m-right { padding: 40px; display: flex; flex-direction: column; align-items: center; justify-content: center; position: relative; }
            
            .stat-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 20px 0; }
            .stat-box { background: #16253d; padding: 12px; border-radius: 12px; text-align: left; }
            .stat-box small { color: #64748b; font-size: 0.55rem; font-weight: 800; text-transform: uppercase; display: block; }
            .stat-box b { font-size: 1.1rem; color: #fff; }
            
            .prob-box { background: #0f172a; border: 1px solid #fbbf24; border-radius: 12px; padding: 20px; margin-top: 15px; text-align: center; }
            .prob-box b { color: #fbbf24; font-size: 2.5rem; display: block; font-family: 'Syncopate'; }

            .yt-helper-btn { position: fixed; bottom: 20px; right: 20px; background: var(--accent); color: #000; border: none; padding: 12px 20px; border-radius: 30px; font-weight: 900; font-family: 'Syncopate'; font-size: 10px; cursor: pointer; z-index: 5000; }
            #loading { position: fixed; inset: 0; background: #030712; display: flex; flex-direction: column; justify-content: center; align-items: center; z-index: 9999; color: var(--accent); }
            .spinner { width: 40px; height: 40px; border: 4px solid rgba(56, 189, 248, 0.1); border-top: 4px solid var(--accent); border-radius: 50%; animation: spin 1s linear infinite; margin-bottom: 20px; }
            @keyframes spin { 100% { transform: rotate(360deg); } }
        </style>
    </head>
    <body>
        <div id="loading"><div class="spinner"></div><h1 style="font-family:'Syncopate'; font-size:1rem;">SYNCING_DATA</h1></div>
        
        <header>
            <a href="/" class="logo">
                <svg viewBox="0 0 24 24"><path d="M21,16.5L12,21.5L3,16.5V7.5L12,2.5L21,7.5V16.5Z" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M12,22V12L21,7.5" stroke="currentColor" stroke-width="1"/><path d="M12,12L3,7.5" stroke="currentColor" stroke-width="1"/></svg>
                <span>NHL ANALYTICA</span>
            </a>
            <input type="text" id="pSearch" class="search-box" placeholder="Search Player Name..." oninput="debounceRender()">
        </header>

        <div class="team-bar" id="team-bar"></div>

        <div class="nav-tabs">
            <button class="tab-btn active" id="regular-mode" onclick="switchMode('regular')">REGULAR</button>
            <button class="tab-btn" id="playoff-mode" onclick="switchMode('playoff')">PLAYOFF</button>
            <button class="tab-btn active" id="skater-tab" onclick="switchType('skater')">SKATERS</button>
            <button class="tab-btn" id="goalie-tab" onclick="switchType('goalie')">GOALIES</button>
        </div>

        <div class="grid" id="main-grid"></div>

        <div id="modal" class="modal" onclick="closeModal()"><div class="modal-box" onclick="event.stopPropagation()"><div class="m-left" id="mInfo"></div><div class="m-right" id="mRight"></div></div></div>
        
        <button class="yt-helper-btn" onclick="generateScript()">GET YT HOOK</button>

        <script>
            let rawData = null; let currentMode = 'regular'; let currentType = 'skater'; 
            let currentTeam = null; let chartInstance = null;
            const teams = ["ANA", "BOS", "BUF", "CGY", "CAR", "CHI", "COL", "CBJ", "DAL", "DET", "EDM", "FLA", "LAK", "MIN", "MTL", "NSH", "NJD", "NYI", "NYR", "OTT", "PHI", "PIT", "SJS", "SEA", "STL", "TBL", "TOR", "UTA", "VAN", "VGK", "WSH", "WPG"];

            // [성능] 데이터 캐싱 및 API 비동기 로드
            async function init() {
                try {
                    const res = await fetch('/api/data?t=' + Date.now()); 
                    rawData = await res.json();
                    document.getElementById('loading').style.display = 'none';
                    buildTeamBar();
                    render();
                } catch (e) { document.getElementById('loading').innerHTML = "<h1>LOAD_ERROR</h1>"; }
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

            function switchMode(m) {
                currentMode = m;
                document.getElementById('regular-mode').classList.toggle('active', m==='regular');
                document.getElementById('playoff-mode').classList.toggle('active', m==='playoff');
                render();
            }

            function switchType(t) {
                currentType = t;
                document.getElementById('skater-tab').classList.toggle('active', t==='skater');
                document.getElementById('goalie-tab').classList.toggle('active', t==='goalie');
                render();
            }

            // [성능] 디바운싱 적용 (검색 시 랙 방지)
            let renderTimer;
            function debounceRender() {
                clearTimeout(renderTimer);
                renderTimer = setTimeout(render, 150);
            }

            // [성능] 가상 렌더링 방식 적용 (한번에 40개씩 끊어서 렌더링)
            function render() {
                const grid = document.getElementById('main-grid');
                if(!rawData) return;
                
                const query = document.getElementById('pSearch').value.toLowerCase();
                let data = rawData[currentMode][currentType + "s"];
                if (currentTeam) data = data.filter(p => p.abbr === currentTeam);
                const filtered = data.filter(p => p.name.toLowerCase().includes(query));

                grid.innerHTML = '';
                let idx = 0;
                function drawChunk() {
                    const chunk = filtered.slice(idx, idx + 40);
                    const html = chunk.map(p => `
                        <div class="card" onclick="openModal('${p.id}')" style="--t-color:${p.col}">
                            <div class="rank-tag">#${p.rank}</div>
                            ${p.trending ? '<div class="live-tag">LIVE</div>' : ''}
                            <div style="display:flex; align-items:center; gap:12px; margin-top:10px;">
                                <img src="https://assets.nhle.com/mugs/nhl/latest/${p.id}.png" style="width:50px; border-radius:50%; background:#000;" onerror="this.src='https://assets.nhle.com/logos/nhl/svg/${p.abbr}_light.svg'">
                                <div style="flex:1; min-width:0;">
                                    <h3 style="margin:0; font-size:0.9rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${p.name}</h3>
                                    <small style="color:#64748b; font-size:0.7rem;">${p.type==='skater'?'PTS '+p.pts:'WINS '+p.w}</small>
                                </div>
                                <div style="text-align:right;"><b style="color:var(--accent); font-size:1.2rem;">${p.ir}</b><br><small style="font-size:0.5rem; color:#475569;">IR</small></div>
                            </div>
                        </div>
                    `).join('');
                    grid.insertAdjacentHTML('beforeend', html);
                    idx += 40;
                    if(idx < filtered.length) requestAnimationFrame(drawChunk);
                }
                drawChunk();
            }

            function openModal(id) {
                const p = rawData[currentMode][currentType + "s"].find(x => x.id === id);
                if(!p) return;
                
                const stats = p.type === 'skater' ? 
                    `<div class="stat-box"><small>GP</small><b>${p.gp}</b></div><div class="stat-box"><small>G</small><b>${p.g}</b></div><div class="stat-box"><small>A</small><b>${p.a}</b></div><div class="stat-box"><small>PTS</small><b>${p.pts}</b></div><div class="stat-box"><small>PPG</small><b>${p.ppg}</b></div><div class="stat-box"><small>IR</small><b style="color:var(--accent)">${p.ir}</b></div>` :
                    `<div class="stat-box"><small>GP</small><b>${p.gp}</b></div><div class="stat-box"><small>W</small><b>${p.w}</b></div><div class="stat-box"><small>SV%</small><b>${p.sv}</b></div><div class="stat-box"><small>GAA</small><b>${p.gaa}</b></div><div class="stat-box"><small>SO</small><b>${p.so}</b></div><div class="stat-box"><small>IR</small><b style="color:var(--accent)">${p.ir}</b></div>`;

                document.getElementById('mInfo').innerHTML = `
                    <img src="https://assets.nhle.com/mugs/nhl/latest/${p.id}.png" style="width:140px; border-radius:50%; border:4px solid ${p.col};">
                    <h2 style="font-family:'Syncopate'; margin:15px 0 5px;">${p.name.toUpperCase()}</h2>
                    <div style="background:${p.col}; padding:4px 12px; border-radius:6px; font-weight:800; font-size:0.8rem; display:inline-block; margin-bottom:20px;">${p.team}</div>
                    <div class="stat-grid">${stats}</div>
                    <div class="prob-box"><small style="font-weight:900; color:#fbbf24; text-transform:uppercase;">Impact Probability</small><b>${p.prob || 0}%</b></div>`;
                
                document.getElementById('mRight').innerHTML = `<canvas id="radar" style="max-width:350px;"></canvas>`;
                document.getElementById('modal').style.display = 'block';
                drawRadar(p);
            }

            function closeModal() { document.getElementById('modal').style.display = 'none'; }

            function drawRadar(p) {
                const ctx = document.getElementById('radar').getContext('2d');
                if(chartInstance) chartInstance.destroy();
                const labels = p.type==='skater' ? ['Scoring', 'Points', 'PPG', 'Efficiency', 'Impact'] : ['Wins', 'Save%', 'GAA', 'Shutout', 'Impact'];
                const data = p.type==='skater' ? [p.g*5, p.pts, p.ppg*50, (p.pts/p.sh)*100, p.ir] : [p.w*5, p.sv, (4-p.gaa)*25, p.so*20, p.ir];
                
                chartInstance = new Chart(ctx, {
                    type: 'radar',
                    data: { labels, datasets: [{ data, backgroundColor: 'rgba(56, 189, 248, 0.2)', borderColor: '#38bdf8', borderWidth: 2, pointRadius: 0 }] },
                    options: { scales: { r: { min: 0, max: 100, grid: { color: 'rgba(255,255,255,0.05)' }, angleLines: { color: 'rgba(255,255,255,0.05)' }, ticks: { display: false } } }, plugins: { legend: { display: false } } }
                });
            }

            function generateScript() {
                const first = document.querySelector('.card h3');
                if(!first) return;
                const name = first.innerText;
                const ir = document.querySelector('.card b').innerText;
                alert(`[Ice Analytics Script Hook]\\n\\n"오늘 분석할 선수는 ${name}입니다. 현재 IR 지표 ${ir}점, 왜 이 수치가 리그 탑 수준인지 숫자로 증명해 드립니다."`);
            }

            init();
        </script>
    </body>
    </html>
    """)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
