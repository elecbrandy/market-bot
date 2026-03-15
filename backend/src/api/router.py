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
    answer = generate_answer(request.messages)
    return ChatResponse(answer=answer)

# backend/src/api/router.py 에 추가

@router.get("/embed/status")
def get_embedding_status():
    """벡터 DB에 저장된 문서 개수와 샘플 데이터를 확인합니다."""
    try:
        from src.service.embedding import vector_store
        
        # 전체 개수 확인
        count = vector_store._collection.count()
        
        # 최신 데이터 5개만 가져오기 (메타데이터 포함)
        sample = vector_store.get(limit=5)
        
        return {
            "total_count": count,
            "sample_titles": [m.get("title") for m in sample.get("metadatas", [])],
            "sample_content_preview": [c[:50] for c in sample.get("documents", [])]
        }
    except Exception as e:
        return {"error": str(e)}