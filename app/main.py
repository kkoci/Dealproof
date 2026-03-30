"""
FastAPI application entry point — Phase 2.

Changes from Phase 1:
  - lifespan context manager added: calls db.init_db() on startup so the
    SQLite deals table is created before the first request arrives.
  - The rest of the wiring (router, /health) is unchanged.
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import settings
import app.db as db

logging.basicConfig(level=settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    await db.reset_stale_negotiations()  # recover deals interrupted by crashes/restarts
    yield


app = FastAPI(
    title="DealProof",
    description="Verifiable AI Negotiation for Private Data Access — TEE-backed escrow via Claude agents",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:4173",
        "https://*.vercel.app",
        "*",  # open during demo; tighten before prod
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "tee_mode": settings.tee_mode}
