import pandas as pd
from flask import Flask, render_template_string, jsonify, request, Response
import requests
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

app = Flask(__name__)

# 팀 데이터 및 컬러 설정 (원본 유지)
TEAM_MAP = {"ANA": "Anaheim Ducks", "BOS": "Boston Bruins", "BUF": "Buffalo Sabres", "CGY": "Calgary Flames", "CAR": "Carolina Hurricanes", "CHI": "Chicago Blackhawks", "COL": "Colorado Avalanche", "CBJ": "Columbus Blue Jackets", "DAL": "Dallas Stars", "DET": "Detroit Red Wings", "EDM": "Edmonton Oilers", "FLA": "Florida Panthers", "LAK": "Los Angeles Kings", "MIN": "Minnesota Wild", "MTL": "Montreal Canadiens", "NSH": "Nashville Predators", "NJD": "New Jersey Devils", "NYI": "New York Islanders", "NYR": "New York Rangers", "OTT": "Ottawa Senators", "PHI": "Philadelphia Flyers", "PIT": "Pittsburgh Penguins", "SJS": "San Jose Sharks", "SEA": "Seattle Kraken", "STL": "St Louis Blues", "TBL": "Tampa Bay Lightning", "TOR": "Toronto Maple Leafs", "UTA": "Utah Hockey Club", "VAN": "Vancouver Canucks", "VGK": "Vegas Golden Knights", "WSH": "Washington Capitals", "WPG": "Winnipeg Jets"}
TEAM_COLORS = {"ANA": "#F47A38", "BOS": "#FFB81C", "BUF": "#002654", "CGY": "#C8102E", "CAR": "#CE1126", "CHI": "#CF0A2C", "COL": "#6F263D", "CBJ": "#002654", "DAL": "#006847", "DET": "#CE1126", "EDM": "#FF4C00", "FLA": "#041E42", "LAK": "#111111", "MIN": "#154734", "MTL": "#AF1E2D", "NSH": "#FFB81C", "NJD": "#CE1126", "NYI": "#00539B", "NYR": "#0038A8", "OTT": "#C8102E", "PHI": "#F74902", "PIT": "#FCB514", "SJS": "#006D75", "SEA": "#001628", "STL": "#002F87", "TBL": "#002868", "TOR": "#00205B", "UTA": "#71AFE2", "VAN": "#00205B", "VGK": "#B4975A", "WSH": "#041E42", "WPG": "#004C97"}

def fetch_nhl_safe(url, season, sort_prop, game_type=2):
    all_data = []
    start, limit = 0, 100
    while True:
        params = {"isAggregate": "false", "isGame": "false", "sort": f'[{{"property":"{sort_prop}","direction":"DESC"}}]', "start": start, "limit": limit, "cayenneExp": f"seasonId={season} and gameTypeId={game_type}"}
        try:
            r = requests.get(url, params=params, timeout=6)
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

