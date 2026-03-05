import gradio as gr

def predict(input_text: str) -> str:
    return f"응답: {input_text}"

demo = gr.Interface(fn=predict, inputs="text", outputs="text")

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=3000)