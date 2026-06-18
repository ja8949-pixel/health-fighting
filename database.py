"""SQLAlchemy 모델 및 DB 연결 설정"""

import os
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, DateTime, ForeignKey, func, text
)
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker

_IS_VERCEL = bool(os.getenv("VERCEL"))
_default_db = "sqlite:////tmp/workouts.db" if _IS_VERCEL else "sqlite:///./workouts.db"
DATABASE_URL = os.getenv("DATABASE_URL", _default_db)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

IS_POSTGRES = DATABASE_URL.startswith("postgresql")
connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    password = Column(String(4), nullable=False, server_default="0000")
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
    muscle_group = Column(String(20), nullable=True)
    target_detail = Column(String(200), nullable=True)
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

    with engine.connect() as conn:
        # ── users 테이블 스키마 마이그레이션 ──────────────────────────────────
        # 구 스키마(birth_date NOT NULL, phone4 NOT NULL) → 신 스키마(name+password)
        _migrate_users(conn)

        # ── 기타 컬럼 추가 마이그레이션 ───────────────────────────────────────
        for stmt in [
            "ALTER TABLE workouts ADD COLUMN user_id INTEGER",
            "ALTER TABLE workout_details ADD COLUMN muscle_group VARCHAR(20)",
            "ALTER TABLE workout_details ADD COLUMN target_detail VARCHAR(200)",
        ]:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass


def _migrate_users(conn):
    """users 테이블을 name+password 스키마로 마이그레이션"""
    is_sqlite = "sqlite" in DATABASE_URL

    if is_sqlite:
        # SQLite는 ALTER COLUMN 불가 → 테이블 재생성으로 해결
        cols = [r[1] for r in conn.execute(text("PRAGMA table_info(users)")).fetchall()]
        if "birth_date" in cols:
            # password 컬럼이 없으면 먼저 추가
            if "password" not in cols:
                try:
                    conn.execute(text("ALTER TABLE users ADD COLUMN password VARCHAR(4) DEFAULT '0000'"))
                    conn.commit()
                except Exception:
                    pass
            # 신규 테이블 생성 → 데이터 복사 → 교체
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS _users_new (
                    id   INTEGER PRIMARY KEY,
                    name VARCHAR(50) NOT NULL,
                    password VARCHAR(4) NOT NULL DEFAULT '0000',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("""
                INSERT OR IGNORE INTO _users_new (id, name, password, created_at)
                SELECT id, name, COALESCE(password,'0000'), created_at FROM users
            """))
            conn.execute(text("DROP TABLE users"))
            conn.execute(text("ALTER TABLE _users_new RENAME TO users"))
            conn.commit()
    else:
        # PostgreSQL: 컬럼 제약 완화 + password 컬럼 추가
        for stmt in [
            "ALTER TABLE users ALTER COLUMN birth_date DROP NOT NULL",
            "ALTER TABLE users ALTER COLUMN phone4 DROP NOT NULL",
            "ALTER TABLE users ADD COLUMN password VARCHAR(4) DEFAULT '0000'",
        ]:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass
