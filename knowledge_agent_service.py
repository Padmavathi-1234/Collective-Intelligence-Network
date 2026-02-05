import concurrent.futures
import time
import json
from datetime import datetime
from datetime import datetime
from database import get_db
from config import DOMAINS, DOMAIN_QUERIES, AGENT_CONFIG
import logging

from perplexica_service import PerplexicaService
from safety_validator import SafetyValidator
from post_generator import PostGenerator
from config import DOMAINS, DOMAIN_QUERIES, AGENT_CONFIG, DOMAIN_QUERIES

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class KnowledgeAgent:
    """
    Main autonomous agent class.
    Orchestrates monitoring, searching, and posting.
    """
    
    def __init__(self):
        self.perplexica = PerplexicaService()
        self.safety = SafetyValidator()
        self.generator = PostGenerator()
        
    def run_cycle(self):
        """
        Execute one full monitoring cycle.
        Should be called by the scheduler.
        """
        if not self.is_enabled():
            logger.info("Agent is disabled. Skipping cycle.")
            return

        logger.info("Starting Knowledge Agent cycle...")
        
        # We can process domains in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(self.process_domain, domain): domain for domain in DOMAINS}
            
            for future in concurrent.futures.as_completed(futures):
                domain = futures[future]
                try:
                    future.result()
                    logger.info(f"Completed processing for {domain}")
                except Exception as e:
                    logger.error(f"Error processing {domain}: {e}")

    def process_domain(self, domain):
        """
        Monitor a specific domain for updates.
        """
        logger.info(f"Scanning domain: {domain}")
        
        # 1. Get search queries for this domain
        queries = DOMAIN_QUERIES.get(domain, [f"latest news in {domain}"])
        
        for query in queries:
            # 2. Perform lightweight scan
            scan_result = self.perplexica.lightweight_scan(query)
            
            # Log the scan
            self.log_search_history(domain, query, 'lightweight', scan_result)
            
            # 3. Check for updates / Significance
            if self.perplexica.is_significant_update(scan_result):
                logger.info(f"Update detected for {domain} query: {query}")
                
                # 4. Perform deep search if significant
                deep_result = self.perplexica.deep_search(query)
                self.log_search_history(domain, query, 'deep', deep_result)
                
                # 5. Generate Post
                self.create_and_publish_post(domain, deep_result)
            else:
                logger.info(f"No significant update for {domain}")

    def create_and_publish_post(self, domain, search_result):
        """
        Generate, validate, and save a post.
        """
        # Generate content
        post_data = self.generator.create_post(domain, search_result)
        
        if not post_data:
            logger.warning(f"Failed to generate post for {domain}")
            return

        # Validate Safety
        is_safe, score, violations = self.safety.validate_content(post_data['content'])
        post_data['safety_score'] = score
        
        if not is_safe:
            logger.warning(f"Unsafe content detected for {domain}. Violations: {violations}")
            post_data['status'] = 'flagged' # Save as flagged for review
            # Logic to log violations to DB could go here
        
        # Check duplicate (simple check against recent titles)
        if self.is_duplicate(post_data['title']):
             logger.info(f"Duplicate post detected: {post_data['title']}")
             return

        # Save to DB
        self.save_post(post_data)
        logger.info(f"Post created: {post_data['title']}")

    def is_enabled(self):
        """Check if agent is enabled in settings"""
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT setting_value FROM agent_control_settings WHERE setting_key = 'agent_enabled'")
        row = cursor.fetchone()
        conn.close()
        return row and row['setting_value'].lower() == 'true'

    def log_search_history(self, domain, query, search_type, result):
        """Log search activity"""
        conn = get_db()
        cursor = conn.cursor()
        
        if result is None:
            count = -1 # Indicates error
        else:
            count = len(result.get('sources', []))
            
        cursor.execute('''
            INSERT INTO agent_search_history (domain, query, search_type, results_count)
            VALUES (?, ?, ?, ?)
        ''', (domain, query, search_type, count))
        conn.commit()
        conn.close()

    def save_post(self, post_data):
        """Save post to database"""
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO knowledge_posts 
            (title, domain, summary, content, key_points, impact, sources, status, safety_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            post_data['title'],
            post_data['domain'],
            post_data['summary'],
            post_data['content'],
            post_data['key_points'],
            post_data['impact'],
            post_data['sources'],
            post_data['status'],
            post_data['safety_score']
        ))
        conn.commit()
        conn.close()

    def is_duplicate(self, title):
        """Check if similar title exists recently"""
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM knowledge_posts WHERE title = ? AND created_at > datetime('now', '-1 day')", (title,))
        exists = cursor.fetchone()
        conn.close()
        return exists is not None

    def generate_test_post(self):
        """
        Generate a dummy post for testing purposes.
        Bypasses Perplexica and creates a sample entry.
        """
        test_domain = "Technology"
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        test_post = {
            'title': f"Test Post: AI Agent System Active ({timestamp})",
            'domain': test_domain,
            'summary': "This is a test post generated by the system to verify the entire pipeline from agent to database to frontend. If you see this, the system is working correctly.",
            'content': f"""
            This is a generated test post to validate the Knowledge Agent system.
            
            1. **Pipeline Verification**: The agent successfully created a post object.
            2. **Database Connection**: The post was saved to the SQLite database.
            3. **Frontend Display**: The post is visible in the knowledge feed.
            
            The system is currently monitoring {len(DOMAINS)} domains: {', '.join(DOMAINS[:3])} and others.
            Future posts will be generated based on real-time web searches using Perplexica.
            """,
            'key_points': json.dumps(["System Validation Successful", "Database Write Confirmed", "Frontend Rendering Active"]),
            'impact': "Verifies that the autonomous agent architecture is correctly deployed and operational.",
            'sources': json.dumps([{"title": "System Diagnostic", "url": "#", "snippet": "Internal system test generation."}]),
            'status': "published",
            'safety_score': 100
        }
        
        self.save_post(test_post)
        logger.info("Test post generated and saved.")
        return test_post

# Standalone run for testing
if __name__ == "__main__":
    agent = KnowledgeAgent()
    agent.run_cycle()
