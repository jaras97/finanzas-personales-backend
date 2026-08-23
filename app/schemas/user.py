from pydantic import BaseModel, EmailStr, Field
from uuid import UUID  # 👈 importar UUID

# Mínimo de caracteres para cualquier contraseña. El frontend ya lo pedía al
# registrarse, pero la API lo aceptaba todo -- se podía crear una cuenta con
# una contraseña de un carácter llamando al endpoint directamente.
MIN_PASSWORD_LENGTH = 8

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=MIN_PASSWORD_LENGTH)

class UserRead(BaseModel):
    id: UUID  # 👈 cambio aquí
    email: EmailStr

    class Config:
        orm_mode = True  # 👈 esto permite serializar objetos ORM