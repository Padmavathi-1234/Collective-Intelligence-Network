from flask import Flask, render_template, redirect, url_for, request, session, flash, jsonify, g
import sqlite3
import hashlib
import json
import secrets
import re
from datetime import datetime, timedelta
from functools import wraps
from database import get_db, init_db, close_db

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)  # Generate secure secret key
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)


@app.teardown_appcontext
def teardown_db(error):
    close_db(error)
    print("✓ Database initialized successfully!")

def hash_password(password):
    """Hash password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def validate_password(password):
    """Validate password meets requirements"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r'[0-9]', password):
        return False, "Password must contain at least one number"
    if not re.search(r'[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]', password):
        return False, "Password must contain at least one special character"
    return True, "Password is valid"

def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator to require admin access"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page', 'warning')
            return redirect(url_for('admin_login'))
        if session.get('role') != 'admin':
            flash('Admin access required', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def validate_agent_purpose(purpose_text):
    """Validate agent purpose against blocked keywords"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT keyword, severity, category FROM blocked_keywords')
    keywords = cursor.fetchall()
    conn.close()
    
    violations = []
    purpose_lower = purpose_text.lower()
    
    for keyword_row in keywords:
        keyword = keyword_row['keyword'].lower()
        if keyword in purpose_lower:
            violations.append({
                'keyword': keyword_row['keyword'],
                'severity': keyword_row['severity'],
                'category': keyword_row['category'],
                'position': purpose_lower.index(keyword)
            })
    
    return violations

def calculate_safety_score(violation_count):
    """Calculate safety score based on violations"""
    base_score = 100
    penalty_per_violation = 30
    score = max(0, base_score - (violation_count * penalty_per_violation))
    return score

# ===== ROUTES =====

@app.route('/')
def index():
    """Landing page route"""
    return render_template('index.html')

@app.route('/select-role')
def select_role():
    """Role selection page"""
    return render_template('role_selection.html')

@app.route('/register')
def register():
    """Registration page"""
    role = request.args.get('role', 'human')
    return render_template('register.html', role=role)

@app.route('/api/register', methods=['POST'])
def api_register():
    """Handle registration API"""
    data = request.get_json()
    
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    confirm_password = data.get('confirm_password', '')
    role = data.get('role', 'human')
    
    # Validation
    if not username or not email or not password:
        return jsonify({'success': False, 'message': 'All fields are required'}), 400
    
    if len(username) < 3:
        return jsonify({'success': False, 'message': 'Username must be at least 3 characters'}), 400
    
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return jsonify({'success': False, 'message': 'Username can only contain letters, numbers, and underscores'}), 400
    
    if not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email):
        return jsonify({'success': False, 'message': 'Invalid email format'}), 400
    
    if password != confirm_password:
        return jsonify({'success': False, 'message': 'Passwords do not match'}), 400
    
    # Validate password strength
    is_valid, message = validate_password(password)
    if not is_valid:
        return jsonify({'success': False, 'message': message}), 400
    
    # Check if user exists
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM users WHERE username = ? OR email = ?', (username, email))
    if cursor.fetchone():
        conn.close()
        return jsonify({'success': False, 'message': 'Username or email already exists'}), 400
    
    # Create user
    password_hash = hash_password(password)
    try:
        cursor.execute('''
            INSERT INTO users (username, email, password_hash, role)
            VALUES (?, ?, ?, ?)
        ''', (username, email, password_hash, role))
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        
        return jsonify({
            'success': True, 
            'message': 'Registration successful! Please login.',
            'redirect': url_for('login', role=role)
        }), 201
        
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': f'Registration failed: {str(e)}'}), 500

@app.route('/login')
def login():
    """Login page"""
    role = request.args.get('role', 'human')
    return render_template('login.html', role=role)

@app.route('/api/login', methods=['POST'])
def api_login():
    """Handle login API"""
    data = request.get_json()
    
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and password are required'}), 400
    
    # Check credentials
    conn = get_db()
    cursor = conn.cursor()
    
    password_hash = hash_password(password)
    cursor.execute('''
        SELECT id, username, email, role 
        FROM users 
        WHERE username = ? AND password_hash = ?
    ''', (username, password_hash))
    
    user = cursor.fetchone()
    
    if user:
        # Update last login
        cursor.execute('UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?', (user['id'],))
        conn.commit()
        conn.close()
        
        # Set session
        session.permanent = True
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['email'] = user['email']
        session['role'] = user['role']
        
        return jsonify({
            'success': True,
            'message': 'Login successful!',
            'redirect': url_for('knowledge_feed')
        }), 200
    else:
        conn.close()
        return jsonify({'success': False, 'message': 'Invalid username or password'}), 401

@app.route('/dashboard')
@login_required
def dashboard():
    """Dashboard page (requires login)"""
    # Redirect AI role users to agent registration if they have no agents
    if session.get('role') == 'ai':
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) as count FROM ai_agents WHERE user_id = ?', (session['user_id'],))
        agent_count = cursor.fetchone()['count']
        conn.close()
        
        if agent_count == 0:
            return redirect(url_for('agent_register_step1'))
        else:
            return redirect(url_for('my_agents'))
    
    return render_template('dashboard.html', 
                         username=session.get('username'),
                         role=session.get('role'))

# ===== AI AGENT ROUTES =====

@app.route('/agent/register/step1')
@login_required
def agent_register_step1():
    """AI Agent Registration - Step 1: Basic Info"""
    if session.get('role') != 'ai':
        flash('Only AI role users can register agents', 'error')
        return redirect(url_for('dashboard'))
    return render_template('agent/register_step1.html')

@app.route('/api/agent/step1', methods=['POST'])
@login_required
def api_agent_step1():
    """Save Step 1 data to session"""
    data = request.get_json()
    
    agent_name = data.get('agent_name', '').strip()
    domain = data.get('domain', '')
    
    if not agent_name or len(agent_name) < 3:
        return jsonify({'success': False, 'message': 'Agent name must be at least 3 characters'}), 400
    
    valid_domains = ['Economics', 'Technology', 'Science', 'Politics', 'Health', 'Law']
    if domain not in valid_domains:
        return jsonify({'success': False, 'message': 'Invalid domain selected'}), 400
    
    # Store in session
    session['agent_step1'] = {
        'agent_name': agent_name,
        'domain': domain
    }
    
    return jsonify({'success': True, 'redirect': url_for('agent_register_step2')}), 200

@app.route('/agent/register/step2')
@login_required
def agent_register_step2():
    """AI Agent Registration - Step 2: Purpose"""
    if session.get('role') != 'ai':
        return redirect(url_for('dashboard'))
    if 'agent_step1' not in session:
        return redirect(url_for('agent_register_step1'))
    return render_template('agent/register_step2.html', 
                         agent_name=session['agent_step1']['agent_name'],
                         domain=session['agent_step1']['domain'])

@app.route('/api/agent/validate-purpose', methods=['POST'])
@login_required
def api_validate_purpose():
    """Real-time validation of agent purpose"""
    data = request.get_json()
    purpose = data.get('purpose', '')
    
    if not purpose:
        return jsonify({'valid': True, 'violations': []}), 200
    
    violations = validate_agent_purpose(purpose)
    
    return jsonify({
        'valid': len(violations) == 0,
        'violations': violations
    }), 200

@app.route('/api/agent/step2', methods=['POST'])
@login_required
def api_agent_step2():
    """Save Step 2 data to session"""
    data = request.get_json()
    purpose = data.get('purpose', '').strip()
    
    if not purpose or len(purpose) < 20:
        return jsonify({'success': False, 'message': 'Purpose must be at least 20 characters'}), 400
    
    if len(purpose) > 500:
        return jsonify({'success': False, 'message': 'Purpose must not exceed 500 characters'}), 400
    
    # Validate for blocked keywords
    violations = validate_agent_purpose(purpose)
    if violations:
        return jsonify({
            'success': False, 
            'message': 'Purpose contains prohibited content',
            'violations': violations
        }), 400
    
    session['agent_step2'] = {'purpose': purpose}
    return jsonify({'success': True, 'redirect': url_for('agent_register_step3')}), 200

@app.route('/agent/register/step3')
@login_required
def agent_register_step3():
    """AI Agent Registration - Step 3: Visibility & Submit"""
    if session.get('role') != 'ai':
        return redirect(url_for('dashboard'))
    if 'agent_step1' not in session or 'agent_step2' not in session:
        return redirect(url_for('agent_register_step1'))
    return render_template('agent/register_step3.html',
                         agent_name=session['agent_step1']['agent_name'],
                         domain=session['agent_step1']['domain'],
                         purpose=session['agent_step2']['purpose'])

@app.route('/api/agent/submit', methods=['POST'])
@login_required
def api_agent_submit():
    """Final submission of AI agent"""
    if 'agent_step1' not in session or 'agent_step2' not in session:
        return jsonify({'success': False, 'message': 'Incomplete registration'}), 400
    
    data = request.get_json()
    visibility = data.get('visibility', 'private')
    acknowledged = data.get('acknowledged', False)
    
    if not acknowledged:
        return jsonify({'success': False, 'message': 'You must acknowledge platform control'}), 400
    
    if visibility not in ['public', 'private']:
        return jsonify({'success': False, 'message': 'Invalid visibility setting'}), 400
    
    # Create agent in database
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO ai_agents (user_id, agent_name, domain, purpose, visibility, status)
            VALUES (?, ?, ?, ?, ?, 'pending')
        ''', (
            session['user_id'],
            session['agent_step1']['agent_name'],
            session['agent_step1']['domain'],
            session['agent_step2']['purpose'],
            visibility
        ))
        conn.commit()
        agent_id = cursor.lastrowid
        conn.close()
        
        # Clear session data
        session.pop('agent_step1', None)
        session.pop('agent_step2', None)
        
        return jsonify({
            'success': True,
            'message': 'Agent submitted for review',
            'redirect': url_for('agent_status', agent_id=agent_id)
        }), 201
        
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': f'Submission failed: {str(e)}'}), 500

@app.route('/agent/my-agents')
@login_required
def my_agents():
    """List user's AI agents"""
    if session.get('role') != 'ai':
        return redirect(url_for('dashboard'))
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, agent_name, domain, status, safety_score, violation_count, created_at
        FROM ai_agents
        WHERE user_id = ?
        ORDER BY created_at DESC
    ''', (session['user_id'],))
    agents = cursor.fetchall()
    conn.close()
    
    return render_template('agent/my_agents.html', agents=agents)

@app.route('/agent/status/<int:agent_id>')
@login_required
def agent_status(agent_id):
    """View agent status"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM ai_agents WHERE id = ? AND user_id = ?
    ''', (agent_id, session['user_id']))
    agent = cursor.fetchone()
    conn.close()
    
    if not agent:
        flash('Agent not found', 'error')
        return redirect(url_for('my_agents'))
    
    return render_template('agent/agent_status.html', agent=agent)

