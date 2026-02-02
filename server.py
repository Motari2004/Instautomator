import os
import json
import random
import time
import threading
import requests
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from instagrapi import Client
from instagrapi.exceptions import ChallengeRequired, TwoFactorRequired, LoginRequired

app = Flask(__name__)

# Detect environment
IS_PROD = "RENDER" in os.environ
RENDER_URL = "https://instautomator.onrender.com" 
STATE_FILE = "/tmp/bot_state.json" if IS_PROD else "bot_state.json"

# Clients
cl_follow = Client()
cl_unfollow = Client()
cl_auto = Client() 

bot_status = "System Ready. Waiting for action..."
last_pulse = "--:--:--"
last_cron_pulse = "WAITING..." # Tracking external cron ping
total_actions = 0

# --- PERSISTENCE HELPERS ---

def get_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except: pass
    return {"day": 1, "last_run_date": None, "last_result": "Auto-Pilot Standby...", "total_actions": 0}

def save_state(day, date_str, result_msg, add_actions=0):
    global total_actions
    state = get_state()
    total_actions = state.get("total_actions", 0) + add_actions
    with open(STATE_FILE, 'w') as f:
        json.dump({
            "day": day, 
            "last_run_date": date_str, 
            "last_result": result_msg,
            "total_actions": total_actions
        }, f)

# --- AUTO-PILOT LOGIC ---

def auto_pilot_loop():
    global bot_status
    user = os.environ.get("IG_USERNAME")
    pw = os.environ.get("IG_PASSWORD")
    target_string = os.environ.get("IG_TARGET_LIST", "")
    target_list = [t.strip() for t in target_string.split(",") if t.strip()]

    while True:
        state = get_state()
        today = time.strftime("%Y-%m-%d")

        if state["last_run_date"] != today and user and pw:
            current_day = state["day"]
            try:
                session_data = os.environ.get("IG_FOLLOW_SESSION")
                cl_auto.set_user_agent("Instagram 269.0.0.18.75 Android (26/8.0.0; 480dpi; 1080x1920; OnePlus; OnePlus3T; oneplus3; qcom; en_US; 445305141)")
                if session_data: cl_auto.set_settings(json.loads(session_data))
                cl_auto.login(user, pw)

                if current_day <= 3:
                    target = random.choice(target_list) if target_list else "cristiano"
                    users = cl_auto.user_followers_v1(cl_auto.user_id_from_username(target), amount=40)
                    for idx, u in enumerate(users):
                        cl_auto.user_follow(u.pk)
                        bot_status = f"🤖 Auto: Day {current_day} | Followed {idx+1}/40"
                        time.sleep(random.uniform(60, 120))
                    msg = f"✅ Auto: Day {current_day} Success (@{target})"
                    save_state(current_day + 1, today, msg, 40)
                else:
                    follower_ids = {u.pk for u in cl_auto.user_followers_v1(cl_auto.user_id, amount=0)}
                    following = cl_auto.user_following_v1(cl_auto.user_id, amount=0)
                    non_followers = [u for u in following if u.pk not in follower_ids][:50]
                    for idx, u in enumerate(non_followers):
                        cl_auto.user_unfollow(u.pk)
                        bot_status = f"🤖 Auto: Day 4 | Unfollowed {idx+1}/{len(non_followers)}"
                        time.sleep(random.uniform(60, 120))
                    msg = "✅ Auto: Day 4 Cleanup Success"
                    save_state(1, today, msg, len(non_followers))
                
                bot_status = msg
            except Exception as e:
                save_state(current_day, today, f"❌ Auto-Error: {str(e)[:30]}")

        time.sleep(3600)

# --- ROUTES ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/cron-ping')
def cron_ping():
    global last_cron_pulse
    last_cron_pulse = datetime.now().strftime("%H:%M:%S")
    return jsonify({"status": "pulse_received", "timestamp": last_cron_pulse})

@app.route('/status')
def get_status():
    global last_pulse
    state = get_state()
    last_pulse = datetime.now().strftime("%H:%M:%S")
    return jsonify({
        "status": bot_status,
        "auto_report": state["last_result"],
        "auto_day": state["day"],
        "heartbeat": last_pulse,
        "cron_heartbeat": last_cron_pulse,
        "total_tasks": state.get("total_actions", 0)
    })

