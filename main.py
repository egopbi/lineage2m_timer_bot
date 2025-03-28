import asyncio
from datetime import datetime, timedelta
from itertools import groupby, tee
import signal
import sys

import pytz
from telethon import events
from telethon.tl.functions.bots import SetBotCommandsRequest, SetBotMenuButtonRequest
from telethon.tl.types import BotCommand, BotCommandScopeDefault, BotMenuButtonCommands
from tzlocal import get_localzone

from database.db_logic import DataBaseAPI
from intervals import respawn_intervals

from utils.time_helper import user_to_system_tz, system_to_user_tz, seconds_to_hh_mm
from utils.logger import backend_logger
from utils.get_client import get_client



db = DataBaseAPI()
moscow_tz = pytz.timezone("Europe/Moscow")
system_tz = pytz.timezone(str(get_localzone()))


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


async def init_db():
    res1 = await db.create_tables()
    res2 =  await db.initialize_boss_respawns()
    if not res1 or not res2:
        backend_logger.error(f"Error: cannot init db")


async def calculate_respawn_datetime(kill_datetime, now, user_id, boss_name):
    if kill_datetime > now: # It was yesterday
        kill_datetime -= timedelta(days=1)

    interval_raw = await db.get_boss_respawn(user_id=user_id, boss_name=boss_name)
    interval = timedelta(hours=interval_raw)                                         
    respawn_datetime = kill_datetime + interval
    return respawn_datetime, interval


