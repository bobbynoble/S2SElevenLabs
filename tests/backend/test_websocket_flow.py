import pytest
from fastapi.testclient import TestClient

from src import pipeline
from src.main import app
from src.session_manager import manager


@pytest.fixture(autouse=True)
def clear_sessions():
    manager._sessions.clear()
    manager._by_token.clear()
    yield
    manager._sessions.clear()
    manager._by_token.clear()


def _create_session(client: TestClient) -> dict:
    response = client.post("/api/sessions")
    assert response.status_code == 200
    return response.json()


def _token_from_join_url(join_url: str) -> str:
    return join_url.rsplit("/", 1)[-1]


def test_patient_join_notifies_receptionist():
    with TestClient(app) as client:
        session_data = _create_session(client)
        session_id = session_data["session_id"]
        secret = session_data["receptionist_secret"]
        token = _token_from_join_url(session_data["patient_join_url"])

        with client.websocket_connect(f"/ws/receptionist/{session_id}?secret={secret}") as receptionist_ws:
            assert receptionist_ws.receive_json() == {
                "type": "status",
                "state": "waiting_for_patient",
                "detail": None,
            }

            with client.websocket_connect(f"/ws/patient/{token}") as patient_ws:
                patient_ws.send_json({"type": "join", "language": "pl"})

                assert receptionist_ws.receive_json() == {
                    "type": "status",
                    "state": "patient_joined",
                    "detail": "pl",
                }


def test_receptionist_can_set_own_language_without_affecting_patient():
    with TestClient(app) as client:
        session_data = _create_session(client)
        session_id = session_data["session_id"]
        secret = session_data["receptionist_secret"]

        with client.websocket_connect(f"/ws/receptionist/{session_id}?secret={secret}") as receptionist_ws:
            receptionist_ws.receive_json()  # waiting_for_patient

            receptionist_ws.send_json({"type": "join", "language": "fr"})

            session = manager.get_by_id(session_id)
            assert session.receptionist_language == "fr"
            assert session.status.value == "pending_patient"


def test_receptionist_socket_rejects_wrong_secret():
    with TestClient(app) as client:
        session_data = _create_session(client)
        session_id = session_data["session_id"]

        with pytest.raises(Exception):
            with client.websocket_connect(f"/ws/receptionist/{session_id}?secret=wrong-secret"):
                pass


def test_turn_produces_caption_for_both_parties(monkeypatch):
    fake_result = pipeline.TurnResult(
        original_text="Hello",
        original_lang="pl",
        translated_text="Cześć",
        translated_lang="en",
        audio=None,
    )

    async def fake_run_turn(session, speaker, audio_bytes):
        return fake_result

    monkeypatch.setattr(pipeline, "run_turn", fake_run_turn)

    with TestClient(app) as client:
        session_data = _create_session(client)
        session_id = session_data["session_id"]
        secret = session_data["receptionist_secret"]
        token = _token_from_join_url(session_data["patient_join_url"])

        with client.websocket_connect(f"/ws/receptionist/{session_id}?secret={secret}") as receptionist_ws:
            receptionist_ws.receive_json()  # waiting_for_patient

            with client.websocket_connect(f"/ws/patient/{token}") as patient_ws:
                patient_ws.send_json({"type": "join", "language": "pl"})
                receptionist_ws.receive_json()  # patient_joined
                patient_ws.receive_json()  # patient_joined (broadcast to both parties)

                patient_ws.send_json({"type": "start_turn"})
                patient_ws.send_bytes(b"\x00\x01" * 10)
                patient_ws.send_json({"type": "end_turn"})

                processing_status = receptionist_ws.receive_json()
                assert processing_status["state"] == "processing"
                patient_ws.receive_json()  # processing (broadcast to both parties)

                caption = receptionist_ws.receive_json()
                assert caption["type"] == "caption"
                assert caption["speaker"] == "patient"
                assert caption["translated_text"] == "Cześć"

                patient_caption = patient_ws.receive_json()
                assert patient_caption == caption


def test_end_session_broadcasts_ended_status():
    with TestClient(app) as client:
        session_data = _create_session(client)
        session_id = session_data["session_id"]
        secret = session_data["receptionist_secret"]
        token = _token_from_join_url(session_data["patient_join_url"])

        with client.websocket_connect(f"/ws/receptionist/{session_id}?secret={secret}") as receptionist_ws:
            receptionist_ws.receive_json()  # waiting_for_patient

            with client.websocket_connect(f"/ws/patient/{token}") as patient_ws:
                patient_ws.send_json({"type": "join", "language": "pl"})
                receptionist_ws.receive_json()  # patient_joined
                patient_ws.receive_json()  # patient_joined (broadcast to both parties)

                receptionist_ws.send_json({"type": "end_session"})

                assert patient_ws.receive_json() == {"type": "status", "state": "ended", "detail": None}
