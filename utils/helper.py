from datetime import datetime, timedelta
import pytz
from tzlocal import get_localzone

moscow_tz = pytz.timezone("Europe/Moscow")
system_tz = pytz.timezone(str(get_localzone()))


def user_to_system_tz(user_time: datetime):
    user_time = moscow_tz.localize(user_time)
    system_time = user_time.astimezone(system_tz)
    return system_time

def system_to_user_tz(system_time: datetime):
    user_time = system_time.astimezone(moscow_tz)
    return user_time.strftime("%H:%M")

def seconds_to_hh_mm(seconds: timedelta):
    hours, remainder = divmod(seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{int(hours):02d}:{int(minutes):02d}"
