import asyncio
import os
import time
from datetime import datetime, timedelta

from telethon import TelegramClient, events
from telethon.tl.functions.bots import SetBotCommandsRequest, SetBotMenuButtonRequest
from telethon.tl.types import BotCommand, BotCommandScopeDefault, BotMenuButtonCommands

from dotenv import load_dotenv

from intervals import respawn_intervals
from utils.get_sesions import get_session_files

load_dotenv()

API_ID = int(os.getenv('API_ID'))
API_HASH = str(os.getenv('API_HASH')).strip("'")
BOT_TOKEN = str(os.getenv('BOT_TOKEN')).strip("'")
SESSIONS_DIRECTORY = os.getenv('SESSIONS_DIRECTORY')

session = get_session_files(SESSIONS_DIRECTORY)[0]
client = TelegramClient(session=session, api_id=API_ID, api_hash=API_HASH).start(bot_token=BOT_TOKEN)

active_timers = {}

async def set_bot_commands():
    commands = [
        BotCommand(command="start", description="Запуск бота"),
        BotCommand(command="set", description="Установка таймера"),
        BotCommand(command="get", description="Получение списка таймеров"),
        BotCommand(command="delete", description="Удаление таймера по ID"),
        BotCommand(command="bosses", description="Список всех доступных боссов"),
        BotCommand(command="help", description="Описание команд бота"),
        BotCommand(command="info", description="Информация о боте"),
    ]

    await client(SetBotCommandsRequest(scope=BotCommandScopeDefault(), lang_code='en', commands=commands))
    await client(SetBotMenuButtonRequest(user_id='self', button=BotMenuButtonCommands()))


@client.on(events.NewMessage(pattern=r'/bosses'))
async def get_bosses(event):
    text_strings = list()
    text_strings.append(f'Список команд для всех боссов\n')
    for boss in respawn_intervals:
        respawn_time = respawn_intervals[boss]
        boss_name = str(boss)
        
        text_strings.append(f"`{boss_name:<20}` | {respawn_time} hours")
        text_message = "\n".join(text_strings)

    await event.reply(text_message, parse_mode='md')


@client.on(events.NewMessage(pattern=r'/set\s+(.+?)\s+(\d{1,2}:\d{2})?$'))
async def set_respawn(event):
    boss_name = str(event.pattern_match.group(1)).title()
    kill_time_str = event.pattern_match.group(2)

    if boss_name not in respawn_intervals:
        await event.reply(f"❌ Босс **{boss_name}** не найден.")
        return
    
    if kill_time_str is None:
        kill_datetime = datetime.now()
    else:
        try:
            kill_time = datetime.strptime(kill_time_str, "%H:%M").time()
        except ValueError:
            await event.reply("❌ Неверный формат времени. Используй ЧЧ:ММ.")
            return
        
        now = datetime.now()
        kill_datetime = datetime.combine(now.date(), kill_time)
    # Убийство было вчера
    if kill_datetime > now:
        kill_datetime -= timedelta(days=1)
                                               
    respawn_datetime = kill_datetime + timedelta(hours=respawn_intervals[boss_name])

    if respawn_datetime < now:
        await event.reply(f"❌ Босс **{boss_name}** уже возродился, скорее беги его убивать!")
        return
    else:        
        timer_id = 0
        while timer_id in list(active_timers.keys()):
            timer_id += 1
        
        active_timers[timer_id] = {'boss': boss_name, 'start': now, 'end': respawn_datetime}
        await event.reply(
            f"✅ Таймер на респаун босса **{boss_name}** установлен на "
            f"{respawn_datetime.strftime('%H:%M')}\nID таймера: {timer_id}"
        )

        wait_seconds = (respawn_datetime - now).total_seconds()
        await asyncio.sleep(wait_seconds)
        active_timers.pop(timer_id)
        await event.reply(f"✅ Босс **{boss_name}** возродился, скорее беги его убивать!")


@client.on(events.NewMessage(pattern=r'/delete\s+(\d+)'))
async def del_timer(event):
    try:
        timer_id = int(event.pattern_match.group(1))
    except ValueError:
        await event.reply(f"❌ Введите целое значение")

    active_timers.pop(timer_id)
    await event.reply(f"✅ Таймер с ID **{timer_id}** удален")


@client.on(events.NewMessage(pattern=r'/get(?:\s+(\d+))?'))
async def get_respawns(event):
    boss_numbers = event.pattern_match.group(1)
    if boss_numbers is None:
        boss_numbers = len(active_timers)

    try:
        boss_numbers = int(boss_numbers)
    except ValueError:
        await event.reply("❌ После `/get` укажи количество ближайших по времени возрождений, "
                          "которое хочешь видеть")
        return
    
    if boss_numbers == 0:
        boss_numbers = len(active_timers)

    if boss_numbers > len(active_timers):
        await event.reply("❌ Введенное количество запрашиваемых таймеров больше общего количества\n"
                          "Вывожу все текущие таймеры")
        boss_numbers = len(active_timers)

    text_strings = list()
    text_strings.append(f"**Ближайшие возрождения**")

    if len(active_timers) < 1:
        await event.reply("В данный момент нет ни одного активного таймера")
        return

    copy_active_timers = active_timers.copy()
    for i in copy_active_timers:
        copy_active_timers[i]["remaining_time"] = (copy_active_timers[i]["end"] - \
                                                   copy_active_timers[i]["start"]).total_seconds()
    sorted_timers = list(copy_active_timers.items())
    sorted_timers.sort(key=lambda x: x[1]["remaining_time"])

    for i in range(boss_numbers):
        timer = sorted_timers[i]
        timer_id = timer[0]
        boss_name = str(timer[1]["boss"])
        time_for_respawn = time.strftime("%H:%M", time.gmtime(int(timer[1]["remaining_time"])))
        
        text_strings.append(f"ID таймера: {timer_id}\nБосс **{boss_name.upper()}**\nОставшееся время: {time_for_respawn}")
    
    text_message = "\n\n".join(text_strings)
    await event.reply(text_message)


@client.on(events.NewMessage(pattern='/start'))
async def start_command(event):
    await event.reply("Привет! Я помогу тебе не проспать сражение с ботом и \
                      уведомлю тебя о его возрождении. Используй команду /help чтобы посмотреть доступные команды.")

@client.on(events.NewMessage(pattern='/info'))
async def info_command(event):
    await event.reply("Бот был создан в качестве помощника для игры lineage2m. Создатель: @egopbi a.k.a Eeee Gorka")

@client.on(events.NewMessage(pattern='/help'))
async def help_command(event):
    help_text = (
        "**Доступные команды:**\n\n"
        f"/bosses \n- Выводит список всех боссов с возможностью быстро скопировать имя\n\n"
        "---------------------------------------\n"
        f"/set <имя_босса> <время_убийства>\n- устанавливает таймер на босса по его имени. "
        f"Формат времени ЧЧ:ММ\n\n"
        "---------------------------------------\n"
        f"/get <кол-во выводимых таймеров>\n- выводит определенное кол-во активных таймеров\n\n"
        "---------------------------------------\n"
        f"/get\n- выводит все активные таймеры\n\n"
        "---------------------------------------\n"
        f"/delete <id_таймера>\n- удаляет таймер с определенным ID\n\n"
         "---------------------------------------\n"
       f"/info\n- Информация о боте\n\n"
        "---------------------------------------\n"
        f"/help\n- список команд"
    )
    await event.reply(help_text)


with client:
    client.loop.run_until_complete(set_bot_commands())
    client.run_until_disconnected()