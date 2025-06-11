from typing import Any, Dict
from pydantic import BaseModel

class SearchDataCreate(BaseModel):
    name: str
    data: Dict[str, Any]

class SearchDataOut(SearchDataCreate):
    id: int

    class Config:
        orm_mode = True
