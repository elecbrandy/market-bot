import streamlit as st
import requests
import os

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8080")

# 페이지 기본 설정
st.set_page_config(page_title="Anime RAG Chatbot", page_icon="🎌", layout="wide")

# 세션 상태 초기화 (대화 기록 저장용)
if "messages" not in st.session_state:
    st.session_state.messages = []

# ==========================================
# 사이드바 (관리 기능)
# ==========================================
with st.sidebar:
    st.header("⚙️ 관리")
    
    # 데이터 임베딩 버튼
    if st.button("데이터 임베딩 실행", type="primary", use_container_width=True):
        with st.spinner("임베딩 진행 중... 잠시만 기다려주세요."):
            try:
                response = requests.post(f"{BACKEND_URL}/embed/run", timeout=120)
                response.raise_for_status()
                count = response.json().get("processed_count", 0)
                st.success(f"✅ 임베딩 완료! (처리된 문서 수: {count}개)")
            except Exception as e:
                st.error(f"❌ 임베딩 오류: {str(e)}")
    
    st.divider()
    
    # 대화 초기화 버튼
    if st.button("대화 초기화", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# ==========================================
# 메인 화면
# ==========================================
st.title("tmp Anime RAG Chatbot")
st.markdown("최신 애니메이션 뉴스를 기반으로 답변합니다.")

# 기존 대화 기록 렌더링
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 사용자 입력 처리
if prompt := st.chat_input("질문을 입력하세요... (Enter로 전송)"):
    # 1. 사용자 메시지 화면에 출력 및 상태 저장
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. 챗봇 응답 대기 및 출력
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        message_placeholder.markdown("답변을 생성하고 있습니다... ⏳")
        
        try:
            # Backend API 호출 (현재까지의 모든 대화 기록 전송)
            response = requests.post(
                f"{BACKEND_URL}/chat",
                json={"messages": st.session_state.messages},
                timeout=30
            )
            response.raise_for_status()
            answer = response.json().get("answer", "응답을 파싱할 수 없습니다.")
            
            # 응답 출력 및 상태 저장
            message_placeholder.markdown(answer)
            st.session_state.messages.append({"role": "assistant", "content": answer})
            
        except requests.exceptions.Timeout:
            error_msg = "오류: 백엔드 응답 시간이 초과되었습니다."
            message_placeholder.error(error_msg)
            st.session_state.messages.append({"role": "assistant", "content": error_msg})
        except Exception as e:
            error_msg = f"오류가 발생했습니다: {str(e)}"
            message_placeholder.error(error_msg)
            st.session_state.messages.append({"role": "assistant", "content": error_msg})
