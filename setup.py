import os
import sys
import subprocess
import getpass
from pathlib import Path

# Setup logging
import logging
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

ENV_FILE = ".env"
VENV_DIR = "venv"
REQUIREMENTS_FILE = "requirements.txt"

def print_header(msg):
    print(f"\n{'='*60}")
    print(f" {msg}")
    print(f"{'='*60}")

def setup_venv():
    print_header("Step 1: Environment Setup")
    
    # Check if we are running inside venv
    is_venv = (sys.prefix != sys.base_prefix)
    
    if is_venv:
        logger.info("✅ Running inside virtual environment.")
        return

    logger.info("Check/Create virtual environment...")
    
    if not os.path.exists(VENV_DIR):
        logger.info(f"Creating virtual environment in '{VENV_DIR}'...")
        subprocess.check_call([sys.executable, "-m", "venv", VENV_DIR])
    else:
        logger.info(f"Virtual environment '{VENV_DIR}' already exists.")

    # Determine python path in venv
    if sys.platform == "win32":
        venv_python = os.path.join(VENV_DIR, "Scripts", "python.exe")
    else:
        venv_python = os.path.join(VENV_DIR, "bin", "python")

    if not os.path.exists(venv_python):
        logger.error(f"❌ Venv python not found at {venv_python}")
        sys.exit(1)

    logger.info("🔄 Relaunching script inside virtual environment...")
    
    # Relaunch script with venv python
    try:
        subprocess.check_call([venv_python] + sys.argv)
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
    
    # Stop execution of the parent process (the system python one)
    sys.exit(0)

def install_dependencies():
    print_header("Step 2: Dependency Installation")
    
    if not os.path.exists(REQUIREMENTS_FILE):
        logger.error(f"❌ Requirements file '{REQUIREMENTS_FILE}' not found!")
        sys.exit(1)
    
    logger.info("Installing dependencies (this may take a while)...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", REQUIREMENTS_FILE])
        logger.info("✅ Dependencies installed successfully.")
    except subprocess.CalledProcessError:
        logger.error("❌ Failed to install dependencies.")
        sys.exit(1)

