from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.database import create_db_and_tables
from app.api import auth, categories, dashboard, debts, monthly_summary, saving_accounts, transactions
from fastapi.middleware.cors import CORSMiddleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield  # Aquí podrías hacer cleanup en shutdown si lo necesitas

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # O usa ["*"] mientras desarrollas
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(transactions.router)
app.include_router(categories.router)
app.include_router(saving_accounts.router)
app.include_router(debts.router)
app.include_router(monthly_summary.router)
app.include_router(dashboard.router)

@app.get("/")
def root():
    return {"message": "Servidor de gastos personales"}