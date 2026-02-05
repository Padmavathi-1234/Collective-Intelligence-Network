from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import atexit
import logging
from config import AGENT_CONFIG
from knowledge_agent_service import KnowledgeAgent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AgentScheduler:
    """
    Manages background tasks for the AI Knowledge Agent.
    """
    
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.agent = KnowledgeAgent()
        
    def start(self):
        """Start the scheduler"""
        if not self.scheduler.running:
            # Add job to run agent cycle
            self.scheduler.add_job(
                func=self.agent.run_cycle,
                trigger=IntervalTrigger(minutes=AGENT_CONFIG['scan_interval_minutes']),
                id='knowledge_agent_cycle',
                name='Run Knowledge Agent Monitoring Cycle',
                replace_existing=True,
                coalesce=True, # Don't stack up missed runs
                max_instances=1
            )
            
            logger.info(f"Starting Agent Scheduler (Interval: {AGENT_CONFIG['scan_interval_minutes']} mins)...")
            self.scheduler.start()
            
            # Shut down scheduler when exiting the app
            atexit.register(lambda: self.scheduler.shutdown())

    def pause_agent(self):
        """Pause the agent job"""
        self.scheduler.pause_job('knowledge_agent_cycle')
        logger.info("Agent job paused")

    def resume_agent(self):
        """Resume the agent job"""
        self.scheduler.resume_job('knowledge_agent_cycle')
        logger.info("Agent job resumed")

    def shutdown(self):
        """Shutdown scheduler"""
        self.scheduler.shutdown()
