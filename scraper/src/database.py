import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.models import Base

# .env 또는 환경변수에서 DB 정보 가져오기
DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
DB_NAME = os.getenv("POSTGRES_DB", "market_db")
DB_HOST = os.getenv("DB_CONTAINER", "db") # 도커 내부망 통신
DB_PORT = "5432" # 내부 포트

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)