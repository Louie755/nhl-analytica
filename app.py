import pandas as pd
from flask import Flask, render_template_string, jsonify, request, Response
import requests
import os
import time
import sqlite3
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

app = Flask(__name__)

# Optional gzip/brotli compression (pip install flask-compress).
# Big win for the bootstrap payload below; silently skipped if not installed.
try:
    from flask_compress import Compress
    Compress(app)
except Exception:
    pass

# Browser-like headers to avoid bot detection
NHL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.nhl.com",
    "Referer": "https://www.nhl.com/",
}

# 팀 데이터 및 컬러 설정 (원본 유지)
TEAM_MAP = {"ANA": "Anaheim Ducks", "BOS": "Boston Bruins", "BUF": "Buffalo Sabres", "CGY": "Calgary Flames", "CAR": "Carolina Hurricanes", "CHI": "Chicago Blackhawks", "COL": "Colorado Avalanche", "CBJ": "Columbus Blue Jackets", "DAL": "Dallas Stars", "DET": "Detroit Red Wings", "EDM": "Edmonton Oilers", "FLA": "Florida Panthers", "LAK": "Los Angeles Kings", "MIN": "Minnesota Wild", "MTL": "Montreal Canadiens", "NSH": "Nashville Predators", "NJD": "New Jersey Devils", "NYI": "New York Islanders", "NYR": "New York Rangers", "OTT": "Ottawa Senators", "PHI": "Philadelphia Flyers", "PIT": "Pittsburgh Penguins", "SJS": "San Jose Sharks", "SEA": "Seattle Kraken", "STL": "St Louis Blues", "TBL": "Tampa Bay Lightning", "TOR": "Toronto Maple Leafs", "UTA": "Utah Hockey Club", "VAN": "Vancouver Canucks", "VGK": "Vegas Golden Knights", "WSH": "Washington Capitals", "WPG": "Winnipeg Jets"}
TEAM_COLORS = {"ANA": "#F47A38", "BOS": "#FFB81C", "BUF": "#002654", "CGY": "#C8102E", "CAR": "#CE1126", "CHI": "#CF0A2C", "COL": "#6F263D", "CBJ": "#002654", "DAL": "#006847", "DET": "#CE1126", "EDM": "#FF4C00", "FLA": "#041E42", "LAK": "#111111", "MIN": "#154734", "MTL": "#AF1E2D", "NSH": "#FFB81C", "NJD": "#CE1126", "NYI": "#00539B", "NYR": "#0038A8", "OTT": "#C8102E", "PHI": "#F74902", "PIT": "#FCB514", "SJS": "#006D75", "SEA": "#001628", "STL": "#002F87", "TBL": "#002868", "TOR": "#00205B", "UTA": "#71AFE2", "VAN": "#00205B", "VGK": "#B4975A", "WSH": "#041E42", "WPG": "#004C97"}

