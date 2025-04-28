import asyncio
from datetime import datetime, timedelta
from itertools import groupby, tee


import pytz
from tzlocal import get_localzone


from database.db_logic import DataBaseAPI
from intervals import respawn_intervals

from utils.time_helper import user_to_system_tz, system_to_user_tz, seconds_to_hh_mm
from utils.logger import backend_logger

db = DataBaseAPI()
moscow_tz = pytz.timezone("Europe/Moscow")
system_tz = pytz.timezone(str(get_localzone()))


async def init_db():
    res1 = await db.create_tables()
    res2 =  await db.initialize_boss_respawns()
    if not res1 or not res2:
        backend_logger.error(f"Error: cannot init db")


async def calculate_respawn_datetime(kill_datetime, now, boss_name, is_new_epoch: bool = False):
    if kill_datetime > now: # It was yesterday
        kill_datetime -= timedelta(days=1)

    if is_new_epoch:
        interval_raw = respawn_intervals[boss_name][1]
    else:
        interval_raw = respawn_intervals[boss_name][0]
    interval = timedelta(hours=interval_raw)                                         
    respawn_datetime = kill_datetime + interval
    return respawn_datetime, interval


async def set_timer(
        chat_id: str, 
        boss_name: str, 
        kill_time_str: str | None, 
        user_id: str, 
        event, 
        is_new_epoch: bool = False,
    ):
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
        boss_name,
        is_new_epoch,
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
    time_to_notification = wait_seconds - 180
    remaining_formatted_time = seconds_to_hh_mm(wait_seconds)
    
    if is_new_epoch:
        await asyncio.sleep(time_to_notification)
        if not await db._get_timer(timer):
            backend_logger.info(f"Timer {timer.timer_id} was already deleted")
            return

        await event.reply(f"‼️ Босс **{boss_name}** возродится через 3 минуты, будьте готовы!")
        backend_logger.success(
            f"In chat {chat_id} User {user_id} response "
            f"notification from timer {timer.timer_id}"
        )

        await asyncio.sleep(180)
        if not await db._get_timer(timer):
            backend_logger.info(f"Timer {timer.timer_id} was already deleted")
            return
        
        await event.reply(f"✅ Босс **{boss_name}** возродился, скорее бегите его убивать!")
        backend_logger.success(
            f"In chat {chat_id} User {user_id} response "
            f"notification from timer {timer.timer_id}"
        )

        timer_id = timer.timer_id
        res = await db.delete_timer(
            user_id=user_id,
            timer_id=timer_id,
        )
        if not res:
            await event.reply("❌ Проблема с доступом в базу данных")
            backend_logger.error(
                "Trouble with db when deleting timer into 'set_timer' function with is_new_epoch"
            )
            return
        
        backend_logger.success(
            f"In chat {chat_id} User {user_id} automatically deleted timer {timer_id}"
        )
        return



    while True:
        await event.reply(
            f"✅ Установлен таймер :\n{system_to_user_tz(timer.respawn_time)} — "
            f"**{timer.boss_name}** ({remaining_formatted_time}) — `{timer.timer_id}`\n"
        )
        
        if time_to_notification > 0:
            await asyncio.sleep(time_to_notification)
            if not await db._get_timer(timer):
                backend_logger.info(f"Timer {timer.timer_id} was already deleted")
                return

            await event.reply(f"‼️ Босс **{boss_name}** возродится через 3 минуты, будьте готовы!")
            backend_logger.success(
                f"In chat {chat_id} User {user_id} response "
                f"notification from timer {timer.timer_id}"
            )

            await asyncio.sleep(180)
        else:
            await asyncio.sleep(wait_seconds)
        
        if not await db._get_timer(timer):
            backend_logger.info(f"Timer {timer.timer_id} was already deleted")
            return
        
        await event.reply(f"✅ Босс **{boss_name}** возродился, скорее беги его убивать!")
        backend_logger.success(
            f"In chat {chat_id} User {user_id} response "
            f"notification from timer {timer.timer_id}"
        )
        fake_dt = respawn_datetime + timedelta(days=7)
        await db.update_timer(timer, fake_dt)
        await asyncio.sleep(60)
        if not await db._get_timer(timer):
            backend_logger.info(f"Timer {timer.timer_id} was already deleted")
            return

        respawn_datetime += interval + timedelta(seconds=60)
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
        time_to_notification = wait_seconds - 180
        remaining_formatted_time = seconds_to_hh_mm(wait_seconds)


async def get_bosses(chat_id: str, user_id: str, event):    
    text_strings = list()
    text_strings.append(f'Список всех боссов\n')

    for boss in respawn_intervals:
        respawn_time = respawn_intervals[boss][0]
        boss_name = str(boss)
        
        text_strings.append(f"`{boss_name:<20}` | {respawn_time} hours")
        text_message = "\n".join(text_strings)

    await event.reply(text_message)
    backend_logger.success(f"In chat {chat_id} User {user_id} got boss-list")


async def delete_timer(user_id: str, chat_id: str, timer_id: str, event):
    res = await db.delete_timer(user_id, timer_id)

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


async def delete_all_timers(chat_id: str, user_id: str, event):
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


async def get_chat_timers(chat_id: str, timer_numbers: int, user_id: str, event):
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
    text_strings.append("**Ближайшие возрождения**\n")
    now = system_tz.localize(datetime.now())

    for timer in timers:
        remaining_time = (timer.respawn_time - now).total_seconds()
        remaining_formatted_time = seconds_to_hh_mm(remaining_time)

        text_strings.append(
        f"{system_to_user_tz(timer.respawn_time)} — "
        f"**{timer.boss_name}** ({remaining_formatted_time}) — `{timer.timer_id}`\n"
        )

    text_message = "\n".join(text_strings)
    await event.reply(text_message)
    backend_logger.success(
        f"In chat {chat_id} User {user_id} got {len(timers)} chat timers"
    )


async def epochs_timers_start(chat_id: str, user_id: str, event):
    bosses = await db.get_all_boss_respawns(user_id=user_id)
    if bosses is False:
        await event.reply(f"❌ Проблема с доступом в базу данных")
        backend_logger.error("Trouble with db when running 'epochs_timers_start' function")
        return

    tasks = []
    for boss in bosses:

        tasks.append(asyncio.create_task(set_timer(
            chat_id=chat_id,
            boss_name=boss.boss_name,
            kill_time_str=None,
            user_id=user_id,
            event=event,
            is_new_epoch=True,
        )))
    
    await event.reply(
        f"✅ Таймеры на респаун всех боссов успешно установлены. Подробную информацию "
        f"можно получить по команде `/get`\n"
    )
    await asyncio.gather(*tasks)



async def start_chat(chat_id: str, chat, participants, event):
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

# Осталось убрать юзеров и оптимизировать запрос эпохи к БД