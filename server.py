import os
import json
import random
import time
import threading
import requests
from flask import Flask, render_template, request, jsonify
from instagrapi import Client
from instagrapi.exceptions import ChallengeRequired, TwoFactorRequired, LoginRequired

app = Flask(__name__)

# --- CONFIGURATION ---
IS_PROD = "RENDER" in os.environ
RENDER_URL = "https://instautomator.onrender.com"
# Persistence file ensures the bot remembers its day/report even after Render restarts
STATE_FILE = "/tmp/bot_state.json" if IS_PROD else "bot_state.json"

# Independent clients for background tasks
cl_follow = Client()
cl_unfollow = Client()

bot_status = "System Ready. Auto-Pilot Standby..."

# --- PERSISTENCE LOGIC ---

def get_state():
    """Reads the current day and last report from the state file."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {
        "day": 1, 
        "last_run_date": None, 
        "last_result": "Waiting for first automated run..."
    }

def save_state(day, date_str, result_msg):
    """Saves the cycle progress and the report message."""
    with open(STATE_FILE, 'w') as f:
        json.dump({
            "day": day, 
            "last_run_date": date_str, 
            "last_result": result_msg
        }, f)

# --- AUTO-PILOT ENGINE ---



def auto_pilot_loop():
    global bot_status
    
    # Credentials from Render Env Vars
    user = os.environ.get("IG_USERNAME")
    pw = os.environ.get("IG_PASSWORD")
    target_string = os.environ.get("IG_TARGET_LIST", "")
    target_list = [t.strip() for t in target_string.split(",") if t.strip()]

    while True:
        state = get_state()
        today = time.strftime("%Y-%m-%d")

        # Only run if we haven't completed a task today
        if state["last_run_date"] != today:
            current_day = state["day"]
            
            if current_day <= 3:
                # DAYS 1, 2, 3: FOLLOW 40
                target = random.choice(target_list) if target_list else "instagram"
                bot_status = f"🤖 Day {current_day}: Target selected -> @{target}"
                
                try:
                    # Load session from IG_FOLLOW_SESSION
                    session_data = os.environ.get("IG_FOLLOW_SESSION")
                    cl_follow.set_user_agent("Instagram 269.0.0.18.75 Android (26/8.0.0; 480dpi; 1080x1920; OnePlus; OnePlus3T; oneplus3; qcom; en_US; 445305141)")
                    if session_data:
                        cl_follow.set_settings(json.loads(session_data))
                    cl_follow.login(user, pw)
                    
                    target_id = cl_follow.user_id_from_username(target)
                    users = cl_follow.user_followers_v1(target_id, amount=40)
                    
                    count = 0
                    for u in users:
                        cl_follow.user_follow(u.pk)
                        count += 1
                        bot_status = f"🤖 Day {current_day}: Following {count}/40 from @{target}"
                        time.sleep(random.uniform(60, 120))
                    
                    # Log success to persistence
                    report = f"✅ Success: Day {current_day} followed {count} users from @{target}."
                    save_state(current_day + 1, today, report)
                    bot_status = report

                except Exception as e:
                    error_report = f"❌ Error on Day {current_day}: {str(e)[:40]}"
                    save_state(current_day, today, error_report)
                    bot_status = error_report

            else:
                # DAY 4: UNFOLLOW 50 NON-FOLLOWERS
                bot_status = "🤖 Day 4: Starting Smart Unfollow..."
                try:
                    session_data = os.environ.get("IG_UNFOLLOW_SESSION")
                    cl_unfollow.set_user_agent("Instagram 269.0.0.18.75 Android (26/8.0.0; 480dpi; 1080x1920; OnePlus; OnePlus3T; oneplus3; qcom; en_US; 445305141)")
                    if session_data:
                        cl_unfollow.set_settings(json.loads(session_data))
                    cl_unfollow.login(user, pw)
                    
                    my_id = cl_unfollow.user_id
                    follower_ids = {u.pk for u in cl_unfollow.user_followers_v1(my_id, amount=0)}
                    following = cl_unfollow.user_following_v1(my_id, amount=0)
                    non_followers = [u for u in following if u.pk not in follower_ids][:50]
                    
                    count = 0
                    for u in non_followers:
                        cl_unfollow.user_unfollow(u.pk)
                        count += 1
                        bot_status = f"🤖 Day 4: Unfollowed {count}/50"
                        time.sleep(random.uniform(60, 120))
                    
                    report = f"✅ Success: Day 4 cleaned {count} non-followers."
                    save_state(1, today, report) # Reset to Day 1
                    bot_status = report
                except Exception as e:
                    error_report = f"❌ Error on Day 4: {str(e)[:40]}"
                    save_state(4, today, error_report)
                    bot_status = error_report

        # Check for new day every hour
        time.sleep(3600)

def keep_alive():
    """Internal ping to prevent Render sleep."""
    while True:
        try:
            requests.get(f"{RENDER_URL}/status", timeout=10)
        except:
            pass
        time.sleep(780)

# --- ROUTES ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/status')
def get_status():
    state = get_state()
    return jsonify({
        "status": bot_status,
        "cycle_day": state["day"],
        "last_report": state["last_result"],
        "last_run": state["last_run_date"]
    })

# Manual routes remain available for on-demand use
@app.route('/run-follow', methods=['POST'])
def run_follow():
    user = request.form.get('username')
    pw = request.form.get('password')
    target = request.form.get('target')
    amount = int(request.form.get('amount'))
    
    def task():
        global bot_status
        bot_status = f"🔄 Manual Follow starting for @{target}..."
        # (Manual follow logic using cl_follow)
    
    threading.Thread(target=task).start()
    return jsonify({"status": "started"})

if __name__ == '__main__':
    if IS_PROD:
        # Keep server awake
        threading.Thread(target=keep_alive, daemon=True).start()
        # Run the automated cycle
        threading.Thread(target=auto_pilot_loop, daemon=True).start()
        
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)