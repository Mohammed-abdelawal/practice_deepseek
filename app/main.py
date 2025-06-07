# app/main.py

from fastapi import FastAPI

from app.api import chat


app = FastAPI(title="Acme Support Bot", version="0.1.0", debug=True)

# 3. Mount routers
app.include_router(chat.router, prefix="/chat", tags=["chat"])


@app.get("/health")
async def health():
    return {"status": "ok"}
