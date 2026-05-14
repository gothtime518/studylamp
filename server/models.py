from sqlalchemy import create_engine, Column, String, Boolean, DateTime, JSON, Integer, Text, Float
from sqlalchemy.orm import DeclarativeBase, Session
from datetime import datetime
import os

DB_PATH = os.environ.get("STUDYLAMP_DB", "./studylamp.db")
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


class Base(DeclarativeBase):
    pass


class StudyEvent(Base):
    __tablename__ = "study_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(String, nullable=False, index=True)
    event_type = Column(String, nullable=False, index=True)
    timestamp = Column(String, nullable=False)
    details = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)


class HomeworkAnalysis(Base):
    __tablename__ = "homework_analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(String, nullable=False, index=True)
    subject = Column(String, nullable=False)
    ocr_text = Column(Text, default="")
    errors = Column(JSON, default=list)
    suggestions = Column(JSON, default=list)
    score_estimate = Column(Integer, nullable=True)
    summary = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class Child(Base):
    """多孩子支持：一个家长可绑定多个孩子设备"""
    __tablename__ = "children"

    id = Column(Integer, primary_key=True, autoincrement=True)
    parent_openid = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)          # 孩子昵称
    device_id = Column(String, nullable=False, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PointsLedger(Base):
    """积分流水，每次学习结束后写入"""
    __tablename__ = "points_ledger"

    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(String, nullable=False, index=True)
    date = Column(String, nullable=False)          # YYYY-MM-DD
    points = Column(Integer, nullable=False)
    reason = Column(String, nullable=False)        # "study_time" | "good_posture" | "streak"
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    Base.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
