from datetime import datetime, timedelta
from typing import Literal, Optional
import secrets

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime,
    CheckConstraint, UniqueConstraint, ForeignKey
)
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from dotenv import load_dotenv
import os

load_dotenv()
# ── Config BD ───────────────────────────────────────────────────────────────────
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL no está definida. Verifica tu entorno o archivo .env")
# DATABASE_URL = "sqlite:///C:/api-libro-interactivo/game.db"
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()

# ── Dominios (tu schema) ───────────────────────────────────────────────────────
School = Literal["Aguachica", "La Argentina", "Aractaca"]
Gender = Literal["Masculino", "Femenino"]

SCHOOL_VALUES = ("Aguachica", "La Argentina", "Aractaca")
GENDER_VALUES = ("Masculino", "Femenino")

LEVEL_REWARDS = {
    1: ["cinturon", "cristal-rojo"],
    2: ["pechera", "cristal-amarillo"],
    3: ["botas", "cristal-gris"],
    4: ["casco", "cristal-verde"]
}


# ── Modelos SQLAlchemy ──────────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    document = Column(String(100), nullable=False)  # login por documento
    name = Column(String(100), nullable=False)
    school = Column(String(50), nullable=False)
    gender = Column(String(20), nullable=False)
    money = Column(String(20), nullable=False, default="0")  # string, como pediste
    level = Column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint("document", name="uq_users_document"),
        CheckConstraint(f"school IN {SCHOOL_VALUES}", name="ck_users_school"),
        CheckConstraint(f"gender IN {GENDER_VALUES}", name="ck_users_gender"),
        CheckConstraint("level >= 1", name="ck_users_level_min"),
    )


class CompleteLevelIn(BaseModel):
    coins_earned: int = Field(ge=0)
    time_spent: int = Field(ge=0)  # tiempo en segundos


class UserTime(Base):
    __tablename__ = "user_time"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    time = Column(Integer, nullable=False)
    level = Column(Integer, nullable=False)


class ItemModel(Base):
    __tablename__ = "item"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    item_type = Column(String(50), nullable=False)


class UserEarnedItem(Base):
    __tablename__ = "user_earned_items"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("item.id"), nullable=False)


class SessionToken(Base):
    __tablename__ = "sessions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String(255), unique=True, index=True, nullable=False)
    expires_at = Column(DateTime, index=True, nullable=False)

Base.metadata.create_all(bind=engine)


# ── Schemas Pydantic (entrada/salida) ───────────────────────────────────────────
class LoginIn(BaseModel):
    document: str = Field(min_length=3)


class RegisterIn(BaseModel):
    document: str = Field(min_length=3)
    name: str = Field(min_length=1)
    school: School
    gender: Gender
    # money: str


class Item(BaseModel):
    id: int
    name: str
    item_type: str

    model_config = ConfigDict(from_attributes=True)


class UserOut(BaseModel):
    id: int
    document: str
    name: str
    school: School
    gender: Gender
    money: str
    level: int
    items: list[Item]  # ← Aquí se agregan los ítems obtenidos
    model_config = ConfigDict(from_attributes=True)


class UpdateMeIn(BaseModel):
    name: Optional[str] = None
    school: Optional[School] = None
    gender: Optional[Gender] = None
    money: Optional[str] = None
    level: Optional[int] = Field(default=None, ge=1)


