from flask import Flask, render_template, request, jsonify
from instagrapi import Client
from instagrapi.exceptions import ChallengeRequired, TwoFactorRequired, LoginRequired
import os
import random
import time
import threading

app = Flask(__name__)
IS_PROD = "RENDER" in os.environ

# Independent clients
cl_follow = Client()
cl_unfollow = Client()

bot_status = "System Ready. Waiting for action..."

def start_session(client, username, password, task_type, 2fa_code=None):
    """Robust login handling for Render/Data Center environments"""
    session_file = f"/tmp/session_{task_type}.json" if IS_PROD else f"session_{task_type}.json"
    
    # 1. Set a realistic Mobile User-Agent to reduce 'Suspicious Login' flags
    client.set_user_agent("Instagram 269.0.0.18.75 Android (26/8.0.0; 480dpi; 1080x1920; OnePlus; OnePlus3T; oneplus3; qcom; en_US; 445305141)")

    try:
        # 2. Try to load an existing session first
        if os.path.exists(session_file):
            client.load_settings(session_file)
            print(f"🔄 Loaded session for {username}")

        # 3. Attempt Login
        # If 2FA is provided from the UI, use it
        if 2fa_code:
            client.login(username, password, verification_code=2fa_code)
        else:
            client.login(username, password)
            
        client.dump_settings(session_file)
        return True

    except TwoFactorRequired:
        print(f"🔐 2FA Required for {username}")
        return "2FA_REQUIRED"
    except ChallengeRequired:
        print(f"⚠️ Challenge Required. Check Instagram app and click 'This Was Me'.")
        return "CHALLENGE_REQUIRED"
    except Exception as e:
        print(f"❌ Login Error: {e}")
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
    two_fa = request.form.get('2fa_code') # Optional field from UI

    def task():
        global bot_status
        bot_status = f"🔄 Authenticating @{user}..."
        
        login_result = start_session(cl_follow, user, pw, "follow", two_fa)
        
        if login_result == "2FA_REQUIRED":
            bot_status = "🔐 2FA Required! Please enter your code in the form."
            return
        elif login_result == "CHALLENGE_REQUIRED":
            bot_status = "⚠️ Challenge! Open IG app & click 'This Was Me', then retry."
            return
        elif not login_result:
            bot_status = "❌ Login Failed. Check credentials or use a Proxy."
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
                    wait = random.uniform(45, 90) # Slower is safer in 2026
                    bot_status = f"⏳ Delay: {int(wait)}s..."
                    time.sleep(wait)

            bot_status = f"🏁 Done! Followed {count} users."
        except Exception as e:
            bot_status = f"❌ Error: {str(e)[:50]}"

    threading.Thread(target=task).start()
    return jsonify({"status": "started"})

# [Unfollow route follows same pattern...]

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)