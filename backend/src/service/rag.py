from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from src.service.embedding import vector_store

# llm 초기화
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)

def generate_answer(query: str) -> str:
    """사용자 질문에 대한 답변 생성"""
    
    # ChromaDB에서 유사한 문서 검색
    results = vector_store.similarity_search(query, k=5)
    
    if not results:
        return "관련된 뉴스 기사를 찾을 수 없습니다."

    # 검색된 문서에서 콘텐츠와 메타데이터 추출
    # doc.content -> doc.page_content 로 변경
    context = "\n\n".join([f"Title: {doc.metadata.get('title', 'No Title')}\nContent: {doc.page_content}" for doc in results])

    # 프롬프트 템플릿 생성
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", "You are a helpful assistant that provides answers based on the following news articles:\n{context}"),
        ("user", "{query}")
    ])

    # 프롬프트에 컨텍스트와 사용자 질문 삽입
    prompt = prompt_template.format(context=context, query=query)

    # LLM을 사용하여 답변 생성
    answer = llm.invoke(prompt)

    return answer.content.strip()
