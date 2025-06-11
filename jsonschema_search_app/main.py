from fastapi import FastAPI, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from .database import engine, Base, get_session
from .models import SearchData
from .schemas import SearchDataCreate, SearchDataOut

app = FastAPI(title="JSON Schema Search App", version="0.1.0")


@app.on_event("startup")
async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@app.post("/items", response_model=SearchDataOut)
async def create_item(
    payload: SearchDataCreate, session: AsyncSession = Depends(get_session)
):
    item = SearchData(name=payload.name, data=payload.data)
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


@app.get("/search", response_model=list[SearchDataOut])
async def search_items(path: str, session: AsyncSession = Depends(get_session)):
    query = select(SearchData).where(func.jsonb_path_exists(SearchData.data, path))
    result = await session.execute(query)
    return result.scalars().all()


@app.get("/health")
async def health():
    return {"status": "ok"}
