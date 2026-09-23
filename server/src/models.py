"""Pydantic schemas for the REST API and the WebSocket control-message protocol."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

# ── REST ──────────────────────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: str


class LanguageInfo(BaseModel):
    code: str
    english_name: str
    native_name: str
    stt_supported: bool
    tts_supported: bool
    stt_low_confidence: bool = False


class CreateSessionResponse(BaseModel):
    session_id: str
    receptionist_secret: str
    patient_join_url: str
    qr_url: str
    expires_at: datetime


# ── WebSocket control messages: client -> server ─────────────────────────────


class JoinMessage(BaseModel):
    type: Literal["join"] = "join"
    language: str


class StartTurnMessage(BaseModel):
    type: Literal["start_turn"] = "start_turn"


class EndTurnMessage(BaseModel):
    type: Literal["end_turn"] = "end_turn"


class EndSessionMessage(BaseModel):
    type: Literal["end_session"] = "end_session"


ClientMessage = Annotated[
    Union[JoinMessage, StartTurnMessage, EndTurnMessage, EndSessionMessage],
    Field(discriminator="type"),
]


class ClientMessageEnvelope(BaseModel):
    """Wraps ClientMessage so pydantic can validate the discriminated union directly."""

    message: ClientMessage


# ── WebSocket control messages: server -> client ─────────────────────────────

StatusState = Literal[
    "waiting_for_patient",
    "patient_joined",
    "processing",
    "speaking",
    "ended",
    "coding",
    "session_expired",
]

ErrorCode = Literal[
    "stt_failed",
    "stt_low_confidence",
    "translation_failed",
    "tts_failed",
    "tts_unsupported_language",
    "session_expired",
    "coding_failed",
]

Speaker = Literal["patient", "receptionist"]


class StatusMessage(BaseModel):
    type: Literal["status"] = "status"
    state: StatusState
    detail: str | None = None


class CaptionMessage(BaseModel):
    type: Literal["caption"] = "caption"
    speaker: Speaker
    original_text: str
    original_lang: str
    translated_text: str
    translated_lang: str
    turn_id: str


class AudioReplyStartMessage(BaseModel):
    type: Literal["audio_reply_start"] = "audio_reply_start"
    turn_id: str


class AudioReplyEndMessage(BaseModel):
    type: Literal["audio_reply_end"] = "audio_reply_end"
    turn_id: str


class ErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    code: ErrorCode
    message: str


class ClinicalCodeSuggestion(BaseModel):
    code: str
    system: str
    description: str | None = None
    justification: str | None = None
    confidence: str | None = None
    review_flag: str | None = None


class ClinicalCodeMessage(BaseModel):
    type: Literal["clinical_code"] = "clinical_code"
    suggestions: list[ClinicalCodeSuggestion]
    coding_notes: str | None = None


class UsageMessage(BaseModel):
    type: Literal["usage"] = "usage"
    stt_seconds: float
    tts_characters: int
    estimated_cost_usd: float
