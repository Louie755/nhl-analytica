import pandas as pd
from flask import Flask, render_template_string, jsonify, request, Response
import requests
import os
from datetime import datetime

app = Flask(__name__)

# [기존 로직 보존] 팀 데이터 및 컬러 설정
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
        <title>NHL ANALYTICA | NEXT-GEN STATS</title>
        
        <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'><rect width='24' height='24' rx='6' fill='%23030712'/><path d='M12,2L22,7V17L12,22L2,17V7L12,2Z' fill='none' stroke='%2338bdf8' stroke-width='1.5'/><circle cx='12' cy='12' r='3' fill='%2338bdf8'/></svg>" type="image/svg+xml">
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&family=Syncopate:wght@700&display=swap" rel="stylesheet">
        
        <style>
            :root { --accent: #38bdf8; --bg: #030712; --card-bg: rgba(15, 23, 42, 0.7); }
            body { background: var(--bg); color: white; font-family: 'Inter', sans-serif; margin: 0; overflow-x: hidden; }

            /* [배경 효과: 초고급형 다크 테마] */
            body::before {
                content: ""; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
                background: radial-gradient(circle at 50% -20%, #1e293b 0%, #030712 100%);
                z-index: -1;
            }

            /* [헤더 업그레이드: Glassmorphism] */
            header { 
                padding: 15px 5%; background: rgba(3, 7, 18, 0.8); border-bottom: 1px solid rgba(255, 255, 255, 0.05);
                display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 1000;
                backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
            }
            .logo { display: flex; align-items: center; gap: 12px; font-family: 'Syncopate'; color: var(--accent); font-size: 1.4rem; text-decoration: none; letter-spacing: -1px; }
            .logo svg { width: 34px; height: 34px; filter: drop-shadow(0 0 8px var(--accent)); }
            
            .search-box { 
                background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.1); 
                padding: 12px 20px; border-radius: 30px; color: white; width: 320px; outline: none;
                transition: all 0.3s; font-size: 0.9rem;
            }
            .search-box:focus { border-color: var(--accent); background: rgba(255, 255, 255, 0.08); width: 380px; box-shadow: 0 0 20px rgba(56, 189, 248, 0.2); }

            /* [팀 바: 미니멀리즘] */
            .team-bar { display: flex; gap: 12px; padding: 15px 5%; overflow-x: auto; scrollbar-width: none; background: rgba(0,0,0,0.2); }
            .team-logo-btn { width: 42px; height: 42px; cursor: pointer; transition: 0.3s; opacity: 0.3; filter: grayscale(1); flex-shrink: 0; }
            .team-logo-btn.active, .team-logo-btn:hover { opacity: 1; filter: grayscale(0); transform: scale(1.15) rotate(5deg); }

            /* [탭: 프로페셔널 다크] */
            .nav-tabs { display: flex; justify-content: center; gap: 40px; padding: 25px 0; }
            .tab-btn { font-family: 'Syncopate'; font-size: 0.75rem; cursor: pointer; color: #475569; border: none; background: none; transition: 0.3s; position: relative; }
            .tab-btn.active { color: var(--accent); }
            .tab-btn.active::after { content: ""; position: absolute; bottom: -8px; left: 0; width: 100%; height: 2px; background: var(--accent); box-shadow: 0 0 10px var(--accent); }

            /* [카드 업그레이드: 전설적인 Glassmorphism] */
            .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; padding: 0 5% 50px; contain: content; }
            .card { 
                background: var(--card-bg); border-radius: 24px; padding: 22px; cursor: pointer;
                border: 1px solid rgba(255, 255, 255, 0.05); position: relative; overflow: hidden;
                transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275); transform: translateZ(0);
            }
            .card:hover { transform: translateY(-8px); border-color: rgba(56, 189, 248, 0.4); background: rgba(30, 41, 59, 0.8); box-shadow: 0 20px 40px rgba(0,0,0,0.4); }
            .card::after { content: ""; position: absolute; top: 0; left: 0; width: 4px; height: 100%; background: var(--t-color); }
            
            .p-header { display: flex; align-items: center; gap: 12px; margin-bottom: 15px; }
            .p-mug { width: 56px; height: 56px; border-radius: 50%; background: #000; border: 2px solid rgba(255,255,255,0.05); }
            .p-name { margin: 0; font-size: 1.05rem; font-weight: 800; letter-spacing: -0.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 150px; }
            .s-tier-badge { background: linear-gradient(45deg, #fbbf24, #f59e0b); color: #000; font-size: 0.6rem; font-weight: 900; padding: 2px 8px; border-radius: 4px; text-transform: uppercase; }

            .rank-tag { position: absolute; top: 15px; left: 20px; background: #000; color: var(--accent); font-size: 0.65rem; font-weight: 900; padding: 2px 8px; border-radius: 6px; border: 1px solid var(--accent); font-family: 'Syncopate'; }
            .live-tag { position: absolute; top: 15px; right: 20px; background: #ef4444; color: white; font-size: 0.6rem; font-weight: 900; padding: 3px 8px; border-radius: 6px; animation: pulse 1.5s infinite; }
            @keyframes pulse { 0% { opacity: 1; transform: scale(1); } 50% { opacity: 0.7; transform: scale(0.95); } 100% { opacity: 1; transform: scale(1); } }

            /* [박스 레이아웃 스탯] */
            .card-stats { display: flex; justify-content: space-between; align-items: flex-end; }
            .ir-box { text-align: right; }
            .ir-box b { font-size: 1.6rem; color: var(--accent); font-family: 'Syncopate'; display: block; line-height: 1; }
            .ir-box small { font-size: 0.6rem; color: #64748b; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; }

            /* [모달: Moneyball 스타일 전문가형 박스] */
            .modal { display:none; position:fixed; inset:0; background:rgba(0,0,0,0.95); z-index: 2000; display: flex; align-items: center; justify-content: center; opacity: 0; pointer-events: none; transition: 0.4s; backdrop-filter: blur(10px); }
            .modal.active { opacity: 1; pointer-events: auto; }
            .modal-box { 
                background: #0b1426; width: 960px; max-width: 95%; border-radius: 32px; border: 1px solid rgba(255,255,255,0.1);
                display: grid; grid-template-columns: 1fr 1.2fr; overflow: hidden; box-shadow: 0 50px 100px rgba(0,0,0,0.8);
            }
            .m-left { padding: 45px; border-right: 1px solid rgba(255,255,255,0.05); text-align: center; }
            .m-right { padding: 45px; background: rgba(255,255,255,0.01); display: flex; align-items: center; justify-content: center; position: relative; }
            
            .kf-box { background: rgba(56, 189, 248, 0.05); border: 1px solid rgba(56, 189, 248, 0.1); border-radius: 16px; padding: 22px; text-align: left; margin: 20px 0; }
            .kf-title { font-family: 'Syncopate'; font-size: 0.7rem; color: var(--accent); margin-bottom: 18px; display: block; opacity: 0.8; }
            .kf-row { display: flex; justify-content: space-between; margin-bottom: 12px; font-size: 0.95rem; }
            .kf-label { color: #94a3b8; font-weight: 500; }
            .kf-val { font-weight: 900; }

            .stat-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 20px; }
            .stat-unit { background: #16253d; padding: 15px; border-radius: 16px; text-align: left; border: 1px solid rgba(255,255,255,0.03); }
            .stat-unit small { color: #64748b; font-size: 0.6rem; font-weight: 800; display: block; margin-bottom: 6px; }
            .stat-unit b { font-size: 1.2rem; color: #fff; }

            .yt-btn { position: fixed; bottom: 30px; right: 30px; background: var(--accent); color: #000; border: none; padding: 14px 28px; border-radius: 40px; font-weight: 900; font-family: 'Syncopate'; font-size: 10px; cursor: pointer; z-index: 5000; box-shadow: 0 10px 30px rgba(56, 189, 248, 0.4); transition: 0.3s; }
            .yt-btn:hover { transform: scale(1.1) translateY(-5px); }

            /* [최적화: 스크롤 및 애니메이션] */
            * { transition: border-color 0.2s, background-color 0.2s; }
            ::-webkit-scrollbar { display: none; }
        </style>
    </head>
    <body>
        <div id="loading"><h1>ANALYZING_LIVE_DATA</h1></div>
        
        <header>
            <a href="/" class="logo">
                <svg viewBox="0 0 24 24"><path d="M21,16.5L12,21.5L3,16.5V7.5L12,2.5L21,7.5V16.5Z" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12,22V12 L21,7.5 M12,12L3,7.5" stroke="currentColor" stroke-width="1.5"/></svg>
                <span>NHL ANALYTICA</span>
            </a>
            <input type="text" id="pSearch" class="search-box" placeholder="Search Player Name..." oninput="render()">
        </header>

        <div class="team-bar" id="team-bar"></div>

        <div class="nav-tabs">
            <button class="tab-btn active" id="reg-tab" onclick="switchMode('regular')">REGULAR SEASON</button>
            <button class="tab-btn" id="ply-tab" onclick="switchMode('playoff')">PLAYOFFS</button>
            <span style="color:rgba(255,255,255,0.1)">|</span>
            <button class="tab-btn active" id="sk-tab" onclick="switchType('skater')">SKATERS</button>
            <button class="tab-btn" id="go-tab" onclick="switchType('goalie')">GOALIES</button>
        </div>

        <div class="grid" id="main-grid"></div>

        <div id="modal" class="modal" onclick="closeModal()"><div class="modal-box" onclick="event.stopPropagation()"><div class="m-left" id="mInfo"></div><div class="m-right" id="mRight"></div></div></div>
        
        <button class="yt-btn" onclick="generateHook()">GET VIDEO HOOK</button>

        <script>
            let rawData = null; let mode = 'regular'; let type = 'skater'; 
            let team = null; let chart = null;
            const teams = ["ANA", "BOS", "BUF", "CGY", "CAR", "CHI", "COL", "CBJ", "DAL", "DET", "EDM", "FLA", "LAK", "MIN", "MTL", "NSH", "NJD", "NYI", "NYR", "OTT", "PHI", "PIT", "SJS", "SEA", "STL", "TBL", "TOR", "UTA", "VAN", "VGK", "WSH", "WPG"];

            async function init() {
                try {
                    const res = await fetch('/api/data?t=' + Date.now()); 
                    rawData = await res.json();
                    document.getElementById('loading').style.opacity = '0';
                    setTimeout(() => document.getElementById('loading').style.display = 'none', 500);
                    buildTeamBar(); render();
                } catch (e) { document.getElementById('loading').innerText = "LOAD_ERROR"; }
            }

            function buildTeamBar() {
                const bar = document.getElementById('team-bar');
                bar.innerHTML = teams.map(t => `<img src="https://assets.nhle.com/logos/nhl/svg/${t}_light.svg" class="team-logo-btn" id="btn-${t}" onclick="filterTeam('${t}')">`).join('');
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

            // [초경량 렌더링 엔진: 랙 완벽 차단]
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
                    const html = chunk.map(p => {
                        const sTier = p.ir >= 90 ? '<span class="s-tier-badge">S-TIER</span>' : '';
                        return `
                        <div class="card" onclick="openModal('${p.id}')" style="--t-color:${p.col}">
                            <div class="rank-tag">#${p.rank}</div>
                            ${p.trending ? '<div class="live-tag">LIVE</div>' : ''}
                            <div class="p-header">
                                <img src="https://assets.nhle.com/mugs/nhl/latest/${p.id}.png" class="p-mug" onerror="this.src='https://assets.nhle.com/logos/nhl/svg/${p.abbr}_light.svg'">
                                <div><h3 class="p-name">${p.name}</h3>${sTier}</div>
                            </div>
                            <div class="card-stats">
                                <small style="color:#64748b; font-size:0.7rem; font-weight:700;">${p.type==='skater'?'PTS '+p.pts:'WINS '+p.w}</small>
                                <div class="ir-box"><b>${p.ir}</b><small>IR SCORE</small></div>
                            </div>
                        </div>`;
                    }).join('');
                    grid.insertAdjacentHTML('beforeend', html);
                    idx += 40; if(idx < filtered.length) requestAnimationFrame(draw);
                }
                draw();
            }

            function openModal(id) {
                const p = rawData[mode][type + "s"].find(x => x.id === id);
                if(!p) return;
                
                let irGrade = p.ir >= 90 ? "ELITE IMPACT" : p.ir >= 75 ? "CORE ASSET" : "MARKET AVG";
                let irCol = p.ir >= 90 ? "#fbbf24" : p.ir >= 75 ? "#38bdf8" : "#94a3b8";

                const stats = p.type === 'skater' ? 
                    `<div class="stat-unit"><small>GP</small><b>${p.gp}</b></div><div class="stat-unit"><small>PPG</small><b>${p.ppg}</b></div><div class="stat-unit"><small>G</small><b>${p.g}</b></div><div class="stat-unit"><small>A</small><b>${p.a}</b></div><div class="stat-unit"><small>+/-</small><b>${p.pm}</b></div><div class="stat-unit"><small>SHOTS</small><b>${p.sh}</b></div>` :
                    `<div class="stat-unit"><small>GP</small><b>${p.gp}</b></div><div class="stat-unit"><small>WINS</small><b>${p.w}</b></div><div class="stat-unit"><small>SV%</small><b>${p.sv}</b></div><div class="stat-unit"><small>GAA</small><b>${p.gaa}</b></div><div class="stat-unit"><small>SO</small><b>${p.so}</b></div><div class="stat-unit"><small>SA</small><b>${p.sa}</b></div>`;

                document.getElementById('mInfo').innerHTML = `
                    <div style="font-size:0.75rem; color:var(--accent); font-weight:900; margin-bottom:10px; font-family:'Syncopate';">RANK #${p.rank} | ${mode.toUpperCase()}</div>
                    <img src="https://assets.nhle.com/mugs/nhl/latest/${p.id}.png" style="width:160px; border-radius:50%; border:4px solid ${p.col}; background:#000;">
                    <h2 style="font-family:'Syncopate'; margin:20px 0 10px; font-size:1.8rem; letter-spacing:-1px;">${p.name.toUpperCase()}</h2>
                    <div style="background:${p.col}; padding:6px 16px; border-radius:10px; font-weight:900; font-size:0.8rem; display:inline-block; margin-bottom:25px;">${p.team.toUpperCase()}</div>
                    
                    <div class="kf-box">
                        <span class="kf-title">ANALYTICS KEY FACTORS</span>
                        <div class="kf-row"><span class="kf-label">Impact Assessment</span><span class="kf-val" style="color:${irCol}">${irGrade}</span></div>
                        <div class="kf-row"><span class="kf-label">Recent Scoring</span><span class="kf-val" style="color:${p.ppg>=0.8?'#ef4444':'#38bdf8'}">${p.ppg>=0.8?'HOT':'STABLE'}</span></div>
                        <div class="kf-row"><span class="kf-label">Game Influence</span><span class="kf-val">${p.ir}% High</span></div>
                    </div>

                    <div class="stat-grid">${stats}</div>
                    <div class="prob-box"><small style="font-weight:900; color:#fbbf24; letter-spacing:1px;">EXPECTED IMPACT PROBABILITY</small><b>${p.prob || p.so || 0}%</b></div>`;
                
                document.getElementById('mRight').innerHTML = `<canvas id="radar"></canvas>`;
                const modal = document.getElementById('modal');
                modal.style.display = 'flex';
                setTimeout(() => modal.classList.add('active'), 10);
                drawRadar(p);
            }

            function closeModal() { 
                const modal = document.getElementById('modal');
                modal.classList.remove('active');
                setTimeout(() => modal.style.display = 'none', 400);
            }

            function drawRadar(p) {
                const ctx = document.getElementById('radar').getContext('2d');
                if(chart) chart.destroy();
                const data = p.type==='skater' ? [p.g*5, p.pts, p.ppg*50, 70, p.ir] : [p.w*5, p.sv, 70, 50, p.ir];
                chart = new Chart(ctx, {
                    type: 'radar',
                    data: { labels: ['GOALS', 'POINTS', 'PPG', 'DEFENSE', 'IMPACT'], datasets: [{ data, backgroundColor: 'rgba(56, 189, 248, 0.2)', borderColor: '#38bdf8', borderWidth: 3, pointRadius: 0 }] },
                    options: { 
                        scales: { r: { min: 0, max: 100, grid: { color: 'rgba(255,255,255,0.05)' }, angleLines: { color: 'rgba(255,255,255,0.05)' }, ticks: { display: false }, pointLabels: { color: '#64748b', font: { family: 'Syncopate', size: 10, weight: 'bold' } } } },
                        plugins: { legend: { display: false } } 
                    }
                });
            }

            function generateHook() {
                const first = document.querySelector('.p-name');
                const ir = document.querySelector('.ir-box b').innerText;
                alert(`[Ice Analytics Video Hook Generator]\\n\\n"오늘의 주인공은 ${first.innerText}입니다. IR 지표 ${ir}점, 데이터가 말해주는 이 선수의 진짜 가치를 공개합니다."`);
            }

            init();
        </script>
    </body>
    </html>
    """)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
