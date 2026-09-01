from datetime import datetime, timedelta, timezone

from src.session_manager import SessionManager, SessionStatus


def test_create_session_generates_unique_ids_and_tokens():
    manager = SessionManager()
    a = manager.create_session()
    b = manager.create_session()

    assert a.id != b.id
    assert a.patient_token != b.patient_token
    assert a.receptionist_secret != b.receptionist_secret
    assert a.status == SessionStatus.PENDING_PATIENT


def test_get_by_id_and_token():
    manager = SessionManager()
    session = manager.create_session()

    assert manager.get_by_id(session.id) is session
    assert manager.get_by_token(session.patient_token) is session
    assert manager.get_by_token("unknown-token") is None


def test_end_session_marks_ended():
    manager = SessionManager()
    session = manager.create_session()

    manager.end_session(session)

    assert session.status == SessionStatus.ENDED


def test_expire_stale_sessions_expires_idle_session():
    manager = SessionManager()
    session = manager.create_session()
    session.status = SessionStatus.ACTIVE
    session.last_activity_at -= timedelta(minutes=100)

    expired = manager.expire_stale_sessions()

    assert session in expired
    assert session.status == SessionStatus.EXPIRED


def test_expire_stale_sessions_leaves_active_session_alone():
    manager = SessionManager()
    session = manager.create_session()
    session.status = SessionStatus.ACTIVE

    expired = manager.expire_stale_sessions()

    assert expired == []
    assert session.status == SessionStatus.ACTIVE


def test_expire_stale_sessions_respects_hard_cap():
    manager = SessionManager()
    session = manager.create_session()
    session.status = SessionStatus.ACTIVE
    session.created_at -= timedelta(minutes=130)
    manager.touch(session)  # recently active, but the session itself is older than the hard cap

    expired = manager.expire_stale_sessions()

    assert session in expired


def test_expire_stale_sessions_after_reconnect_grace_period():
    manager = SessionManager()
    session = manager.create_session()
    session.status = SessionStatus.ACTIVE
    manager.touch(session)
    now = datetime.now(timezone.utc)
    session.patient_disconnected_at = now - timedelta(seconds=200)
    session.receptionist_disconnected_at = now - timedelta(seconds=200)

    expired = manager.expire_stale_sessions()

    assert session in expired
