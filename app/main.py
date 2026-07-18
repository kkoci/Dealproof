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
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.routes import router
from app.offercheck.routes import router as offercheck_router
from app.offercheck import demo_auth
from app.devcred.routes import router as devcred_router
from app.config import settings
from app.rate_limit import limiter
import app.db as db

logging.basicConfig(level=settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    demo_auth.require_secret_key_configured()  # fails fast — see app/offercheck/demo_auth.py
    demo_auth.warn_if_anthropic_keys_identical()
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

class CatchAllExceptionsMiddleware(BaseHTTPMiddleware):
    """
    Converts any unhandled exception into a real Response *before* it reaches
    CORSMiddleware. A handler registered via app.add_exception_handler(Exception, ...)
    does NOT work for this: Starlette special-cases bare-Exception handlers to run
    in ServerErrorMiddleware, which wraps outside all user middleware (including
    CORSMiddleware) — so the resulting 500 still has no Access-Control-Allow-Origin
    header and cross-origin callers see an opaque browser-level CORS/network error
    instead of the real status. This middleware must be added before CORSMiddleware
    (see below) so it sits inside it and its response passes back through normally.
    """
    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception:
            logging.getLogger(__name__).exception("Unhandled exception on %s", request.url.path)
            return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.add_middleware(CatchAllExceptionsMiddleware)

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
app.include_router(offercheck_router)
app.include_router(devcred_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "tee_mode": settings.tee_mode}