@app.route('/manifest.json')
def manifest():
    return jsonify({
        "name": "NHL Analytica",
        "short_name": "NHLAnalytica",
        "description": "Real-time NHL player stats powered by the proprietary Impact Rating (IR) metric.",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#030712",
        "theme_color": "#030712",
        "orientation": "portrait-primary",
        "icons": [
            {"src": "/static/images/logo.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
            {"src": "/static/images/logo.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}
        ],
        "categories": ["sports", "news"],
        "lang": "en"
    })

@app.route('/service-worker.js')
def service_worker():
    sw_code = """
const CACHE_NAME = 'nhl-analytica-v2';
const STATIC_ASSETS = ['/'];

self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
    );
    self.skipWaiting();
});

self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys => Promise.all(
            keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
        ))
    );
    self.clients.claim();
});

self.addEventListener('fetch', event => {
    const url = new URL(event.request.url);
    if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/push/')) {
        event.respondWith(fetch(event.request));
        return;
    }
    event.respondWith(
        fetch(event.request)
            .then(response => {
                const clone = response.clone();
                caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
                return response;
            })
            .catch(() => caches.match(event.request))
    );
});

// Handle incoming push notifications
self.addEventListener('push', event => {
    const data = event.data ? event.data.json() : {};
    const title = data.title || 'NHL Analytica';
    const options = {
        body: data.body || 'Roster move detected!',
        icon: data.icon || '/static/images/logo.png',
        badge: '/static/images/logo.png',
        data: { url: data.url || '/' },
        vibrate: [200, 100, 200],
        tag: data.tag || 'nhl-alert',
        renotify: true,
        actions: [
            { action: 'view', title: 'View Player' },
            { action: 'dismiss', title: 'Dismiss' }
        ]
    };
    event.waitUntil(self.registration.showNotification(title, options));
});

// Handle notification click
self.addEventListener('notificationclick', event => {
    event.notification.close();
    if (event.action === 'dismiss') return;
    const url = event.notification.data?.url || '/';
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(clientList => {
            for (const client of clientList) {
                if (client.url.includes('nhlanalytica.com') && 'focus' in client) {
                    client.navigate(url);
                    return client.focus();
                }
            }
            if (clients.openWindow) return clients.openWindow(url);
        })
    );
});
"""
    return Response(sw_code, mimetype='application/javascript')

_roster_cache = {"data": {}, "ts": 0, "loading": False}

# ── PUSH NOTIFICATION SYSTEM ──
import json, hashlib, time, base64

VAPID_PUBLIC_KEY = "BJZTmoobqKLvTUvuaxlU7P0m6xjpzpzSL1kR6y7Dnuz5y9OTodNcamM1xUu4KUg1xj88GUI1VDtIuPsbgL-Of18"
VAPID_PRIVATE_PEM = """-----BEGIN PRIVATE KEY-----
MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQgVKEdtzKhOVbJI081
ZMKz29NQ9cXG2+fq3rxOiV3ubO6hRANCAASWU5qKG6ii701L7msZVOz9JusY6c6c
0i9ZEesuw57s+cvTk6HTXGpjNcVLuClINcY/PBlCNVQ7SLj7G4C/jn9f
-----END PRIVATE KEY-----"""
VAPID_CONTACT = "mailto:louie@nhlanalytica.com"

_push_subscriptions = {}
_roster_snapshot = {}

@app.route('/push/vapid-public-key')
def get_vapid_key():
    return jsonify({"publicKey": VAPID_PUBLIC_KEY})

@app.route('/push/subscribe', methods=['POST'])
def push_subscribe():
    data = request.get_json()
    if not data or 'endpoint' not in data:
        return jsonify({"error": "Invalid subscription"}), 400
    sub_id = hashlib.md5(data['endpoint'].encode()).hexdigest()
    _push_subscriptions[sub_id] = data
    return jsonify({"status": "subscribed", "id": sub_id})

@app.route('/push/unsubscribe', methods=['POST'])
def push_unsubscribe():
    data = request.get_json()
    if data and 'endpoint' in data:
        sub_id = hashlib.md5(data['endpoint'].encode()).hexdigest()
        _push_subscriptions.pop(sub_id, None)
    return jsonify({"status": "unsubscribed"})

@app.route('/push/subscribers')
def push_subscriber_count():
    return jsonify({"count": len(_push_subscriptions)})

def send_push_notification(subscription, payload):
    """Send push notification via pywebpush (lazy import so startup isn't slowed)."""
    try:
        from pywebpush import webpush, WebPushException
        webpush(
            subscription_info=subscription,
            data=json.dumps(payload),
            vapid_private_key=VAPID_PRIVATE_PEM,
            vapid_claims={"sub": VAPID_CONTACT},
            content_encoding="aes128gcm"
        )
        return True
    except Exception:
        return False

def broadcast_push(title, body, url='/', tag='nhl-alert'):
    """Send push notification to all subscribers in background - never blocks."""
    if not _push_subscriptions:
        return 0
    payload = {"title": title, "body": body, "url": url, "tag": tag, "icon": "/static/images/logo.png"}
    sent = 0
    dead = []
    for sub_id, sub in list(_push_subscriptions.items()):
        if send_push_notification(sub, payload):
            sent += 1
        else:
            dead.append(sub_id)
    for sub_id in dead:
        _push_subscriptions.pop(sub_id, None)
    return sent

def detect_roster_changes(new_roster):
    """Compare new roster to snapshot. Returns list of moves."""
    global _roster_snapshot
    changes = []
    if not _roster_snapshot:
        _roster_snapshot = dict(new_roster)
        return changes
    for pid, new_team in new_roster.items():
        old_team = _roster_snapshot.get(pid)
        if old_team and old_team != new_team:
            changes.append({"pid": pid, "old_team": old_team, "new_team": new_team})
    _roster_snapshot = dict(new_roster)
    return changes

def fetch_team_roster(abbr):
    try:
        r = requests.get(f"https://api-web.nhle.com/v1/roster/{abbr}/current", timeout=6)
        data = r.json()
        result = {}
        for group in ('forwards', 'defensemen', 'goalies'):
            for player in data.get(group, []):
                pid = str(player.get('id', ''))
                if pid:
                    result[pid] = abbr
        return result
    except:
        return {}

def refresh_roster_cache():
    """Fetch all 32 rosters in parallel. Detects roster moves and sends push notifications."""
    global _roster_cache
    if _roster_cache["loading"]:
        return
    _roster_cache["loading"] = True
    try:
        roster_map = {}
        with ThreadPoolExecutor(max_workers=16) as executor:
            futures = {executor.submit(fetch_team_roster, abbr): abbr for abbr in TEAM_MAP.keys()}
            for future in as_completed(futures):
                roster_map.update(future.result())
        if roster_map:
            # Detect roster changes before updating cache
            changes = detect_roster_changes(roster_map)
            for change in changes:
                pid = change['pid']
                old_abbr = change['old_team']
                new_abbr = change['new_team']
                old_team = TEAM_MAP.get(old_abbr, old_abbr)
                new_team = TEAM_MAP.get(new_abbr, new_abbr)
                # Fire push notification
                threading.Thread(
                    target=broadcast_push,
                    args=(
                        f"🚨 NHL Roster Move",
                        f"Player moved: {old_team} → {new_team}",
                        f"/?player={pid}&mode=regular&type=skater",
                        f"roster-{pid}"
                    ),
                    daemon=True
                ).start()
            _roster_cache["data"] = roster_map
            _roster_cache["ts"] = datetime.now().timestamp()
    finally:
        _roster_cache["loading"] = False

def get_current_roster_map():
    """Return cached roster map immediately. Triggers background refresh if stale (>10 min)."""
    now_ts = datetime.now().timestamp()
    if (now_ts - _roster_cache["ts"]) > 600 and not _roster_cache["loading"]:
        threading.Thread(target=refresh_roster_cache, daemon=True).start()
    return _roster_cache["data"]  # always returns instantly, never blocks

# Warm up roster cache on startup
threading.Thread(target=refresh_roster_cache, daemon=True).start()

# 사이트맵 경로 (동작 보장)
@app.route('/sitemap.xml')
def sitemap_xml_route():
    host_root = request.host_url
    now_date = datetime.now().strftime('%Y-%m-%d')
    sitemap_data = f"""<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <url><loc>{host_root}</loc><lastmod>{now_date}</lastmod><priority>1.0</priority></url>
    </urlset>"""
    return Response(sitemap_data, mimetype='application/xml')

_data_cache = {"data": None, "ts": 0, "loading": False}

def build_data(s_reg, s_ply, g_reg, g_ply, today_scorers, roster_map):
    def process_skaters(raw, min_gp):
        processed = []
        for p in raw:
            gp = p.get('gamesPlayed', 0)
            if gp < min_gp: continue
            pts, sh, pm = p.get('points', 0), max(1, p.get('shots', 0)), p.get('plusMinus', 0)
            ppg = round(pts/gp, 2); ir = min(99.9, round((ppg * 40) + ((pts/sh)*25) + (max(0, pm+10)/2) + (gp/10), 1))
            pid = str(p.get('playerId'))
            if pid in roster_map:
                main_abbr = roster_map[pid]
            else:
                raw_abbr = p.get('teamAbbrevs', p.get('teamAbbrev', ''))
                teams_list = [t.strip().upper() for t in str(raw_abbr).split(',') if t.strip()]
                main_abbr = teams_list[-1] if teams_list else ""
            processed.append({
                "id": pid, "name": p.get('skaterFullName'), "type": "skater",
                "abbr": main_abbr, "pos": p.get('positionCode'), "gp": gp, "pts": pts, "ppg": ppg, "ir": ir,
                "g": p.get('goals', 0), "a": p.get('assists', 0), "sh": sh, "pm": pm,
                "team": TEAM_MAP.get(main_abbr, main_abbr),
                "prob": min(round(((p.get('goals', 0)/gp)*50 + (sh/gp)*10), 1), 95.0),
                "trending": pid in today_scorers,
                "col": TEAM_COLORS.get(main_abbr, "#38bdf8")
            })
        processed.sort(key=lambda x: (-x['pts'], x['gp']))
        for i, p in enumerate(processed): p['rank'] = i + 1
        return processed

    def process_goalies(raw, min_gp):
        processed = []
        for p in raw:
            gp = p.get('gamesPlayed', 0)
            if gp < min_gp: continue
            ga, sa, wins = p.get('goalsAgainst', 0), max(1, p.get('shotsAgainst', 0)), p.get('wins', 0)
            sv_val = round((1 - (ga/sa)) * 100, 2) if sa > 0 else 0.0
            gaa = round(ga/gp, 2); ir = min(99.9, round((wins/gp * 40) + (sv_val - 85) * 4 + (5 - gaa) * 2, 1))
            pid = str(p.get('playerId'))
            if pid in roster_map:
                main_abbr = roster_map[pid]
            else:
                raw_abbr = p.get('teamAbbrevs', p.get('teamAbbrev', ''))
                teams_list = [t.strip().upper() for t in str(raw_abbr).split(',') if t.strip()]
                main_abbr = teams_list[-1] if teams_list else ""
            processed.append({
                "id": pid, "name": p.get('goalieFullName'), "type": "goalie",
                "abbr": main_abbr, "pos": "G", "gp": gp, "w": wins, "sv": sv_val, "gaa": gaa, "ir": ir,
                "so": p.get('shutouts', 0), "sa": sa, "ga": ga,
                "team": TEAM_MAP.get(main_abbr, main_abbr),
                "trending": pid in today_scorers,
                "col": TEAM_COLORS.get(main_abbr, "#38bdf8")
            })
        processed.sort(key=lambda x: (-x['w'], x['gp']))
        for i, p in enumerate(processed): p['rank'] = i + 1
        return processed

    return {"regular": {"skaters": process_skaters(s_reg, 5), "goalies": process_goalies(g_reg, 3)},
            "playoff": {"skaters": process_skaters(s_ply, 2), "goalies": process_goalies(g_ply, 1)}}

def refresh_data_cache():
    """Fetch all NHL stats in background and update cache. Never blocks a request."""
    global _data_cache
    if _data_cache["loading"]:
        return
    _data_cache["loading"] = True
    try:
        now = datetime.now()
        ts = int(now.timestamp())
        # NHL season runs Oct-June. After June, use the season that just ended.
        # Season format: start_year + end_year (e.g. 20242025)
        if now.month >= 10:
            season = f"{now.year}{now.year + 1}"
        elif now.month <= 6:
            season = f"{now.year - 1}{now.year}"
        else:
            # July-Sept: offseason, use the season that just ended
            season = f"{now.year - 1}{now.year}"

        def fetch_s_reg(): return fetch_nhl_safe(f"https://api.nhle.com/stats/rest/en/skater/summary?t={ts}", season, "points", 2)
        def fetch_s_ply(): return fetch_nhl_safe(f"https://api.nhle.com/stats/rest/en/skater/summary?t={ts}", season, "points", 3)
        def fetch_g_reg(): return fetch_nhl_safe(f"https://api.nhle.com/stats/rest/en/goalie/summary?t={ts}", season, "wins", 2)
        def fetch_g_ply(): return fetch_nhl_safe(f"https://api.nhle.com/stats/rest/en/goalie/summary?t={ts}", season, "wins", 3)

        with ThreadPoolExecutor(max_workers=5) as executor:
            f_sr = executor.submit(fetch_s_reg)
            f_sp = executor.submit(fetch_s_ply)
            f_gr = executor.submit(fetch_g_reg)
            f_gp = executor.submit(fetch_g_ply)
            f_ts = executor.submit(get_today_scorers)
            s_reg = f_sr.result(timeout=20) or []
            s_ply = f_sp.result(timeout=20) or []
            g_reg = f_gr.result(timeout=20) or []
            g_ply = f_gp.result(timeout=20) or []
            today_scorers = f_ts.result(timeout=10) or set()

        roster_map = get_current_roster_map()
        if s_reg or g_reg:
            _data_cache["data"] = build_data(s_reg, s_ply, g_reg, g_ply, today_scorers, roster_map)
            _data_cache["ts"] = datetime.now().timestamp()
    except Exception:
        pass
    finally:
        _data_cache["loading"] = False

@app.route('/api/data')
def get_nhl_data():
    now_ts = datetime.now().timestamp()
    # Trigger background refresh if cache is older than 5 minutes
    if (now_ts - _data_cache["ts"]) > 300 and not _data_cache["loading"]:
        threading.Thread(target=refresh_data_cache, daemon=True).start()
    # Return cached data instantly if available
    if _data_cache["data"]:
        return jsonify(_data_cache["data"])
    # First ever load — wait for data (with timeout)
    deadline = now_ts + 25
    while not _data_cache["data"] and datetime.now().timestamp() < deadline:
        time.sleep(0.3)
    if _data_cache["data"]:
        return jsonify(_data_cache["data"])
    return jsonify({"error": "NHL API unavailable", "regular": {"skaters": [], "goalies": []}, "playoff": {"skaters": [], "goalies": []}}), 503

# Warm up data cache on startup
threading.Thread(target=refresh_data_cache, daemon=True).start()

@app.route('/og-image')
def og_image():
    import base64, io
    b64 = "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"
    img_bytes = base64.b64decode(b64)
    return Response(img_bytes, mimetype='image/png', headers={
        'Cache-Control': 'public, max-age=86400',
        'Content-Type': 'image/png'
    })

@app.route('/')
def nhl_dashboard_main():
    # Read URL params for dynamic OG tags
    player_id = request.args.get('player', '')
    compare_ids = request.args.get('compare', '')
    mode = request.args.get('mode', 'regular')
    type_ = request.args.get('type', 'skater')

    og_title = "NHL ANALYTICA"
    og_desc = "Real-time NHL player stats powered by the proprietary Impact Rating (IR) metric. Built by Louie Suh."
    og_image = "https://nhlanalytica.com/og-image"

    if player_id:
        og_image = f"https://nhlanalytica.com/og-image?player={player_id}&mode={mode}&type={type_}"
    elif compare_ids:
        og_image = f"https://nhlanalytica.com/og-image?compare={compare_ids}&mode={mode}&type={type_}"

    return render_template_string("""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta name="description" content="NHL Analytica: Real-time NHL player stats powered by the proprietary Impact Rating (IR) metric. Built by Louie Suh.">
        <meta name="theme-color" content="#030712">
        <meta name="mobile-web-app-capable" content="yes">
        <meta name="apple-mobile-web-app-capable" content="yes">
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
        <meta name="apple-mobile-web-app-title" content="NHL Analytica">

        <!-- Open Graph -->
        <meta property="og:type" content="website">
        <meta property="og:site_name" content="NHL Analytica">
        <meta property="og:title" content="{{ og_title }}">
        <meta property="og:description" content="{{ og_desc }}">
        <meta property="og:image" content="{{ og_image }}">
        <meta property="og:image:width" content="1200">
        <meta property="og:image:height" content="630">
        <meta property="og:url" content="https://nhlanalytica.com/">

        <!-- Twitter Card -->
        <meta name="twitter:card" content="summary_large_image">
        <meta name="twitter:site" content="@nhl_analytica">
        <meta name="twitter:title" content="{{ og_title }}">
        <meta name="twitter:description" content="{{ og_desc }}">
        <meta name="twitter:image" content="{{ og_image }}">
        <meta name="twitter:creator" content="@nhl_analytica">

        <link rel="manifest" href="/manifest.json">
        <link rel="apple-touch-icon" sizes="180x180" href="{{ url_for('static', filename='images/logo.png') }}">

        <title>NHL ANALYTICA</title>

        <!-- FAVICON: embedded as base64, no file path needed -->
        <link rel="icon" type="image/png" sizes="32x32" href="data:image/png;base64,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">
        <link rel="icon" type="image/png" sizes="16x16" href="data:image/png;base64,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">
        <link rel="apple-touch-icon" sizes="180x180" href="data:image/png;base64,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">
        <link rel="shortcut icon" href="data:image/png;base64,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">

        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&family=Syncopate:wght@700&display=swap" rel="stylesheet">
        <style>
            :root { --accent: #38bdf8; --bg: #030712; --card: rgba(31, 41, 55, 0.45); }
            body { background: #030712; color: white; font-family: 'Inter', sans-serif; margin: 0; overflow-x: hidden; }
            header { padding: 20px 5%; background: rgba(3,7,18,0.95); border-bottom: 1px solid rgba(255,255,255,0.1); display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 1000; backdrop-filter: blur(10px); }
            .logo { display: flex; align-items: center; gap: 12px; font-family: 'Syncopate'; color: var(--accent); font-size: 1.5rem; text-decoration: none; }
            .logo svg { width: 38px; height: 38px; }
            .search-box { background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2); padding: 12px 20px; border-radius: 12px; color: white; width: 300px; outline: none; }
            .team-bar { display: flex; gap: 15px; padding: 15px 5%; overflow-x: auto; background: rgba(255,255,255,0.01); border-bottom: 1px solid rgba(255,255,255,0.05); scrollbar-width: none; }
            .team-bar::-webkit-scrollbar { display: none; }
            .team-logo-btn { width: 45px; height: 45px; cursor: pointer; transition: 0.3s; opacity: 0.4; filter: grayscale(1); flex-shrink: 0; }
            .team-logo-btn:hover, .team-logo-btn.active { opacity: 1; filter: grayscale(0); transform: scale(1.1); }
            .nav-tabs { display: flex; justify-content: center; gap: 40px; padding: 20px 0; }
            .tab-btn { font-family: 'Syncopate'; font-size: 0.8rem; cursor: pointer; color: #64748b; border: none; background: none; outline:none; transition: 0.3s; padding-bottom: 5px; }
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
            .m-left { padding: 40px; border-right: 1px solid rgba(255,255,255,0.05); text-align: center; overflow-y: auto; }
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
            .rank-info { font-size: 0.7rem; color: #64748b; text-align: center; padding: 10px 0; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; }
            /* IR About Modal */
            .ir-about-btn { background: none; border: 1px solid rgba(255,255,255,0.2); color: #aab4be; font-size: 0.7rem; font-family: 'Syncopate'; padding: 6px 12px; border-radius: 8px; cursor: pointer; transition: 0.3s; }
            .ir-about-btn:hover { border-color: var(--accent); color: var(--accent); }
            .ir-modal { display:none; position:fixed; z-index:3000; left:0; top:0; width:100%; height:100%; background:rgba(2,6,23,0.97); backdrop-filter:blur(10px); }
            .ir-modal-box { background: #0b1426; width: 600px; max-width: 92%; margin: 10vh auto; border-radius: 25px; border: 1px solid #1f3a52; padding: 40px; overflow-y: auto; max-height: 80vh; }
            .ir-formula { background: #16253d; border: 1px solid #1f3a52; border-radius: 12px; padding: 16px; font-family: monospace; font-size: 0.85rem; color: var(--accent); margin: 15px 0; line-height: 1.8; }
            .ir-grade-row { display: flex; align-items: center; gap: 12px; margin: 8px 0; }
            .ir-grade-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
            /* Push notification bell */
            .notif-btn { background: none; border: 1px solid rgba(255,255,255,0.15); color: #aab4be; width: 40px; height: 40px; border-radius: 50%; cursor: pointer; font-size: 1.1rem; transition: 0.3s; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
            .notif-btn:hover { border-color: var(--accent); color: var(--accent); }
            .notif-btn.subscribed { border-color: #2ecc71; color: #2ecc71; }
            /* Last updated indicator */
            .last-updated { font-size: 0.65rem; color: #64748b; text-align: center; padding: 4px 0 8px; font-weight: 600; letter-spacing: 0.5px; }
            .last-updated.refreshing { color: var(--accent); animation: blink 1.2s infinite; }
            /* Back to top */
            .back-to-top { position: fixed; bottom: 30px; right: 30px; background: var(--accent); color: #000; border: none; width: 44px; height: 44px; border-radius: 50%; font-size: 1.2rem; cursor: pointer; display: none; align-items: center; justify-content: center; z-index: 999; box-shadow: 0 4px 15px rgba(56,189,248,0.4); transition: 0.3s; }
            .back-to-top:hover { background: #fff; transform: translateY(-3px); }
            /* Footer */
            footer { border-top: 1px solid rgba(255,255,255,0.07); padding: 30px 5%; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px; margin-top: 40px; }
            .footer-left { font-family: 'Syncopate'; color: var(--accent); font-size: 0.75rem; }
            .footer-left span { color: #64748b; font-family: 'Inter'; font-size: 0.75rem; font-weight: 400; display: block; margin-top: 4px; }
            .footer-yt { display: flex; align-items: center; gap: 8px; color: #aab4be; text-decoration: none; font-size: 0.8rem; font-weight: 700; border: 1px solid rgba(255,255,255,0.1); padding: 8px 16px; border-radius: 10px; transition: 0.3s; }
            .footer-yt:hover { border-color: #ff0000; color: #ff4444; }
            .footer-yt svg { width: 18px; height: 18px; fill: currentColor; }
            /* Team Page */
            .team-page { display:none; position:fixed; z-index:1500; left:0; top:0; width:100%; height:100%; background:#030712; overflow-y:auto; }
            .team-page-inner { max-width: 1100px; margin: 0 auto; padding: 30px 5%; }
            .team-page-header { display: flex; align-items: center; gap: 20px; margin-bottom: 30px; padding-bottom: 20px; border-bottom: 1px solid rgba(255,255,255,0.07); }
            .back-btn { background: none; border: 1px solid rgba(255,255,255,0.2); color: #aab4be; padding: 8px 16px; border-radius: 8px; cursor: pointer; font-family: 'Syncopate'; font-size: 0.65rem; transition: 0.3s; }
            .back-btn:hover { border-color: var(--accent); color: var(--accent); }
            .team-stat-summary { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 12px; margin-bottom: 28px; }
            .team-stat-card { background: #0f1f35; border: 1px solid #1f3a52; border-radius: 14px; padding: 16px; text-align: center; }
            .team-stat-card small { color: #637381; font-size: 0.6rem; font-weight: 800; text-transform: uppercase; }
            .team-stat-card b { font-size: 1.4rem; display: block; margin-top: 6px; color: var(--accent); }
            /* Trending IR Leaderboard */
            .trending-modal { display:none; position:fixed; z-index:3000; left:0; top:0; width:100%; height:100%; background:rgba(2,6,23,0.97); backdrop-filter:blur(10px); }
            .trending-modal-box { background: #0b1426; width: 600px; max-width: 96%; margin: 8vh auto; border-radius: 25px; border: 1px solid #1f3a52; padding: 36px; overflow-y: auto; max-height: 84vh; box-sizing: border-box; }
            .trend-row { display: flex; align-items: center; gap: 10px; padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.05); min-width: 0; }
            .trend-rank { font-family: 'Syncopate'; font-size: 0.65rem; color: #64748b; width: 28px; flex-shrink: 0; }
            .trend-arrow { font-size: 0.8rem; font-weight: 900; width: 16px; flex-shrink: 0; }
            .trend-ir { font-weight: 900; font-size: 1.05rem; flex-shrink: 0; min-width: 42px; text-align: right; }
            /* Share button in modal */
            .share-btn { background: none; border: 1px solid rgba(56,189,248,0.4); color: var(--accent); font-size: 0.65rem; font-family: 'Syncopate'; padding: 6px 12px; border-radius: 8px; cursor: pointer; transition: 0.3s; margin-top: 10px; }
            .share-btn:hover { background: var(--accent); color: #000; }
            /* Mobile responsive */
            @media (max-width: 768px) {
                header { padding: 14px 4%; flex-wrap: wrap; gap: 10px; }
                .logo { font-size: 1rem; }
                .logo svg { width: 28px; height: 28px; }
                .search-box { width: 100%; box-sizing: border-box; padding: 10px 14px; font-size: 0.9rem; }
                .footer-yt { font-size: 0.7rem; padding: 6px 10px; }
                .footer-yt svg { width: 14px; height: 14px; }
                .nav-tabs { gap: 18px; padding: 14px 0; flex-wrap: wrap; justify-content: center; }
                .tab-btn { font-size: 0.7rem; }
                .grid { grid-template-columns: 1fr; padding: 16px 4%; gap: 14px; }
                .modal-box { grid-template-columns: 1fr; width: 96%; margin: 4vh auto; border-radius: 18px; max-height: 92vh; overflow-y: auto; }
                .m-left { padding: 24px 20px; max-height: none; border-right: none; border-bottom: 1px solid rgba(255,255,255,0.05); overflow-y: visible; }
                .m-right { padding: 24px 20px; min-height: 280px; }
                .m-left h2 { font-size: 1.2rem !important; }
                .comp-btn { top: 16px; right: 16px; padding: 8px 12px; font-size: 0.65rem; }
                .comp-info-text { bottom: 12px; font-size: 0.65rem; }
                .stat-grid { grid-template-columns: repeat(3, 1fr); }
                .ir-modal-box { padding: 24px 20px; margin: 6vh auto; }
                .trending-modal-box { padding: 24px 16px; }
                footer { flex-direction: column; align-items: flex-start; }
            }
        </style>
    </head>
    <body>
        <div id="loading"><h1>SYNCING LIVE STATS...</h1><p id="loading-msg">Initializing Team Rosters.</p></div>
        <header>
            <a href="/" class="logo">
                <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M21,16.5C21,16.88 20.79,17.21 20.47,17.38L12.57,21.82C12.41,21.94 12.21,22 12,22C11.79,22 11.59,21.94 11.43,21.82L3.53,17.38C3.21,17.21 3,16.88 3,16.5V7.5C3,7.12 3.21,6.79 3.53,6.62L11.43,2.18C11.59,2.06 11.79,2 12,2C12.21,2 12.41,2.06 12.57,2.18L20.47,6.62C20.79,6.79 21,7.12 21,7.5V16.5Z" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M12,22V12 L20.47,7.38 M12,12L3.53,7.38" stroke="currentColor" stroke-width="1.2"/><path d="M18,15V11.5" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/><path d="M15,15V13" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/><path d="M12,15V12.5" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/></svg>
                <span>NHL ANALYTICA</span>
            </a>
            <input type="text" id="pSearch" class="search-box" placeholder="Search Player Name..." oninput="render()">
            <button class="notif-btn" id="notif-btn" onclick="togglePushSubscription()" title="Get trade alerts">🔔</button>
            <a href="https://www.youtube.com/@nhl_analytica" target="_blank" class="footer-yt">
                <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>
                WATCH ON YOUTUBE
            </a>
        </header>
        <!-- IR About Modal -->
        <div id="ir-modal" class="ir-modal" onclick="closeIRModal()">
            <div class="ir-modal-box" onclick="event.stopPropagation()">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:24px;">
                    <span style="font-family:'Syncopate'; color:var(--accent); font-size:1rem;">IMPACT RATING (IR)</span>
                    <button onclick="closeIRModal()" style="background:none; border:none; color:#aab4be; font-size:1.4rem; cursor:pointer;">✕</button>
                </div>
                <p style="color:#aab4be; font-size:0.9rem; line-height:1.7; margin-bottom:20px;">Impact Rating (IR) is a proprietary composite metric developed by NHL Analytica to measure a player's overall contribution beyond raw counting stats. It combines scoring efficiency, shot quality, puck possession impact, and durability into a single score from 0–99.9.</p>
                <div style="font-family:'Syncopate'; font-size:0.7rem; color:var(--accent); margin-bottom:10px;">SKATER FORMULA</div>
                <div class="ir-formula">IR = (PPG × 40)<br>   + (PTS/Shots × 25)<br>   + (max(0, PM+10) / 2)<br>   + (GP / 10)<br><br>Capped at 99.9</div>
                <div style="font-family:'Syncopate'; font-size:0.7rem; color:var(--accent); margin-bottom:10px; margin-top:20px;">GOALIE FORMULA</div>
                <div class="ir-formula">IR = (W/GP × 40)<br>   + ((SV% − 85) × 4)<br>   + ((5 − GAA) × 2)<br><br>Capped at 99.9</div>
                <div style="font-family:'Syncopate'; font-size:0.7rem; color:var(--accent); margin: 20px 0 12px;">IR GRADES</div>
                <div class="ir-grade-row"><div class="ir-grade-dot" style="background:#ff6b6b"></div><span style="color:#ff6b6b; font-weight:800;">Elite</span><span style="color:#aab4be; font-size:0.85rem; margin-left:4px;">— IR ≥ 90</span></div>
                <div class="ir-grade-row"><div class="ir-grade-dot" style="background:#f1c40f"></div><span style="color:#f1c40f; font-weight:800;">Above Average</span><span style="color:#aab4be; font-size:0.85rem; margin-left:4px;">— IR 75–89</span></div>
                <div class="ir-grade-row"><div class="ir-grade-dot" style="background:#2ecc71"></div><span style="color:#2ecc71; font-weight:800;">Average</span><span style="color:#aab4be; font-size:0.85rem; margin-left:4px;">— IR 60–74</span></div>
                <div class="ir-grade-row"><div class="ir-grade-dot" style="background:#aab4be"></div><span style="color:#aab4be; font-weight:800;">Below Average</span><span style="color:#aab4be; font-size:0.85rem; margin-left:4px;">— IR &lt; 60</span></div>
                <p style="color:#637381; font-size:0.75rem; margin-top:24px; line-height:1.6;">IR is calculated using full-season regular season or playoff data from the NHL Stats API. Minimum games played thresholds apply to filter out small sample sizes.</p>
            </div>
        </div>
        <div class="team-bar" id="team-bar"></div>
        <div class="nav-tabs">
            <button class="tab-btn active" id="regular-mode" onclick="switchMode('regular')">REGULAR</button>
            <button class="tab-btn" id="playoff-mode" onclick="switchMode('playoff')">PLAYOFF</button>
            <div class="divider"></div>
            <button class="tab-btn active" id="skater-tab" onclick="switchType('skater')">SKATERS</button>
            <button class="tab-btn" id="goalie-tab" onclick="switchType('goalie')">GOALIES</button>
            <div class="divider"></div>
            <button class="ir-about-btn" onclick="document.getElementById('ir-modal').style.display='block'; document.body.style.overflow='hidden'">WHAT IS IR?</button>
            <button class="ir-about-btn" onclick="openTrending()">IR TOP 10</button>
        </div>
        <div class="rank-info" id="rank-info-text">RANKING BY POINTS (MIN 5 GP)</div>
        <div class="last-updated" id="last-updated">—</div>
        <div class="grid" id="main-grid"></div>
        <div id="modal" class="modal" onclick="closeModal()"><div class="modal-box" onclick="event.stopPropagation()"><div class="m-left" id="mInfo"></div><div class="m-right" id="mRight"></div></div></div>
        <!-- Team Page -->
        <div id="team-page" class="team-page">
            <div class="team-page-inner">
                <div class="team-page-header">
                    <button class="back-btn" onclick="closeTeamPage()">← BACK</button>
                    <img id="tp-logo" style="width:60px; height:60px;">
                    <div>
                        <div id="tp-name" style="font-family:'Syncopate'; font-size:1.3rem; color:white;"></div>
                        <div id="tp-subtitle" style="font-size:0.75rem; color:#64748b; margin-top:4px;"></div>
                    </div>
                </div>
                <div class="team-stat-summary" id="tp-summary"></div>
                <div style="font-family:'Syncopate'; font-size:0.7rem; color:var(--accent); margin-bottom:14px;">SKATERS — RANKED BY IR</div>
                <div id="tp-skaters"></div>
                <div style="font-family:'Syncopate'; font-size:0.7rem; color:var(--accent); margin: 24px 0 14px;">GOALIES — RANKED BY IR</div>
                <div id="tp-goalies"></div>
            </div>
        </div>

        <!-- Trending IR Modal -->
        <div id="trending-modal" class="trending-modal" onclick="closeTrending()">
            <div class="trending-modal-box" onclick="event.stopPropagation()">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;">
                    <span style="font-family:'Syncopate'; color:var(--accent); font-size:0.9rem;">IR TOP 10 — <span id="trending-mode-label">REGULAR</span></span>
                    <button onclick="closeTrending()" style="background:none; border:none; color:#aab4be; font-size:1.4rem; cursor:pointer;">✕</button>
                </div>
                <div style="font-size:0.75rem; color:#64748b; margin-bottom:18px;">Players ranked by Impact Rating (IR) score this season. Click any player to view their full profile.</div>
                <div style="font-family:'Syncopate'; font-size:0.65rem; color:#64748b; margin-bottom:10px;">TOP SKATERS</div>
                <div id="trending-skaters"></div>
                <div style="font-family:'Syncopate'; font-size:0.65rem; color:#64748b; margin: 18px 0 10px;">TOP GOALIES</div>
                <div id="trending-goalies"></div>
            </div>
        </div>

        <!-- Footer -->
        <footer>
            <div class="footer-left">
                NHL ANALYTICA
                <span>© 2025 Louie Suh · Proprietary IR Metric · Data via NHL Stats API</span>
            </div>
        </footer>
        <button class="back-to-top" id="back-to-top" onclick="window.scrollTo({top:0,behavior:'smooth'})">↑</button>
        <script>
            let rawData = null; let currentMode = 'regular'; let currentType = 'skater'; 
            let currentTeam = null; let chartInstance = null; let compareBasePlayer = null;
            const teams = ["ANA", "BOS", "BUF", "CGY", "CAR", "CHI", "COL", "CBJ", "DAL", "DET", "EDM", "FLA", "LAK", "MIN", "MTL", "NSH", "NJD", "NYI", "NYR", "OTT", "PHI", "PIT", "SJS", "SEA", "STL", "TBL", "TOR", "UTA", "VAN", "VGK", "WSH", "WPG"];

            let lastUpdated = null;

            async function init() {
                const loadingMsg = document.getElementById('loading-msg');
                // Show retry button after 8 seconds if still loading
                const slowTimer = setTimeout(() => {
                    if (document.getElementById('loading').style.display !== 'none') {
                        loadingMsg.innerHTML = 'Taking longer than usual... <button onclick="location.reload()" style="background:var(--accent);color:#000;border:none;padding:6px 14px;border-radius:8px;font-weight:900;cursor:pointer;margin-left:8px;">RETRY</button>';
                    }
                }, 8000);
                try {
                    const controller = new AbortController();
                    const timeout = setTimeout(() => controller.abort(), 25000);
                    const res = await fetch('/api/data?t=' + Date.now(), { signal: controller.signal });
                    clearTimeout(timeout);
                    clearTimeout(slowTimer);
                    rawData = await res.json();
                    lastUpdated = new Date();
                    // Check if we actually got data
                    const hasData = rawData?.regular?.skaters?.length > 0 || rawData?.regular?.goalies?.length > 0;
                    if (!hasData) {
                        document.getElementById('loading').innerHTML = '<h1 style="font-size:1.2rem">NHL API is temporarily unavailable</h1><p style="color:#64748b;margin:10px 0 20px;">Stats are refreshed automatically. Check back in a few minutes.</p><button onclick="location.reload()" style="background:var(--accent);color:#000;border:none;padding:10px 24px;border-radius:10px;font-weight:900;cursor:pointer;font-size:1rem;">TRY AGAIN</button>';
                        return;
                    }
                    document.getElementById('loading').style.display = 'none';
                    buildTeamBar(); render();
                    handleURLParams();
                    startAutoRefresh();
                } catch (e) {
                    clearTimeout(slowTimer);
                    document.getElementById('loading').innerHTML = '<h1>LOAD ERROR</h1><p>NHL API may be down.</p><button onclick="location.reload()" style="background:var(--accent);color:#000;border:none;padding:10px 24px;border-radius:10px;font-weight:900;cursor:pointer;font-size:1rem;margin-top:16px;">TRY AGAIN</button>';
                }
            }

            async function refreshData() {
                const el = document.getElementById('last-updated');
                if (el) { el.textContent = '⟳ REFRESHING ROSTER DATA...'; el.classList.add('refreshing'); }
                try {
                    const res = await fetch('/api/data?t=' + Date.now());
                    const newData = await res.json();
                    const hasData = newData?.regular?.skaters?.length > 0;
                    if (hasData) {
                        rawData = newData;
                        lastUpdated = new Date();
                        // If we were showing the error screen, recover
                        if (document.getElementById('loading').style.display !== 'none') {
                            document.getElementById('loading').style.display = 'none';
                            buildTeamBar(); render();
                        }
                        if (el) { el.classList.remove('refreshing'); updateLastUpdatedLabel(); }
                        render();
                    } else {
                        if (el) { el.classList.remove('refreshing'); el.textContent = 'NHL API UNAVAILABLE · RETRYING...'; }
                    }
                } catch (e) {
                    if (el) { el.classList.remove('refreshing'); el.textContent = 'REFRESH FAILED · RETRYING SOON'; }
                }
            }

            function updateLastUpdatedLabel() {
                if (!lastUpdated) return;
                const mins = Math.floor((new Date() - lastUpdated) / 60000);
                const el = document.getElementById('last-updated');
                el.textContent = mins === 0 ? 'ROSTER DATA UPDATED JUST NOW' : `ROSTER DATA UPDATED ${mins} MIN AGO`;
            }

            function startAutoRefresh() {
                updateLastUpdatedLabel();
                // update the "X mins ago" label every minute
                setInterval(updateLastUpdatedLabel, 60000);
                // refresh data every 5 minutes
                setInterval(refreshData, 5 * 60 * 1000);
            }

            function buildTeamBar() {
                const bar = document.getElementById('team-bar');
                bar.innerHTML = teams.map(t => `<img src="https://assets.nhle.com/logos/nhl/svg/${t}_light.svg" class="team-logo-btn" id="btn-${t}" onclick="filterByTeam('${t}')" ondblclick="openTeamPage('${t}')" title="${t} — click to filter, double-click for team page">`).join('');
            }

            function filterByTeam(team) {
                const btns = document.querySelectorAll('.team-logo-btn');
                if (currentTeam === team) {
                    currentTeam = null;
                    btns.forEach(b => b.classList.remove('active'));
                } else {
                    currentTeam = team;
                    btns.forEach(b => b.classList.remove('active'));
                    const target = document.getElementById('btn-' + team);
                    if(target) target.classList.add('active');
                }
                render();
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
                let data = rawData[currentMode][currentType + "s"];
                
                if (currentTeam) {
                    const target = currentTeam.trim().toUpperCase();
                    data = data.filter(p => (p.abbr || "").trim().toUpperCase() === target);
                }
                
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
            function startCompare(id) { const data = rawData[currentMode][currentType + "s"]; compareBasePlayer = data.find(x => x.id === id); document.getElementById('modal').style.display = 'none'; document.body.style.overflow = ''; render(); }
            function closeModal() { 
                document.getElementById('modal').style.display = 'none'; 
                document.body.style.overflow = ''; 
                compareBasePlayer = null; 
                // clear compare params from URL
                const url = new URL(window.location);
                url.searchParams.delete('compare');
                window.history.replaceState({}, '', url);
                render(); 
            }
            function closeIRModal() { document.getElementById('ir-modal').style.display = 'none'; document.body.style.overflow = ''; }

            // ── SHAREABLE COMPARE URL ──
            function openModal(id, compareWith = null) {
                const data = rawData[currentMode][currentType + "s"];
                const p = data.find(x => x.id === id); if(!p) return;
                let irGrade = p.ir >= 90 ? "Elite" : p.ir >= 75 ? "Above Average" : p.ir >= 60 ? "Average" : "Below Average";
                let irCol = p.ir >= 90 ? "#ff6b6b" : p.ir >= 75 ? "#f1c40f" : p.ir >= 60 ? "#2ecc71" : "#aab4be";
                const kfHtml = `<div class="kf-item"><span class="kf-label">Recent Form</span><span class="kf-val" style="color:${p.ppg>=0.7?'#ff6b6b':'#38bdf8'}">${p.ppg>=0.7?'Hot':'Cold'} ▲</span></div><div class="kf-item"><span class="kf-label">Impact Rating</span><span class="kf-val" style="color:${irCol}">${irGrade} ▲</span></div><div class="kf-item"><span class="kf-label">Shot Efficiency</span><span class="kf-val" style="color:${p.type==='skater'?(p.pts/Math.max(1,p.sh))>=0.18?'#2ecc71':'#f1c40f':'#aab4be'}">${p.type==='skater'?((p.pts/Math.max(1,p.sh))>=0.18?'High ▲':'Moderate ▲'):'N/A'}</span></div>`;
                let statsHtml = p.type === 'skater' ? `<div class="stat-box"><small>GP</small><b>${p.gp}</b></div><div class="stat-box"><small>PPG</small><b>${p.ppg}</b></div><div class="stat-box"><small>IR SCORE</small><b style="color:var(--accent)">${p.ir}</b></div><div class="stat-box"><small>+/-</small><b>${p.pm}</b></div><div class="stat-box"><small>GOALS</small><b>${p.g}</b></div>` : `<div class="stat-box"><small>GP</small><b>${p.gp}</b></div><div class="stat-box"><small>WINS</small><b>${p.w}</b></div><div class="stat-box"><small>IR SCORE</small><b style="color:var(--accent)">${p.ir}</b></div><div class="stat-box"><small>SV%</small><b>${p.sv}%</b></div><div class="stat-box"><small>GAA</small><b>${p.gaa}</b></div>`;
                // share button
                const shareUrl = compareWith 
                    ? `${window.location.origin}?compare=${p.id},${compareWith.id}&mode=${currentMode}&type=${currentType}`
                    : `${window.location.origin}?player=${p.id}&mode=${currentMode}&type=${currentType}`;
                const shareBtnHtml = `<button class="share-btn" onclick="copyShareLink('${shareUrl}')">🔗 COPY SHARE LINK</button>`;
                document.getElementById('mInfo').innerHTML = `<div style="font-size:0.7rem; color:var(--accent); font-weight:900; margin-bottom:10px; font-family:'Syncopate';">LEAGUE RANK #${p.rank}</div><img src="https://assets.nhle.com/mugs/nhl/latest/${p.id}.png" style="width:150px; border-radius:50%; border:4px solid ${p.col};"><h2 style="font-family:'Syncopate'; margin:15px 0 10px; font-size:1.8rem;">${p.name.toUpperCase()}</h2><div style="background:${p.col}; color:#ffffff; padding: 6px 14px; border-radius: 8px; font-weight:800; font-size:0.85rem; letter-spacing: 1px; margin-bottom:12px; display:inline-block; box-shadow: 0 4px 10px rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.2); text-shadow: 1px 1px 2px rgba(0,0,0,0.7);">${p.team.toUpperCase()}</div><br>${shareBtnHtml}<div class="stat-grid" style="margin-top:16px;">${statsHtml}</div><div class="kf-container"><div class="kf-title">Key Factors</div>${kfHtml}</div><div class="prob-box"><small style="color:#fbbf24; font-weight:800;">${p.type==='skater'?'GOAL PROBABILITY':'SHUTOUTS'}</small><b>${p.type==='skater'?p.prob+'%':p.so}</b></div>`;
                const compBtnHtml = compareWith ? '' : `<button class="comp-btn" onclick="startCompare('${p.id}')">COMPARE</button>`;
                document.getElementById('mRight').innerHTML = `${compBtnHtml}<canvas id="radar"></canvas><div class="comp-info-text">${compareWith ? 'VS ' + compareWith.name : 'ANALYZING ' + currentMode.toUpperCase()}</div>`;
                document.getElementById('modal').style.display = 'block'; document.body.style.overflow = 'hidden'; drawRadar(p, compareWith);
                // update URL without reloading
                const urlParams = compareWith ? `?compare=${p.id},${compareWith.id}&mode=${currentMode}&type=${currentType}` : `?player=${p.id}&mode=${currentMode}&type=${currentType}`;
                window.history.replaceState({}, '', urlParams);
            }
            function copyShareLink(url) {
                navigator.clipboard.writeText(url).then(() => {
                    const btn = document.querySelector('.share-btn');
                    if(btn) { btn.textContent = '✓ COPIED!'; setTimeout(() => btn.textContent = '🔗 COPY SHARE LINK', 2000); }
                });
            }
            // handle URL params on load
            function handleURLParams() {
                const params = new URLSearchParams(window.location.search);
                const mode = params.get('mode') || 'regular';
                const type = params.get('type') || 'skater';
                currentMode = mode; currentType = type;
                document.getElementById('regular-mode').classList.toggle('active', mode === 'regular');
                document.getElementById('playoff-mode').classList.toggle('active', mode === 'playoff');
                document.getElementById('skater-tab').classList.toggle('active', type === 'skater');
                document.getElementById('goalie-tab').classList.toggle('active', type === 'goalie');
                const playerId = params.get('player');
                const compareIds = params.get('compare');
                if (compareIds) {
                    const [id1, id2] = compareIds.split(',');
                    const data = rawData[mode][type + 's'];
                    const p2 = data.find(x => x.id === id2);
                    if (p2) openModal(id1, p2); else if(id1) openModal(id1);
                } else if (playerId) { openModal(playerId); }
            }

            // ── TEAM PAGE ──
            function openTeamPage(abbr) {
                if (!rawData) return;
                const skaters = rawData[currentMode].skaters.filter(p => p.abbr === abbr).sort((a,b) => b.ir - a.ir);
                const goalies = rawData[currentMode].goalies.filter(p => p.abbr === abbr).sort((a,b) => b.ir - a.ir);
                const teamName = skaters[0]?.team || goalies[0]?.team || abbr;
                const col = skaters[0]?.col || goalies[0]?.col || '#38bdf8';
                const avgIR = skaters.length ? (skaters.reduce((s,p)=>s+p.ir,0)/skaters.length).toFixed(1) : 'N/A';
                const topScorer = skaters[0];
                const topGoalie = goalies[0];
                document.getElementById('tp-logo').src = `https://assets.nhle.com/logos/nhl/svg/${abbr}_light.svg`;
                document.getElementById('tp-name').textContent = teamName.toUpperCase();
                document.getElementById('tp-subtitle').textContent = `${currentMode.toUpperCase()} SEASON · ${skaters.length} SKATERS · ${goalies.length} GOALIES`;
                document.getElementById('tp-summary').innerHTML = `
                    <div class="team-stat-card"><small>Avg Team IR</small><b style="color:${col}">${avgIR}</b></div>
                    <div class="team-stat-card"><small>Top Scorer</small><b style="font-size:0.85rem; color:white">${topScorer ? topScorer.name.split(' ').pop() : '—'}</b></div>
                    <div class="team-stat-card"><small>Top IR Skater</small><b style="font-size:0.85rem; color:var(--accent)">${skaters[0]?.ir || '—'}</b></div>
                    <div class="team-stat-card"><small>Top Goalie IR</small><b style="font-size:0.85rem; color:var(--accent)">${topGoalie?.ir || '—'}</b></div>
                    <div class="team-stat-card"><small>Total Points</small><b>${skaters.reduce((s,p)=>s+p.pts,0)}</b></div>
                    <div class="team-stat-card"><small>Goalie SV%</small><b style="font-size:0.9rem">${topGoalie ? topGoalie.sv + '%' : '—'}</b></div>`;
                const makeRow = (p) => `<div onclick="closeTeamPage(); setTimeout(()=>openModal('${p.id}'),100)" style="display:flex; align-items:center; gap:12px; padding:10px 14px; background:#0f1f35; border-radius:12px; margin-bottom:8px; cursor:pointer; border:1px solid rgba(255,255,255,0.04); transition:0.2s;" onmouseover="this.style.borderColor='${col}'" onmouseout="this.style.borderColor='rgba(255,255,255,0.04)'">
                    <img src="https://assets.nhle.com/mugs/nhl/latest/${p.id}.png" style="width:36px;height:36px;border-radius:50%;background:#000" onerror="this.src='https://assets.nhle.com/logos/nhl/svg/${p.abbr}_light.svg'">
                    <div style="flex:1"><div style="font-weight:700; font-size:0.9rem;">${p.name}</div><div style="font-size:0.7rem; color:#64748b;">${p.pos || 'G'} · ${p.type==='skater'?p.pts+' PTS':p.w+' W'}</div></div>
                    <div style="text-align:right"><div style="color:var(--accent); font-weight:900; font-size:1.1rem;">${p.ir}</div><div style="font-size:0.6rem; color:#64748b;">IR</div></div></div>`;
                document.getElementById('tp-skaters').innerHTML = skaters.map(makeRow).join('') || '<div style="color:#64748b; padding:10px;">No skaters found.</div>';
                document.getElementById('tp-goalies').innerHTML = goalies.map(makeRow).join('') || '<div style="color:#64748b; padding:10px;">No goalies found.</div>';
                document.getElementById('team-page').style.display = 'block';
                document.body.style.overflow = 'hidden';
            }
            function closeTeamPage() { document.getElementById('team-page').style.display = 'none'; document.body.style.overflow = ''; }

            // ── TRENDING IR TOP 10 ──
            function openTrending() {
                if (!rawData) return;
                document.getElementById('trending-mode-label').textContent = currentMode.toUpperCase();
                const skaters = [...rawData[currentMode].skaters].sort((a,b) => b.ir - a.ir).slice(0,10);
                const goalies = [...rawData[currentMode].goalies].sort((a,b) => b.ir - a.ir).slice(0,5);
                const makeRow = (p, i) => {
                    const arrow = p.trending ? '<span style="color:#2ecc71">▲</span>' : '<span style="color:#64748b">–</span>';
                    const irCol = p.ir >= 90 ? '#ff6b6b' : p.ir >= 75 ? '#f1c40f' : '#2ecc71';
                    return `<div class="trend-row" onclick="closeTrending(); setTimeout(()=>openModal('${p.id}'),100)" style="cursor:pointer;">
                        <div class="trend-rank">#${i+1}</div>
                        <div class="trend-arrow">${arrow}</div>
                        <img src="https://assets.nhle.com/mugs/nhl/latest/${p.id}.png" style="width:34px;height:34px;border-radius:50%;background:#000;flex-shrink:0;" onerror="this.src='https://assets.nhle.com/logos/nhl/svg/${p.abbr}_light.svg'">
                        <div style="flex:1;min-width:0;overflow:hidden;"><div style="font-weight:700; font-size:0.85rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${p.name}</div><div style="font-size:0.68rem; color:#64748b; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${p.team}</div></div>
                        <div class="trend-ir" style="color:${irCol};">${p.ir}</div></div>`;
                };
                document.getElementById('trending-skaters').innerHTML = skaters.map(makeRow).join('');
                document.getElementById('trending-goalies').innerHTML = goalies.map(makeRow).join('');
                document.getElementById('trending-modal').style.display = 'block';
                document.body.style.overflow = 'hidden';
            }
            function closeTrending() { document.getElementById('trending-modal').style.display = 'none'; document.body.style.overflow = ''; }

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
            // ── PUSH NOTIFICATIONS ──
            let pushSubscription = null;

            function urlBase64ToUint8Array(base64String) {
                const padding = '='.repeat((4 - base64String.length % 4) % 4);
                const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
                const rawData = window.atob(base64);
                return new Uint8Array([...rawData].map(c => c.charCodeAt(0)));
            }

            async function togglePushSubscription() {
                const btn = document.getElementById('notif-btn');
                if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
                    alert('Push notifications are not supported in this browser.');
                    return;
                }
                if (pushSubscription) {
                    // Unsubscribe
                    await fetch('/push/unsubscribe', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(pushSubscription.toJSON())
                    });
                    await pushSubscription.unsubscribe();
                    pushSubscription = null;
                    btn.textContent = '🔔';
                    btn.classList.remove('subscribed');
                    btn.title = 'Get trade alerts';
                } else {
                    // Subscribe
                    try {
                        const permission = await Notification.requestPermission();
                        if (permission !== 'granted') {
                            alert('Please allow notifications to get trade alerts.');
                            return;
                        }
                        const reg = await navigator.serviceWorker.ready;
                        const keyRes = await fetch('/push/vapid-public-key');
                        const { publicKey } = await keyRes.json();
                        pushSubscription = await reg.pushManager.subscribe({
                            userVisibleOnly: true,
                            applicationServerKey: urlBase64ToUint8Array(publicKey)
                        });
                        await fetch('/push/subscribe', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify(pushSubscription.toJSON())
                        });
                        btn.textContent = '🔕';
                        btn.classList.add('subscribed');
                        btn.title = 'Alerts on — click to unsubscribe';
                        showToast('🔔 Trade alerts enabled! You\'ll be notified of any roster moves.');
                    } catch (err) {
                        alert('Could not enable notifications: ' + err.message);
                    }
                }
            }

            async function checkExistingSubscription() {
                if (!('serviceWorker' in navigator) || !('PushManager' in window)) return;
                try {
                    const reg = await navigator.serviceWorker.ready;
                    const sub = await reg.pushManager.getSubscription();
                    if (sub) {
                        pushSubscription = sub;
                        const btn = document.getElementById('notif-btn');
                        btn.textContent = '🔕';
                        btn.classList.add('subscribed');
                        btn.title = 'Alerts on — click to unsubscribe';
                    }
                } catch(e) {}
            }

            function showToast(message) {
                const toast = document.createElement('div');
                toast.style.cssText = 'position:fixed;bottom:90px;left:50%;transform:translateX(-50%);background:#0b1426;border:1px solid #2ecc71;color:#2ecc71;padding:12px 24px;border-radius:12px;font-size:0.85rem;font-weight:700;z-index:9999;animation:fadeIn 0.3s;max-width:90%;text-align:center;';
                toast.textContent = message;
                document.body.appendChild(toast);
                setTimeout(() => toast.remove(), 4000);
            }

            // Back to top
            const btt = document.getElementById('back-to-top');
            window.addEventListener('scroll', () => { btt.style.display = window.scrollY > 400 ? 'flex' : 'none'; });

            // Register service worker for PWA
            if ('serviceWorker' in navigator) {
                navigator.serviceWorker.register('/service-worker.js')
                    .then(() => checkExistingSubscription())
                    .catch(err => console.log('SW registration failed:', err));
            }

            init();
        </script>
    </body>
    </html>
    """, og_title=og_title, og_desc=og_desc, og_image=og_image)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
