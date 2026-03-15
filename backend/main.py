from fastapi import FastAPI
from contextlib import asynccontextmanager

from src.core.database import init_db
from src.api.router import router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 서버 시작 시 데이터베이스 테이블 생성
    init_db()
    yield
    # 서버 종료 시 필요한 로직이 있다면 여기에 추가

app = FastAPI(
    title="Market RAG API",
    description="뉴스 데이터를 기반으로 답변을 생성하는 RAG API",
    version="1.0.0",
    lifespan=lifespan
)

# 라우터 등록
app.include_router(router)

@app.get("/")
def root():
    return {"message": "Market RAG API is running!"}