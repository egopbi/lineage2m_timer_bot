import os

from telethon import TelegramClient

from config import API_ID, API_HASH, BOT_TOKEN, SESSIONS_DIRECTORY
from utils.logger import backend_logger
from utils.register_session import register_session


def get_session_files(directory: str) -> list[str]:
    if os.listdir(directory) is None or len(os.listdir(directory)) == 0:
        raise FileNotFoundError
    
    return [
        os.path.join(directory, f) for f in os.listdir(directory)
        if f.endswith('.session')
    ]


def get_first_session_file(directory: str) -> str:
    return get_session_files(directory)[0]


async def get_client(as_bot: bool = False) -> TelegramClient:
    os.makedirs(SESSIONS_DIRECTORY, exist_ok=True)

    if len(os.listdir(SESSIONS_DIRECTORY)) == 0:
        backend_logger.error("You need to create at least one session by register_session()")
        backend_logger.info("Creating session")
        try:
            client = await register_session(as_bot=as_bot)
        except ValueError as e:
            backend_logger.error(f'Error in get_client function: {e}')
            return
    else:
        session = get_first_session_file(SESSIONS_DIRECTORY)
        if as_bot:
            client = await TelegramClient(
                session=session, 
                api_id=API_ID, 
                api_hash=API_HASH
            ).start(BOT_TOKEN)
        else:
            client = TelegramClient(
                session=session, 
                api_id=API_ID, 
                api_hash=API_HASH
            )

    return client