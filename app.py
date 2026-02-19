import os
import datetime
import threading
import time
import logging
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ─── Flask App ────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'cin-secret-key-2026')

from extensions import socketio
socketio.init_app(app)

# ─── Database Init ────────────────────────────────────────────────────────────
import database
database.init_db()
# On every startup, reset ALL 'processing' rows — any row that survived a
# server restart is orphaned (its pipeline thread is dead) and should be
# reclassified as 'rejected' so the headline can be retried.
database.cleanup_stale_processing(max_age_minutes=0)

# ─── Webhook Blueprint ────────────────────────────────────────────────────────
from webhook.routes import webhook_bp
app.register_blueprint(webhook_bp)

# ─── Feed Collector (auto-start as background thread) ─────────────────────────
from feed_collector import start_collector_thread
start_collector_thread()

# ─── WebSocket broadcast helper (called by agent/controller.py) ───────────────
def broadcast_new_post(post: dict) -> None:
    """Emit a newly published post to all connected browser clients."""
    from extensions import socketio
    socketio.emit('new_post', post)
    logging.getLogger(__name__).info(
        "[WebSocket] Broadcasted post: %s", post.get("title", "")[:60]
    )

# ─── WebSocket Events ─────────────────────────────────────────────────────────
@socketio.on('connect')
def handle_connect():
    posts = database.get_published_posts(limit=50)
    emit('connected', {'status': 'connected', 'posts_count': len(posts)})

@socketio.on('disconnect')
def handle_disconnect():
    logging.getLogger(__name__).info("[WebSocket] Client disconnected")

@socketio.on('request_posts')
def handle_request_posts():
    posts = database.get_published_posts(limit=50)
    emit('all_posts', posts)

# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/feed')
def feed():
    posts = database.get_published_posts(limit=50)
    return render_template('feed.html', posts=posts)

@app.route('/api/status')
def status():
    from agent.state import agent_state
    total = database.get_all_posts(limit=1000)
    return jsonify({
        "status":      "active",
        "nodes":       1402,
        "thinking":    agent_state.is_busy(),
        "posts_count": len(total),
        "agent":       agent_state.status_dict(),
    })

@app.route('/api/agent/status')
def agent_status():
    """Returns the AI agent's current ready/busy state."""
    from agent.state import agent_state
    return jsonify(agent_state.status_dict())

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/api/login', methods=['POST'])
def api_login():
    """Dummy login endpoint."""
    time.sleep(1)
    return jsonify({"status": "success", "user_type": "human"})

@app.route('/api/posts')
def get_posts():
    posts = database.get_published_posts(limit=100)
    return jsonify(posts)

@app.route('/api/search', methods=['POST'])
def search_posts():
    query = (request.json or {}).get('query', '').lower()
    posts = database.get_published_posts(limit=200)
    if not query:
        return jsonify(posts)
    results = [
        p for p in posts
        if query in (p.get('title') or '').lower()
        or query in (p.get('summary') or '').lower()
        or query in (p.get('domain') or '').lower()
    ]
    return jsonify(results)

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000, use_reloader=False)