# Hardcoded 2024-25 season fallback data — used when NHL API is down
# Based on final 2024-25 regular season stats
FALLBACK_SKATERS = [
    {"playerId": "8478402", "skaterFullName": "Connor McDavid", "teamAbbrevs": "EDM", "positionCode": "C", "gamesPlayed": 81, "points": 123, "goals": 44, "assists": 79, "plusMinus": 28, "shots": 261},
    {"playerId": "8476453", "skaterFullName": "Nikita Kucherov", "teamAbbrevs": "TBL", "positionCode": "R", "gamesPlayed": 82, "points": 121, "goals": 39, "assists": 82, "plusMinus": 22, "shots": 231},
    {"playerId": "8477492", "skaterFullName": "Nathan MacKinnon", "teamAbbrevs": "COL", "positionCode": "C", "gamesPlayed": 80, "points": 118, "goals": 43, "assists": 75, "plusMinus": 30, "shots": 298},
    {"playerId": "8480785", "skaterFullName": "Mitch Marner", "teamAbbrevs": "VGK", "positionCode": "R", "gamesPlayed": 82, "points": 102, "goals": 32, "assists": 70, "plusMinus": 18, "shots": 198},
    {"playerId": "8477934", "skaterFullName": "Leon Draisaitl", "teamAbbrevs": "EDM", "positionCode": "C", "gamesPlayed": 80, "points": 97, "goals": 38, "assists": 59, "plusMinus": 12, "shots": 278},
    {"playerId": "8481600", "skaterFullName": "Macklin Celebrini", "teamAbbrevs": "SJS", "positionCode": "C", "gamesPlayed": 68, "points": 61, "goals": 24, "assists": 37, "plusMinus": -8, "shots": 189},
    {"playerId": "8480801", "skaterFullName": "Lane Hutson", "teamAbbrevs": "MTL", "positionCode": "D", "gamesPlayed": 82, "points": 72, "goals": 11, "assists": 61, "plusMinus": 5, "shots": 156},
    {"playerId": "8479318", "skaterFullName": "Mark Stone", "teamAbbrevs": "VGK", "positionCode": "R", "gamesPlayed": 61, "points": 58, "goals": 20, "assists": 38, "plusMinus": 14, "shots": 142},
    {"playerId": "8480744", "skaterFullName": "Nick Suzuki", "teamAbbrevs": "MTL", "positionCode": "C", "gamesPlayed": 82, "points": 88, "goals": 28, "assists": 60, "plusMinus": 9, "shots": 221},
    {"playerId": "8480803", "skaterFullName": "Evan Bouchard", "teamAbbrevs": "EDM", "positionCode": "D", "gamesPlayed": 82, "points": 76, "goals": 19, "assists": 57, "plusMinus": 16, "shots": 212},
]
FALLBACK_GOALIES = [
    {"playerId": "8481533", "goalieFullName": "Dylan Garand", "teamAbbrevs": "NYR", "gamesPlayed": 44, "wins": 26, "goalsAgainst": 98, "shotsAgainst": 1180, "shutouts": 4},
    {"playerId": "8478009", "goalieFullName": "Andrei Vasilevskiy", "teamAbbrevs": "TBL", "gamesPlayed": 58, "wins": 35, "goalsAgainst": 140, "shotsAgainst": 1620, "shutouts": 5},
    {"playerId": "8476945", "goalieFullName": "Connor Hellebuyck", "teamAbbrevs": "WPG", "gamesPlayed": 60, "wins": 37, "goalsAgainst": 138, "shotsAgainst": 1720, "shutouts": 6},
]
def fetch_nhl_safe(url, season, sort_prop, game_type=2):
    all_data = []
    start, limit = 0, 100
    while True:
        params = {"isAggregate": "false", "isGame": "false", "sort": f'[{{"property":"{sort_prop}","direction":"DESC"}}]', "start": start, "limit": limit, "cayenneExp": f"seasonId={season} and gameTypeId={game_type}"}
        try:
            r = requests.get(url, params=params, timeout=6, headers=NHL_HEADERS)
            data = r.json().get('data', [])
            if not data: break
            all_data.extend(data)
            if len(data) < limit: break
            start += limit
        except: break
    return all_data

