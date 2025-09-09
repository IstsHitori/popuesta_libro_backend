# app/models.py
from sqlalchemy import Column, Integer, String
from .db import Base

class User(Base):
    __tablename__ = "users"
    id       = Column(Integer, primary_key=True, index=True)
    document = Column(String, unique=True, index=True, nullable=False)
    name     = Column(String, nullable=False)
    school   = Column(String, nullable=False)           # validamos en la API
    gender   = Column(String, nullable=False, default="Masculino")  # NUEVO
    money    = Column(String, nullable=False, default="0")          # NUEVO
    level    = Column(Integer, default=1)
    score    = Column(Integer, default=0)
