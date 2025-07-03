from pydantic import BaseModel, EmailStr
from uuid import UUID  # 👈 importar UUID

class UserCreate(BaseModel):
    email: EmailStr
    password: str

class UserRead(BaseModel):
    id: UUID  # 👈 cambio aquí
    email: EmailStr

    class Config:
        orm_mode = True  # 👈 esto permite serializar objetos ORM