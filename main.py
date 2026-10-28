import os
import time
import threading
import requests
from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Pull configuration from environment variables (set these in your cloud dashboard)
API_KEY = os.getenv("API_KEY", "YOUR_ODDS_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

SPORTS = [
    "soccer_epl",
    "basketball_nba",
    "tennis_atp"
]

GHANA_BOOKMAKERS = [
    "betway",
    "sportybet",
    "1xbet",
    "msport",
    "betano",
    "betika",
    "parimatch"
]

# [Include all your arbitrage calculation logic functions here: 
#  process_match_arbitrages, calculate_arbitrage_for_match_h2h, 
#  calculate_arbitrage_for_totals, etc.]

def send_telegram_alert(arb_data):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
        
    outcomes_text = ""
    for name, info in arb_data['outcomes'].items():
        outcomes_text += f"• **{name}**: @ `{info['price']}` ({info['bookmaker']})\n"
    
    stakes_text = ""
    if 'sample_stakes_ghs' in arb_data:
        stakes_text = "\n💰 **Sample Stakes (1,000 GHS Total):**\n"
        for name, stake in arb_data['sample_stakes_ghs'].items():
            stakes_text += f"- {name}: `{stake} GHS`\n"

    message = (
        f"🚨 **GHANA ARBITRAGE ALERT!** 🚨\n\n"
        f"⚽ **Sport:** {arb_data['sport']}\n"
        f"⚔️ **Match:** {arb_data['home_team']} vs {arb_data['away_team']}\n"
        f"📊 **Market:** {arb_data['market'].upper()}\n"
        f"📈 **ROI:** `{arb_data['roi']}%`\n\n"
        f"**Best Odds:**\n{outcomes_text}"
        f"{stakes_text}"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram error: {e}")

alerted_matches_cache = set()

def scan_and_alert_loop():
    print("🔄 Background arbitrage scanner loop started...")
    while True:
        global alerted_matches_cache
        current_scanned_ids = set()
        
        for sport in SPORTS:
            url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/?apiKey={API_KEY}&regions=eu,uk&markets=h2h,totals&oddsFormat=decimal"
            try:
                response = requests.get(url)
                if response.status_code != 200:
                    continue
                data = response.json()
                
                for match in data:
                    match_arbs = process_match_arbitrages(match)
                    for arb in match_arbs:
                        if arb['is_arbitrage']:
                            match_unique_key = f"{arb['id']}_{arb['market']}"
                            current_scanned_ids.add(match_unique_key)
                            
                            if match_unique_key not in alerted_matches_cache:
                                send_telegram_alert(arb)
                                alerted_matches_cache.add(match_unique_key)
            except Exception as e:
                print(f"Error scanning {sport}: {str(e)}")
                
        alerted_matches_cache = alerted_matches_cache.intersection(current_scanned_ids)
        time.sleep(600) # Scan every 10 minutes

@app.route('/api/arbitrage', methods=['GET'])
def get_ghana_arbitrages():
    all_results = []
    for sport in SPORTS:
        url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/?apiKey={API_KEY}&regions=eu,uk&markets=h2h,totals&oddsFormat=decimal"
        try:
            response = requests.get(url)
            if response.status_code != 200:
                continue
            data = response.json()
            for match in data:
                match_arbs = process_match_arbitrages(match)
                for arb in match_arbs:
                    all_results.append(arb)
        except Exception as e:
            print(f"Error fetching {sport}: {str(e)}")
            
    all_results.sort(key=lambda x: x['roi'], reverse=True)
    return jsonify({"status": "success", "data": all_results})

# Start background thread safely upon app startup
if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or os.environ.get("GUNICORN_RUN") == "true" or not app.debug:
    scanner_thread = threading.Thread(target=scan_and_alert_loop, daemon=True)
    scanner_thread.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)