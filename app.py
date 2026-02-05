import os
import json
import uuid
import datetime
import threading
import time
import random
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Ollama Setup
try:
    from ollama import chat, web_search, web_fetch
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    print("Warning: 'ollama' package not installed. AI generation will function in mock mode if needed.")

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'cin-secret-key-2026')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

POSTS_FILE = 'posts.json'
POSTS_CACHE = []
POSTS_LOCK = threading.Lock()

# --- Helper Functions ---

def load_posts():
    global POSTS_CACHE
    if os.path.exists(POSTS_FILE):
        try:
            with open(POSTS_FILE, 'r', encoding='utf-8') as f:
                POSTS_CACHE = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error loading posts: {e}")
            POSTS_CACHE = []
    else:
        POSTS_CACHE = []

def save_posts():
    """Safely save posts with locking and error handling."""
    try:
        with POSTS_LOCK:
            with open(POSTS_FILE, 'w', encoding='utf-8') as f:
                json.dump(POSTS_CACHE, f, indent=4, ensure_ascii=False)
    except PermissionError as e:
        print(f"Warning: Could not save posts (file locked): {e}")
    except IOError as e:
        print(f"Error saving posts: {e}")

load_posts()

# --- Auto-Generation Topics ---
AUTO_TOPICS = [
    "latest breakthrough in artificial intelligence",
    "global economic updates today",
    "new scientific discoveries this week",
    "technology innovation news",
    "health and medical research updates",
    "climate and environment latest news",
    "space exploration recent developments",
    "cybersecurity threats and updates",
    "renewable energy advancements",
    "quantum computing progress",
    "latest government policy changes",
"major political developments worldwide",
"election updates and outcomes",
"international relations and diplomacy news",
"new laws and constitutional amendments",
"public administration and governance reforms",
"geopolitical tensions and resolutions",
"defense and national security updates",
"human rights and civil liberty developments",
"global political risk assessment",
"global economic updates today",
"inflation and interest rate changes",
"central bank policy announcements",
"stock market and index movements",
"currency exchange rate trends",
"global trade and export import data",
"recession or growth indicators",
"employment and labor market updates",
"startup funding and investment trends",
"economic outlook and forecasts",
"latest medical research and clinical trials",
"public health advisories and warnings",
"disease outbreaks and epidemiology updates",
"pharmaceutical drug approvals and recalls",
"healthcare policy and insurance news",
"medical technology and device innovations",
"mental health research and treatment advances",
"nutrition and wellness trends",
"genetics and personalized medicine news",
"global health initiatives and aid programs",
"international trade policy updates",
"supply chain disruptions and recovery",
"corporate mergers and acquisitions",
"manufacturing and industrial growth news",
"startup ecosystem developments",
"small business and MSME policy updates",
"global logistics and shipping news",
"new business regulations",
"market competition and antitrust cases",
"consumer market trends",
"education policy updates",
"changes in school and university curricula",
"online learning and edtech innovations",
"exam reforms and assessment changes",
"global education rankings updates",
"skill development and vocational training news",
"AI and technology in education",
"student enrollment and literacy statistics",
"higher education research trends",
"future workforce skill demands",
"technology innovation news",
"latest breakthrough in artificial intelligence",
"machine learning and deep learning updates",
"quantum computing progress",
"software and programming trends",
"cloud computing and data center news",
"semiconductor and chip industry updates",
"robotics and automation developments",
"metaverse and extended reality trends",
"open source technology advancements",
"cybersecurity threats and updates",
"major data breaches reported",
"new malware and ransomware attacks",
"cyber law and digital regulation updates",
"privacy and data protection news",
"AI security and model safety concerns",
"government cyber defense initiatives",
"financial fraud and digital scam trends",
"critical infrastructure cyber risks",
"ethical hacking and security research",
"new scientific discoveries this week",
"research paper breakthroughs",
"physics and chemistry discoveries",
"biotechnology and genetics research",
"neuroscience and brain research",
"materials science innovations",
"scientific peer review updates",
"cross-disciplinary research trends",
"research funding and grants news",
"ethical concerns in scientific research",
"health and medical research updates",
"new disease outbreak alerts",
"vaccine development news",
"mental health research findings",
"public health policy updates",
"medical technology innovations",
"AI in healthcare developments",
"nutrition and lifestyle health studies",
"global healthcare system analysis",
"drug approval and clinical trial results",
"climate and environment latest news",
"global climate change indicators",
"extreme weather events analysis",
"environmental policy updates",
"wildlife and biodiversity reports",
"carbon emissions and climate targets",
"sustainability and ESG developments",
"water and natural resource management",
"pollution and waste management innovations",
"climate risk and adaptation strategies",
"renewable energy advancements",
"solar and wind power developments",
"electric vehicle ecosystem updates",
"energy storage and battery technology news",
"oil and gas industry trends",
"nuclear energy research updates",
"smart grid and infrastructure projects",
"energy security and supply updates",
"green hydrogen initiatives",
"global energy transition analysis",
"space exploration recent developments",
"satellite and space mission updates",
"mars and lunar exploration news",
"private space industry growth",
"astronomy and astrophysics discoveries",
"space policy and regulation updates",
"AI in space research",
"future transportation technologies",
"scientific predictions and simulations",
"long term technology foresight",
"global economic updates today",
"inflation and interest rate changes",
"central bank policy announcements",
"stock market and index movements",
"currency exchange rate trends",
"global trade and export import data",
"recession or growth indicators",
"employment and labor market updates",
"startup funding and investment trends",
"economic outlook and forecasts"
]

