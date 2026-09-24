from datetime import datetime, timedelta, timezone

import pytest

from src import elevenlabs_client, pipeline, translator
from src.languages import script_mismatch
from src.session_manager import Session


def _make_session(patient_language="so", receptionist_language="en") -> Session:
    now = datetime.now(timezone.utc)
    return Session(
        id="session-1",
        patient_token="token",
        receptionist_secret="secret",
        created_at=now,
        expires_at=now + timedelta(minutes=30),
        patient_language=patient_language,
        receptionist_language=receptionist_language,
    )


async def test_run_turn_raises_stt_low_confidence_before_translating(monkeypatch):
    async def fake_transcribe(audio_bytes, language_hint=None):
        return elevenlabs_client.TranscriptResult(text="garbled", detected_language="so", min_word_logprob=-0.995)

    async def fake_translate(text, source_lang, target_lang):
        pytest.fail("translate() should not run when the transcript is low-confidence")

    monkeypatch.setattr(elevenlabs_client, "transcribe", fake_transcribe)
    monkeypatch.setattr(translator, "translate", fake_translate)

    session = _make_session()
    with pytest.raises(pipeline.PipelineError) as exc_info:
        await pipeline.run_turn(session, "patient", b"\x00\x00")

    assert exc_info.value.code == "stt_low_confidence"


async def test_run_turn_translates_normally_when_confident(monkeypatch):
    async def fake_transcribe(audio_bytes, language_hint=None):
        return elevenlabs_client.TranscriptResult(text="hello", detected_language="so", min_word_logprob=-0.02)

    async def fake_translate(text, source_lang, target_lang):
        return "translated"

    monkeypatch.setattr(elevenlabs_client, "transcribe", fake_transcribe)
    monkeypatch.setattr(translator, "translate", fake_translate)

    session = _make_session()
    result = await pipeline.run_turn(session, "patient", b"\x00\x00")

    assert result.translated_text == "translated"


async def test_run_turn_raises_stt_low_confidence_on_script_mismatch(monkeypatch):
    # Real captured failure: Scribe transcribed Punjabi (Gurmukhi) speech fluently in Devanagari
    # (Hindi) instead -- confident-sounding logprobs, wrong language entirely.
    async def fake_transcribe(audio_bytes, language_hint=None):
        return elevenlabs_client.TranscriptResult(
            text="नमस्ते, online धन्यवाद। आज केड़ी समस्या है?", detected_language="pa", min_word_logprob=-0.05
        )

    async def fake_translate(text, source_lang, target_lang):
        pytest.fail("translate() should not run when the transcript script doesn't match")

    monkeypatch.setattr(elevenlabs_client, "transcribe", fake_transcribe)
    monkeypatch.setattr(translator, "translate", fake_translate)

    session = _make_session(patient_language="pa")
    with pytest.raises(pipeline.PipelineError) as exc_info:
        await pipeline.run_turn(session, "patient", b"\x00\x00")

    assert exc_info.value.code == "stt_low_confidence"


async def test_run_turn_passes_correctly_scripted_punjabi(monkeypatch):
    async def fake_transcribe(audio_bytes, language_hint=None):
        return elevenlabs_client.TranscriptResult(
            text="ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ! ਆਉਣ ਲਈ ਧੰਨਵਾਦ। ਅੱਜ ਕੀ ਸਮੱਸਿਆ ਹੈ?", detected_language="pa", min_word_logprob=-0.2
        )

    async def fake_translate(text, source_lang, target_lang):
        return "translated"

    monkeypatch.setattr(elevenlabs_client, "transcribe", fake_transcribe)
    monkeypatch.setattr(translator, "translate", fake_translate)

    session = _make_session(patient_language="pa")
    result = await pipeline.run_turn(session, "patient", b"\x00\x00")

    assert result.translated_text == "translated"


def test_script_mismatch_ignores_languages_without_a_defined_script():
    assert script_mismatch("anything at all", "en") is False


def test_script_mismatch_ignores_very_short_transcripts():
    assert script_mismatch("ਹਾਂ", "pa") is False


async def test_run_turn_translates_when_confidence_signal_unavailable(monkeypatch):
    async def fake_transcribe(audio_bytes, language_hint=None):
        return elevenlabs_client.TranscriptResult(text="hello", detected_language="so", min_word_logprob=None)

    async def fake_translate(text, source_lang, target_lang):
        return "translated"

    monkeypatch.setattr(elevenlabs_client, "transcribe", fake_transcribe)
    monkeypatch.setattr(translator, "translate", fake_translate)

    session = _make_session()
    result = await pipeline.run_turn(session, "patient", b"\x00\x00")

    assert result.translated_text == "translated"
