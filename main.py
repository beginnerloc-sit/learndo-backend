from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from database import Base, engine, SessionLocal
from routers import users, garden, words, auth
import seed


def _run_migrations():
    with engine.connect() as conn:
        for stmt in [
            "ALTER TABLE garden_plants ADD COLUMN gifted_by VARCHAR(20) NULL",
            "ALTER TABLE users ADD COLUMN collection_locked TINYINT(1) NOT NULL DEFAULT 0",
        ]:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass  # column already exists


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _run_migrations()

    db = SessionLocal()
    try:
        seed.run_seed(db)
    finally:
        db.close()

    yield
    # (shutdown logic goes here if needed)


app = FastAPI(
    title="Learndo API",
    description="Backend for the language-learning garden game.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(garden.router)
app.include_router(words.router)


@app.get("/", tags=["health"])
def health_check():
    return {"status": "ok", "service": "learndo-api"}
