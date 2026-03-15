from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.api.request import ChatRequest
from src.api.response import ChatResponse, EmbedResponse
from src.service.embedding import run_embedding
from src.service.rag import generate_answer

router = APIRouter()

@router.post("/embed/run", response_model=EmbedResponse)
def trigger_embedding(db: Session = Depends(get_db)):
    """RDB에 있는 새로운 뉴스를 ChromaDB로 임베딩합니다."""
    count = run_embedding(db)
    return EmbedResponse(message="Embedding process completed.", processed_count=count)

@router.post("/chat", response_model=ChatResponse)
def chat_with_rag(request: ChatRequest):
    """사용자의 질문을 받아 RAG 기반의 답변을 반환합니다."""
    answer = generate_answer(request.query)
    return ChatResponse(answer=answer)