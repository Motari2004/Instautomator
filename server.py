from flask import Flask, render_template, request, jsonify
from instagrapi import Client
import os
import random
import time
import threading

app = Flask(__name__)

# Detect environment
IS_PROD = "RENDER" in os.environ

# Two independent clients
cl_follow = Client()
cl_unfollow = Client()

bot_status = "System Ready. Waiting for action..."

def start_session(client, username, password, task_type):
    """Handles session paths based on environment"""
    if IS_PROD:
        # Production (Render) uses /tmp
        session_file = f"/tmp/session_{task_type}.json"
    else:
        # Local development uses current folder
        session_file = f"session_{task_type}.json"
        
    try:
        if os.path.exists(session_file):
            print(f"🔄 Loading {task_type} session from {session_file}...")
            client.load_settings(session_file)
        
        client.login(username, password)
        client.dump_settings(session_file)
        return True
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

    def task():
        global bot_status
        bot_status = f"🔄 Starting Follow Session for @{user}..."
        
        if not start_session(cl_follow, user, pw, "follow"):
            bot_status = "❌ Login Failed. Check your credentials."
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
                    wait = random.uniform(30, 60)
                    bot_status = f"⏳ Delay: {int(wait)}s remaining..."
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

    def task():
        global bot_status
        bot_status = f"🔄 Starting Unfollow Session for @{user}..."
        
        if not start_session(cl_unfollow, user, pw, "unfollow"):
            bot_status = "❌ Unfollow Login Failed."
            return

        try:
            bot_status = "📊 Fetching following list..."
            following = cl_unfollow.user_following_v1(cl_unfollow.user_id, amount=amount)
            
            count = 0
            for u in following:
                bot_status = f"🗑️ Unfollowing @{u.username}..."
                cl_unfollow.user_unfollow(u.pk)
                count += 1
                time.sleep(random.uniform(30, 60))

            bot_status = f"🏁 Done! Unfollowed {count} users."
        except Exception as e:
            bot_status = f"❌ Unfollow Error: {str(e)[:50]}"

    threading.Thread(target=task).start()
    return jsonify({"status": "started"})

if __name__ == '__main__':
    # Local Dev: uses port 10000 by default
    # Production: Render automatically injects the PORT variable
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)