def fetch_skaters_web(season, game_type=2, limit=200):
    try:
        url = f"https://api-web.nhle.com/v1/skater-stats-leaders/{season}/{game_type}?categories=points,goals,assists,plusMinus&limit={limit}"
        r = requests.get(url, timeout=8, headers=NHL_HEADERS)
        data = r.json()
        players = {}
        for cat, entries in data.items():
            if not isinstance(entries, list): continue
            for e in entries:
                pid = str(e.get('playerId', e.get('id', '')))
                if not pid: continue
                if pid not in players:
                    fn = e.get('firstName', {})
                    ln = e.get('lastName', {})
                    fname = fn.get('default', '') if isinstance(fn, dict) else str(fn)
                    lname = ln.get('default', '') if isinstance(ln, dict) else str(ln)
                    ta = e.get('teamAbbrev', '')
                    players[pid] = {
                        'playerId': pid,
                        'skaterFullName': f"{fname} {lname}".strip(),
                        'teamAbbrevs': ta.get('default', '') if isinstance(ta, dict) else str(ta),
                        'positionCode': e.get('position', 'F'),
                        'gamesPlayed': e.get('gamesPlayed', 0),
                        'points': 0, 'goals': 0, 'assists': 0, 'plusMinus': 0, 'shots': 1
                    }
                val = e.get('value', 0)
                if cat == 'points': players[pid]['points'] = val
                elif cat == 'goals': players[pid]['goals'] = val
                elif cat == 'assists': players[pid]['assists'] = val
                elif cat == 'plusMinus': players[pid]['plusMinus'] = val
        return list(players.values())
    except: return []

def fetch_goalies_web(season, game_type=2, limit=100):
    try:
        url = f"https://api-web.nhle.com/v1/goalie-stats-leaders/{season}/{game_type}?categories=wins,savePctg,goalsAgainstAverage,shutouts&limit={limit}"
        r = requests.get(url, timeout=8, headers=NHL_HEADERS)
        data = r.json()
        goalies = {}
        for cat, entries in data.items():
            if not isinstance(entries, list): continue
            for e in entries:
                pid = str(e.get('playerId', e.get('id', '')))
                if not pid: continue
                if pid not in goalies:
                    fn = e.get('firstName', {})
                    ln = e.get('lastName', {})
                    fname = fn.get('default', '') if isinstance(fn, dict) else str(fn)
                    lname = ln.get('default', '') if isinstance(ln, dict) else str(ln)
                    ta = e.get('teamAbbrev', '')
                    goalies[pid] = {
                        'playerId': pid,
                        'goalieFullName': f"{fname} {lname}".strip(),
                        'teamAbbrevs': ta.get('default', '') if isinstance(ta, dict) else str(ta),
                        'gamesPlayed': e.get('gamesPlayed', 0),
                        'wins': 0, 'savePct': 0.900, 'goalsAgainstAverage': 2.50,
                        'shutouts': 0, 'shotsAgainst': 100, 'goalsAgainst': 10
                    }
                val = e.get('value', 0)
                if cat == 'wins': goalies[pid]['wins'] = val
                elif cat == 'savePctg': goalies[pid]['savePct'] = val
                elif cat == 'goalsAgainstAverage': goalies[pid]['goalsAgainstAverage'] = val
                elif cat == 'shutouts': goalies[pid]['shutouts'] = val
        return list(goalies.values())
    except: return []

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

# Security: VAPID keys now read from environment variables first.
# Set VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY in your host's environment
# (Render → Environment tab). The hardcoded values remain as fallback so
# existing subscribers keep working until you migrate.
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "BJZTmoobqKLvTUvuaxlU7P0m6xjpzpzSL1kR6y7Dnuz5y9OTodNcamM1xUu4KUg1xj88GUI1VDtIuPsbgL-Of18")
VAPID_PRIVATE_PEM = os.environ.get("VAPID_PRIVATE_KEY", """-----BEGIN PRIVATE KEY-----
MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQgVKEdtzKhOVbJI081
ZMKz29NQ9cXG2+fq3rxOiV3ubO6hRANCAASWU5qKG6ii701L7msZVOz9JusY6c6c
0i9ZEesuw57s+cvTk6HTXGpjNcVLuClINcY/PBlCNVQ7SLj7G4C/jn9f
-----END PRIVATE KEY-----""")
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

