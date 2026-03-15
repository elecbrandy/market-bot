from pydantic import BaseModel

class EmbedResponse(BaseModel):
    message: str
    processed_count: int

class ChatResponse(BaseModel):
    answer: str
