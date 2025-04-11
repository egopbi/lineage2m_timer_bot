import asyncio
import signal
import sys

from telethon import events
from telethon.tl.functions.bots import SetBotCommandsRequest, SetBotMenuButtonRequest
from telethon.tl.types import BotCommand, BotCommandScopeDefault, BotMenuButtonCommands

from backend_logic import (
    set_timer, 
    init_db, 
    get_bosses, 
    delete_timer, 
    delete_all_timers,
    get_chat_timers,
    epochs_timers_start,
    start_chat,
)

from utils.logger import backend_logger
from utils.get_client import get_client



# db = DataBaseAPI()
# moscow_tz = pytz.timezone("Europe/Moscow")
# system_tz = pytz.timezone(str(get_localzone()))


async def shutdown(signal_name):
    backend_logger.info(f"Received exit signal {signal_name}")
    tasks = [t for t in asyncio.all_tasks() if not t.done() and t is not asyncio.current_task()]

    backend_logger.info("Canceling all pending tasks...")
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    backend_logger.info("All tasks canceled")

    backend_logger.info("Shutting down event loop...")
    loop = asyncio.get_running_loop()
    loop.stop()


async def main():
    try:
        client = await get_client(as_bot=True)
        backend_logger.success("Bot successfully started")
        
        async def set_bot_commands():
            commands = [
                BotCommand(command="start", description="Запуск бота"),
                BotCommand(command="set", description="Установка таймера"),
                BotCommand(command="get", description="Получение списка таймеров беседы"),
                BotCommand(command="delete", description="Удаление таймера по ID"),
                BotCommand(command="bosses", description="Список всех доступных боссов"),
                BotCommand(command="all_start", description="Запуск таймеров на всех босов"),
                BotCommand(command="help", description="Описание команд бота"),
                BotCommand(command="info", description="Информация о боте"),
            ]
            await client(SetBotCommandsRequest(
                scope=BotCommandScopeDefault(), 
                lang_code='en', 
                commands=commands
            ))
            await client(SetBotMenuButtonRequest(user_id='self', button=BotMenuButtonCommands()))
            return True
        

        if await set_bot_commands():
            backend_logger.success("Bot commands was successfully setted")


        @client.on(events.NewMessage(pattern=r'/bosses'))
        async def get_bosses_command(event):
            chat_id = str(event.chat_id)
            user_id = str(event.sender_id)
            backend_logger.info(f"In chat {chat_id} User {user_id} used `{event.message.message}`")
            await get_bosses(chat_id=chat_id, user_id=user_id, event=event)


        @client.on(events.NewMessage(pattern=r'/set\s+(.+?)\s*(\d{1,2}:\d{2})?$'))
        async def set_timer_command(event):
            chat_id = str(event.chat_id)
            boss_name = str(event.pattern_match.group(1)).title()
            kill_time_str = event.pattern_match.group(2)
            user_id = str(event.sender_id)
            
            backend_logger.info(f"In chat {chat_id} User {user_id} used `{event.message.message}`")
            await set_timer(
                chat_id=chat_id, 
                boss_name=boss_name, 
                kill_time_str=kill_time_str, 
                user_id=user_id,
                event=event,
            )

        @client.on(events.NewMessage(pattern='/all_start'))
        async def epochs_timers_start_command(event):
            chat_id = str(event.chat_id)
            user_id = str(event.sender_id)
            await epochs_timers_start(
                chat_id=chat_id,
                user_id=user_id,
                event=event
            )
        

        @client.on(events.NewMessage(pattern=r'^/delete(?!_)\s*([\w-]+)$'))
        async def delete_timer_command(event):
            chat_id = str(event.chat_id)
            user_id = str(event.sender_id)

            try:
                timer_id = str(event.pattern_match.group(1))
            except ValueError:
                await event.reply("❌ Введите целое значение")
                backend_logger.error(
                    f"In chat {chat_id} User {user_id} used wrong command "
                    f"`{event.message.message}`. "
                    f"Error: not str timer_id"
                )
                return

            backend_logger.info(
                f"In chat {chat_id} User {user_id} use `{event.message.message}`"
            )

            await delete_timer(
                user_id=user_id,
                chat_id=chat_id,
                timer_id=timer_id,
                event=event,
            )


        @client.on(events.NewMessage(pattern=r'/delete_all_timers'))
        async def delete__all_timers_command(event):
            chat_id = str(event.chat_id)
            user_id = str(event.sender_id)

            backend_logger.info(
                f"In chat {chat_id} User {user_id} use `{event.message.message}`"
            )
            await delete_all_timers(chat_id=chat_id, user_id=user_id, event=event)
            

        @client.on(events.NewMessage(pattern=r'^/get(?!_my)(?:@\w+)?(?:\s+(\d+))?$'))
        async def get_chat_timers_command(event):
            chat_id = str(event.chat_id)
            timer_numbers = event.pattern_match.group(1)
            user_id = str(event.sender_id)

            if timer_numbers is None:
                timer_numbers = 0
                
            try:
                timer_numbers = int(timer_numbers)
            except ValueError:
                await event.reply(
                    "❌ После `/get` укажи количество ближайших по времени "
                    "возрождений, которое хочешь видеть"
                    )
                backend_logger.error(
                    f"In chat {chat_id} User {user_id} used wrong command "
                    f"`{event.message.message}`. "
                    f"Error: not int timer_numbers"
                )
                return

            backend_logger.info(f"In chat {chat_id} User {user_id} used `{event.message.message}`")
            await get_chat_timers(
                chat_id=chat_id, 
                timer_numbers=timer_numbers, 
                user_id=user_id, 
                event=event
            )
        

        @client.on(events.NewMessage(pattern=r'^/start(@\w+)?$'))
        async def start_command(event):
            chat_id = str(event.chat_id)
            chat = await event.get_chat()
            participants = await client.get_participants(chat)
            await start_chat(chat_id=chat_id, chat=chat, participants=participants, event=event)


        @client.on(events.NewMessage(pattern=r'^/info(@\w+)?$'))
        async def info_command(event):
            await event.reply(
                "Бот был создан в качестве помощника для игры lineage2m. "
                "Создатель: @egopbi a.k.a Eeee Gorka"
            )


        @client.on(events.NewMessage(pattern=r'^/help(@\w+)?$'))
        async def help_command(event):
            help_text = (
                "**Доступные команды:**\n\n"
                "/bosses \n- Выводит список всех боссов с возможностью быстро скопировать имя\n\n"
                "-------------------------------------\n"
                "/set <имя_босса> <время_убийства>\n- устанавливает таймер на босса по его имени. "
                "Формат времени ЧЧ:ММ (если время убийства не указано, "
                "то учитывается как текущее)\n\n"
                "-------------------------------------\n"
                "/get <кол-во выводимых таймеров>\n- выводит "
                "определенное кол-во активных таймеров в беседе\n\n"
                "-------------------------------------\n"
                "/get\n- выводит все активные таймеры в беседе\n\n"
                "-------------------------------------\n"
                "/delete <id_таймера>\n- удаляет таймер с определенным ID\n\n"
                "-------------------------------------\n"
                "/all_start\n- запускает таймеры на всех боссов\n\n"
                "-------------------------------------\n"
                "/info\n- Информация о боте\n\n"
                "-------------------------------------\n"
                "/help\n- список команд"
            )
            await event.reply(help_text)

        await client.run_until_disconnected()
        backend_logger.success("Bot successfully working")

    except Exception as e:
        backend_logger.error(f"Error during bot execution: {e}")
    
    except asyncio.CancelledError:
        backend_logger.info("Bot task cancelled. Disconnecting...")

    finally:
        if client:
            try:
                await client.disconnect()
                backend_logger.info("Tg_client successfully disconnected")
            except Exception as e:
                backend_logger.error(f"Error when disconnecting tg_client: {e}")


async def run_bot():
    loop = asyncio.get_running_loop()

    for s in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(s, lambda s=s: loop.create_task(shutdown(s.name)))
   
    await init_db()

    while True:
        try:
            await main()
        except ConnectionError:
            backend_logger.error("ConnectionError. Restarting in 30 seconds...")
            asyncio.sleep(30)
        else:
            backend_logger.info("Main finished without ConnectionError, exiting run_bot loop.")
            break



if __name__ == "__main__":
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        backend_logger.info("Bot terminated via KeyboardInterrupt")
        sys.exit(0)
    except Exception as e:
        backend_logger.error(f"Unexpected error during startup: {str(e)}")
        sys.exit(1)
