import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.core.model import Base

DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
DB_NAME = os.getenv("POSTGRES_DB", "market_db")
DB_HOST = os.getenv("DB_CONTAINER", "db")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# pool_pre_ping=True: 연결을 사용하기 전에 DB가 살아있는지 체크 (끊김 방지)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    """FastAPI Depends()에 주입할 DB 세션 제너레이터"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() # API 요청이 끝나면 반드시 세션을 반납