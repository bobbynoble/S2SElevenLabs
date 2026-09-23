"""WebSocket routes: connection handling, per-turn audio buffering, and message dispatch
between the patient and receptionist sockets of a session."""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from . import clinical_coding, elevenlabs_client, pipeline
from .languages import is_supported, is_tts_supported
from .models import ClientMessageEnvelope, Speaker
from .pipeline import TurnResult
from .session_manager import Session, SessionStatus, TurnRecord, manager

logger = logging.getLogger(__name__)

# Kill switch for the clinical-coding step -- e.g. while the coding service's own upstream
# (Azure OpenAI/Search) is down, so a demo session ending doesn't surface a coding_failed error.
CLINICAL_CODING_ENABLED = os.getenv("CLINICAL_CODING_ENABLED", "true").strip().lower() != "false"


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
            await _send_usage_summary(session)
            await _run_clinical_coding(session)
        return turn_active, turn_buffer

    return turn_active, turn_buffer


async def _process_turn(session: Session, speaker: Speaker, audio_bytes: bytes) -> None:
    await _broadcast_status(session, "processing")
    turn_id = uuid.uuid4().hex

    session.total_stt_seconds += len(audio_bytes) / 2 / elevenlabs_client.PCM_SAMPLE_RATE_HZ

    try:
        result = await pipeline.run_turn(session, speaker, audio_bytes)
    except pipeline.PipelineError as exc:
        await _send_error(session, speaker, exc.code, exc.message)
        return

    session.total_tts_characters += len(result.translated_text)
    session.turns.append(
        TurnRecord(
            speaker=speaker,
            original_text=result.original_text,
            original_lang=result.original_lang,
            translated_text=result.translated_text,
            translated_lang=result.translated_lang,
            at=_now(),
        )
    )

    await _broadcast_caption(session, speaker, result, turn_id)

    if not is_tts_supported(result.translated_lang):
        return
    listener_ws = session.receptionist_ws if speaker == "patient" else session.patient_ws
    if listener_ws is None:
        return

    await _broadcast_status(session, "speaking")
    await listener_ws.send_json({"type": "audio_reply_start", "turn_id": turn_id})
    try:
        async for pcm_chunk in elevenlabs_client.synthesize_stream(
            result.translated_text, language=result.translated_lang
        ):
            await listener_ws.send_bytes(pcm_chunk)
    except elevenlabs_client.ElevenLabsError as exc:
        logger.warning("Turn %s (%s): TTS streaming failed: %s", turn_id, speaker, exc)
        await _send_error(session, speaker, "tts_failed", str(exc))
        return
    await listener_ws.send_json({"type": "audio_reply_end", "turn_id": turn_id})


async def _send_usage_summary(session: Session) -> None:
    """Once the receptionist ends the session, report the ElevenLabs API usage/estimated cost
    for it. Receptionist-only -- this is an operational figure, not patient-facing."""
    if session.receptionist_ws is None:
        return
    await session.receptionist_ws.send_json(
        {
            "type": "usage",
            "stt_seconds": round(session.total_stt_seconds, 2),
            "tts_characters": session.total_tts_characters,
            "estimated_cost_usd": round(
                elevenlabs_client.estimated_cost_usd(session.total_stt_seconds, session.total_tts_characters), 4
            ),
        }
    )


def _transcript_note(session: Session) -> str:
    """Build a single-language conversation note for the clinical coding service: whichever side
    of each turn was spoken/heard in the receptionist's own language, so the note reads as one
    coherent conversation rather than a mix of source and translated text."""
    lines = []
    for turn in session.turns:
        text = turn.translated_text if turn.speaker == "patient" else turn.original_text
        label = "Patient" if turn.speaker == "patient" else "Receptionist"
        lines.append(f"{label}: {text}")
    return "\n".join(lines)


async def _run_clinical_coding(session: Session) -> None:
    """Once the receptionist ends the session, send the finished transcript to the clinical
    coding service and pass the suggested codes back to the receptionist for review. Coding is
    a clinical-staff concern, so the result (and any failure) goes to the receptionist only,
    never the patient."""
    if not CLINICAL_CODING_ENABLED or not session.turns or session.receptionist_ws is None:
        return

    await _send_status(session.receptionist_ws, "coding")

    try:
        result = await clinical_coding.get_clinical_code(_transcript_note(session))
    except clinical_coding.ClinicalCodingError as exc:
        await _send_error(session, "receptionist", "coding_failed", str(exc))
        return

    if session.receptionist_ws is not None:
        await session.receptionist_ws.send_json(
            {
                "type": "clinical_code",
                "suggestions": [
                    {
                        "code": s.code,
                        "system": s.system,
                        "description": s.description,
                        "justification": s.justification,
                        "confidence": s.confidence,
                        "review_flag": s.review_flag,
                    }
                    for s in result.suggestions
                ],
                "coding_notes": result.coding_notes,
            }
        )


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
