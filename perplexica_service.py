import requests
import json
import logging
from datetime import datetime
from config import PERPLEXICA_CONFIG, AGENT_CONFIG

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PerplexicaService:
    """Service to interact with self-hosted Perplexica API"""
    
    def __init__(self):
        self.endpoint = PERPLEXICA_CONFIG['endpoint']
        self.headers = {'Content-Type': 'application/json'}
        
    def search(self, query, mode='copilot', focus='internet'):
        """
        Perform a search using Perplexica
        
        Args:
            query (str): The search query
            mode (str): Search mode (copilot, normal)
            focus (str): Search focus (internet, scholar, news, etc.)
            
        Returns:
            dict: Search results and text response
        """
        url = f"{self.endpoint}/api/search"
        
        payload = {
            "query": query,
            "mode": mode,
            "focus": focus,
            # Add any other required parameters for Perplexica API here
            # Based on standard usage, chatModel might be needed depending on config
            # "chatModel": { "provider": "openai", "model": "gpt-3.5-turbo" } # Example
        }
        
        try:
            response = requests.post(
                url, 
                json=payload, 
                headers=self.headers,
                timeout=PERPLEXICA_CONFIG['timeout']
            )
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Perplexica search failed for query '{query}': {str(e)}")
            return None

    def lightweight_scan(self, domain_query):
        """
        Perform a quick scan for a domain to check for updates
        Using 'news' focus if available, or 'internet'
        """
        return self.search(domain_query, mode='normal', focus='news')

    def deep_search(self, query):
        """
        Perform a deep search for comprehensive information
        Using 'copilot' mode if available for more detailed steps
        """
        return self.search(query, mode='copilot', focus='internet')

    def extract_sources(self, search_result):
        """Extract sources from search result"""
        if not search_result or 'sources' not in search_result:
            return []
        
        return search_result['sources']

    def is_significant_update(self, new_result, last_known_hash=None):
        """
        Determine if the result contains significant new information
        This is a simplified check - in production it would need vector comparison or more complex logic
        """
        if not new_result:
            return False
            
        # Placeholder for update detection logic
        # For now, we assume if we got good results, it might be new
        # In a real implementation, we would compare with previous results
        return True
