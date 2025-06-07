# app/api/chat.py
from fastapi import APIRouter, HTTPException
from app.services.chat_service import process_user_message
from app.schemas.chat_schemas import ChatRequest, ChatResponse

router = APIRouter()


@router.post("/", response_model=ChatResponse)
async def chat_endpoint(payload: ChatRequest):
    try:
        assistant_reply, _ = await process_user_message(
            session_id=payload.session_id,
            user_message=payload.user_message,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return ChatResponse(assistant_reply=assistant_reply)
