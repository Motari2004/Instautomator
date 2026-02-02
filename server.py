import os
import json
import random
import time
import threading
from flask import Flask, render_template, request, jsonify
from instagrapi import Client
from instagrapi.exceptions import ChallengeRequired, TwoFactorRequired, LoginRequired

app = Flask(__name__)

# Detect environment
IS_PROD = "RENDER" in os.environ

# Two independent clients
cl_follow = Client()
cl_unfollow = Client()

bot_status = "System Ready. Waiting for action..."

def start_session(client, username, password, task_type, verification_code=None):
    """
    Session Strategy:
    1. Check Render Env Vars (IG_FOLLOW_SESSION / IG_UNFOLLOW_SESSION)
    2. Check Local Files (session_follow.json / session_unfollow.json)
    3. Fallback to Login
    """
    # 1. Try Environment Variables (Production Path)
    env_key = f"IG_{task_type.upper()}_SESSION"
    env_data = os.environ.get(env_key)

    # 2. Set realistic headers
    client.set_user_agent("Instagram 269.0.0.18.75 Android (26/8.0.0; 480dpi; 1080x1920; OnePlus; OnePlus3T; oneplus3; qcom; en_US; 445305141)")

    try:
        if env_data:
            print(f"🚀 Loading {task_type} session from Render Environment Variable...")
            client.set_settings(json.loads(env_data))
        else:
            # 3. Fallback to Local Files (Development Path)
            file_path = f"session_{task_type}.json"
            if os.path.exists(file_path):
                print(f"📂 Loading {task_type} session from local file...")
                client.load_settings(file_path)

        # 4. Attempt Authentication
        if verification_code:
            client.login(username, password, verification_code=verification_code)
        else:
            # login() returns True if session is valid or login succeeds
            client.login(username, password)
        
        # In Prod, we can't write back to Env Vars, but we can log the new session
        # so you can copy it if it changes.
        return True

    except TwoFactorRequired:
        return "2FA_REQUIRED"
    except ChallengeRequired:
        return "CHALLENGE_REQUIRED"
    except Exception as e:
        print(f"❌ {task_type} Login Error: {e}")
        return False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/status')
def get_status():
    return jsonify({"status": bot_status})

@app.route('/run-follow', methods=['POST'])
def run_follow():
    user = request.form.get('username')
    pw = request.form.get('password')
    target = request.form.get('target')
    amount = int(request.form.get('amount'))
    two_fa = request.form.get('2fa_code')

    def task():
        global bot_status
        bot_status = f"🔄 Initializing Follow Session for @{user}..."
        
        login_result = start_session(cl_follow, user, pw, "follow", verification_code=two_fa)
        
        if login_result == "2FA_REQUIRED":
            bot_status = "🔐 2FA Required! Please enter your code in the UI."
            return
        elif login_result == "CHALLENGE_REQUIRED":
            bot_status = "⚠️ Challenge! Open IG app & click 'This Was Me'."
            return
        elif not login_result:
            bot_status = "❌ Login Failed. Check credentials or Render Env Vars."
            return

        try:
            bot_status = f"🔍 Locating @{target}..."
            target_id = cl_follow.user_id_from_username(target)
            followers = cl_follow.user_followers_v1(target_id, amount=amount)

            count = 0
            for info in followers:
                bot_status = f"👤 Following @{info.username}..."
                cl_follow.user_follow(info.pk)
                count += 1
                if count < amount:
                    wait = random.uniform(50, 100) # 2026 Safety: Slower is better
                    bot_status = f"⏳ Delay: {int(wait)}s..."
                    time.sleep(wait)

            bot_status = f"🏁 Done! Followed {count} users."
        except Exception as e:
            bot_status = f"❌ Follow Error: {str(e)[:50]}"

    threading.Thread(target=task).start()
    return jsonify({"status": "started"})

@app.route('/run-unfollow', methods=['POST'])
def run_unfollow():
    user = request.form.get('username')
    pw = request.form.get('password')
    amount = int(request.form.get('amount'))
    two_fa = request.form.get('2fa_code')

    def task():
        global bot_status
        bot_status = f"🔄 Initializing Unfollow Session..."
        
        login_result = start_session(cl_unfollow, user, pw, "unfollow", verification_code=two_fa)
        
        if not login_result or login_result in ["2FA_REQUIRED", "CHALLENGE_REQUIRED"]:
            bot_status = f"❌ Unfollow Login failed ({login_result})"
            return

        try:
            bot_status = "📊 Fetching following list..."
            following = cl_unfollow.user_following_v1(cl_unfollow.user_id, amount=amount)
            
            count = 0
            for u in following:
                bot_status = f"🗑️ Unfollowing @{u.username}..."
                cl_unfollow.user_unfollow(u.pk)
                count += 1
                time.sleep(random.uniform(50, 100))

            bot_status = f"🏁 Done! Unfollowed {count} users."
        except Exception as e:
            bot_status = f"❌ Unfollow Error: {str(e)[:50]}"

    threading.Thread(target=task).start()
    return jsonify({"status": "started"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)