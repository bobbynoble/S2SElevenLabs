"""In-memory session state for the patient<->receptionist interpreter conversation.

Single-process only (see server/Dockerfile: --workers 1 is load-bearing). Horizontal scaling
would need a shared store (e.g. Redis) -- out of scope for this MVP.
"""

from __future__ import annotations

import os
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum

from fastapi import WebSocket

SESSION_TTL_MINUTES = int(os.getenv("SESSION_TTL_MINUTES", "30"))
SESSION_HARD_CAP_MINUTES = 120
RECONNECT_GRACE_SECONDS = 90


class SessionStatus(str, Enum):
    PENDING_PATIENT = "pending_patient"
    ACTIVE = "active"
    ENDED = "ended"
    EXPIRED = "expired"


@dataclass
class Session:
    id: str
    patient_token: str
    receptionist_secret: str
    created_at: datetime
    expires_at: datetime
    status: SessionStatus = SessionStatus.PENDING_PATIENT
    patient_language: str | None = None
    receptionist_language: str = "en"
    patient_ws: WebSocket | None = field(default=None, repr=False)
    receptionist_ws: WebSocket | None = field(default=None, repr=False)
    last_activity_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    patient_disconnected_at: datetime | None = None
    receptionist_disconnected_at: datetime | None = None


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._by_token: dict[str, str] = {}

    def create_session(self) -> Session:
        now = datetime.now(timezone.utc)
        session = Session(
            id=str(uuid.uuid4()),
            patient_token=secrets.token_urlsafe(24),
            receptionist_secret=secrets.token_urlsafe(24),
            created_at=now,
            expires_at=now + timedelta(minutes=SESSION_TTL_MINUTES),
        )
        self._sessions[session.id] = session
        self._by_token[session.patient_token] = session.id
        return session

    def get_by_id(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def get_by_token(self, token: str) -> Session | None:
        session_id = self._by_token.get(token)
        return self._sessions.get(session_id) if session_id else None

    def touch(self, session: Session) -> None:
        session.last_activity_at = datetime.now(timezone.utc)

    def end_session(self, session: Session) -> None:
        session.status = SessionStatus.ENDED

    def expire_stale_sessions(self) -> list[Session]:
        now = datetime.now(timezone.utc)
        expired: list[Session] = []
        for session in list(self._sessions.values()):
            if session.status in (SessionStatus.ENDED, SessionStatus.EXPIRED):
                continue
            idle_for = now - session.last_activity_at
            age = now - session.created_at
            both_disconnected_too_long = (
                session.patient_disconnected_at is not None
                and session.receptionist_disconnected_at is not None
                and now - session.patient_disconnected_at > timedelta(seconds=RECONNECT_GRACE_SECONDS)
            )
            if (
                idle_for > timedelta(minutes=SESSION_TTL_MINUTES)
                or age > timedelta(minutes=SESSION_HARD_CAP_MINUTES)
                or both_disconnected_too_long
            ):
                session.status = SessionStatus.EXPIRED
                expired.append(session)
        return expired

    def remove(self, session: Session) -> None:
        self._sessions.pop(session.id, None)
        self._by_token.pop(session.patient_token, None)


manager = SessionManager()
