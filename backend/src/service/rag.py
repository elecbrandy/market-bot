from typing import Annotated, Sequence, TypedDict
from langchain_core.documents import Document
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from src.service.embedding import vector_store

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)

# State) 정의
class GraphState(TypedDict):
    """
    그래프 실행 중에 유지되는 상태를 정의하는 TypedDict.
    - messages:
        - 대화 기록을 저장하는 리스트
        - 프론트엔드에서 넘어온 dict 형태의 대화 기록을 LangChain 메시지로 변환하여 저장
    - context:
        - 검색 노드에서 ChromaDB로부터 가져온 관련 뉴스 기사들의 내용을 저장하는 문자열
        - 답변 생성 노드에서 시스템 프롬프트에 포함되어 LLM이 참고할 수 있도록 함
    """
    messages: Annotated[Sequence[BaseMessage], add_messages]
    context: str


# 검색 노드 (Retrieve)
def retrieve_node(state: GraphState):
    # 가장 최근 사용자 질문 가져오기
    recent_msg = state["messages"][-1].content
    
    # ChromaDB 검색
    results: list[Document] = vector_store.similarity_search(recent_msg, k=5)
    if not results:
        return {"context": "관련된 뉴스 기사를 찾을 수 없습니다."}
        
    # 출처(URL, 제목)를 포함해 context 구성
    context_parts = []
    for doc in results:
        title = doc.metadata.get('title', '제목 없음')
        url = doc.metadata.get('url', '#')
        content = doc.page_content
        context_parts.append(f"Source: [{title}]({url})\nContent: {content}")
    
    context = "\n\n---\n\n".join(context_parts)
    context = context.replace("{", "{{").replace("}", "}}")  # ← join 이후에
    return {"context": context}

# 답변 생성 노드
def generate_node(state: GraphState):

    # 프론트엔드에서 넘어온 dict 형태의 대화 기록을 LangChain 메시지로 변환하여 상태에 저장
    messages = state["messages"]
    context = state.get("context", "")
    
    system_prompt = (
        "You are an expert assistant specializing in Japanese anime news.\n"
        "Answer the user's question based ONLY on the provided news articles below.\n"
        "If the answer cannot be found in the articles, say '제공된 뉴스에서 관련 정보를 찾을 수 없습니다.' and do not make up information.\n"
        "Always respond in Korean unless the user asks otherwise.\n"
        "At the end of your answer, list the referenced articles in markdown format as:\n"
        "#### 참고 기사\n- [기사 제목](링크)\n\n"
        f"Context:\n{context}"
    )
    
    # 프롬프트 템플릿에 시스템 메시지와 전체 대화 기록(MessagesPlaceholder) 삽입
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder(variable_name="messages"),
    ])
    
    chain = prompt | llm
    response = chain.invoke({"messages": messages})
    
    # 상태 업데이트용 메시지 반환
    return {"messages": [response]}

# 조건부 노드 (Conditional)
def should_generate(state: GraphState):
    return "generate"

# 4. 그래프(Workflow) 구성
workflow = StateGraph(GraphState)
workflow.add_node("retrieve", retrieve_node)
workflow.add_node("generate", generate_node)

# 노드 연결
workflow.add_edge(START, "retrieve")
workflow.add_conditional_edges(
    "retrieve",
    should_generate,
    {
        "generate": "generate",
        "end": END
    }
)
workflow.add_edge("generate", END)

# 앱 컴파일
rag_app = workflow.compile()

# API에서 호출할 최종 함수
def generate_answer(messages_dicts: list) -> str:
    if not messages_dicts:
        return "질문을 입력해주세요."
        
    langchain_messages = []
    for msg in messages_dicts:
        if msg["role"] == "user":
            langchain_messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            langchain_messages.append(AIMessage(content=msg["content"]))
    
    result = rag_app.invoke({"messages": langchain_messages})
    
    # 마지막 메시지가 AI 메시지인지 확인하는 방어 코드
    last_msg = result["messages"][-1]
    if isinstance(last_msg, AIMessage):
        return last_msg.content
    else:
        return "죄송합니다. 답변을 생성하지 못했습니다. (검색된 내용이 없습니다)"