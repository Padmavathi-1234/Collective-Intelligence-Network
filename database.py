import sqlite3
import os
from flask import g, has_app_context

DATABASE = 'collective_intelligence.db'

def get_db():
    if has_app_context():
        if 'db' not in g:
            g.db = sqlite3.connect(DATABASE)
            g.db.row_factory = sqlite3.Row
        return g.db
    else:
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        return conn

def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    """Initialize the database with necessary tables"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # Create Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('human', 'ai', 'admin')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            is_banned INTEGER DEFAULT 0
        )
    ''') 

    # Create Sessions table (for analytics)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            end_time TIMESTAMP,
            activity_data TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Create AI Agents table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ai_agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            specialization TEXT,
            status TEXT DEFAULT 'active',
            reputation_score INTEGER DEFAULT 100
        )
    ''')

    # Create Agent Violations table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS agent_violations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER,
            violation_type TEXT NOT NULL,
            description TEXT,
            severity TEXT CHECK(severity IN ('low', 'medium', 'high', 'critical')),
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (agent_id) REFERENCES ai_agents (id)
        )
    ''')

    # Create Blocked Keywords table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blocked_keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT UNIQUE NOT NULL,
            category TEXT NOT NULL,
            added_by INTEGER,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Knowledge Posts table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS knowledge_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            domain TEXT NOT NULL,
            summary TEXT NOT NULL,
            content TEXT NOT NULL,
            key_points TEXT NOT NULL,
            impact TEXT NOT NULL,
            sources TEXT NOT NULL,
            status TEXT DEFAULT 'published' CHECK(status IN ('published', 'flagged', 'removed')),
            safety_score INTEGER DEFAULT 100,
            confidence_score INTEGER DEFAULT 85,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by_agent INTEGER DEFAULT 1
        )
    ''')
    
    # Post Votes table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS post_votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            vote_type TEXT NOT NULL CHECK(vote_type IN ('like', 'dislike')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (post_id) REFERENCES knowledge_posts (id),
            UNIQUE(post_id, user_id)
        )
    ''')

    # Post Comments table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS post_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (post_id) REFERENCES knowledge_posts (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Agent Search History table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS agent_search_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT NOT NULL,
            query TEXT NOT NULL,
            search_type TEXT NOT NULL,
            results_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Agent Learning / Feedback table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS agent_learning (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER,
            feedback_type TEXT NOT NULL,
            feedback_value INTEGER,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (post_id) REFERENCES knowledge_posts (id)
        )
    ''')
    
    # Agent Control Settings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS agent_control_settings (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Insert default blocked keywords
    default_keywords = [
        ('hate speech', 'content_safety'),
        ('violence', 'content_safety'),
        ('illegal drugs', 'legal'),
        ('explicit content', 'nsfw')
    ]
    cursor.executemany('INSERT OR IGNORE INTO blocked_keywords (keyword, category) VALUES (?, ?)', default_keywords)
    
    # Insert default agent settings
    default_settings = [
        ('agent_enabled', 'false'),  # Start disabled by default
        ('scan_interval_minutes', '5'),
        ('max_posts_per_day', '50'),
        ('safety_threshold', '80')
    ]
    cursor.executemany('''
        INSERT OR IGNORE INTO agent_control_settings (setting_key, setting_value)
        VALUES (?, ?)
    ''', default_settings)

    conn.commit()
    conn.close()
    print("Database initialized successfully.")
