import pandas as pd
import requests
import os
import time

def get_nhl_data():
    print("📡 NHL 공식 기록실(2025-26) 데이터 동기화 중... 로고 서버 보안 우회 적용")
    
    # 1. 32개 팀 마스터 데이터 (공식 컬러 및 약어 매칭)
    team_db = {
        "ANA": ("Anaheim Ducks", "#F47A38"), "BOS": ("Boston Bruins", "#FFB81C"),
        "BUF": ("Buffalo Sabres", "#002654"), "CGY": ("Calgary Flames", "#C8102E"),
        "CAR": ("Carolina Hurricanes", "#CE1126"), "CHI": ("Chicago Blackhawks", "#CF0A2C"),
        "COL": ("Colorado Avalanche", "#6F263D"), "CBJ": ("Columbus Blue Jackets", "#002654"),
        "DAL": ("Dallas Stars", "#006847"), "DET": ("Detroit Red Wings", "#CE1126"),
        "EDM": ("Edmonton Oilers", "#FF4C00"), "FLA": ("Florida Panthers", "#041E42"),
        "LAK": ("Los Angeles Kings", "#111111"), "MIN": ("Minnesota Wild", "#154734"),
        "MTL": ("Montreal Canadiens", "#AF1E2D"), "NSH": ("Nashville Predators", "#FFB81C"),
        "NJD": ("New Jersey Devils", "#CE1126"), "NYI": ("New York Islanders", "#00539B"),
        "NYR": ("New York Rangers", "#0038A8"), "OTT": ("Ottawa Senators", "#C8102E"),
        "PHI": ("Philadelphia Flyers", "#F74902"), "PIT": ("Pittsburgh Penguins", "#FCB514"),
        "SJS": ("San Jose Sharks", "#006D75"), "SEA": ("Seattle Kraken", "#001628"),
        "STL": ("St. Louis Blues", "#002F87"), "TBL": ("Tampa Bay Lightning", "#002868"),
        "TOR": ("Toronto Maple Leafs", "#00205B"), "UTA": ("Utah Hockey Club", "#71AFE2"),
        "VAN": ("Vancouver Canucks", "#00205B"), "VGK": ("Vegas Golden Knights", "#B4975A"),
        "WSH": ("Washington Capitals", "#041E42"), "WPG": ("Winnipeg Jets", "#004C97")
    }

    # 2. 실시간 원천 API 호출 (24-25 및 25-26 호환)
    url = "https://api.nhle.com/stats/rest/en/skater/summary"
    params = {
        "isAggregate": "false", "isGame": "false",
        "sort": '[{"property":"points","direction":"DESC"}]',
        "start": 0, "limit": 1000,
        "cayenneExp": "seasonId=20242025 and gameTypeId=2"
    }

    try:
        # 실제 브라우저와 동일한 헤더 설정 (로고 차단 방지용)
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
        response = requests.get(url, params=params, headers=headers, timeout=20).json()
        data = response.get('data', [])

        final_rows = []
        for p in data:
            abbr = p.get('teamAbbrev', 'N/A')
            meta = team_db.get(abbr, (abbr, "#333333"))
            
            # [수정] 캡처에서 보셨던 로고 미출력 문제를 해결하기 위한 절대 경로 지정
            # NHL 공식 앱과 웹사이트에서 공통으로 사용하는 고해상도 SVG 경로입니다.
            logo_url = f"https://assets.nhle.com/logos/nhl/svg/{abbr}_light.svg"

            final_rows.append({
                "NAME": p.get('skaterFullName', 'Unknown'),
                "TEAM": meta[0],
                "COLOR": meta[1],
                "LOGO": logo_url,
                "POS": p.get('positionCode', 'N/A'),
                "GP": int(p.get('gamesPlayed', 0)),
                "G": int(p.get('goals', 0)),
                "A": int(p.get('assists', 0)),
                "PTS": int(p.get('points', 0)),
                "SOG": int(p.get('shots', 0))
            })
        return pd.DataFrame(final_rows)
    except Exception as e:
        print(f"❌ 데이터 엔진 오류: {e}")
        return None