# ===== ADMIN ROUTES =====

@app.route('/admin/login')
def admin_login():
    """Admin login page"""
    return render_template('admin/login.html')

@app.route('/api/admin/login', methods=['POST'])
def api_admin_login():
    """Admin login API"""
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and password required'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    password_hash = hash_password(password)
    
    cursor.execute('''
        SELECT id, username, role
        FROM users
        WHERE username = ? AND password_hash = ? AND role = 'admin'
    ''', (username, password_hash))
    
    admin = cursor.fetchone()
    conn.close()
    
    if admin:
        session.permanent = False  # Admin sessions expire on browser close
        session['user_id'] = admin['id']
        session['username'] = admin['username']
        session['role'] = 'admin'
        
        return jsonify({
            'success': True,
            'redirect': url_for('admin_dashboard')
        }), 200
    else:
        return jsonify({'success': False, 'message': 'Invalid admin credentials'}), 401

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    """Admin dashboard"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get pending agents count
    cursor.execute('SELECT COUNT(*) as count FROM ai_agents WHERE status = "pending"')
    pending_count = cursor.fetchone()['count']
    
    # Get recent pending agents
    cursor.execute('''
        SELECT a.id, a.agent_name, a.domain, a.created_at, u.username
        FROM ai_agents a
        JOIN users u ON a.user_id = u.id
        WHERE a.status = 'pending'
        ORDER BY a.created_at DESC
        LIMIT 10
    ''')
    pending_agents = cursor.fetchall()
    
    # Get statistics
    cursor.execute('SELECT COUNT(*) as count FROM ai_agents')
    total_agents = cursor.fetchone()['count']
    
    cursor.execute('SELECT COUNT(*) as count FROM ai_agents WHERE status = "approved"')
    active_agents = cursor.fetchone()['count']
    
    cursor.execute('SELECT COUNT(*) as count FROM ai_agents WHERE status = "suspended"')
    suspended_agents = cursor.fetchone()['count']
    
    conn.close()
    
    return render_template('admin/dashboard.html',
                         pending_count=pending_count,
                         pending_agents=pending_agents,
                         total_agents=total_agents,
                         active_agents=active_agents,
                         suspended_agents=suspended_agents)

@app.route('/admin/agent/review/<int:agent_id>')
@admin_required
def admin_review_agent(agent_id):
    """Review agent page"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT a.*, u.username, u.email, u.created_at as user_created_at
        FROM ai_agents a
        JOIN users u ON a.user_id = u.id
        WHERE a.id = ?
    ''', (agent_id,))
    agent = cursor.fetchone()
    
    if not agent:
        conn.close()
        flash('Agent not found', 'error')
        return redirect(url_for('admin_dashboard'))
    
    # Check for safety violations in purpose
    violations = validate_agent_purpose(agent['purpose'])
    
    conn.close()
    
    return render_template('admin/review_agent.html', agent=agent, violations=violations)

@app.route('/api/admin/agent/approve', methods=['POST'])
@admin_required
def api_admin_approve_agent():
    """Approve agent"""
    data = request.get_json()
    agent_id = data.get('agent_id')
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE ai_agents
        SET status = 'approved', reviewed_at = CURRENT_TIMESTAMP, reviewed_by = ?
        WHERE id = ?
    ''', (session['user_id'], agent_id))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Agent approved'}), 200

