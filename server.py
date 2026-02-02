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

# Detect environment
IS_PROD = "RENDER" in os.environ
RENDER_URL = "https://instautomator.onrender.com"
STATE_FILE = "/tmp/bot_state.json" if IS_PROD else "bot_state.json"

# Independent clients
cl_follow = Client()
cl_unfollow = Client()

bot_status = "System Ready. Auto-Pilot Standby..."

# --- STATE MANAGEMENT ---

def get_state():
    """Reads the current day and last run date from the persistence file."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {"day": 1, "last_run_date": None}

def save_state(day, date_str):
    """Saves the cycle progress."""
    with open(STATE_FILE, 'w') as f:
        json.dump({"day": day, "last_run_date": date_str}, f)

# --- AUTO-PILOT TASK ---

def auto_pilot_loop():
    global bot_status
    
    # Credentials & Config from Render Env Vars
    user = os.environ.get("IG_USERNAME")
    pw = os.environ.get("IG_PASSWORD")
    # Comma-separated list: "user1, user2, user3..."
    target_string = os.environ.get("IG_TARGET_LIST", "")
    target_list = [t.strip() for t in target_string.split(",") if t.strip()]

    while True:
        state = get_state()
        today = time.strftime("%Y-%m-%d")

        # Only run once per 24 hours
        if state["last_run_date"] != today:
            current_day = state["day"]
            
            if current_day <= 3:
                # DAYS 1, 2, 3: FOLLOW 40
                target = random.choice(target_list) if target_list else "instagram"
                bot_status = f"🤖 Day {current_day}: Target selected -> @{target}"
                
                # Use same session logic as manual
                session_data = os.environ.get("IG_FOLLOW_SESSION")
                cl_follow.set_user_agent("Instagram 269.0.0.18.75 Android (26/8.0.0; 480dpi; 1080x1920; OnePlus; OnePlus3T; oneplus3; qcom; en_US; 445305141)")
                
                try:
                    if session_data:
                        cl_follow.set_settings(json.loads(session_data))
                    cl_follow.login(user, pw)
                    
                    target_id = cl_follow.user_id_from_username(target)
                    users = cl_follow.user_followers_v1(target_id, amount=40)
                    
                    count = 0
                    for u in users:
                        cl_follow.user_follow(u.pk)
                        count += 1
                        bot_status = f"🤖 Day {current_day}: Followed {count}/40 from @{target}"
                        time.sleep(random.uniform(60, 120))
                    
                    save_state(current_day + 1, today)
                    bot_status = f"🏁 Day {current_day} Complete. Next run tomorrow."
                except Exception as e:
                    bot_status = f"❌ Auto-Follow Error: {str(e)[:50]}"

            else:
                # DAY 4: UNFOLLOW 50 NON-FOLLOWERS
                bot_status = "🤖 Day 4: Starting Smart Unfollow (50 users)..."
                
                session_data = os.environ.get("IG_UNFOLLOW_SESSION")
                cl_unfollow.set_user_agent("Instagram 269.0.0.18.75 Android (26/8.0.0; 480dpi; 1080x1920; OnePlus; OnePlus3T; oneplus3; qcom; en_US; 445305141)")
                
                try:
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
                    
                    save_state(1, today) # Reset to Day 1
                    bot_status = "🏁 Cycle Reset! Day 4 finished."
                except Exception as e:
                    bot_status = f"❌ Auto-Unfollow Error: {str(e)[:50]}"

        # Sleep 1 hour before checking the date again
        time.sleep(3600)

def keep_alive():
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
    curr = get_state()
    return jsonify({
        "status": bot_status,
        "day": curr["day"],
        "last_run": curr["last_run_date"]
    })

# (Include manual /run-follow and /run-unfollow from previous version)

if __name__ == '__main__':
    if IS_PROD:
        threading.Thread(target=keep_alive, daemon=True).start()
        # Start the 24-hour cycle manager
        threading.Thread(target=auto_pilot_loop, daemon=True).start()
        
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)