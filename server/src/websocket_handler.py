"""WebSocket routes: connection handling, per-turn audio buffering, and message dispatch
between the patient and receptionist sockets of a session."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from . import pipeline
from .languages import is_supported
from .models import ClientMessageEnvelope, Speaker
from .pipeline import TurnResult
from .session_manager import Session, SessionStatus, manager

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def handle_patient_socket(websocket: WebSocket, token: str) -> None:
    session = manager.get_by_token(token)
    if session is None or session.status in (SessionStatus.ENDED, SessionStatus.EXPIRED):
        await websocket.close(code=4404)
        return

    await websocket.accept()
    session.patient_ws = websocket
    session.patient_disconnected_at = None
    try:
        await _run_participant_loop(session, "patient", websocket)
    except WebSocketDisconnect:
        session.patient_ws = None
        session.patient_disconnected_at = _now()
    finally:
        manager.touch(session)


async def handle_receptionist_socket(websocket: WebSocket, session_id: str, secret: str) -> None:
    session = manager.get_by_id(session_id)
    if session is None or session.receptionist_secret != secret:
        await websocket.close(code=4403)
        return
    if session.status in (SessionStatus.ENDED, SessionStatus.EXPIRED):
        await websocket.close(code=4404)
        return

    await websocket.accept()
    session.receptionist_ws = websocket
    session.receptionist_disconnected_at = None

    if session.status == SessionStatus.PENDING_PATIENT:
        await _send_status(websocket, "waiting_for_patient")
    else:
        await _send_status(websocket, "patient_joined", detail=session.patient_language)

    try:
        await _run_participant_loop(session, "receptionist", websocket)
    except WebSocketDisconnect:
        session.receptionist_ws = None
        session.receptionist_disconnected_at = _now()
    finally:
        manager.touch(session)


async def _run_participant_loop(session: Session, speaker: Speaker, websocket: WebSocket) -> None:
    turn_buffer = bytearray()
    turn_active = False

    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            raise WebSocketDisconnect(message.get("code", 1000))

        text = message.get("text")
        if text is not None:
            turn_active, turn_buffer = await _handle_control_message(
                session, speaker, text, turn_active, turn_buffer
            )
            continue

        audio_bytes = message.get("bytes")
        if audio_bytes is not None and turn_active:
            turn_buffer.extend(audio_bytes)


async def _handle_control_message(
    session: Session,
    speaker: Speaker,
    raw_text: str,
    turn_active: bool,
    turn_buffer: bytearray,
) -> tuple[bool, bytearray]:
    try:
        parsed = json.loads(raw_text)
        envelope = ClientMessageEnvelope.model_validate({"message": parsed})
        client_message = envelope.message
    except (json.JSONDecodeError, ValidationError) as exc:
        logger.warning("Rejected malformed WS control message from %s: %s", speaker, exc)
        return turn_active, turn_buffer

    msg_type = client_message.type

    if msg_type == "join":
        if not is_supported(client_message.language):
            return turn_active, turn_buffer
        if speaker == "patient":
            session.patient_language = client_message.language
            session.status = SessionStatus.ACTIVE
            manager.touch(session)
            await _broadcast_status(session, "patient_joined", detail=client_message.language)
        else:
            session.receptionist_language = client_message.language
            manager.touch(session)
        return turn_active, turn_buffer

    if msg_type == "start_turn":
        return True, bytearray()

    if msg_type == "end_turn":
        if turn_active and turn_buffer:
            await _process_turn(session, speaker, bytes(turn_buffer))
        return False, bytearray()

    if msg_type == "end_session":
        if speaker == "receptionist":
            manager.end_session(session)
            await _broadcast_status(session, "ended")
        return turn_active, turn_buffer

    return turn_active, turn_buffer


async def _process_turn(session: Session, speaker: Speaker, audio_bytes: bytes) -> None:
    await _broadcast_status(session, "processing")
    turn_id = uuid.uuid4().hex

    try:
        result = await pipeline.run_turn(session, speaker, audio_bytes)
    except pipeline.PipelineError as exc:
        await _send_error(session, speaker, exc.code, exc.message)
        return

    await _broadcast_caption(session, speaker, result, turn_id)

    if result.audio:
        listener_ws = session.receptionist_ws if speaker == "patient" else session.patient_ws
        if listener_ws is not None:
            await _broadcast_status(session, "speaking")
            await listener_ws.send_json({"type": "audio_reply_start", "turn_id": turn_id})
            await listener_ws.send_bytes(result.audio)
            await listener_ws.send_json({"type": "audio_reply_end", "turn_id": turn_id})


async def _send_status(websocket: WebSocket, state: str, detail: str | None = None) -> None:
    await websocket.send_json({"type": "status", "state": state, "detail": detail})


async def _broadcast_status(session: Session, state: str, detail: str | None = None) -> None:
    for ws in (session.patient_ws, session.receptionist_ws):
        if ws is not None:
            await _send_status(ws, state, detail)


async def _broadcast_caption(session: Session, speaker: Speaker, result: TurnResult, turn_id: str) -> None:
    payload = {
        "type": "caption",
        "speaker": speaker,
        "original_text": result.original_text,
        "original_lang": result.original_lang,
        "translated_text": result.translated_text,
        "translated_lang": result.translated_lang,
        "turn_id": turn_id,
    }
    for ws in (session.patient_ws, session.receptionist_ws):
        if ws is not None:
            await ws.send_json(payload)


async def _send_error(session: Session, speaker: Speaker, code: str, message: str) -> None:
    ws = session.patient_ws if speaker == "patient" else session.receptionist_ws
    if ws is not None:
        await ws.send_json({"type": "error", "code": code, "message": message})
