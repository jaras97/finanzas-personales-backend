from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select
from app.models.user import User
from app.schemas.user import UserCreate, UserRead
from app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    get_current_user,
)
from app.database import engine
from app.utils.category_helpers import create_base_categories

router = APIRouter(prefix="/auth", tags=["auth"])

# Registro
@router.post("/register", response_model=UserRead)
def register(user_create: UserCreate):
    with Session(engine) as session:
        user_exists = session.exec(select(User).where(User.email == user_create.email)).first()
        if user_exists:
            raise HTTPException(status_code=400, detail="Email ya registrado")

        hashed_pwd = get_password_hash(user_create.password)
        user = User(email=user_create.email, hashed_password=hashed_pwd)
        session.add(user)
        session.commit()
        session.refresh(user)

        create_base_categories(user.id, session)
        session.commit()
        return UserRead(id=user.id, email=user.email)

# Login
@router.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == form_data.username)).first()
        if not user or not verify_password(form_data.password, user.hashed_password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales incorrectas")

        access_token = create_access_token(data={"sub": str(user.id)})
        return {"access_token": access_token, "token_type": "bearer"}

# Ruta protegida
@router.get("/me")
def read_users_me(user_id: str = Depends(get_current_user)):
    return {"user_id": user_id}