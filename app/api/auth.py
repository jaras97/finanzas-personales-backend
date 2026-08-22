from datetime import timedelta

from fastapi import APIRouter, HTTPException, Depends, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select
from app.models.user import User
from app.schemas.user import UserCreate, UserRead
from app.core.config import ACCESS_TOKEN_EXPIRE_MINUTES, COOKIE_DOMAIN, COOKIE_SECURE
from app.core.security import (
    ACCESS_TOKEN_COOKIE_NAME,
    get_password_hash,
    verify_password,
    create_access_token,
    get_current_user,
)
from app.database import engine
from app.utils.category_helpers import create_base_categories

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_access_token_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE_NAME,
        value=token,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        domain=COOKIE_DOMAIN,
        path="/",
    )

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
def login(response: Response, form_data: OAuth2PasswordRequestForm = Depends()):
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == form_data.username)).first()
        if not user or not verify_password(form_data.password, user.hashed_password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales incorrectas")

        access_token = create_access_token(data={"sub": str(user.id)})
        _set_access_token_cookie(response, access_token)
        # El body sigue trayendo el token para clientes API (Postman, Swagger,
        # scripts de administración) que no pueden depender de la cookie.
        # El frontend web ya no lo persiste: se autentica solo con la cookie.
        return {"access_token": access_token, "token_type": "bearer"}


# Logout: limpia la cookie httpOnly. El navegador no puede borrarla por sí
# solo (es justamente el punto de httpOnly), así que el logout ahora pasa
# por el backend en vez de manipular document.cookie/localStorage.
@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(
        key=ACCESS_TOKEN_COOKIE_NAME,
        domain=COOKIE_DOMAIN,
        path="/",
    )
    return {"message": "Sesión cerrada"}

# Ruta protegida
@router.get("/me")
def read_users_me(user_id: str = Depends(get_current_user)):
    return {"user_id": user_id}