async def main():
    try:
        client = await get_client(as_bot=True)
        backend_logger.success("Bot successfully started")
        
        async def set_bot_commands():
            commands = [
                BotCommand(command="start", description="Запуск бота"),
                BotCommand(command="set", description="Установка таймера"),
                BotCommand(command="get", description="Получение списка таймеров беседы"),
                BotCommand(command="get_my", description="Получение личного списка таймеров"),
                BotCommand(command="delete", description="Удаление таймера по ID"),
                BotCommand(command="bosses", description="Список всех доступных боссов"),
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
        async def get_bosses(event):
            chat_id = str(event.chat_id)
            user_id = str(event.sender_id)
            backend_logger.info(f"In chat {chat_id} User {user_id} used `{event.message.message}`")
            
            text_strings = list()
            text_strings.append(f'Список всех боссов\n')
        
            for boss in respawn_intervals:
                respawn_time = respawn_intervals[boss]
                boss_name = str(boss)
                
                text_strings.append(f"`{boss_name:<20}` | {respawn_time} hours")
                text_message = "\n".join(text_strings)

            await event.reply(text_message)
            backend_logger.success(f"In chat {chat_id} User {user_id} got boss-list")


        @client.on(events.NewMessage(pattern=r'/set\s+(.+?)\s*(\d{1,2}:\d{2})?$'))
        async def set_timer(event):
            chat_id = str(event.chat_id)
            boss_name = str(event.pattern_match.group(1)).title()
            kill_time_str = event.pattern_match.group(2)
            user_id = str(event.sender_id)
            
            backend_logger.info(f"In chat {chat_id} User {user_id} used `{event.message.message}`")

            if boss_name not in respawn_intervals:
                await event.reply(f"❌ Босс **{boss_name}** не найден.")
                backend_logger.error(
                    f"In chat {chat_id} User {user_id} used wrong command "
                    f"`{event.message.message}`. "
                    f"Error: non-existed Boss name"
                )
                return
        
            if kill_time_str is None:
                now = moscow_tz.localize(datetime.now())
                kill_datetime = now
            else:
                try:
                    kill_time = datetime.strptime(kill_time_str, "%H:%M").time()
                except ValueError:
                    await event.reply("❌ Неверный формат времени. Используй ЧЧ:ММ.")
                    backend_logger.error(
                        f"In chat {chat_id} User {user_id} used wrong command "
                        f"`{event.message.message}`. "
                        f"Error: wrong time format"
                    )
                    return
                else:
                    now = system_tz.localize(datetime.now())
                    kill_datetime = user_to_system_tz(datetime.combine(now.date(), kill_time))

            respawn_datetime, interval = await calculate_respawn_datetime(
                kill_datetime, 
                now, 
                user_id, 
                boss_name
            )        

            if respawn_datetime < now:
                await event.reply(
                    f"❌ Босс **{boss_name}** уже возродился, скорее беги его убивать!"
                )
                backend_logger.error(
                    f"In chat {chat_id} User {user_id} tried to create expired timer"
                )
                return
            
            timer = await db.add_timer(
                user_id=user_id,
                chat_id=chat_id, 
                boss_name=boss_name, 
                respawn_time=respawn_datetime
            )
            if not timer:
                await event.reply("❌ Проблема с доступом в базу данных")
                backend_logger.error(
                    "Trouble with db when adding timer into 'add_timer' function"
                )
                return
            backend_logger.success(
                f"In chat {chat_id} User {user_id} created timer {timer.timer_id}"
            )

            remaining_time = respawn_datetime - now
            wait_seconds = remaining_time.total_seconds()
            remaining_formatted_time = seconds_to_hh_mm(wait_seconds)

            while True:
                await event.reply(
                    f"✅ Таймер на респаун босса **{timer.boss_name}** установлен на "
                    f"{system_to_user_tz(respawn_datetime)}\nID таймера: `{timer.timer_id}`\n"
                    f"Оставшееся время {remaining_formatted_time}"
                )

                await asyncio.sleep(wait_seconds)
                if not await db._get_timer(timer):
                    backend_logger.info(f"Timer {timer.timer_id} was already deleted")
                    return
                
                await event.reply(f"✅ Босс **{boss_name}** возродился, скорее беги его убивать!")
                backend_logger.success(
                    f"In chat {chat_id} User {user_id} response "
                    f"notification from timer {timer.timer_id}"
                )
                await asyncio.sleep(300)
                if not await db._get_timer(timer):
                    backend_logger.info(f"Timer {timer.timer_id} was already deleted")
                    return
                
                respawn_datetime += interval + timedelta(seconds=300)
                timer = await db.update_timer(timer, respawn_datetime)
                if not timer:
                    await event.reply("❌ Проблема с доступом в базу данных")
                    backend_logger.error(
                        "Trouble with db when updating timer into 'add_timer' function"
                    )
                    return
    
                backend_logger.success(
                    f"In chat {chat_id} User {user_id} automatically updated timer {timer.timer_id}"
                )
                wait_seconds = interval.total_seconds()
                remaining_formatted_time = seconds_to_hh_mm(wait_seconds)


        @client.on(events.NewMessage(pattern=r'^/delete(?!_)\s*([\w-]+)$'))
        async def delete_timer(event):
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

            backend_logger.info(
                f"In chat {chat_id} User {user_id} use `{event.message.message}`"
            )
            res = await db.delete_timer(user_id, chat_id, timer_id)

            if res == 'alien':
                await event.reply("❌ Нельзя удалить чужой таймер")
                backend_logger.error(
                    f"In chat {chat_id} User {user_id} tried to delete alien timer"
                )
                return

            if not res:
                await event.reply("❌ Проблема с доступом в базу данных")
                backend_logger.error("Trouble with db when running 'delete_timer' function")
                return

            await event.reply(f"✅ Таймер с ID {timer_id} удален")
            backend_logger.success(f"In chat {chat_id} User {user_id} "
                                   f"succesfully deleted timer {timer_id}")


        @client.on(events.NewMessage(pattern=r'/delete_all_timers'))
        async def delete__all_timers(event):
            chat_id = str(event.chat_id)
            user_id = str(event.sender_id)

            backend_logger.info(
                f"In chat {chat_id} User {user_id} use `{event.message.message}`"
            )
            res = await db.delete_all_timers_in_chat(chat_id)

            if res == 'no_timers':
                await event.reply("❌ В беседе нет таймеров")
                backend_logger.error(
                    f"In chat {chat_id} User {user_id} tried to "
                    f"delete all_timers but ther were gone"
                )
                return

            if not res:
                await event.reply(f"❌ Проблема с доступом в базу данных")
                backend_logger.error("Trouble with db when running 'delete_timer' function")
                return

            await event.reply("✅ Все таймеры успешно удалены")
            backend_logger.success(f"In chat {chat_id} User {user_id} "
                                   f"succesfully deleted all timers")
            

        @client.on(events.NewMessage(pattern=r'^/get(?!_my)(?:@\w+)?(?:\s+(\d+))?$'))
        async def get_chat_timers(event):
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

            user_info = await db.get_userinfo(user_id)
            nickname = user_info[0]
            firstname = user_info[1]


            if timer_numbers < 1:
                timers = await db.get_all_chat_timers(user_id, chat_id)
            else:
                timers = await db.get_chat_timers(user_id, chat_id, timer_numbers)
            
            if timers is False:
                await event.reply("❌ Проблема с доступом в базу данных")
                backend_logger.error("Trouble with db when running 'get_chat_timers' function")
                return
            
            if len(timers) < 1:
                await event.reply("В данный момент нет ни одного активного таймера")
                backend_logger.success(f"In chat {chat_id} User {user_id} got 0 chat timers")
                return
        
            text_strings = list()
            text_strings.append("**Ближайшие возрождения**")
            now = moscow_tz.localize(datetime.now())
            

            for user_id, timer_group in groupby(timers, key=lambda x: x.user_id):
                timer_group, timer_group_copy = tee(timer_group)
                example_timer = list(timer_group_copy)[0]
                user_id = example_timer.user_id
                userinfo = await db.get_userinfo(user_id)
                nickname, firstname = userinfo[0], userinfo[1]
                text_strings.append(
                    f"\n-------------------------------------\n"
                    f"Участник: **{firstname}** ({nickname})"
                )

                for timer in timer_group:
                    remaining_time = (timer.respawn_time - now).total_seconds()
                    remaining_formatted_time = seconds_to_hh_mm(remaining_time)

                    text_strings.append(
                        f"ID таймера: `{timer.timer_id}`\nБосс **{timer.boss_name}**\n"
                        f"Время возрождения: {system_to_user_tz(timer.respawn_time)}\n"
                        f"Оставшееся время: {remaining_formatted_time}"
                    )
        
            text_message = "\n".join(text_strings)
            await event.reply(text_message)
            backend_logger.success(
                f"In chat {chat_id} User {user_id} got {len(timers)} chat timers"
            )
        
        
        @client.on(events.NewMessage(pattern=r'/get_my(?:\s+(\d+))?'))
        async def get_user_timers(event):
            chat_id = str(event.chat_id)
            timer_numbers = event.pattern_match.group(1)
            user_id = str(event.sender_id)

            if timer_numbers is None:
                timer_numbers = 0
                
            try:
                timer_numbers = int(timer_numbers)
            except ValueError:
                await event.reply(
                    "❌ После `/get_my` укажи количество ближайших по времени "
                    "возрождений, которое хочешь видеть"
                    )
                backend_logger.error(
                    f"In chat {chat_id} User {user_id} used wrong command "
                    f"`{event.message.message}`. "
                    f"Error: not int timer_numbers"
                )
                return

            backend_logger.info(f"In chat {chat_id} User {user_id} used `{event.message.message}`")

            user_info = await db.get_userinfo(user_id)
            nickname = user_info[0]
            firstname = user_info[1]


            if timer_numbers < 1:
                timers = await db.get_all_user_timers(user_id, chat_id)
            else:
                timers = await db.get_user_timers(user_id, chat_id, timer_numbers)
            
            if timers is False:
                await event.reply(f"❌ Проблема с доступом в базу данных")
                backend_logger.error("Trouble with db when running 'get_user_timers' function")
                return
            
            if len(timers) < 1:
                await event.reply("В данный момент нет ни одного активного таймера")
                backend_logger.success(f"In chat {chat_id} User {user_id} got 0 personal timers")
                return
        
            text_strings = list()
            text_strings.append(
                f"Участник: **{firstname}** ({nickname})\n"
                f"**Ближайшие возрождения**"
                )
            now = moscow_tz.localize(datetime.now())
            
            for timer in timers:
                remaining_time = (timer.respawn_time - now).total_seconds()
                remaining_formatted_time = seconds_to_hh_mm(remaining_time)

                text_strings.append(
                    f"ID таймера: `{timer.timer_id}`\nБосс **{timer.boss_name}**\n"
                    f"Время возрождения: {system_to_user_tz(timer.respawn_time)}\n"
                    f"Оставшееся время: {remaining_formatted_time}"
                )
        
            text_message = "\n\n".join(text_strings)
            await event.reply(text_message)
            backend_logger.success(
                f"In chat {chat_id} User {user_id} "
                f"got {len(timers)} personal timers"
            )


        @client.on(events.NewMessage(pattern=r'^/start(@\w+)?$'))
        async def start_command(event):
            chat_id = str(event.chat_id)
            chat = await event.get_chat()
            participants = await client.get_participants(chat)
            for p in participants:
                user_id = str(p.id)
                nickname = p.username
                firstname = p.first_name
                res = await db.add_userinfo(user_id, nickname, firstname)
                if not res:
                    backend_logger.error(f"Trouble with db when adding User {user_id}")
                    return

            backend_logger.success(f"In chat {chat_id} users was added to Database")

            await event.reply(
                "Привет! Я помогу тебе не проспать сражение с ботом и "
                "уведомлю тебя о его возрождении. Используй команду /help"
                " чтобы посмотреть доступные команды."
            )


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
                "/get_my\n- выводит все личные активные таймеры в беседе\n\n"
                "-------------------------------------\n"
                "/delete <id_таймера>\n- удаляет таймер с определенным ID\n\n"
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
        backend_logger.error("Bot task cancelled. Disconnecting...")

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