# ── App y CORS ─────────────────────────────────────────────────────────────────
app = FastAPI(title="Game API (SQLite)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # AJUSTA en producción
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Helpers de sesión ──────────────────────────────────────────────────────────
def create_session(db: Session, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    sess = SessionToken(
        user_id=user_id,
        token=token,
        expires_at=datetime.utcnow() + timedelta(days=7)
    )
    db.add(sess)
    db.commit()
    return token


def user_by_token(db: Session, token: str) -> Optional[User]:
    sess = db.query(SessionToken).filter(
        SessionToken.token == token,
        SessionToken.expires_at > datetime.utcnow()
    ).first()
    if not sess:
        return None
    return db.query(User).get(sess.user_id)


def require_auth(
        db: Session = Depends(get_db),
        authorization: Optional[str] = Header(None)
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Falta token o formato inválido")
    token = authorization.split(" ")[1]
    user = user_by_token(db, token)
    if not user:
        raise HTTPException(401, "Token inválido o expirado")
    return user


# ── Endpoints ──────────────────────────────────────────────────────────────────
@app.post("/auth/register", response_model=UserOut)
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    if payload.school not in SCHOOL_VALUES:
        raise HTTPException(400, "school inválido")
    if payload.gender not in GENDER_VALUES:
        raise HTTPException(400, "gender inválido")

    exists = db.query(User).filter_by(document=payload.document).first()
    if exists:
        raise HTTPException(400, "Documento ya registrado")

    user = User(
        document=payload.document,
        name=payload.name,
        school=payload.school,
        gender=payload.gender,
        # money=payload.money,
        level=1,

    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.post("/auth/login")
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(document=payload.document).first()
    if not user:
        raise HTTPException(404, "Usuario no encontrado; regístrese primero")

    token = create_session(db, user.id)

    # Obtener ítems ganados
    earned_items = db.query(ItemModel).join(UserEarnedItem).filter(
        UserEarnedItem.user_id == user.id
    ).all()
    items_out = [Item.model_validate(item) for item in earned_items]

    # Construir respuesta manualmente
    user_out = UserOut(
        id=user.id,
        document=user.document,
        name=user.name,
        school=user.school,
        gender=user.gender,
        money=user.money,
        level=user.level,
        items=items_out
    )

    return {"token": token, "user": user_out}


@app.post("/auth/logout")
def logout(token: str, db: Session = Depends(get_db)):
    deleted = db.query(SessionToken).filter_by(token=token).delete()
    db.commit()
    return {"ok": True, "deleted": deleted}


@app.get("/me", response_model=UserOut)
def me(
        db: Session = Depends(get_db),
        current: User = Depends(require_auth)
):
    # Obtener los ítems ganados por el usuario
    earned_items = db.query(ItemModel).join(UserEarnedItem).filter(
        UserEarnedItem.user_id == current.id
    ).all()

    # Convertir los ítems a Pydantic
    items_out = [Item.model_validate(item) for item in earned_items]

    # Construir el objeto UserOut manualmente
    user_out = UserOut(
        id=current.id,
        document=current.document,
        name=current.name,
        school=current.school,
        gender=current.gender,
        money=current.money,
        level=current.level,
        items=items_out
    )
    return user_out


@app.post("/me/complete-level", response_model=UserOut)
def complete_level(
        data: CompleteLevelIn,
        db: Session = Depends(get_db),
        current: User = Depends(require_auth)
):
    # Sumar nivel (máximo hasta 5)
    if current.level < 5:
        current.level += 1

    # Sumar monedas
    try:
        current_money = int(current.money)
    except ValueError:
        raise HTTPException(500, "Formato inválido en campo 'money'")
    current.money = str(current_money + data.coins_earned)

    # Registrar tiempo en la tabla user_time
    time_record = UserTime(
        user_id=current.id,
        time=data.time_spent,
        level=current.level - 1  # nivel que acaba de completar
    )
    db.add(time_record)

    # Obtener ítems por nivel completado
    rewards = LEVEL_REWARDS.get(current.level - 1, [])  # nivel recién completado

    # Buscar ítems en la base de datos
    items_to_add = db.query(ItemModel).filter(ItemModel.name.in_(rewards)).all()

    # Registrar ítems ganados si no los tiene
    for item in items_to_add:
        already_has = db.query(UserEarnedItem).filter_by(
            user_id=current.id,
            item_id=item.id
        ).first()
        if not already_has:
            earned = UserEarnedItem(user_id=current.id, item_id=item.id)
            db.add(earned)

    # Guardar cambios
    db.commit()
    db.refresh(current)

    # Obtener todos los ítems ganados
    earned_items = db.query(ItemModel).join(UserEarnedItem).filter(
        UserEarnedItem.user_id == current.id
    ).all()
    items_out = [Item.model_validate(item) for item in earned_items]

    # Construir respuesta
    return UserOut(
        id=current.id,
        document=current.document,
        name=current.name,
        school=current.school,
        gender=current.gender,
        money=current.money,
        level=current.level,
        items=items_out
    )


@app.put("/me", response_model=UserOut)
def update_me(
        data: UpdateMeIn,
        db: Session = Depends(get_db),
        current: User = Depends(require_auth),
):
    if data.name is not None:
        current.name = data.name
    if data.school is not None:
        if data.school not in SCHOOL_VALUES:
            raise HTTPException(400, "school inválido")
        current.school = data.school
    if data.gender is not None:
        if data.gender not in GENDER_VALUES:
            raise HTTPException(400, "gender inválido")
        current.gender = data.gender
    if data.money is not None:
        current.money = data.money
    if data.level is not None:
        current.level = data.level

    db.commit()
    db.refresh(current)
    return current
