from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.database import create_db_and_tables
from app.api import account, admin_users, auth, auth_extra, budgets, cash_flow, categories, category_rules, csv_import, currencies, debts, recurring_transactions, saving_accounts, subscriptions, subscriptions_admin, summary, summary_extra, transactions
from fastapi.middleware.cors import CORSMiddleware
from app.routes.fx import router as fx_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield  # Aquí podrías hacer cleanup en shutdown si lo necesitas

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://finanzas-personal-frontend-1xt6.vercel.app",  
        "https://www.balancedcent.com",
        "http://localhost:3000","http://localhost:3001"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(currencies.router)
app.include_router(transactions.router)
app.include_router(categories.router)
app.include_router(saving_accounts.router)
app.include_router(debts.router)
app.include_router(subscriptions_admin.router)
app.include_router(subscriptions.router)
app.include_router(admin_users.router)
app.include_router(recurring_transactions.router)
app.include_router(budgets.router)
app.include_router(csv_import.transactions_import_router)
app.include_router(csv_import.import_profiles_router)
app.include_router(category_rules.router)
app.include_router(account.router)
app.include_router(summary.router)
app.include_router(summary_extra.router)
app.include_router(cash_flow.router)
app.include_router(auth_extra.router)
app.include_router(fx_router)

@app.get("/")
def root():
    return {"message": "Servidor de gastos personales"}