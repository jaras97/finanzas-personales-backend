from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.database import create_db_and_tables
from app.api import auth, cash_flow, categories,  debts, saving_accounts, subscriptions, subscriptions_admin, summary, summary_extra, transactions
from fastapi.middleware.cors import CORSMiddleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield  # Aquí podrías hacer cleanup en shutdown si lo necesitas

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://finanzas-personal-frontend-1xt6.vercel.app",  
        "http://localhost:3000"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(transactions.router)
app.include_router(categories.router)
app.include_router(saving_accounts.router)
app.include_router(debts.router)
app.include_router(subscriptions_admin.router)
app.include_router(subscriptions.router)
app.include_router(summary.router)
app.include_router(summary_extra.router)
app.include_router(cash_flow.router)

@app.get("/")
def root():
    return {"message": "Servidor de gastos personales"}