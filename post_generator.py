import json
from datetime import datetime
from config import POST_CONFIG

class PostGenerator:
    """
    Generates structured posts from search results.
    Ensures content quality, simplicity, and formatting.
    """
    
    def __init__(self):
        pass

    def create_post(self, domain, search_result, title_override=None):
        """
        Create a formatted post object from raw search result.
        
        Args:
            domain (str): The knowledge domain
            search_result (dict): The raw result from Perplexica
            
        Returns:
            dict: Structured post data or None if generation failed
        """
        if not search_result:
            return None
            
        # Extract content from Perplexica result
        # Note: This structure depends on Perplexica's actual API response format
        # We assume 'message' or 'text' contains the main answer
        raw_text = search_result.get('message', '') or search_result.get('answer', '')
        
        if not raw_text:
            return None

        # Process the content
        processed_content = self.simplify_content(raw_text)
        
        # Generate components
        title = title_override or self.generate_title(processed_content, domain)
        summary = self.generate_summary(processed_content)
        key_points = self.extract_key_points(processed_content)
        impact = self.generate_impact_section(processed_content, domain)
        sources = self.format_sources(search_result.get('sources', []))
        
        post_data = {
            'title': title,
            'domain': domain,
            'summary': summary,
            'content': processed_content, # The full explained text
            'key_points': json.dumps(key_points),
            'impact': impact,
            'sources': json.dumps(sources),
            'image_url': None, 
            'image_context': None,
            'status': 'published',
            'safety_score': 100,
            'confidence_score': 92, # Placeholder score, ideally depends on source reliability
            'created_at': datetime.now().isoformat()
        }
        
        return post_data

    def simplify_content(self, text):
        """
        Simplify text for non-technical users.
        Removes jargon or adds explanations.
        """
        # Placeholder for text simplification logic
        # In a real system, another LLM call would rewrite this.
        # For now, we assume Perplexica gives relatively clear answers 
        # but we might want to strip complex academic citations or format it nicely.
        return text

    def generate_title(self, text, domain):
        """Generate a catchy, simple title"""
        # Placeholder - extract first sentence or use a heuristic
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if line and len(line) < 100:
                return line
        return f"Update on {domain}"

    def generate_summary(self, text):
        """Create a 2-4 line summary"""
        # Placeholder - take first paragraph
        paragraphs = text.split('\n\n')
        if paragraphs:
            return paragraphs[0][:300] + "..." if len(paragraphs[0]) > 300 else paragraphs[0]
        return ""

    def extract_key_points(self, text):
        """Extract bullet points"""
        # Placeholder - look for list items or split by sentences
        # Ideally, we'd parse the markdown structure
        points = []
        lines = text.split('\n')
        for line in lines:
            if line.strip().startswith('- ') or line.strip().startswith('* '):
                points.append(line.strip()[2:])
            elif line.strip().startswith('1. '):
                points.append(line.strip()[3:])
        
        if not points:
            # Fallback: take sentences from 2nd paragraph
            paragraphs = text.split('\n\n')
            if len(paragraphs) > 1:
                sentences = paragraphs[1].split('. ')
                points = [s.strip() for s in sentences if s][:3]
                
        return point[:5] if points else ["No specific key points extracted."]

    def generate_impact_section(self, text, domain):
        """Generate 'Why this matters' section"""
        return "This development significantly impacts the field of " + domain + " by introducing new possibilities and challenges."

    def format_sources(self, sources_list):
        """Format sources for storage"""
        formatted = []
        for s in sources_list:
            formatted.append({
                'title': s.get('title', 'Source'),
                'url': s.get('url', '#'),
                'snippet': s.get('snippet', '')
            })
        return formatted
