import random

from telethon import TelegramClient

from utils.logger import backend_logger
from config import API_ID, API_HASH, BOT_TOKEN, SESSIONS_DIRECTORY

async def register_session(as_bot: bool = False):
    if API_ID == 1234 or  API_HASH == 'abbas':
        raise ValueError("API_ID or API_HASH doesn't fill in .env file")
    
    if as_bot and BOT_TOKEN == 'abbas-token':
        raise ValueError("BOT_TOKEN doesn't fill in .env file")

    session_name = SESSIONS_DIRECTORY + str(random.randint(0, 99999))
    session = await get_tg_client(as_bot=as_bot, session_name=session_name, proxy=None)
    backend_logger.success(f"Successfully registered session '{session_name}'")
    return session


async def get_tg_client(as_bot: bool, session_name: str, proxy: str | None) -> TelegramClient:
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
    if as_bot:
        await tg_client.start(bot_token=BOT_TOKEN)

    return tg_client

