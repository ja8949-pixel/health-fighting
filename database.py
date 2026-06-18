"""SQLAlchemy 모델 및 DB 연결 설정"""

import os
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, DateTime, ForeignKey, func, text
)
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker

# Vercel 서버리스 환경에서는 /tmp만 쓰기 가능
_IS_VERCEL = bool(os.getenv("VERCEL"))
_default_db = "sqlite:////tmp/workouts.db" if _IS_VERCEL else "sqlite:///./workouts.db"
DATABASE_URL = os.getenv("DATABASE_URL", _default_db)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    birth_date = Column(String(10), nullable=False)   # YYYY-MM-DD
    phone4 = Column(String(4), nullable=False)         # 전화번호 뒷 4자리
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    workouts = relationship("Workout", back_populates="user", cascade="all, delete-orphan")


class Workout(Base):
    __tablename__ = "workouts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    date = Column(String(10), nullable=False, index=True)
    total_minutes = Column(Integer, nullable=True)
    total_time_str = Column(String(20), nullable=True)
    photo_url = Column(String(500), nullable=True)
    raw_text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="workouts")
    details = relationship("WorkoutDetail", back_populates="workout", cascade="all, delete-orphan")


class WorkoutDetail(Base):
    __tablename__ = "workout_details"

    id = Column(Integer, primary_key=True, index=True)
    workout_id = Column(Integer, ForeignKey("workouts.id", ondelete="CASCADE"), nullable=False)
    exercise_name = Column(String(100), nullable=False)
    sets = Column(Integer, nullable=True)
    duration = Column(Integer, nullable=True)
    exercise_type = Column(String(20), default="weight")
    muscle_group = Column(String(20), nullable=True)    # 등/가슴/어깨·팔/하체/복근/유산소/기타
    target_detail = Column(String(200), nullable=True)  # 광배근, 승모근 등 상세
    order_index = Column(Integer, default=0)

    workout = relationship("Workout", back_populates="details")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    Base.metadata.create_all(bind=engine)
    # 기존 테이블에 새 컬럼 추가 (마이그레이션)
    migrations = [
        "ALTER TABLE workouts ADD COLUMN user_id INTEGER",
        "ALTER TABLE workout_details ADD COLUMN muscle_group VARCHAR(20)",
        "ALTER TABLE workout_details ADD COLUMN target_detail VARCHAR(200)",
    ]
    with engine.connect() as conn:
        for stmt in migrations:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass  # 이미 존재하는 컬럼이면 무시
