import gradio as gr
import requests
import os

# Docker Compose 내부 네트워크를 사용하므로 컨테이너 이름(backend)으로 통신합니다.
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")

def predict(input_text: str) -> str:
    """사용자 질문을 백엔드로 보내 답변을 받아오는 함수"""
    if not input_text.strip():
        return "질문을 입력해주세요."
    
    try:
        response = requests.post(
            f"{BACKEND_URL}/chat",
            json={"query": input_text},
            timeout=30
        )
        response.raise_for_status()
        
        data = response.json()
        return data.get("answer", "응답을 파싱할 수 없습니다.")
        
    except Exception as e:
        return f"오류가 발생했습니다: {str(e)}"

def trigger_embedding() -> str:
    """백엔드의 임베딩 API를 호출하는 함수"""
    try:
        # 임베딩은 시간이 좀 걸릴 수 있으므로 timeout을 넉넉히 줍니다.
        response = requests.post(f"{BACKEND_URL}/embed/run", timeout=120)
        response.raise_for_status()
        
        data = response.json()
        count = data.get("processed_count", 0)
        return f"✅ 임베딩 완료! (새롭게 처리된 뉴스 문서 수: {count}개)"
        
    except Exception as e:
        return f"❌ 임베딩 중 오류 발생: {str(e)}"

# 화면 레이아웃 구성 (gr.Blocks 활용)
with gr.Blocks(title="Market RAG Chatbot") as demo:
    gr.Markdown("# 📈 Market RAG AI Chatbot")
    gr.Markdown("수집된 뉴스 데이터를 기반으로 답변을 제공합니다. 데이터가 추가되었다면 먼저 **임베딩 실행** 버튼을 눌러주세요.")
    
    with gr.Row():
        # 왼쪽 단: 챗봇 영역
        with gr.Column(scale=3):
            chatbot_output = gr.Textbox(label="RAG AI 응답", lines=10, interactive=False)
            user_input = gr.Textbox(label="질문 입력", placeholder="예: 최근 미국 금리 인상과 관련된 뉴스가 있나요?")
            
            with gr.Row():
                clear_btn = gr.ClearButton([user_input, chatbot_output], value="초기화")
                submit_btn = gr.Button("질문 전송", variant="primary")
        
        # 오른쪽 단: 관리/기능 영역
        with gr.Column(scale=1):
            gr.Markdown("### ⚙️ 시스템 관리")
            embed_btn = gr.Button("데이터 임베딩 실행", variant="secondary")
            embed_output = gr.Textbox(label="임베딩 처리 결과", lines=2, interactive=False)

    # 이벤트 연결
    submit_btn.click(predict, inputs=user_input, outputs=chatbot_output)
    user_input.submit(predict, inputs=user_input, outputs=chatbot_output) # 엔터키 지원
    
    embed_btn.click(trigger_embedding, inputs=None, outputs=embed_output)

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=3000)
    