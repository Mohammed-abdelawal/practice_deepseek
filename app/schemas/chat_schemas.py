# app/schemas/chat_schemas.py

from pydantic import BaseModel


class ChatRequest(BaseModel):
    session_id: str
    user_message: str


class ChatResponse(BaseModel):
    assistant_reply: str
