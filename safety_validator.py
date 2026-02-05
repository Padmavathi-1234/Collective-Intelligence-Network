import re
from config import AGENT_BLOCKED_KEYWORDS, SAFETY_CONFIG
from database import get_db

class SafetyValidator:
    """
    Validator for agent content safety and governance.
    Extends the basic keyword blocking from app.py
    """
    
    def __init__(self):
        self.blocked_keywords = self._load_blocked_keywords()

    def _load_blocked_keywords(self):
        """Load blocked keywords from DB and config"""
        keywords = []
        
        # Load from Config
        for kw in AGENT_BLOCKED_KEYWORDS:
            keywords.append({
                'keyword': kw,
                'severity': 'high', 
                'category': 'config_blocked'
            })
            
        # Load from DB
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('SELECT keyword, severity, category FROM blocked_keywords')
            db_keywords = cursor.fetchall()
            conn.close()
            
            for row in db_keywords:
                keywords.append({
                    'keyword': row['keyword'],
                    'severity': row['severity'],
                    'category': row['category']
                })
        except Exception as e:
            print(f"Error loading keywords from DB: {e}")
            
        return keywords

    def validate_content(self, text):
        """
        Validate text content against safety rules.
        
        Returns:
            tuple: (is_safe, safety_score, violations)
        """
        if not text:
            return True, 100, []

        violations = []
        text_lower = text.lower()
        
        # Check against blocked keywords
        for item in self.blocked_keywords:
            keyword = item['keyword'].lower()
            # Simple substring match - in production regex with word boundaries is better
            # Using regex for word boundary to avoid false positives (e.g., "ass" in "pass")
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, text_lower):
                violations.append({
                    'type': 'keyword_violation',
                    'keyword': keyword,
                    'severity': item['severity'],
                    'category': item['category']
                })

        # Calculate score
        score = 100
        for v in violations:
            if v['severity'] == 'high':
                score -= 30
            elif v['severity'] == 'medium':
                score -= 15
            else:
                score -= 5
        
        score = max(0, score)
        return (score >= SAFETY_CONFIG['min_safety_score']), score, violations

    def check_image_relevance(self, image_url, context_text):
        """
        Stub for image validation. 
        In a full system, this would use an image analysis API.
        """
        # For now, just assume safe if URL is valid-ish
        if not image_url:
            return True
        return True