# ── IR HISTORY (SQLite) ──
# Daily IR snapshots power the sparkline in the player modal and 7-day IR
# deltas in the Top 10. Writes happen ONLY inside the background refresh
# thread — a request never touches a write. Reads (/api/history) are a
# single indexed lookup on a tiny table: effectively instant.
HISTORY_DB = os.environ.get("IR_HISTORY_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "ir_history.db"))

def _history_conn():
    conn = sqlite3.connect(HISTORY_DB, timeout=5)
    conn.execute("""CREATE TABLE IF NOT EXISTS ir_history (
        snap_date TEXT NOT NULL,
        player_id TEXT NOT NULL,
        mode TEXT NOT NULL,
        ir REAL,
        pts REAL,
        PRIMARY KEY (snap_date, player_id, mode))""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_hist_player ON ir_history(player_id, mode, snap_date)")
    return conn

def save_ir_snapshot(data):
    """Write today's IR snapshot for every ranked player. Background thread only."""
    today = datetime.now().strftime('%Y-%m-%d')
    rows = []
    for mode in ('regular', 'playoff'):
        for group in ('skaters', 'goalies'):
            for p in data.get(mode, {}).get(group, []):
                rows.append((today, p['id'], mode, p.get('ir', 0), p.get('pts', p.get('w', 0))))
    if not rows:
        return
    conn = _history_conn()
    try:
        conn.executemany("INSERT OR REPLACE INTO ir_history VALUES (?,?,?,?,?)", rows)
        conn.commit()
    finally:
        conn.close()

def attach_ir_deltas(data):
    """Attach 7-day IR delta (d7) to every player in the cached payload.
    Uses the nearest snapshot at or before 7 days ago (or the oldest one
    available while history is still building). Background thread only."""
    conn = _history_conn()
    try:
        target = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        today = datetime.now().strftime('%Y-%m-%d')
        for mode in ('regular', 'playoff'):
            row = conn.execute("SELECT MAX(snap_date) FROM ir_history WHERE mode=? AND snap_date<=?", (mode, target)).fetchone()
            base_date = row[0] if row else None
            if not base_date:
                row = conn.execute("SELECT MIN(snap_date) FROM ir_history WHERE mode=? AND snap_date<?", (mode, today)).fetchone()
                base_date = row[0] if row else None
            if not base_date:
                continue
            old = dict(conn.execute("SELECT player_id, ir FROM ir_history WHERE mode=? AND snap_date=?", (mode, base_date)).fetchall())
            for group in ('skaters', 'goalies'):
                for p in data.get(mode, {}).get(group, []):
                    prev = old.get(p['id'])
                    if prev is not None:
                        p['d7'] = round(p.get('ir', 0) - prev, 1)
    finally:
        conn.close()

@app.route('/api/history/<player_id>')
def api_history(player_id):
    """Season-to-date daily IR history for one player. Indexed read, ~0ms."""
    mode = request.args.get('mode', 'regular')
    if mode not in ('regular', 'playoff'):
        mode = 'regular'
    try:
        conn = _history_conn()
        rows = conn.execute(
            "SELECT snap_date, ir FROM ir_history WHERE player_id=? AND mode=? ORDER BY snap_date DESC LIMIT 90",
            (player_id, mode)).fetchall()
        conn.close()
        rows.reverse()
        resp = jsonify([{"date": r[0], "ir": r[1]} for r in rows])
        resp.headers['Cache-Control'] = 'public, max-age=1800'
        return resp
    except Exception:
        return jsonify([])

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
            wins = p.get('wins', 0)
            # Handle both old API (goalsAgainst/shotsAgainst) and new web API (savePct/goalsAgainstAverage)
            if 'savePct' in p:
                sv_val = round(p.get('savePct', 0.900) * 100, 2)
                gaa = round(p.get('goalsAgainstAverage', 2.50), 2)
                ga = round(gaa * gp)
                sa = max(1, round(ga / max(0.001, 1 - p.get('savePct', 0.900))))
            else:
                ga, sa = p.get('goalsAgainst', 0), max(1, p.get('shotsAgainst', 0))
                sv_val = round((1 - (ga/sa)) * 100, 2) if sa > 0 else 0.0
                gaa = round(ga/gp, 2)
            ir = min(99.9, round((wins/gp * 40) + (sv_val - 85) * 4 + (5 - gaa) * 2, 1))
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

        def fetch_s_reg():
            data = fetch_skaters_web(season, 2)
            if not data: data = fetch_nhl_safe(f"https://api.nhle.com/stats/rest/en/skater/summary?t={ts}", season, "points", 2)
            return data
        def fetch_s_ply():
            data = fetch_skaters_web(season, 3)
            if not data: data = fetch_nhl_safe(f"https://api.nhle.com/stats/rest/en/skater/summary?t={ts}", season, "points", 3)
            return data
        def fetch_g_reg():
            data = fetch_goalies_web(season, 2)
            if not data: data = fetch_nhl_safe(f"https://api.nhle.com/stats/rest/en/goalie/summary?t={ts}", season, "wins", 2)
            return data
        def fetch_g_ply():
            data = fetch_goalies_web(season, 3)
            if not data: data = fetch_nhl_safe(f"https://api.nhle.com/stats/rest/en/goalie/summary?t={ts}", season, "wins", 3)
            return data

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
            # Snapshot IR history + attach 7-day deltas.
            # Still inside the background thread — zero request impact.
            try:
                save_ir_snapshot(_data_cache["data"])
                attach_ir_deltas(_data_cache["data"])
            except Exception:
                pass
        elif not _data_cache["data"]:
            # All APIs failed — use hardcoded fallback so site always loads
            _data_cache["data"] = build_data(FALLBACK_SKATERS, [], FALLBACK_GOALIES, [], set(), {})
            _data_cache["ts"] = 0  # ts=0 so it retries on next request
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
    import base64
    # ─────────────────────────────────────────────────────────────────────
    # ⚠️ ONE-LINE MIGRATION STEP:
    # Paste your existing base64 string from your current app.py's og_image()
    # route here (the long "iVBORw0KGgo..." string), replacing the placeholder.
    # It was too large to reproduce safely, so it's the only line you carry over.
    # Until you do, the route falls back to your logo so nothing 500s.
    # ─────────────────────────────────────────────────────────────────────
    b64 = "PASTE_YOUR_EXISTING_OG_IMAGE_BASE64_HERE"
    try:
        img_bytes = base64.b64decode(b64, validate=True)
        if len(img_bytes) < 100:
            raise ValueError("placeholder not replaced")
        return Response(img_bytes, mimetype='image/png', headers={
            'Cache-Control': 'public, max-age=86400',
            'Content-Type': 'image/png'
        })
    except Exception:
        # Graceful fallback if the base64 hasn't been pasted back in yet
        try:
            return app.send_static_file('images/logo.png')
        except Exception:
            return Response(status=404)

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

    # ⚡ SERVER-SIDE BOOTSTRAP: inject the cached leaderboard straight into the
    # page. The browser paints instantly with zero API round-trip — no more
    # "SYNCING LIVE STATS" screen when the cache is warm. Reading an in-memory
    # dict costs nothing; this makes first paint FASTER, never slower.
    bootstrap_json = "null"
    try:
        if _data_cache["data"]:
            bootstrap_json = json.dumps(_data_cache["data"])
    except Exception:
        bootstrap_json = "null"

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

        <title>NHL ANALYTICA</title>

        <!-- FAVICON: served from static with long cache (trims ~12KB of inline base64 per page load) -->
        <link rel="icon" type="image/png" sizes="32x32" href="{{ url_for('static', filename='images/logo.png') }}">
        <link rel="icon" type="image/png" sizes="16x16" href="{{ url_for('static', filename='images/logo.png') }}">
        <link rel="apple-touch-icon" sizes="180x180" href="{{ url_for('static', filename='images/logo.png') }}">
        <link rel="shortcut icon" href="{{ url_for('static', filename='images/logo.png') }}">

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
            /* IR Trend sparkline */
            .spark-wrap { height: 70px; position: relative; }
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
                <div style="font-size:0.75rem; color:#64748b; margin-bottom:18px;">Players ranked by Impact Rating (IR) score this season. ▲▼ shows 7-day IR movement. Click any player to view their full profile.</div>
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
        <script>window.__BOOTSTRAP__ = {{ bootstrap_json|safe }};</script>
        <script>
            let rawData = null; let currentMode = 'regular'; let currentType = 'skater'; 
            let currentTeam = null; let chartInstance = null; let compareBasePlayer = null;
            let sparkChart = null;
            const teams = ["ANA", "BOS", "BUF", "CGY", "CAR", "CHI", "COL", "CBJ", "DAL", "DET", "EDM", "FLA", "LAK", "MIN", "MTL", "NSH", "NJD", "NYI", "NYR", "OTT", "PHI", "PIT", "SJS", "SEA", "STL", "TBL", "TOR", "UTA", "VAN", "VGK", "WSH", "WPG"];

            let lastUpdated = null;

            async function init() {
                // ⚡ SERVER-SIDE BOOTSTRAP: if the server injected cached data,
                // paint instantly — no fetch, no "SYNCING" screen at all.
                if (window.__BOOTSTRAP__ && window.__BOOTSTRAP__.regular && window.__BOOTSTRAP__.regular.skaters && window.__BOOTSTRAP__.regular.skaters.length) {
                    rawData = window.__BOOTSTRAP__;
                    lastUpdated = new Date();
                    document.getElementById('loading').style.display = 'none';
                    buildTeamBar(); render();
                    handleURLParams();
                    startAutoRefresh();
                    refreshData(); // silent freshness check in the background
                    return;
                }
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
                // 7-day IR delta badge (powered by the server-side IR history)
                const deltaBadge = (p.d7 !== undefined && p.d7 !== null && p.d7 !== 0)
                    ? `<span style="float:right; color:${p.d7 > 0 ? '#2ecc71' : '#ff6b6b'};">${p.d7 > 0 ? '▲ +' : '▼ '}${p.d7} (7D)</span>` : '';
                const sparkHtml = `<div class="kf-container" style="margin-bottom:14px;"><div class="kf-title">IR Trend — Season ${deltaBadge}</div><div class="spark-wrap"><canvas id="ir-spark"></canvas></div><div id="spark-empty" style="display:none; color:#637381; font-size:0.72rem; margin-top:4px;">Tracking started — daily IR history will appear here.</div></div>`;
                // share button
                const shareUrl = compareWith 
                    ? `${window.location.origin}?compare=${p.id},${compareWith.id}&mode=${currentMode}&type=${currentType}`
                    : `${window.location.origin}?player=${p.id}&mode=${currentMode}&type=${currentType}`;
                const shareBtnHtml = `<button class="share-btn" onclick="copyShareLink('${shareUrl}')">🔗 COPY SHARE LINK</button>`;
                document.getElementById('mInfo').innerHTML = `<div style="font-size:0.7rem; color:var(--accent); font-weight:900; margin-bottom:10px; font-family:'Syncopate';">LEAGUE RANK #${p.rank}</div><img src="https://assets.nhle.com/mugs/nhl/latest/${p.id}.png" style="width:150px; border-radius:50%; border:4px solid ${p.col};"><h2 style="font-family:'Syncopate'; margin:15px 0 10px; font-size:1.8rem;">${p.name.toUpperCase()}</h2><div style="background:${p.col}; color:#ffffff; padding: 6px 14px; border-radius: 8px; font-weight:800; font-size:0.85rem; letter-spacing: 1px; margin-bottom:12px; display:inline-block; box-shadow: 0 4px 10px rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.2); text-shadow: 1px 1px 2px rgba(0,0,0,0.7);">${p.team.toUpperCase()}</div><br>${shareBtnHtml}<div class="stat-grid" style="margin-top:16px;">${statsHtml}</div>${sparkHtml}<div class="kf-container"><div class="kf-title">Key Factors</div>${kfHtml}</div><div class="prob-box"><small style="color:#fbbf24; font-weight:800;">${p.type==='skater'?'GOAL PROBABILITY':'SHUTOUTS'}</small><b>${p.type==='skater'?p.prob+'%':p.so}</b></div>`;
                const compBtnHtml = compareWith ? '' : `<button class="comp-btn" onclick="startCompare('${p.id}')">COMPARE</button>`;
                document.getElementById('mRight').innerHTML = `${compBtnHtml}<canvas id="radar"></canvas><div class="comp-info-text">${compareWith ? 'VS ' + compareWith.name : 'ANALYZING ' + currentMode.toUpperCase()}</div>`;
                document.getElementById('modal').style.display = 'block'; document.body.style.overflow = 'hidden'; drawRadar(p, compareWith);
                loadSparkline(p.id);
                // update URL without reloading
                const urlParams = compareWith ? `?compare=${p.id},${compareWith.id}&mode=${currentMode}&type=${currentType}` : `?player=${p.id}&mode=${currentMode}&type=${currentType}`;
                window.history.replaceState({}, '', urlParams);
            }
            // ── IR TREND SPARKLINE (lazy-loaded, never blocks the modal) ──
            async function loadSparkline(pid) {
                try {
                    const res = await fetch(`/api/history/${pid}?mode=${currentMode}`);
                    const hist = await res.json();
                    const canvas = document.getElementById('ir-spark');
                    if (!canvas) return;
                    if (!Array.isArray(hist) || hist.length < 2) {
                        canvas.parentElement.style.display = 'none';
                        const empty = document.getElementById('spark-empty');
                        if (empty) empty.style.display = 'block';
                        return;
                    }
                    if (sparkChart) sparkChart.destroy();
                    sparkChart = new Chart(canvas.getContext('2d'), {
                        type: 'line',
                        data: {
                            labels: hist.map(h => h.date.slice(5)),
                            datasets: [{ data: hist.map(h => h.ir), borderColor: '#38bdf8', backgroundColor: 'rgba(56,189,248,0.12)', fill: true, tension: 0.35, pointRadius: 0, borderWidth: 2 }]
                        },
                        options: {
                            maintainAspectRatio: false,
                            plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => 'IR ' + c.parsed.y } } },
                            scales: {
                                x: { display: false },
                                y: { ticks: { color: '#637381', font: { size: 9 } }, grid: { color: '#16253d' } }
                            }
                        }
                    });
                } catch (e) {}
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
                    const d7 = (p.d7 !== undefined && p.d7 !== null && p.d7 !== 0)
                        ? `<div style="font-size:0.58rem; font-weight:800; color:${p.d7>0?'#2ecc71':'#ff6b6b'};">${p.d7>0?'+':''}${p.d7} 7D</div>` : '';
                    return `<div class="trend-row" onclick="closeTrending(); setTimeout(()=>openModal('${p.id}'),100)" style="cursor:pointer;">
                        <div class="trend-rank">#${i+1}</div>
                        <div class="trend-arrow">${arrow}</div>
                        <img src="https://assets.nhle.com/mugs/nhl/latest/${p.id}.png" style="width:34px;height:34px;border-radius:50%;background:#000;flex-shrink:0;" onerror="this.src='https://assets.nhle.com/logos/nhl/svg/${p.abbr}_light.svg'">
                        <div style="flex:1;min-width:0;overflow:hidden;"><div style="font-weight:700; font-size:0.85rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${p.name}</div><div style="font-size:0.68rem; color:#64748b; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${p.team}</div></div>
                        <div class="trend-ir" style="color:${irCol};">${p.ir}${d7}</div></div>`;
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
                        showToast("🔔 Trade alerts enabled! You will be notified of any roster moves.");
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
    """, og_title=og_title, og_desc=og_desc, og_image=og_image, bootstrap_json=bootstrap_json)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
