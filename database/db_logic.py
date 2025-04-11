import uuid
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from sqlalchemy.sql import func

from config import DATABASE_URL, DATABASE_ECHO
from intervals import respawn_intervals
from database.models import Base, Timer, BossRespawn, User
from utils.logger import database_logger


class DataBaseAPI():
    def __init__(self):
        self.engine = create_async_engine(DATABASE_URL, echo=DATABASE_ECHO, future=True)

        self.async_session = sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

    async def create_tables(self) -> bool:
        async with self.engine.begin() as conn: # Работает напрямую с соединением, а не с сессией, так как не ORM
            try:
                await conn.run_sync(Base.metadata.create_all)
                database_logger.success("All metadata was created")
                return True
            except Exception as e:
                database_logger.error(f"Error while create tables: {str(e)}")
                return False
                


    async def initialize_boss_respawns(self) -> bool:
        async with self.async_session() as session:
            try:
                result = await session.execute(select(BossRespawn))
                bosses = result.scalars().all()

                if len(bosses) == 0:
                    for boss_name, times in respawn_intervals.items():
                        time_to_respawn = times[0]
                        epoch_time_to_respawn = times[1]
                        respawn = BossRespawn(
                            boss_name=boss_name, 
                            time_to_respawn=time_to_respawn,
                            epoch_time_to_respawn=epoch_time_to_respawn,
                        )
                        session.add(respawn)
                    await session.commit()
                    database_logger.success(f"Table '{BossRespawn.__tablename__}' was updated")
                else:
                    database_logger.info(f"Table '{BossRespawn.__tablename__}' was already filled")
                return True
            except Exception as e:
                database_logger.error(f"Error while initializing boss respawns: {str(e)}")
                return False


    async def get_boss_respawn(self, user_id, boss_name) -> int:
        async with self.async_session() as session:
            try:
                result = await session.execute(
                    select(BossRespawn.time_to_respawn)
                    .filter(BossRespawn.boss_name == boss_name)
                )
                database_logger.success(f"User {user_id} got boss respawn info")
                return result.scalar_one_or_none()
            except Exception as e:
                database_logger.error(
                    f"Error while getting boss respawn by user {user_id}: {str(e)}"
                )
                return False
                

    async def get_all_boss_respawns(self, user_id) -> list[BossRespawn]:
        async with self.async_session() as session:
            try:
                result = await session.execute(select(BossRespawn))
                database_logger.success(f"User {user_id} got boss_respawns info")

                return result.scalars().all()
            except Exception as e:
                database_logger.error(
                    f"Error while getting all boss respawns by user {user_id}: {str(e)}"
                )
                return False



    async def add_timer(self, user_id, chat_id, boss_name, respawn_time) -> Timer:
        async with self.async_session() as session:
            async with session.begin():
                try:
                    result = await session.execute(
                        select(Timer).filter(
                            Timer.chat_id == chat_id,
                            Timer.boss_name == boss_name
                        )
                    )
                    old_timer: Timer = result.scalars().first()

                    if old_timer:
                        database_logger.info(
                            f"In db there was the timer {old_timer.timer_id} "
                            f"with same parameters. Deleting old timer..."
                        )

                        await session.delete(old_timer)
                        database_logger.success(
                            f"User {user_id} autodeleted old timer with timer_id: {old_timer.timer_id}"
                        )


                except Exception as e:
                    database_logger.error(
                        f"Error while deleting timer {old_timer.timer_id} before setting"
                        f" new one by user {user_id}: {str(e)}"
                    )
                    return False

                try:
                    timer_id = str(uuid.uuid4())[:10]
                    timer = Timer(
                        timer_id=timer_id, 
                        chat_id=chat_id, 
                        boss_name=boss_name, 
                        respawn_time=respawn_time
                    )
                    session.add(timer)
                    database_logger.success(f"User {user_id} add timer with timer_id: {timer_id}")
                    await session.commit()
                    return timer
                
                except Exception as e:
                    database_logger.error(f"Error while adding timer by user {user_id}: {str(e)}")
                    return False
                
        
    async def update_timer(self, timer: Timer, new_respawn_time) -> Timer:
        async with self.async_session() as session:
            async with session.begin():
                try:
                    timer.respawn_time = new_respawn_time
                    session.add(timer)
                    await session.commit()
                    database_logger.success(
                        f"Automatically updated timer with timer_id: {timer.timer_id}"
                    )
                    return timer
                except Exception as e:
                    database_logger.error(
                        f"Error while updating timer {timer.timer_id}: {str(e)}"
                    )
                    return False


    async def get_all_chat_timers(self, user_id, chat_id) -> list[Timer]:
        async with self.async_session() as session:
            try:
                await self._delete_expired_timers(chat_id)
                result = await session.execute(
                    select(Timer)
                    .filter(Timer.chat_id == chat_id)
                    .order_by(
                        Timer.respawn_time
                    )
                )
                timers = result.scalars().all()
                database_logger.success(f"User {user_id} got all chat timers")
                
                return timers
            except Exception as e:
                database_logger.error(
                    f"Error while getting all chat timers by user {user_id}: {str(e)}"
                )
                return False
            

    async def get_chat_timers(self, user_id, chat_id, count) -> list[Timer]:
        async with self.async_session() as session:
            try:
                await self._delete_expired_timers(chat_id)
                total_count_result = await session.execute(
                    select(func.count())
                    .select_from(Timer).filter(Timer.chat_id == chat_id)
                )
                total_count = total_count_result.scalar()

                if count < total_count:
                    result = await session.execute(
                        select(Timer)
                        .filter(Timer.chat_id == chat_id)
                        .order_by(Timer.respawn_time)
                        .limit(count)
                    )
                    timers = result.scalars().all()
                else:
                    timers = await self.get_all_chat_timers(user_id, chat_id)

                database_logger.success(f"User {user_id} got {count} chat nearest timers")
                return timers
            except Exception as e:
                database_logger.error(
                    f"Error while getting chat nearest timers by user {user_id}: {str(e)}"
                )
                return False


    async def delete_timer(self, user_id, timer_id) -> bool:
        async with self.async_session() as session:
            async with session.begin():
                try:
                    result = await session.execute(
                        select(Timer).filter(
                            Timer.timer_id == timer_id
                        )
                    )
                    timer = result.scalars().first()

                    if not timer:
                        database_logger.error(
                            f"User {user_id} tried to "
                            f"delete non-existent timer_id: {timer_id}"
                        )
                        return False

                    await session.delete(timer)
                    await session.commit()
                    database_logger.success(
                        f"User {user_id} deleted timer with timer_id: {timer_id}"
                    )
                    return True
                
                except Exception as e:
                    database_logger.error(
                        f"Error while deleting timer {timer_id} by user {user_id}: {str(e)}"
                    )
                    return False
    
    
    async def delete_all_timers_in_chat(self, chat_id) -> bool:
        async with self.async_session() as session:
            async with session.begin():
                try:
                    result = await session.execute(
                        select(Timer)
                        .filter(Timer.chat_id == chat_id)
                    )
                    timers = result.scalars().all()
                    
                    if not timers:
                        database_logger.info(f"In chat {chat_id} there is no timers")
                        return "no_timers"

                    for timer in timers:
                        await session.delete(timer)
                
                    await session.commit()
                    database_logger.success(f"In chat {chat_id} all timers was deleted")
                    return True
                except Exception as e:
                    database_logger.error(
                        f"Error while deleting all timers in chat {chat_id}: {str(e)}"
                    )
                    return False


    async def _get_timer(self, timer: Timer) -> Timer:
        async with self.async_session() as session:
            async with session.begin():
                try:
                    result = await session.execute(
                        select(Timer)
                        .filter(Timer.timer_id == timer.timer_id)
                    )
                    existing_timer = result.scalars().first()
                    
                    if not existing_timer:
                        database_logger.info(f"Timer {timer.timer_id} was deleted")
                        return False
                    
                    database_logger.success(
                        f"Timer {timer.timer_id} is present in Database"
                    )
                    return timer
                except Exception as e:
                    database_logger.error(
                        f"Error while updating timer {timer.timer_id}: {str(e)}"
                    )
                    return False



    async def _delete_expired_timers(self, chat_id) -> bool:
        async with self.async_session() as session:
            try:
                now = datetime.now() - timedelta(seconds=5)

                result = await session.execute(
                    select(Timer)
                    .filter(Timer.respawn_time < now)
                )
                expired_timers = result.scalars().all()
                
                if not expired_timers:
                    database_logger.info(f"In chat {chat_id} There is no expired timers in Database")

                for timer in expired_timers:
                        timer_id = timer.timer_id
                        await session.delete(timer)
                        database_logger.info(
                            f"Expired timer {timer_id} was deleted"
                        )
                
                await session.commit()
                return True
            
            except Exception as e:
                await session.rollback()
                database_logger.error(f"Error while deleting expired timers {str(e)}")
                return False


    async def add_userinfo(self, user_id, user_nickname, user_firstname) -> User:
        async with self.async_session() as session:
            async with session.begin():
                try:
                    result = await session.execute(
                        select(User).filter(
                            User.user_id == user_id
                        )
                    )
                    old_user = result.scalars().first()
                    
                    if old_user:
                        database_logger.info(f"User {user_id} is already in Database")
                        return old_user

                    user = User(
                        user_id=user_id,
                        user_nickname = user_nickname,
                        user_firstname=user_firstname
                    )
                    session.add(user)
                    database_logger.success(f"User {user_id} was added to Database")
                    return user
                except Exception as e:
                    database_logger.error(f"Error while adding userinfo of user {user_id}: {str(e)}")
                    return False


    async def get_userinfo(self, user_id) -> User:
        async with self.async_session() as session:
            try:
                result = await session.execute(
                    select(User.user_nickname, User.user_firstname)
                    .filter(User.user_id == user_id)
                )
                user_info = result.first()
                
                if user_info:
                    database_logger.success(f"User {user_id} was retrieved from Database")
                    return user_info

                database_logger.error(f"There is no user {user_id} in Database")    
                return False
            except Exception as e:
                database_logger.error(f"Error while getting userinfo: {str(e)}")
                return False
