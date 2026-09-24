"""
Hospital Reception Speech-to-Speech Interpreter -- FastAPI application.

Endpoints
---------
POST /api/sessions               -- create a new kiosk session (issues a QR-code join token)
GET  /api/sessions/{id}/qr.png   -- QR code PNG for a session's patient join URL
GET  /api/languages              -- supported language list
GET  /health                     -- liveness check
WS   /ws/patient/{token}         -- patient audio/caption relay
WS   /ws/receptionist/{id}       -- receptionist audio/caption relay (requires ?secret=)
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

# Must run before importing any of our own modules below -- several of them read
# environment variables (API keys, FRONTEND_ORIGIN, etc.) as module-level constants at
# import time, so .env has to be loaded into the process first or they'll silently fall
# back to their hardcoded defaults for the lifetime of the process.
load_dotenv()

from fastapi import Depends, FastAPI, HTTPException, Response, Security, WebSocket, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader

from . import websocket_handler
from .languages import SUPPORTED_LANGUAGES
from .models import CreateSessionResponse, HealthResponse, LanguageInfo
from .qr import build_join_url, generate_qr_png
from .session_manager import manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ── Optional API-key auth for kiosk session provisioning ─────────────────────

_SESSION_API_KEY = os.getenv("SESSION_API_KEY", "")
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def _verify_api_key(api_key: str | None = Security(_api_key_header)) -> None:
    if _SESSION_API_KEY and api_key != _SESSION_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key header.",
        )


# ── Background session-expiry sweep ──────────────────────────────────────────

_EXPIRY_SWEEP_INTERVAL_SECONDS = 60


async def _expiry_sweep_loop() -> None:
    while True:
        await asyncio.sleep(_EXPIRY_SWEEP_INTERVAL_SECONDS)
        expired = manager.expire_stale_sessions()
        for session in expired:
            logger.info("Session %s expired", session.id)


# ── App lifecycle ─────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.getenv("ELEVENLABS_API_KEY"):
        raise RuntimeError(
            "ELEVENLABS_API_KEY environment variable is not set. "
            "Copy .env.example -> .env and add your key."
        )
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY environment variable is not set. "
            "Copy .env.example -> .env and add your key."
        )
    sweep_task = asyncio.create_task(_expiry_sweep_loop())
    logger.info("Hospital interpreter backend started")
    yield
    sweep_task.cancel()
    logger.info("Hospital interpreter backend shutting down")


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="DXC Demo for NHS Participants",
    description=(
        "Live multilingual speech-to-speech interpreter for hospital reception desks. "
        "ElevenLabs performs speech-to-text and text-to-speech; Claude performs the "
        "text-translation step in between. The browser only captures and plays back audio."
    ),
    version="0.1.0",
    lifespan=lifespan,
    contact={"name": "bobbynoble"},
)

_cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── REST routes ───────────────────────────────────────────────────────────────


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/api/languages", response_model=list[LanguageInfo], tags=["Languages"])
async def get_languages() -> list[LanguageInfo]:
    return SUPPORTED_LANGUAGES


@app.post(
    "/api/sessions",
    response_model=CreateSessionResponse,
    dependencies=[Depends(_verify_api_key)],
    tags=["Sessions"],
)
async def create_session() -> CreateSessionResponse:
    session = manager.create_session()
    join_url = build_join_url(session.patient_token)
    return CreateSessionResponse(
        session_id=session.id,
        receptionist_secret=session.receptionist_secret,
        patient_join_url=join_url,
        qr_url=f"/api/sessions/{session.id}/qr.png",
        expires_at=session.expires_at,
    )


@app.get("/api/sessions/{session_id}/qr.png", tags=["Sessions"])
async def get_session_qr(session_id: str) -> Response:
    session = manager.get_by_id(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    join_url = build_join_url(session.patient_token)
    png_bytes = generate_qr_png(join_url)
    return Response(content=png_bytes, media_type="image/png")


# ── WebSocket routes ──────────────────────────────────────────────────────────


@app.websocket("/ws/patient/{token}")
async def ws_patient(websocket: WebSocket, token: str) -> None:
    await websocket_handler.handle_patient_socket(websocket, token)


@app.websocket("/ws/receptionist/{session_id}")
async def ws_receptionist(websocket: WebSocket, session_id: str, secret: str) -> None:
    await websocket_handler.handle_receptionist_socket(websocket, session_id, secret)