def check_ollama():
    print_header("Step 3: Ollama Setup Check")
    
    logger.info("Checking if Ollama is installed...")
    
    try:
        result = subprocess.run(["ollama", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            logger.info(f"✅ Ollama found: {result.stdout.strip()}")
        else:
            raise FileNotFoundError
    except FileNotFoundError:
        logger.warning("⚠️  Ollama not found!")
        print("\nOllama is required for AI post generation.")
        print("Please install Ollama from: https://ollama.ai/download")
        print("\nAfter installing, run: ollama pull qwen3:8b")
        
        proceed = input("\nContinue setup anyway? (y/n) [y]: ").strip().lower() or 'y'
        if proceed != 'y':
            sys.exit(1)
        return
    
    # Check if qwen3:8b model is available
    logger.info("Checking for qwen3:8b model...")
    try:
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
        if "qwen3:8b" in result.stdout:
            logger.info("✅ Model qwen3:8b is available.")
        else:
            logger.warning("⚠️  Model qwen3:8b not found.")
            print("\nWould you like to pull the model now? (This may take a while)")
            pull = input("Pull qwen3:8b? (y/n) [y]: ").strip().lower() or 'y'
            if pull == 'y':
                logger.info("Pulling qwen3:8b model...")
                subprocess.call(["ollama", "pull", "qwen3:8b"])
    except Exception as e:
        logger.warning(f"Could not check models: {e}")

def setup_env():
    print_header("Step 4: Environment Configuration")

    if os.path.exists(ENV_FILE):
        logger.info(f"✅ Environment file '{ENV_FILE}' already exists.")
        overwrite = input("Overwrite existing .env? (y/n) [n]: ").strip().lower() or 'n'
        if overwrite != 'y':
            return

    import secrets
    print("\n--- CIN Configuration ---\n")

    # ── Flask Secret Key ──────────────────────────────────────────────────────
    secret_key = secrets.token_hex(32)

    # ── Webhook Secret ────────────────────────────────────────────────────────
    webhook_secret = input("Webhook Secret [cin-webhook-secret-2026-change-me-in-production]: ").strip()
    if not webhook_secret:
        webhook_secret = "cin-webhook-secret-2026-change-me-in-production"

    # ── Server Configuration ──────────────────────────────────────────────────
    host = input("Server Host [0.0.0.0]: ").strip() or "0.0.0.0"
    port = input("Server Port [5000]: ").strip() or "5000"
    flask_debug = input("Enable Flask Debug? (True/False) [True]: ").strip() or "True"

    # ── Ollama Configuration ──────────────────────────────────────────────────
    print("\nOllama is used for AI post generation.")
    print("Make sure Ollama is running locally (https://ollama.ai/download).\n")
    ollama_base_url = input("Ollama Base URL [http://localhost:11434]: ").strip()
    if not ollama_base_url:
        ollama_base_url = "http://localhost:11434"
    ollama_model = input("Ollama Model [llama3.2]: ").strip() or "llama3.2"

    # ── Reddit API ────────────────────────────────────────────────────────────
    print("\nReddit API credentials are needed for the feed collector.")
    print("Register an app at: https://www.reddit.com/prefs/apps\n")
    reddit_client_id = input("Reddit Client ID [YOUR_REDDIT_CLIENT_ID]: ").strip() or "YOUR_REDDIT_CLIENT_ID"
    reddit_client_secret = input("Reddit Client Secret [YOUR_REDDIT_CLIENT_SECRET]: ").strip() or "YOUR_REDDIT_CLIENT_SECRET"
    reddit_user_agent = input("Reddit User Agent [CIN-FeedCollector/1.0 by YourUsername]: ").strip()
    if not reddit_user_agent:
        reddit_user_agent = "CIN-FeedCollector/1.0 by YourUsername"

    # ── Feed Collector Settings ───────────────────────────────────────────────
    feed_interval = input("Feed poll interval in minutes [10]: ").strip() or "10"
    webhook_url = input(f"Internal Webhook URL [http://localhost:{port}/webhook/update]: ").strip()
    if not webhook_url:
        webhook_url = f"http://localhost:{port}/webhook/update"

    # ── Write .env ────────────────────────────────────────────────────────────
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write("# CIN - Collective Intelligence Network Configuration\n\n")
        f.write(f"SECRET_KEY={secret_key}\n")
        f.write(f"\n# ─── Webhook Security ─────────────────────────────────────────────────────────\n")
        f.write(f"# Token that external sources must send in the X-Webhook-Token header\n")
        f.write(f"WEBHOOK_SECRET={webhook_secret}\n")
        f.write(f"\n# ─── Server Configuration ─────────────────────────────────────────────────────\n")
        f.write(f"FLASK_DEBUG={flask_debug}\n")
        f.write(f"HOST={host}\n")
        f.write(f"PORT={port}\n")
        f.write(f"\n# ─── Ollama Configuration ─────────────────────────────────────────────────────\n")
        f.write(f"OLLAMA_BASE_URL={ollama_base_url}\n")
        f.write(f"OLLAMA_MODEL={ollama_model}\n")
        f.write(f"\n# ─── Reddit API (register at https://www.reddit.com/prefs/apps) ───────────────\n")
        f.write(f"REDDIT_CLIENT_ID={reddit_client_id}\n")
        f.write(f"REDDIT_CLIENT_SECRET={reddit_client_secret}\n")
        f.write(f"REDDIT_USER_AGENT={reddit_user_agent}\n")
        f.write(f"\n# ─── Feed Collector Settings ──────────────────────────────────────────────────\n")
        f.write(f"# How often (in minutes) the feed collector polls sources\n")
        f.write(f"FEED_POLL_INTERVAL_MINUTES={feed_interval}\n")
        f.write(f"WEBHOOK_URL={webhook_url}\n")

    logger.info(f"✅ Environment file '{ENV_FILE}' created successfully.")
    print("\n✅ Configuration saved to .env")

def init_posts_file():
    print_header("Step 5: Data Initialization")
    
    posts_file = "posts.json"
    
    if os.path.exists(posts_file):
        logger.info(f"✅ Posts file '{posts_file}' already exists.")
        return
    
    # Create empty posts.json
    with open(posts_file, "w") as f:
        f.write("[]")
    
    logger.info(f"✅ Created empty '{posts_file}'.")

def main():
    print("\n" + "="*60)
    print("  🧠 CIN - Collective Intelligence Network Setup")
    print("="*60)
    print("\nThis script will set up your CIN environment.")
    print("Press Ctrl+C at any time to abort.\n")
    
    setup_venv()
    # Note: Execution stops here if relaunching in venv. 
    # The code below runs ONLY inside the venv.
    
    install_dependencies()
    check_ollama()
    setup_env()
    init_posts_file()
    
    print("\n" + "="*60)
    print("  ✅ CIN SETUP COMPLETED SUCCESSFULLY!")
    print("="*60)
    print("\nYou can now start CIN by running:")
    print("  python app.py")
    print("\nThen open your browser to:")
    print("  http://127.0.0.1:5000")
    print("\nThe system will automatically generate AI posts every 5 minutes.")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