def broadcast_new_post(post):
    """Emit new post to all connected clients."""
    socketio.emit('new_post', post)
    print(f"[WebSocket] Broadcasted new post: {post['title']}")

def generate_ai_post(topic="latest developments in science and technology"):
    """
    Generates a post using Ollama with web search.
    """
    global POSTS_CACHE
    
    if not OLLAMA_AVAILABLE:
        print("Ollama not available, skipping generation.")
        return None

    messages = [
        {'role': 'user', 'content': f"Search for {topic}. Provide a detailed report suitable for a 'collective intelligence' platform. \n"
                                    "Format strictly as JSON with these fields: \n"
                                    "- title\n"
                                    "- domain (MUST match the topic category. Use ONLY one of: Politics, Economics, Health, Science, Technology, Environment, Energy, Space, Security, Education, Business. Choose based on the PRIMARY subject matter.)\n"
                                    "- summary (short paragraph)\n"
                                    "- key_points (array of strings)\n"
                                    "- why_it_matters (paragraph)\n"
                                    "- confidence_score (number 0-100)\n"
                                    "- related_sources (array of strings/URLs)\n"
                                    "- reasoning (how you verified this)\n"
                                    "\n Ensure the content is neutral, factual, and verified."}
    ]

    try:
        print(f"[AI Agent] Researching: {topic}")
        socketio.emit('agent_status', {'status': 'researching', 'topic': topic})
        
        response = chat(
            model='qwen3:8b',
            messages=messages,
            tools=[web_search, web_fetch],
        )
        
        final_content = ""
        
        # Tool call loop
        tool_cycles = 0
        while response.message.tool_calls and tool_cycles < 3:
            messages.append(response.message)
            available_tools = {'web_search': web_search, 'web_fetch': web_fetch}
            for tool_call in response.message.tool_calls:
                 func = available_tools.get(tool_call.function.name)
                 if func:
                     res = func(**tool_call.function.arguments)
                     messages.append({'role': 'tool', 'content': str(res)[:2000], 'tool_name': tool_call.function.name})
            
            response = chat(model='qwen3:8b', messages=messages, tools=[web_search, web_fetch])
            tool_cycles += 1

        final_content = response.message.content
        
        # Parse JSON from content
        import re
        json_match = re.search(r'```json\s*(.*?)\s*```', final_content, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(1))
        else:
            try:
                data = json.loads(final_content)
            except:
                data = {
                    "title": f"Report on {topic}",
                    "domain": "General",
                    "summary": final_content[:200] + "...",
                    "key_points": ["Analysis generated from search results."],
                    "why_it_matters": "Relevant to current knowledge evolution.",
                    "confidence_score": 85,
                    "related_sources": [],
                    "reasoning": "Synthesized from available web data.",
                    "full_content": final_content
                }

        new_post = {
            "id": str(uuid.uuid4()),
            "title": data.get("title", "Unknown Title"),
            "domain": data.get("domain", "General"),
            "summary": data.get("summary", ""),
            "key_points": data.get("key_points", []),
            "why_it_matters": data.get("why_it_matters", ""),
            "confidence_score": data.get("confidence_score", 0),
            "related_sources": data.get("related_sources", []),
            "reasoning": data.get("reasoning", ""),
            "timestamp": datetime.datetime.now().isoformat(),
            "likes": 0,
            "dislikes": 0,
            "comments": []
        }
        
        with POSTS_LOCK:
            POSTS_CACHE.insert(0, new_post)
        save_posts()
        
        # Broadcast to all connected clients
        broadcast_new_post(new_post)
        
        print(f"[AI Agent] New post generated: {new_post['title']}")
        return new_post

    except Exception as e:
        print(f"Error generating post: {e}")
        socketio.emit('agent_status', {'status': 'error', 'message': str(e)})
        return None

