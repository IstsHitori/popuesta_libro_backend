# app/db.py
import os
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

# 1) Si viene DATABASE_URL, la usamos tal cual (útil en Render)
env_url = os.getenv("DATABASE_URL")

if env_url:
    # En Render, por ej: sqlite:////var/data/app.db
    DB_URL = env_url
else:
    # 2) Local: construimos UNA ruta ABSOLUTA segura
    #    Quedará algo como: sqlite:///C:/api-libro-interactivo/data/app.db
    db_file = Path("./data/app.db").expanduser().resolve()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    # Importante: usar as_posix() para que SQLAlchemy reciba barras con formato sqlite
    DB_URL = f"sqlite:///{db_file.as_posix()}"

engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

# PRAGMAs recomendados (concurrencia ligera)
@event.listens_for(engine, "connect")
def set_sqlite_pragmas(dbapi_connection, connection_record):
    cur = dbapi_connection.cursor()
    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("PRAGMA synchronous=NORMAL;")
    cur.execute("PRAGMA busy_timeout=5000;")
    cur.close()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


print("DB_URL:", DB_URL)
if not env_url:
    print("DB file will be at:", db_file)
    print("Dir exists?", db_file.parent.exists())