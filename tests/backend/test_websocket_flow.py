import time

import pytest
from fastapi.testclient import TestClient

from src import clinical_coding, elevenlabs_client, pipeline, websocket_handler
from src.main import app
from src.session_manager import manager


@pytest.fixture(autouse=True)
def clear_sessions():
    manager._sessions.clear()
    manager._by_token.clear()
    yield
    manager._sessions.clear()
    manager._by_token.clear()


@pytest.fixture(autouse=True)
def no_real_tts(monkeypatch):
    """Every test that runs a turn ends up with a TTS-supported target language by default
    (e.g. "en") -- without this, each of those would make a real ElevenLabs streaming call.
    Tests that care about the audio stream itself override this with _patch_synthesize_stream."""

    async def empty_stream(text, language=None, voice_id=None):
        return
        yield b""  # pragma: no cover -- unreachable, just makes this an async generator

    monkeypatch.setattr(elevenlabs_client, "synthesize_stream", empty_stream)


def _create_session(client: TestClient) -> dict:
    response = client.post("/api/sessions")
    assert response.status_code == 200
    return response.json()


def _token_from_join_url(join_url: str) -> str:
    return join_url.rsplit("/", 1)[-1]


def _patch_run_turn(monkeypatch, original_text="Hello", translated_text="Cześć"):
    fake_result = pipeline.TurnResult(
        original_text=original_text,
        original_lang="pl",
        translated_text=translated_text,
        translated_lang="en",
    )

    async def fake_run_turn(session, speaker, audio_bytes):
        return fake_result

    monkeypatch.setattr(pipeline, "run_turn", fake_run_turn)
    return fake_result


def _patch_synthesize_stream(monkeypatch, chunks):
    async def fake_synthesize_stream(text, language=None, voice_id=None):
        for chunk in chunks:
            yield chunk

    monkeypatch.setattr(elevenlabs_client, "synthesize_stream", fake_synthesize_stream)


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

            # The receptionist's own "join" has no server response to synchronize on (only a
            # patient join broadcasts a status), so poll briefly rather than assert immediately.
            session = manager.get_by_id(session_id)
            for _ in range(50):
                if session.receptionist_language == "fr":
                    break
                time.sleep(0.01)
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
    _patch_run_turn(monkeypatch)

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
                assert caption["original_text"] == "Hello"
                assert caption["translated_text"] == "Cześć"
                assert caption["original_lang"] == "pl"
                assert caption["translated_lang"] == "en"

                patient_caption = patient_ws.receive_json()
                assert patient_caption == caption


def test_turn_streams_audio_to_listener_only(monkeypatch):
    _patch_run_turn(monkeypatch)
    _patch_synthesize_stream(monkeypatch, [b"\x01\x02", b"\x03\x04", b"\x05\x06"])

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
                patient_ws.receive_json()  # patient_joined

                patient_ws.send_json({"type": "start_turn"})
                patient_ws.send_bytes(b"\x00\x01" * 10)
                patient_ws.send_json({"type": "end_turn"})

                receptionist_ws.receive_json()  # processing
                patient_ws.receive_json()  # processing
                receptionist_ws.receive_json()  # caption
                patient_ws.receive_json()  # caption

                # Patient spoke -> receptionist is the listener: gets "speaking" + the audio reply.
                assert receptionist_ws.receive_json() == {"type": "status", "state": "speaking", "detail": None}
                audio_start = receptionist_ws.receive_json()
                assert audio_start["type"] == "audio_reply_start"
                turn_id = audio_start["turn_id"]

                assert receptionist_ws.receive_bytes() == b"\x01\x02"
                assert receptionist_ws.receive_bytes() == b"\x03\x04"
                assert receptionist_ws.receive_bytes() == b"\x05\x06"

                assert receptionist_ws.receive_json() == {"type": "audio_reply_end", "turn_id": turn_id}


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


def _join_and_run_one_turn(receptionist_ws, patient_ws, audio_bytes=b"\x00\x01" * 10):
    patient_ws.send_json({"type": "join", "language": "pl"})
    receptionist_ws.receive_json()  # patient_joined
    patient_ws.receive_json()  # patient_joined (broadcast to both parties)

    patient_ws.send_json({"type": "start_turn"})
    patient_ws.send_bytes(audio_bytes)
    patient_ws.send_json({"type": "end_turn"})

    receptionist_ws.receive_json()  # processing
    patient_ws.receive_json()  # processing
    receptionist_ws.receive_json()  # caption
    patient_ws.receive_json()  # caption

    # translated_lang defaults to "en" (tts_supported): "speaking" is broadcast to both parties,
    # but the audio reply itself (empty, under the no_real_tts fixture) goes to the listener only.
    receptionist_ws.receive_json()  # speaking
    patient_ws.receive_json()  # speaking
    receptionist_ws.receive_json()  # audio_reply_start
    receptionist_ws.receive_json()  # audio_reply_end


