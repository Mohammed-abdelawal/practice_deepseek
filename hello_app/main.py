from fastapi import FastAPI

app = FastAPI(title="Hello App", version="0.1.0")

@app.get("/hello")
async def say_hello():
    return {"message": "Hello from the new app"}

@app.get("/health")
async def health():
    return {"status": "ok"}