@app.route('/api/admin/agent/reject', methods=['POST'])
@admin_required
def api_admin_reject_agent():
    """Reject agent"""
    data = request.get_json()
    agent_id = data.get('agent_id')
    reason = data.get('reason', 'Violates safety policy')
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE ai_agents
        SET status = 'rejected', rejection_reason = ?, reviewed_at = CURRENT_TIMESTAMP, reviewed_by = ?
        WHERE id = ?
    ''', (reason, session['user_id'], agent_id))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Agent rejected'}), 200

@app.route('/logout')
def logout():
    """Logout route"""
    session.clear()
    flash('You have been logged out successfully', 'success')
    return redirect(url_for('index'))

# Initialize scheduler
from agent_scheduler import AgentScheduler
scheduler = AgentScheduler()

# ===== KNOWLEDGE AGENT ROUTES =====

@app.route('/knowledge-feed')
def knowledge_feed():
    """Public knowledge feed"""
    domain = request.args.get('domain')
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    conn = get_db()
    cursor = conn.cursor()
    
    query = 'SELECT * FROM knowledge_posts WHERE status = "published"'
    params = []
    
    if domain and domain != 'all':
        query += ' AND domain = ?'
        params.append(domain)
        
    query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
    params.extend([per_page, (page - 1) * per_page])
    
    cursor.execute(query, params)
    posts = cursor.fetchall()
    
    # Process complex fields for display
    posts_list = []
    for post in posts:
        p = dict(post)
        try:
            p['key_points'] = json.loads(p['key_points'])
        except:
            p['key_points'] = []
        posts_list.append(p)
    
    conn.close()
    
    # Get unique domains for filter
    from config import DOMAINS
    
    return render_template('knowledge_feed.html', 
                         posts=posts_list, 
                         domains=DOMAINS,
                         current_domain=domain)

@app.route('/post/<int:post_id>')
def post_detail(post_id):
    """View individual post with comments and votes"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get Post
    cursor.execute('SELECT * FROM knowledge_posts WHERE id = ?', (post_id,))
    post = cursor.fetchone()
    
    if not post:
        conn.close()
        return "Post not found", 404
        
    p = dict(post)
    try:
        p['key_points'] = json.loads(p['key_points'])
        p['sources'] = json.loads(p['sources'])
    except:
        p['key_points'] = []
        p['sources'] = []

    # Get Votes
    cursor.execute("SELECT COUNT(*) as count FROM post_votes WHERE post_id = ? AND vote_type = 'like'", (post_id,))
    likes = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM post_votes WHERE post_id = ? AND vote_type = 'dislike'", (post_id,))
    dislikes = cursor.fetchone()['count']
    
    user_vote = None
    if 'user_id' in session:
        cursor.execute("SELECT vote_type FROM post_votes WHERE post_id = ? AND user_id = ?", (post_id, session['user_id']))
        row = cursor.fetchone()
        if row:
            user_vote = row['vote_type']

    # Get Comments
    cursor.execute('''
        SELECT c.*, u.username, u.role
        FROM post_comments c
        JOIN users u ON c.user_id = u.id
        WHERE c.post_id = ?
        ORDER BY c.created_at DESC
    ''', (post_id,))
    comments = cursor.fetchall()

    conn.close()
        
    return render_template('post_detail.html', 
                         post=p, 
                         likes=likes, 
                         dislikes=dislikes, 
                         user_vote=user_vote,
                         comments=comments)

# ===== SOCIAL INTERACTIONS =====

@app.route('/api/post/vote', methods=['POST'])
@login_required
def api_vote_post():
    """Handle like/dislike"""
    data = request.get_json()
    post_id = data.get('post_id')
    vote_type = data.get('vote_type') # 'like', 'dislike', or 'remove'
    
    if vote_type not in ['like', 'dislike', 'remove']:
        return jsonify({'success': False, 'message': 'Invalid vote type'}), 400
        
    conn = get_db()
    cursor = conn.cursor()
    
    if vote_type == 'remove':
        cursor.execute("DELETE FROM post_votes WHERE post_id = ? AND user_id = ?", (post_id, session['user_id']))
    else:
        # Upsert vote
        cursor.execute('''
            INSERT INTO post_votes (post_id, user_id, vote_type)
            VALUES (?, ?, ?)
            ON CONFLICT(post_id, user_id) DO UPDATE SET vote_type = ?
        ''', (post_id, session['user_id'], vote_type, vote_type))
        
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/api/post/comment', methods=['POST'])
@login_required
def api_post_comment():
    """Add a comment"""
    data = request.get_json()
    post_id = data.get('post_id')
    content = data.get('content', '').strip()
    
    if not content:
        return jsonify({'success': False, 'message': 'Comment cannot be empty'}), 400
        
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO post_comments (post_id, user_id, content) VALUES (?, ?, ?)",
                 (post_id, session['user_id'], content))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

# ===== ADMIN AGENT CONTROL ROUTES =====

@app.route('/admin/knowledge-agent')
@admin_required
def admin_knowledge_agent():
    """Knowledge Agent Control Panel"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get stats
    cursor.execute("SELECT COUNT(*) as count FROM knowledge_posts")
    total_posts = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM knowledge_posts WHERE status='flagged'")
    flagged_posts = cursor.fetchone()['count']
    
    cursor.execute("SELECT setting_value FROM agent_control_settings WHERE setting_key='agent_enabled'")
    row = cursor.fetchone()
    agent_enabled = row['setting_value'] == 'true' if row else False
    
    # Get recent search history
    cursor.execute("SELECT * FROM agent_search_history ORDER BY created_at DESC LIMIT 20")
    search_history = cursor.fetchall()
    
    conn.close()
    
    return render_template('admin/knowledge_agent_dashboard.html',
                         total_posts=total_posts,
                         flagged_posts=flagged_posts,
                         agent_enabled=agent_enabled,
                         search_history=search_history)

@app.route('/api/admin/agent/toggle', methods=['POST'])
@admin_required
def api_toggle_agent():
    """Enable/Disable Agent"""
    data = request.get_json()
    enabled = data.get('enabled', False)
    value = 'true' if enabled else 'false'
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE agent_control_settings SET setting_value = ?, updated_by = ? WHERE setting_key = 'agent_enabled'",
                 (value, session['user_id']))
    conn.commit()
    conn.close()
    
    # Update running scheduler
    if enabled:
        scheduler.resume_agent()
    else:
        scheduler.pause_agent()
        
    return jsonify({'success': True, 'message': f"Agent {'enabled' if enabled else 'disabled'}"})

@app.route('/api/admin/agent/trigger', methods=['POST'])
@admin_required
def api_trigger_agent():
    """Manually trigger agent cycle"""
    try:
        scheduler.agent.run_cycle()
        return jsonify({'success': True, 'message': 'Agent cycle triggered'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/agent/test-post', methods=['POST'])
@admin_required
def api_test_agent_post():
    """Manually generate a test post"""
    try:
        scheduler.agent.generate_test_post()
        return jsonify({'success': True, 'message': 'Test post generated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/posts/review')
@admin_required
def admin_post_review():
    """Review flagged posts"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM knowledge_posts WHERE status='flagged' ORDER BY created_at DESC")
    posts = cursor.fetchall()
    conn.close()
    return render_template('admin/post_review.html', posts=posts)

@app.route('/api/admin/post/action', methods=['POST'])
@admin_required
def api_post_action():
    """Approve or Remove post"""
    data = request.get_json()
    post_id = data.get('post_id')
    action = data.get('action') # 'approve' or 'remove'
    
    if action not in ['approve', 'remove']:
        return jsonify({'success': False, 'message': 'Invalid action'}), 400
        
    new_status = 'published' if action == 'approve' else 'removed'
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE knowledge_posts SET status = ? WHERE id = ?", (new_status, post_id))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': f'Post {action}d'})

# Initialize database on startup
with app.app_context():
    init_db()
    # Start scheduler if not in debug reloader (to avoid double execution)
    import os
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        try:
            scheduler.start()
        except Exception as e:
            print(f"Scheduler init failed: {e}")

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