def test_end_session_sends_clinical_code_to_receptionist_only(monkeypatch):
    _patch_run_turn(monkeypatch)

    async def fake_get_clinical_code(note, systems=None):
        # Patient turns contribute their translated (receptionist-language) text to the note.
        assert note == "Patient: Cześć"
        suggestion = clinical_coding.ClinicalCodeSuggestion(
            code="R51", system="ICD-10", description="Headache",
            justification="Patient reports headache", confidence="high", review_flag=None,
        )
        return clinical_coding.ClinicalCodingResult(suggestions=[suggestion], coding_notes="Single complaint.")

    monkeypatch.setattr(websocket_handler.clinical_coding, "get_clinical_code", fake_get_clinical_code)

    with TestClient(app) as client:
        session_data = _create_session(client)
        session_id = session_data["session_id"]
        secret = session_data["receptionist_secret"]
        token = _token_from_join_url(session_data["patient_join_url"])

        with client.websocket_connect(f"/ws/receptionist/{session_id}?secret={secret}") as receptionist_ws:
            receptionist_ws.receive_json()  # waiting_for_patient

            with client.websocket_connect(f"/ws/patient/{token}") as patient_ws:
                _join_and_run_one_turn(receptionist_ws, patient_ws)

                receptionist_ws.send_json({"type": "end_session"})

                assert patient_ws.receive_json() == {"type": "status", "state": "ended", "detail": None}
                assert receptionist_ws.receive_json() == {"type": "status", "state": "ended", "detail": None}

                usage = receptionist_ws.receive_json()
                assert usage["type"] == "usage"
                assert usage["tts_characters"] == len("Cześć")
                expected_cost = elevenlabs_client.estimated_cost_usd(usage["stt_seconds"], usage["tts_characters"])
                assert usage["estimated_cost_usd"] == pytest.approx(round(expected_cost, 4), abs=0.0001)

                assert receptionist_ws.receive_json() == {"type": "status", "state": "coding", "detail": None}
                assert receptionist_ws.receive_json() == {
                    "type": "clinical_code",
                    "suggestions": [
                        {
                            "code": "R51",
                            "system": "ICD-10",
                            "description": "Headache",
                            "justification": "Patient reports headache",
                            "confidence": "high",
                            "review_flag": None,
                        }
                    ],
                    "coding_notes": "Single complaint.",
                }


def test_end_session_reports_coding_failure_to_receptionist(monkeypatch):
    _patch_run_turn(monkeypatch)

    async def fake_get_clinical_code(note, systems=None):
        raise clinical_coding.ClinicalCodingError("service unavailable")

    monkeypatch.setattr(websocket_handler.clinical_coding, "get_clinical_code", fake_get_clinical_code)

    with TestClient(app) as client:
        session_data = _create_session(client)
        session_id = session_data["session_id"]
        secret = session_data["receptionist_secret"]
        token = _token_from_join_url(session_data["patient_join_url"])

        with client.websocket_connect(f"/ws/receptionist/{session_id}?secret={secret}") as receptionist_ws:
            receptionist_ws.receive_json()  # waiting_for_patient

            with client.websocket_connect(f"/ws/patient/{token}") as patient_ws:
                _join_and_run_one_turn(receptionist_ws, patient_ws)

                receptionist_ws.send_json({"type": "end_session"})

                assert patient_ws.receive_json() == {"type": "status", "state": "ended", "detail": None}
                assert receptionist_ws.receive_json() == {"type": "status", "state": "ended", "detail": None}
                receptionist_ws.receive_json()  # usage
                assert receptionist_ws.receive_json() == {"type": "status", "state": "coding", "detail": None}
                assert receptionist_ws.receive_json() == {
                    "type": "error",
                    "code": "coding_failed",
                    "message": "service unavailable",
                }


def test_end_session_skips_coding_when_disabled(monkeypatch):
    _patch_run_turn(monkeypatch)

    async def fail_if_called(note, systems=None):
        raise AssertionError("clinical coding should not be called while CLINICAL_CODING_ENABLED is false")

    monkeypatch.setattr(websocket_handler.clinical_coding, "get_clinical_code", fail_if_called)
    monkeypatch.setattr(websocket_handler, "CLINICAL_CODING_ENABLED", False)

    with TestClient(app) as client:
        session_data = _create_session(client)
        session_id = session_data["session_id"]
        secret = session_data["receptionist_secret"]
        token = _token_from_join_url(session_data["patient_join_url"])

        with client.websocket_connect(f"/ws/receptionist/{session_id}?secret={secret}") as receptionist_ws:
            receptionist_ws.receive_json()  # waiting_for_patient

            with client.websocket_connect(f"/ws/patient/{token}") as patient_ws:
                _join_and_run_one_turn(receptionist_ws, patient_ws)

                receptionist_ws.send_json({"type": "end_session"})

                assert patient_ws.receive_json() == {"type": "status", "state": "ended", "detail": None}
                assert receptionist_ws.receive_json() == {"type": "status", "state": "ended", "detail": None}
                receptionist_ws.receive_json()  # usage
