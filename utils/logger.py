from loguru import logger
import sys
import os

logger.remove()

os.makedirs("logs", exist_ok=True)

backend_logger = logger.bind(name="BACKEND")
logger.add(
    sys.stdout,
    format="<white>BACKEND</white>"
           " | <white>{time:YYYY-MM-DD HH:mm:ss}</white>"
           " | <level>{level: <8}</level>"
           " - <white><b>{message}</b></white>",
    filter=lambda record: record["extra"].get("name") == "BACKEND"
)
logger.add(
    "logs/backend.log",
    format="<white>BACKEND</white>"
           " | <white>{time:YYYY-MM-DD HH:mm:ss}</white>"
           " | <level>{level: <8}</level>"
           " - <white><b>{message}</b></white>",
    rotation="100 MB",
    filter=lambda record: record["extra"].get("name") == "BACKEND"
)

database_logger = logger.bind(name="DATABASE")
logger.add(
    sys.stdout,
    format="<white>DATABASE</white>"
           " | <white>{time:YYYY-MM-DD HH:mm:ss}</white>"
           " | <level>{level: <8}</level>"
           " - <white><b>{message}</b></white>",
    filter=lambda record: record["extra"].get("name") == "DATABASE"
)
logger.add(
    "logs/database.log",
    format="<white>DATABASE</white>"
           " | <white>{time:YYYY-MM-DD HH:mm:ss}</white>"
           " | <level>{level: <8}</level>"
           " - <white><b>{message}</b></white>",
    rotation="100 MB",
    filter=lambda record: record["extra"].get("name") == "DATABASE"
)