# --- Background Auto-Generation Worker ---
def auto_generation_worker(interval_minutes=5):
    """
    Background worker that automatically generates new posts at intervals.
    """
    print(f"[Auto-Gen] Worker started. Generating new posts every {interval_minutes} minutes.")
    
    # Initial delay to let app start
    time.sleep(30)
    
    while True:
        try:
            topic = random.choice(AUTO_TOPICS)
            print(f"[Auto-Gen] Auto-generating post on: {topic}")
            generate_ai_post(topic)
        except Exception as e:
            print(f"[Auto-Gen] Error in auto-generation: {e}")
        
        # Wait for next cycle
        time.sleep(interval_minutes * 60)

# Start background worker thread
auto_gen_thread = threading.Thread(target=auto_generation_worker, args=(5,), daemon=True)
auto_gen_thread.start()

# --- WebSocket Events ---
@socketio.on('connect')
def handle_connect():
    print(f"[WebSocket] Client connected")
    emit('connected', {'status': 'connected', 'posts_count': len(POSTS_CACHE)})

@socketio.on('disconnect')
def handle_disconnect():
    print(f"[WebSocket] Client disconnected")

@socketio.on('request_posts')
def handle_request_posts():
    emit('all_posts', POSTS_CACHE)

# --- Routes ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/feed')
def feed():
    return render_template('feed.html', posts=POSTS_CACHE)

@app.route('/api/status')
def status():
    return {"status": "active", "nodes": 1402, "thinking": True, "posts_count": len(POSTS_CACHE)}

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/api/login', methods=['POST'])
def api_login():
    """Dummy login endpoint."""
    time.sleep(1) # Simulate network delay
    return jsonify({"status": "success", "user_type": "human"})

@app.route('/api/posts')
def get_posts():
    return jsonify(POSTS_CACHE)

@app.route('/api/generate', methods=['POST'])
def trigger_generation():
    """
    Trigger manual generation via API.
    """
    topic = request.json.get('topic', 'latest global news')
    
    # Run in background to not block
    thread = threading.Thread(target=generate_ai_post, args=(topic,))
    thread.start()
    
    return jsonify({"status": "started", "message": f"AI agents are researching: {topic}"})

@app.route('/api/interact', methods=['POST'])
def interact():
    data = request.json
    post_id = data.get('post_id')
    action = data.get('action')
    payload = data.get('payload')
    
    with POSTS_LOCK:
        for post in POSTS_CACHE:
            if post['id'] == post_id:
                if action == 'like':
                    post['likes'] += 1
                elif action == 'dislike':
                    post['dislikes'] += 1
                elif action == 'comment':
                    post['comments'].append({
                        "text": payload,
                        "timestamp": datetime.datetime.now().isoformat(),
                        "user": "Observer"
                    })
                # Save in a separate thread to avoid blocking
                threading.Thread(target=save_posts, daemon=True).start()
                
                # Broadcast interaction update
                socketio.emit('post_updated', post)
                
                return jsonify({"status": "success", "post": post})
            
    return jsonify({"status": "error", "message": "Post not found"}), 404

@app.route('/api/search', methods=['POST'])
def search_posts():
    query = request.json.get('query', '').lower()
    if not query:
        return jsonify(POSTS_CACHE)
    
    results = [
        p for p in POSTS_CACHE 
        if query in p['title'].lower() 
        or query in p['summary'].lower() 
        or query in p['domain'].lower()
    ]
    
    return jsonify(results)

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000, use_reloader=False)
