from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey

Base = declarative_base()

class BossRespawn(Base):
    __tablename__ = "boss_respawns"

    boss_name = Column(String, primary_key=True)
    time_to_respawn = Column(Integer)

    timers = relationship("Timer", back_populates="boss_respawns")


class Timer(Base):
    __tablename__ = "timers"

    timer_id = Column(String(36), primary_key=True, index=True)
    chat_id = Column(String, index=True)
    user_id = Column(String, index=True)
    boss_name = Column(String, ForeignKey("boss_respawns.boss_name"))
    respawn_time = Column(DateTime(timezone=True))

    boss_respawns = relationship("BossRespawn", back_populates="timers")


class User(Base):
    __tablename__ = "users"

    user_id = Column(String, primary_key=True, index=True)
    user_nickname = Column(String)
    user_firstname = Column(String)
