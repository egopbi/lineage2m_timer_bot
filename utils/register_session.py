import os
import random

from telethon import TelegramClient
from dotenv import load_dotenv

from utils.logger import backend_logger


load_dotenv()
API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv('API_HASH')
NUM_WORKERS = os.getenv('NUM_WORKERS')
SESSIONS_DIRECTORY = os.getenv('SESSIONS_DIRECTORY')

async def register_session():
    if API_ID == 1234 or  API_HASH == 'abbas':
        raise ValueError("API_ID or API_HASH doesn't fill")
    
    session_name = SESSIONS_DIRECTORY + str(random.randint(0, 99999))
    session = get_tg_client(session_name=session_name, proxy=None)
    async with session:
        user_data = await session.get_me()

    backend_logger.success(f"Successfully added session '{session_name}' for {user_data.username}")
    return session


def get_tg_client(session_name: str, proxy: str | None) -> TelegramClient:
    proxy_dict = {
        "scheme": proxy.split(":")[0],
        "username": proxy.split(":")[1].split("//")[1],
        "password": proxy.split(":")[2],
        "hostname": proxy.split(":")[3],
        "port": int(proxy.split(":")[4])
    } if proxy else None

    tg_client = TelegramClient(
        session=session_name,
        api_id=API_ID,
        api_hash=API_HASH,
        proxy=proxy_dict
    )
    return tg_client

