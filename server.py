import os
import json
import random
import time
import threading
from datetime import datetime
import requests
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

# Globals for UI
bot_status = "System Ready. Waiting for action..."
last_heartbeat = "No Pulse Detected"

# --- PERSISTENCE HELPERS ---

def get_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except: pass
    return {"day": 1, "last_run_date": None, "last_result": "Auto-Pilot Standby...", "total_tasks": 0}

def save_state(day, date_str, result_msg, task_inc=0):
    state = get_state()
    new_total = state.get("total_tasks", 0) + task_inc
    with open(STATE_FILE, 'w') as f:
        json.dump({
            "day": day, 
            "last_run_date": date_str, 
            "last_result": result_msg,
            "total_tasks": new_total
        }, f)

# --- THE "SUPER" PING LOGIC ---

@app.route('/heartbeat')
def heartbeat_endpoint():
    """External ping endpoint for Cron-job.org or BetterStack"""
    global last_heartbeat
    last_heartbeat = datetime.now().strftime("%H:%M:%S")
    return jsonify({"status": "alive", "pulse": last_heartbeat})

def keep_alive():
    """Internal ping loop to keep the process warm"""
    while True:
        try:
            requests.get(f"{RENDER_URL}/heartbeat", timeout=10)
        except: pass
        time.sleep(780) # 13 minutes

# --- AUTO-PILOT LOGIC ---

def auto_pilot_loop():
    global bot_status
    user = os.environ.get("IG_USERNAME")
    pw = os.environ.get("IG_PASSWORD")
    target_string = os.environ.get("IG_TARGET_LIST", "")
    target_list = [t.strip() for t in target_string.split(",") if t.strip()]

    while True:
        state = get_state()
        today = datetime.now().strftime("%Y-%m-%d")

        if state["last_run_date"] != today and user and pw:
            current_day = state["day"]
            try:
                cl_auto.set_user_agent("Instagram 269.0.0.18.75 Android (26/8.0.0; 480dpi; 1080x1920; OnePlus; OnePlus3T; oneplus3; qcom; en_US; 445305141)")
                cl_auto.login(user, pw)

                if current_day <= 3:
                    target = random.choice(target_list) if target_list else "cristiano"
                    users = cl_auto.user_followers_v1(cl_auto.user_id_from_username(target), amount=40)
                    for idx, u in enumerate(users):
                        cl_auto.user_follow(u.pk)
                        bot_status = f"🤖 Auto: Day {current_day} | Followed {idx+1}/40"
                        time.sleep(random.uniform(60, 120))
                    save_state(current_day + 1, today, f"✅ Day {current_day} Success (@{target})", 40)
                else:
                    follower_ids = {u.pk for u in cl_auto.user_followers_v1(cl_auto.user_id, amount=0)}
                    following = cl_auto.user_following_v1(cl_auto.user_id, amount=0)
                    non_followers = [u for u in following if u.pk not in follower_ids][:50]
                    for idx, u in enumerate(non_followers):
                        cl_auto.user_unfollow(u.pk)
                        bot_status = f"🤖 Auto: Day 4 | Unfollowed {idx+1}/{len(non_followers)}"
                        time.sleep(random.uniform(60, 120))
                    save_state(1, today, "✅ Day 4 Cleanup Success", len(non_followers))
                
                bot_status = "🤖 Auto-Pilot resting until tomorrow."
            except Exception as e:
                save_state(current_day, today, f"❌ Auto-Error: {str(e)[:30]}")

        time.sleep(3600)

# --- MANUAL ROUTES ---

def start_session(client, username, password, task_type):
    client.set_user_agent("Instagram 269.0.0.18.75 Android (26/8.0.0; 480dpi; 1080x1920; OnePlus; OnePlus3T; oneplus3; qcom; en_US; 445305141)")
    try:
        client.login(username, password)
        return True
    except: return False

@app.route('/status')
def get_status():
    state = get_state()
    return jsonify({
        "status": bot_status,
        "auto_report": state["last_result"],
        "auto_day": state["day"],
        "heartbeat": last_heartbeat,
        "total_tasks": state.get("total_tasks", 0)
    })

@app.route('/run-follow', methods=['POST'])
def run_follow():
    user, pw, target = request.form.get('username'), request.form.get('password'), request.form.get('target')
    amount = int(request.form.get('amount', 20))

    def task():
        global bot_status
        bot_status = f"🔄 Manual: Authenticating @{user}..."
        if start_session(cl_follow, user, pw, "follow"):
            try:
                followers = cl_follow.user_followers_v1(cl_follow.user_id_from_username(target), amount=amount)
                for idx, info in enumerate(followers):
                    bot_status = f"👤 Manual: Following {idx+1}/{amount}"
                    cl_follow.user_follow(info.pk)
                    time.sleep(random.uniform(60, 120))
                bot_status = f"🏁 Manual Done! Followed {amount}."
                save_state(get_state()["day"], datetime.now().strftime("%Y-%m-%d"), "Manual Follow Done", amount)
            except Exception as e: bot_status = f"❌ Error: {str(e)[:40]}"
        else: bot_status = "❌ Login Failed"

    threading.Thread(target=task).start()
    return jsonify({"status": "started"})

@app.route('/run-unfollow', methods=['POST'])
def run_unfollow():
    user, pw = request.form.get('username'), request.form.get('password')
    amount = int(request.form.get('amount', 20))

    def task():
        global bot_status
        bot_status = "🔄 Manual: Starting Unfollow..."
        if start_session(cl_unfollow, user, pw, "unfollow"):
            try:
                follower_ids = {u.pk for u in cl_unfollow.user_followers_v1(cl_unfollow.user_id, amount=0)}
                following = cl_unfollow.user_following_v1(cl_unfollow.user_id, amount=0)
                non_followers = [u for u in following if u.pk not in follower_ids][:amount]
                for idx, u in enumerate(non_followers):
                    bot_status = f"🗑️ Manual: Unfollowing {idx+1}/{len(non_followers)}"
                    cl_unfollow.user_unfollow(u.pk)
                    time.sleep(random.uniform(60, 120))
                bot_status = f"🏁 Manual Done! Removed {len(non_followers)}."
                save_state(get_state()["day"], datetime.now().strftime("%Y-%m-%d"), "Manual Unfollow Done", len(non_followers))
            except Exception as e: bot_status = f"❌ Error: {str(e)[:40]}"

    threading.Thread(target=task).start()
    return jsonify({"status": "started"})

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    if IS_PROD:
        threading.Thread(target=keep_alive, daemon=True).start()
        threading.Thread(target=auto_pilot_loop, daemon=True).start()
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)