# --- ORIGINAL MANUAL LOGIC ---

def keep_alive():
    global last_pulse
    while True:
        try:
            requests.get(f"{RENDER_URL}/status", timeout=10)
            last_pulse = datetime.now().strftime("%H:%M:%S")
        except: pass
        time.sleep(780)

def start_session(client, username, password, task_type, verification_code=None):
    env_key = f"IG_{task_type.upper()}_SESSION"
    env_data = os.environ.get(env_key)
    client.set_user_agent("Instagram 269.0.0.18.75 Android (26/8.0.0; 480dpi; 1080x1920; OnePlus; OnePlus3T; oneplus3; qcom; en_US; 445305141)")
    try:
        if env_data: client.set_settings(json.loads(env_data))
        else:
            file_path = f"session_{task_type}.json"
            if os.path.exists(file_path): client.load_settings(file_path)
        client.login(username, password, verification_code=verification_code) if verification_code else client.login(username, password)
        return True
    except (TwoFactorRequired, ChallengeRequired) as e: return str(e)
    except Exception: return False

@app.route('/run-follow', methods=['POST'])
def run_follow():
    user, pw, target = request.form.get('username'), request.form.get('password'), request.form.get('target')
    try: amount = int(request.form.get('amount'))
    except: amount = 20
    two_fa = request.form.get('2fa_code')

    def task():
        global bot_status
        bot_status = f"🔄 Manual: Authenticating @{user}..."
        if start_session(cl_follow, user, pw, "follow", two_fa) == True:
            try:
                followers = cl_follow.user_followers_v1(cl_follow.user_id_from_username(target), amount=amount)
                for idx, info in enumerate(followers):
                    bot_status = f"👤 Manual: Following @{info.username} ({idx+1}/{amount})"
                    cl_follow.user_follow(info.pk)
                    if idx+1 < amount: time.sleep(random.uniform(60, 120))
                bot_status = f"🏁 Manual Done! Followed {amount}."
                save_state(get_state()["day"], time.strftime("%Y-%m-%d"), bot_status, amount)
            except Exception as e: bot_status = f"❌ Error: {str(e)[:50]}"
        else: bot_status = "❌ Login Failed"

    threading.Thread(target=task).start()
    return jsonify({"status": "started"})

@app.route('/run-unfollow', methods=['POST'])
def run_unfollow():
    user, pw = request.form.get('username'), request.form.get('password')
    try: amount = int(request.form.get('amount'))
    except: amount = 20
    two_fa = request.form.get('2fa_code')

    def task():
        global bot_status
        bot_status = "🔄 Manual: Starting Unfollow..."
        if start_session(cl_unfollow, user, pw, "unfollow", two_fa) == True:
            try:
                follower_ids = {u.pk for u in cl_unfollow.user_followers_v1(cl_unfollow.user_id, amount=0)}
                following = cl_unfollow.user_following_v1(cl_unfollow.user_id, amount=0)
                non_followers = [u for u in following if u.pk not in follower_ids][:amount]
                for idx, u in enumerate(non_followers):
                    bot_status = f"🗑️ Manual: Unfollowing @{u.username} ({idx+1}/{len(non_followers)})"
                    cl_unfollow.user_unfollow(u.pk)
                    if idx+1 < len(non_followers): time.sleep(random.uniform(60, 120))
                bot_status = f"🏁 Manual Done! Removed {len(non_followers)}."
                save_state(get_state()["day"], time.strftime("%Y-%m-%d"), bot_status, len(non_followers))
            except Exception as e: bot_status = f"❌ Error: {str(e)[:50]}"
        else: bot_status = "❌ Login Failed"

    threading.Thread(target=task).start()
    return jsonify({"status": "started"})

if __name__ == '__main__':
    if IS_PROD:
        threading.Thread(target=keep_alive, daemon=True).start()
        threading.Thread(target=auto_pilot_loop, daemon=True).start()
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)