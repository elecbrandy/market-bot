# Market News RAG System

- 뉴스 기사를 수집하고, 이를 기반으로 사용자의 질의에 답변하는 RAG 시스템입니다.
- FastAPI 기반의 백엔드와 Gradio 프론트엔드, 그리고 벡터 DB를 Docker Compose로 통합하여 구성했습니다.

<br>

## 기술 스택

- **Language:** Python 3.11
- **Backend:** FastAPI, Uvicorn, SQLAlchemy
- **Frontend:** Gradio
- **AI / RAG:** LangChain, LangGraph, OpenAI (`gpt-4o-mini`, `text-embedding-3-small`)
- **Database:** PostgreSQL (RDB), ChromaDB (VectorDB)

<br>

## 환경 설정

``` ini
POSTGRES_USER=market_user
POSTGRES_PASSWORD=market_password
POSTGRES_DB=market_db
POSTGRES_PORT=5432
DB_CONTAINER=db

VECTOR_DB_CONTAINER=vector_db
VECTOR_DB_PORT=8000

BACKEND_CONTAINER=backend
BACKEND_PORT=8000

FRONTEND_CONTAINER=frontend
FRONTEND_PORT=3000

# OpenAI API Key
OPENAI_API_KEY=your-openai-api-key

```

<br>

## 실행 방법

> 현재 개발용 서술

| 명령어 | 설명 | 비고 |
| --- | --- | --- |
| **`make up`** | 전체 컨테이너 백그라운드 실행 | 기본 시작 명령어 |
| **`make down`** | 전체 컨테이너 중지 | 데이터(볼륨)는 유지 |
| **`make rebuild`** | 전체 이미지 재빌드 후 시작 | 인프라 설정 변경 시 사용 |
| **`make logs-backend`** | 백엔드(FastAPI) 로그 확인 | 실시간 오류 디버깅용 |
| **`make restart-backend`** | 백엔드 컨테이너만 재시작 | 상태 이상 및 멈춤 해결용 |
| **`make rebuild-backend`** | 백엔드 컨테이너 재빌드 | `requirements.txt` 패키지 추가 시 |
| **`make scrape`** | 뉴스 스크래퍼 실행 | DB에 기사 적재 |
| **`make embed`** | 미처리 기사 벡터 임베딩 | **최초 1회 실행 요망 (API 비용 발생)** |
| **`make flush-db`** | RDB(PostgreSQL) 데이터 초기화 | 스크래핑 로직 수정 후 재수집 시 |
| **`make flush-vector`** | 벡터DB(ChromaDB) 데이터 초기화 | 임베딩 모델/청크 사이즈 변경 시 |
| **`make flush-all`** | RDB 및 벡터DB 데이터 모두 초기화 | 전체 데이터 파이프라인 재구축 시 |
| **`make clean`** | 사용 중지된 컨테이너/네트워크 삭제 | 시스템 자원 확보 |
| ~~**`make fclean`**~~ | ~~시스템 완전 초기화 (위험)~~ | ~~모든 컨테이너, 이미지, 로컬 데이터 삭제~~ |

