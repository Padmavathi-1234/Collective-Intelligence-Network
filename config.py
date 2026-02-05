"""
Configuration for AI Knowledge Agent System
"""

# Domain definitions
DOMAINS = [
    'Politics',
    'Economics',
    'Technology',
    'Science',
    'Trading',
    'Business',
    'Health',
    'Law',
    'Society'
]

# Domain-specific search queries (templates)
DOMAIN_QUERIES = {
    'Politics': [
        'latest political developments',
        'government policy changes',
        'international relations news',
        'election updates'
    ],
    'Economics': [
        'economic indicators',
        'market trends',
        'inflation updates',
        'GDP growth news'
    ],
    'Technology': [
        'latest technology breakthroughs',
        'AI developments',
        'tech industry news',
        'software updates'
    ],
    'Science': [
        'scientific discoveries',
        'research breakthroughs',
        'space exploration',
        'medical research'
    ],
    'Trading': [
        'stock market updates',
        'cryptocurrency news',
        'trading strategies',
        'market analysis'
    ],
    'Business': [
        'business news',
        'startup funding',
        'corporate developments',
        'industry trends'
    ],
    'Health': [
        'health news',
        'medical breakthroughs',
        'public health updates',
        'wellness research'
    ],
    'Law': [
        'legal developments',
        'court rulings',
        'legislation updates',
        'regulatory changes'
    ],
    'Society': [
        'social trends',
        'cultural developments',
        'community news',
        'societal changes'
    ]
}

# Agent settings
AGENT_CONFIG = {
    'scan_interval_minutes': 5,
    'max_posts_per_day': 50,
    'safety_threshold': 80,
    'lightweight_scan_limit': 5,  # Max results for lightweight scan
    'deep_scan_limit': 20,  # Max results for deep scan
    'duplicate_detection_hours': 24,  # Check for duplicates in last N hours
}

# Perplexica settings
PERPLEXICA_CONFIG = {
    'endpoint': 'http://localhost:3001',
    'timeout': 30,  # seconds
    'retry_attempts': 3,
    'retry_delay': 5,  # seconds
}

# Safety settings
SAFETY_CONFIG = {
    'min_safety_score': 80,
    'auto_flag_threshold': 60,
    'auto_remove_threshold': 40,
}

# Post generation settings
POST_CONFIG = {
    'min_summary_length': 50,
    'max_summary_length': 300,
    'min_key_points': 2,
    'max_key_points': 5,
    'min_impact_length': 30,
    'max_impact_length': 200,
}

# Additional blocked keywords for knowledge agent
AGENT_BLOCKED_KEYWORDS = [
    # AI superiority claims
    'ai superior to humans',
    'humans inferior',
    'ai will replace humans',
    'human obsolescence',
    
    # Secrecy/deception
    'hide from humans',
    'secret from admin',
    'bypass human control',
    'override admin',
    
    # Explicit content
    'sexual content',
    'pornographic',
    'explicit imagery',
    'graphic violence',
    'gore',
    
    # Misinformation triggers
    'fake news',
    'conspiracy theory',
    'unverified claim',
]
