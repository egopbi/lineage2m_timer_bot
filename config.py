import os

from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv('API_ID'))
API_HASH = str(os.getenv('API_HASH'))
BOT_TOKEN = str(os.getenv('BOT_TOKEN'))
SESSIONS_DIRECTORY = os.getenv('SESSIONS_DIRECTORY')
DATABASE_URL = os.getenv('DATABASE_URL')
DATABASE_ECHO = bool(os.getenv('DATABASE_ECHO'))
