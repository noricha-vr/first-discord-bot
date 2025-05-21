from dotenv import load_dotenv
from pathlib import Path
import os

# Load environment variables
DOTENV_PATH = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(dotenv_path=DOTENV_PATH)

DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
MYSQL_HOST = os.getenv('MYSQL_HOST')
MYSQL_USER = os.getenv('MYSQL_USER')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD')
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE')
RAW_MYSQL_PORT = os.getenv('MYSQL_PORT', '3306')
MYSQL_PORT = int(RAW_MYSQL_PORT.split('#')[0].strip().strip('"').strip("'"))
