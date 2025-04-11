from datetime import datetime

from sqlalchemy.orm import declarative_base, relationship, Mapped, mapped_column
from sqlalchemy import DateTime, ForeignKey

Base = declarative_base()

class BossRespawn(Base):
    __tablename__ = "boss_respawns"

    boss_name: Mapped[str] = mapped_column(primary_key=True)
    time_to_respawn: Mapped[int]
    epoch_time_to_respawn: Mapped[int] 

    timers = relationship("Timer", back_populates="boss_respawns")


class Timer(Base):
    __tablename__ = "timers"

    timer_id: Mapped[str] = mapped_column(primary_key=True, index=True)
    chat_id: Mapped[str] = mapped_column(index=True)
    boss_name: Mapped[str] = mapped_column(ForeignKey("boss_respawns.boss_name"))
    respawn_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    boss_respawns = relationship("BossRespawn", back_populates="timers")


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(primary_key=True, index=True)
    user_nickname: Mapped[str]
    user_firstname: Mapped[str]