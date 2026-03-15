import chromadb
from sqlalchemy.orm import Session
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from src.core.model import News
from src.core.config import settings

# ChromaDB 클라이언트와 OpenAI 임베딩 모델 초기화
chroma_client = chromadb.HttpClient(host="vector_db", port=settings.VECTOR_DB_PORT)
embeddings = OpenAIEmbeddings(model="text-embedding-3-small", openai_api_key=settings.OPENAI_API_KEY)

vector_store = Chroma(
    client=chroma_client,
    collection_name="market_news_embeddings",
    embedding_function=embeddings
)

def run_embedding(db: Session) -> int:
    """RDB에서 임베딩이 필요한 뉴스 데이터를 가져와서 ChromaDB에 저장"""
    
    # RDB에서 임베딩이 필요한 뉴스 데이터 조회
    new_articles = db.query(News).filter(News.is_embedded == False).all()
    if not new_articles:
        return 0

    documents = []
    for article in new_articles:
        # 뉴스 데이터를 Document 객체로 변환
        doc = Document(
            page_content=article.content,
            metadata={
                "id": str(article.id),
                "source": article.source,
                "keyword": article.keyword,
                "title": article.title,
                "url": article.url,
                "published_date": str(article.published_date)
            }
        )
        documents.append(doc)

    # ChromaDB에 임베딩 저장
    vector_store.add_documents(documents)

    # RDB 상태 업데이트
    for article in new_articles:
        article.is_embedded = True
    db.commit()

    # 처리된 문서 수 반환
    return len(documents)

