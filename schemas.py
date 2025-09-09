# app/schemas.py
from pydantic import BaseModel, ConfigDict
from typing import Literal

School = Literal["Aguachica", "La Argentina", "Aractaca"]
Gender = Literal["Masculino", "Femenino"]

class LoginIn(BaseModel):
    document: str

class RegisterIn(BaseModel):
    document: str
    name: str
    school: School
    gender: Gender
    money: str

class UserOut(BaseModel):
    id: int
    document: str
    name: str
    school: School
    gender: Gender
    money: str
    level: int
    score: int

    # >>> reemplaza orm_mode por from_attributes <<<
    model_config = ConfigDict(from_attributes=True)
