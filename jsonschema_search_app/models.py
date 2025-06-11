from sqlalchemy import Column, Integer, String
from sqlalchemy.dialects.postgresql import JSONB

from .database import Base

class SearchData(Base):
    __tablename__ = "search_data"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    data = Column(JSONB, nullable=False)
