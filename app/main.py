"""
FastAPI application entry point — Phase 2.

Changes from Phase 1:
  - lifespan context manager added: calls db.init_db() on startup so the
    SQLite deals table is created before the first request arrives.
  - The rest of the wiring (router, /health) is unchanged.
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.routes import router
from app.devcred.routes import router as devcred_router
from app.config import settings
from app.rate_limit import limiter
import app.db as db

logging.basicConfig(level=settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    await db.create_hedera_messages_table()
    await db.create_arc_anchors_table()
    await db.create_transcript_corpora_table()
    await db.create_dev_credentials_table()
    await db.create_eval_counter_table()
    await db.reset_stale_negotiations()  # recover deals interrupted by crashes/restarts
    yield


app = FastAPI(
    title="DealProof",
    description="Verifiable AI Negotiation for Private Data Access — TEE-backed escrow via Claude agents",
    version="0.2.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

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
app.include_router(devcred_router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Unhandled exceptions otherwise hit Starlette's ServerErrorMiddleware, which sits
    # outside CORSMiddleware — the resulting 500 has no Access-Control-Allow-Origin
    # header, so cross-origin callers (the Vercel frontend) see an opaque NetworkError
    # instead of the real status. Handling it here keeps the response inside the
    # middleware stack so CORS headers still get attached.
    logging.getLogger(__name__).exception("Unhandled exception on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "tee_mode": settings.tee_mode}