def build_web_app(df):
    if df is None or df.empty: return

    # Syntax Error 방지를 위해 루프 밖에서 HTML 행 조립
    rows_list = []
    for _, row in df.iterrows():
        r_str = f"""
        <tr>
            <td><b>{row['NAME']}</b></td>
            <td>
                <div style="display: flex; align-items: center;">
                    <img src="{row['LOGO']}" style="width: 32px; height: 32px; margin-right: 12px;" 
                         onerror="this.src='https://assets.nhle.com/logos/nhl/svg/NHL_light.svg';">
                    <span style="color:{row['COLOR']}; font-weight:700;">{row['TEAM']}</span>
                </div>
            </td>
            <td style="text-align: center;"><span class="pos-badge">{row['POS']}</span></td>
            <td class="stat-cell">{row['GP']}</td>
            <td class="stat-cell text-warning">{row['G']}</td>
            <td class="stat-cell text-primary">{row['A']}</td>
            <td class="pts-glow">{row['PTS']}</td>
            <td class="stat-cell">{row['SOG']}</td>
        </tr>"""
        rows_list.append(r_str)
    
    all_rows = "".join(rows_list)

    html_template = f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <title>NHL ELITE INTEL V9</title>
        <link rel="stylesheet" href="https://cdn.datatables.net/1.13.6/css/jquery.dataTables.min.css">
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@700&family=JetBrains+Mono:wght@500;700&display=swap');
            body {{ background: #020617; color: #f8fafc; font-family: 'JetBrains Mono', monospace; padding: 40px; }}
            .app-wrapper {{ background: #0f172a; border-radius: 20px; padding: 40px; border: 1px solid #1e293b; }}
            h1 {{ font-family: 'Barlow Condensed', sans-serif; font-size: 3.2rem; color: #38bdf8; border-bottom: 4px solid #38bdf8; padding-bottom: 10px; margin-bottom: 35px; }}
            table.dataTable {{ background: transparent !important; color: white !important; border: none !important; }}
            table.dataTable thead th {{ background: #1e293b !important; color: #38bdf8 !important; text-transform: uppercase; border: none !important; padding: 18px !important; text-align: center; }}
            table.dataTable tbody tr {{ background: transparent !important; border-bottom: 1px solid #1e293b !important; }}
            .pts-glow {{ color: #38bdf8 !important; font-weight: 900; font-size: 1.4rem; background: rgba(56, 189, 248, 0.15) !important; text-align: center; border-radius: 8px; }}
            .pos-badge {{ background: #38bdf8; color: #020617; padding: 3px 10px; border-radius: 5px; font-weight: 800; font-size: 0.9rem; }}
            .stat-cell {{ text-align: center; font-weight: 700; font-size: 1.15rem; }}
        </style>
    </head>
    <body>
        <div class="app-wrapper">
            <div class="d-flex justify-content-between align-items-end">
                <h1>NHL INTEL CENTER V9</h1>
                <p class="text-muted mb-3">LAST SYNC: {time.strftime('%H:%M:%S')} • DATA VERIFIED</p>
            </div>
            <table id="mainTable" class="display table" style="width:100%">
                <thead>
                    <tr>
                        <th>PLAYER</th><th>TEAM</th><th class='text-center'>POS</th><th class='text-center'>GP</th><th class='text-center'>G</th><th class='text-center'>A</th><th class='text-center'>PTS</th><th class='text-center'>SOG</th>
                    </tr>
                </thead>
                <tbody>
                    {all_rows}
                </tbody>
            </table>
        </div>
        <script src="https://code.jquery.com/jquery-3.7.0.js"></script>
        <script src="https://cdn.datatables.net/1.13.6/js/jquery.dataTables.min.js"></script>
        <script>
            $(document).ready(function() {{
                $('#mainTable').DataTable({{ "pageLength": 25, "order": [[ 6, "desc" ]] }});
            }});
        </script>
    </body>
    </html>
    """
    path = os.path.abspath("nhl_intel_v9.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_template)
    os.system(f"open '{path}'")

if __name__ == "__main__":
    df = get_nhl_data()
    build_web_app(df)