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
        <title>NHL ANALYTICA</title>
        
        <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'><path d='M21,16.5C21,16.88 20.79,17.21 20.47,17.38L12.57,21.82C12.41,21.94 12.21,22 12,22C11.79,22 11.59,21.94 11.43,21.82L3.53,17.38C3.21,17.21 3,16.88 3,16.5V7.5C3,7.12 3.21,6.79 3.53,6.62L11.43,2.18C11.59,2.06 11.79,2 12,2C12.21,2 12.41,2.06 12.57,2.18L20.47,6.62C20.79,6.79 21,7.12 21,7.5V16.5Z' fill='none' stroke='%2338bdf8' stroke-width='1.5'/><path d='M12,22V12 L20.47,7.38 M12,12L3.53,7.38' stroke='%2338bdf8' stroke-width='1.2'/><path d='M18,15V11.5' stroke='%23fff' stroke-width='1.8' stroke-linecap='round'/><path d='M15,15V13' stroke='%23fff' stroke-width='1.8' stroke-linecap='round'/><path d='M12,15V12.5' stroke='%23fff' stroke-width='1.8' stroke-linecap='round'/></svg>" type="image/svg+xml">
        
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&family=Syncopate:wght@700&display=swap" rel="stylesheet">
        
        <style>
            :root { --accent: #38bdf8; --bg: #030712; --card-bg: #0f172a; }
            body { background: var(--bg); color: white; font-family: 'Inter', sans-serif; margin: 0; overflow-x: hidden; }
            header { padding: 15px 5%; background: #030712; border-bottom: 1px solid rgba(255,255,255,0.1); display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 1000; }
            .logo { display: flex; align-items: center; gap: 10px; font-family: 'Syncopate'; color: var(--accent); font-size: 1.3rem; text-decoration: none; }
            .logo svg { width: 32px; height: 32px; }
            .search-box { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); padding: 10px 15px; border-radius: 8px; color: white; width: 250px; outline: none; }
            
            .team-bar { display: flex; gap: 12px; padding: 12px 5%; overflow-x: auto; background: #030712; border-bottom: 1px solid rgba(255,255,255,0.05); scrollbar-width: none; }
            .team-logo-btn { width: 40px; height: 40px; cursor: pointer; transition: 0.2s; opacity: 0.3; filter: grayscale(1); flex-shrink: 0; }
            .team-logo-btn.active, .team-logo-btn:hover { opacity: 1; filter: grayscale(0); }

            .nav-tabs { display: flex; justify-content: center; gap: 30px; padding: 15px 0; background: #030712; }
            .tab-btn { font-family: 'Syncopate'; font-size: 0.75rem; cursor: pointer; color: #475569; border: none; background: none; transition: 0.2s; }
            .tab-btn.active { color: var(--accent); border-bottom: 2px solid var(--accent); }

            /* [핵심 최적화: 랙 유발 요소 Blur 제거 & GPU 가속] */
            .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 15px; padding: 20px 5%; contain: content; }
            .card { 
                background: var(--card-bg); 
                border-radius: 12px; 
                padding: 16px; 
                cursor: pointer; 
                border: 1px solid rgba(255,255,255,0.05);
                position: relative; 
                transform: translateZ(0); /* GPU 가속 */
                will-change: transform;
                contain: layout paint;
            }
            .card:hover { border-color: var(--accent); transform: translateY(-3px); }
            .card::before { content: ""; position: absolute; top: 0; left: 0; width: 3px; height: 100%; background: var(--t-color); border-radius: 12px 0 0 12px; }

            .card h3 { display: flex; align-items: center; gap: 8px; margin: 0; font-size: 0.95rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
            .s-tier-badge { background: rgba(251, 191, 36, 0.15); color: #fbbf24; border: 1px solid #fbbf24; font-size: 0.55rem; font-weight: 900; padding: 2px 5px; border-radius: 3px; }

            .rank-tag { position: absolute; top: 10px; left: 10px; background: #000; color: var(--accent); font-size: 0.6rem; font-weight: 900; padding: 2px 5px; border-radius: 3px; border: 1px solid var(--accent); font-family: 'Syncopate'; }
            .live-tag { position: absolute; top: 10px; right: 10px; background: #ef4444; color: white; font-size: 0.55rem; font-weight: 900; padding: 2px 5px; border-radius: 3px; animation: blink 1.2s infinite; }
            @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }

            /* [모달 최적화] */
            .modal { display:none; position:fixed; z-index:2000; left:0; top:0; width:100%; height:100%; background:rgba(0,0,0,0.9); }
            .modal-box { background: #0b1426; width: 900px; max-width: 95%; margin: 5vh auto; border-radius: 20px; display: grid; grid-template-columns: 1fr 1.2fr; overflow: hidden; border: 1px solid #1e293b; }
            .m-left { padding: 30px; text-align: center; border-right: 1px solid rgba(255,255,255,0.05); }
            .m-right { padding: 30px; display: flex; align-items: center; justify-content: center; }
            
            .stat-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 15px 0; }
            .stat-box { background: #1e293b; padding: 10px; border-radius: 8px; text-align: left; }
            .stat-box small { color: #94a3b8; font-size: 0.55rem; font-weight: 800; display: block; }
            .stat-box b { font-size: 1rem; color: #f8fafc; }

            .yt-hook-btn { position:fixed; bottom:20px; right:20px; z-index:5000; background:#000; color:var(--accent); border:1px solid var(--accent); padding:10px 15px; border-radius:30px; font-size:9px; cursor:pointer; font-family:'Syncopate'; font-weight:900; }
            
            #loading { position: fixed; inset: 0; background: #030712; display: flex; justify-content: center; align-items: center; z-index: 9999; color: var(--accent); font-family: 'Syncopate'; }
        </style>
    </head>
    <body>
        <div id="loading">SYNCING_DATA...</div>
        
        <header>
            <a href="/" class="logo">
                <svg viewBox="0 0 24 24"><path d="M21,16.5L12,21.5L3,16.5V7.5L12,2.5L21,7.5V16.5Z" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M12,22V12L21,7.5" stroke="currentColor" stroke-width="1"/><path d="M12,12L3,7.5" stroke="currentColor" stroke-width="1"/></svg>
                <span>NHL ANALYTICA</span>
            </a>
            <input type="text" id="pSearch" class="search-box" placeholder="Search Player..." oninput="render()">
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
        
        <button class="yt-hook-btn" onclick="generateHook()">GET YT HOOK</button>

        <script>
            let rawData = null; let mode = 'regular'; let type = 'skater'; let team = null;
            let chart = null;
            const teams = ["ANA", "BOS", "BUF", "CGY", "CAR", "CHI", "COL", "CBJ", "DAL", "DET", "EDM", "FLA", "LAK", "MIN", "MTL", "NSH", "NJD", "NYI", "NYR", "OTT", "PHI", "PIT", "SJS", "SEA", "STL", "TBL", "TOR", "UTA", "VAN", "VGK", "WSH", "WPG"];

            async function init() {
                try {
                    const res = await fetch('/api/data?t=' + Date.now());
                    rawData = await res.json();
                    document.getElementById('loading').style.display = 'none';
                    document.getElementById('team-bar').innerHTML = teams.map(t => `<img src="https://assets.nhle.com/logos/nhl/svg/${t}_light.svg" class="team-logo-btn" onclick="filterTeam(this, '${t}')">`).join('');
                    render();
                } catch(e) { document.getElementById('loading').innerText = "LOAD_ERROR"; }
            }

            function filterTeam(el, t) {
                document.querySelectorAll('.team-logo-btn').forEach(b => b.classList.remove('active'));
                if(team === t) team = null;
                else { team = t; el.classList.add('active'); }
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

            // [초경량 렌더링 엔진]
            function render() {
                const query = document.getElementById('pSearch').value.toLowerCase();
                const grid = document.getElementById('main-grid');
                if(!rawData) return;

                let data = rawData[mode][type + "s"];
                if(team) data = data.filter(p => p.abbr === team);
                const filtered = data.filter(p => p.name.toLowerCase().includes(query));

                grid.innerHTML = '';
                // 성능을 위해 초기 50개만 즉시 렌더링, 나머지는 비동기 처리
                const draw = (start) => {
                    const chunk = filtered.slice(start, start + 50);
                    const html = chunk.map(p => `
                        <div class="card" onclick="openModal('${p.id}')" style="--t-color:${p.col}">
                            <div class="rank-tag">#${p.rank}</div>
                            ${p.trending ? '<div class="live-tag">LIVE</div>' : ''}
                            <div style="display:flex; align-items:center; gap:12px; margin-top:8px;">
                                <img src="https://assets.nhle.com/mugs/nhl/latest/${p.id}.png" style="width:45px; border-radius:50%; background:#000;" onerror="this.src='https://assets.nhle.com/logos/nhl/svg/${p.abbr}_light.svg'">
                                <div style="flex:1; min-width:0;">
                                    <h3>${p.name} ${p.ir >= 90 ? '<span class="s-tier-badge">S-TIER</span>' : ''}</h3>
                                    <small style="color:#64748b; font-size:0.65rem;">${p.type==='skater'?'PTS '+p.pts:'WINS '+p.w}</small>
                                </div>
                                <div style="text-align:right;"><b style="color:var(--accent); font-size:1.1rem;">${p.ir}</b><br><small style="font-size:0.5rem; color:#475569;">IR</small></div>
                            </div>
                        </div>
                    `).join('');
                    grid.insertAdjacentHTML('beforeend', html);
                    if(start + 50 < filtered.length) requestAnimationFrame(() => draw(start + 50));
                };
                draw(0);
            }

            function openModal(id) {
                const p = rawData[mode][type+"s"].find(x => x.id === id);
                if(!p) return;
                
                const stats = p.type === 'skater' ? 
                    `<div class="stat-box"><small>GP</small><b>${p.gp}</b></div><div class="stat-box"><small>PTS</small><b>${p.pts}</b></div><div class="stat-box"><small>PPG</small><b>${p.ppg}</b></div>` :
                    `<div class="stat-box"><small>GP</small><b>${p.gp}</b></div><div class="stat-box"><small>WINS</small><b>${p.w}</b></div><div class="stat-box"><small>SV%</small><b>${p.sv}</b></div>`;

                document.getElementById('mInfo').innerHTML = `
                    <img src="https://assets.nhle.com/mugs/nhl/latest/${p.id}.png" style="width:120px; border-radius:50%; border:3px solid ${p.col};">
                    <h2 style="font-family:'Syncopate'; margin:10px 0;">${p.name.toUpperCase()}</h2>
                    <div style="background:${p.col}; display:inline-block; padding:4px 10px; border-radius:5px; font-size:0.7rem; font-weight:800;">${p.team}</div>
                    <div class="stat-grid">${stats}</div>
                    <div style="background:#1e293b; padding:15px; border-radius:10px; border:1px solid #fbbf24;">
                        <small style="color:#fbbf24; font-weight:900;">GOAL PROBABILITY</small>
                        <div style="font-size:2rem; font-weight:900; color:#fbbf24;">${p.prob || p.so || 0}%</div>
                    </div>
                `;
                
                document.getElementById('mRight').innerHTML = `<canvas id="radar"></canvas>`;
                document.getElementById('modal').style.display = 'block';
                drawRadar(p);
            }

            function drawRadar(p) {
                const ctx = document.getElementById('radar').getContext('2d');
                if(chart) chart.destroy();
                const vals = p.type === 'skater' ? [p.g*5, p.a*5, p.pts*2, p.ppg*50, p.ir] : [p.w*5, p.sv, (4-p.gaa)*20, p.so*20, p.ir];
                chart = new Chart(ctx, {
                    type: 'radar',
                    data: {
                        labels: ['G/W', 'A/SV', 'PTS/GAA', 'PPG/SO', 'IR'],
                        datasets: [{ data: vals, backgroundColor: 'rgba(56, 189, 248, 0.2)', borderColor: '#38bdf8', borderWidth: 2, pointRadius: 0 }]
                    },
                    options: { scales: { r: { min: 0, max: 100, grid: { color: '#334155' }, angleLines: { color: '#334155' }, ticks: { display: false } } }, plugins: { legend: { display: false } } }
                });
            }

            function generateHook() {
                const first = document.querySelector('.card h3');
                if(!first) return;
                const name = first.innerText.replace('S-TIER', '').trim();
                const ir = document.querySelector('.card b').innerText;
                console.log(`%c[ICE ANALYTICS HOOK] "오늘 분석할 선수는 ${name}입니다. IR 지표 ${ir}점, 왜 이 수치가 무서운지 숫자로 증명해 드립니다."`, "color:#38bdf8; font-weight:bold;");
                alert("콘솔(F12)에 대본 훅이 생성되었습니다.");
            }

            init();
        </script>
    </body>
    </html>
    """)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
