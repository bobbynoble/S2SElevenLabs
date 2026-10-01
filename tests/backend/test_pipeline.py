from datetime import datetime, timedelta, timezone

import pytest

from src import elevenlabs_client, pipeline, translator
from src.languages import script_mismatch
from src.session_manager import Session

_ONE_SECOND = b"\x00\x00" * 16000


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
        await pipeline.run_turn(session, "patient", _ONE_SECOND)

    assert exc_info.value.code == "stt_low_confidence"


async def test_run_turn_refuses_same_language_on_both_sides_before_stt(monkeypatch):
    async def fake_transcribe(audio_bytes, language_hint=None):
        pytest.fail("transcribe() should not run when both sides share a language")

    monkeypatch.setattr(elevenlabs_client, "transcribe", fake_transcribe)

    session = _make_session(patient_language="ha", receptionist_language="ha")
    with pytest.raises(pipeline.PipelineError) as exc_info:
        await pipeline.run_turn(session, "receptionist", _ONE_SECOND)

    assert exc_info.value.code == "same_language"
    assert "Hausa" in exc_info.value.message


async def test_run_turn_translates_normally_when_confident(monkeypatch):
    async def fake_transcribe(audio_bytes, language_hint=None):
        return elevenlabs_client.TranscriptResult(text="hello", detected_language="so", min_word_logprob=-0.02)

    async def fake_translate(text, source_lang, target_lang):
        return "translated"

    monkeypatch.setattr(elevenlabs_client, "transcribe", fake_transcribe)
    monkeypatch.setattr(translator, "translate", fake_translate)

    session = _make_session()
    result = await pipeline.run_turn(session, "patient", _ONE_SECOND)

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
        await pipeline.run_turn(session, "patient", _ONE_SECOND)

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
    result = await pipeline.run_turn(session, "patient", _ONE_SECOND)

    assert result.translated_text == "translated"


async def test_run_turn_refuses_a_tap_before_stt(monkeypatch):
    async def fake_transcribe(audio_bytes, language_hint=None):
        pytest.fail("transcribe() should not run for a turn shorter than MIN_TURN_SECONDS")

    monkeypatch.setattr(elevenlabs_client, "transcribe", fake_transcribe)

    with pytest.raises(pipeline.PipelineError) as exc_info:
        await pipeline.run_turn(_make_session(), "patient", _ONE_SECOND[:3200])

    assert exc_info.value.code == "no_speech"


async def test_run_turn_refuses_a_transcript_of_only_sound_labels(monkeypatch):
    # Real capture: phone taps transcribed as "[clicking]" and sent on as a translated turn.
    async def fake_transcribe(audio_bytes, language_hint=None):
        return elevenlabs_client.TranscriptResult(text="[clicking]", detected_language="lg", min_word_logprob=None)

    async def fake_translate(text, source_lang, target_lang):
        pytest.fail("translate() should not run when nothing was said")

    monkeypatch.setattr(elevenlabs_client, "transcribe", fake_transcribe)
    monkeypatch.setattr(translator, "translate", fake_translate)

    with pytest.raises(pipeline.PipelineError) as exc_info:
        await pipeline.run_turn(_make_session(patient_language="lg"), "patient", _ONE_SECOND)

    assert exc_info.value.code == "no_speech"


async def test_run_turn_strips_sound_labels_around_speech(monkeypatch):
    async def fake_transcribe(audio_bytes, language_hint=None):
        return elevenlabs_client.TranscriptResult(text="[clicking] Omutwe gunnuma", detected_language="lg", min_word_logprob=-0.1)

    seen = {}

    async def fake_translate(text, source_lang, target_lang):
        seen["text"] = text
        return "My head hurts."

    monkeypatch.setattr(elevenlabs_client, "transcribe", fake_transcribe)
    monkeypatch.setattr(translator, "translate", fake_translate)

    result = await pipeline.run_turn(_make_session(patient_language="lg"), "patient", _ONE_SECOND)

    assert seen["text"] == "Omutwe gunnuma"
    assert result.original_text == "Omutwe gunnuma"


async def test_run_turn_refuses_english_sound_alikes_in_a_non_english_transcript(monkeypatch):
    # Real capture: Luganda "today I fell" heard as "Leero nna good day", then translated as
    # "Today I'm having a good day".
    async def fake_transcribe(audio_bytes, language_hint=None):
        return elevenlabs_client.TranscriptResult(text="Leero nna good day", detected_language="lg", min_word_logprob=-0.1)

    async def fake_translate(text, source_lang, target_lang):
        pytest.fail("translate() should not run on a likely mis-hearing")

    monkeypatch.setattr(elevenlabs_client, "transcribe", fake_transcribe)
    monkeypatch.setattr(translator, "translate", fake_translate)

    with pytest.raises(pipeline.PipelineError) as exc_info:
        await pipeline.run_turn(_make_session(patient_language="lg"), "patient", _ONE_SECOND)

    assert exc_info.value.code == "stt_low_confidence"


@pytest.mark.parametrize("text", ["Njagala kumanya result ez'omusaayi", "Omugongo gunnuma njagala kugenda ku X-ray"])
async def test_run_turn_allows_single_english_loanwords(monkeypatch, text):
    async def fake_transcribe(audio_bytes, language_hint=None):
        return elevenlabs_client.TranscriptResult(text=text, detected_language="lg", min_word_logprob=-0.1)

    async def fake_translate(text, source_lang, target_lang):
        return "translated"

    monkeypatch.setattr(elevenlabs_client, "transcribe", fake_transcribe)
    monkeypatch.setattr(translator, "translate", fake_translate)

    result = await pipeline.run_turn(_make_session(patient_language="lg"), "patient", _ONE_SECOND)

    assert result.translated_text == "translated"


def test_script_mismatch_allows_latin_drug_names_inside_urdu():
    assert script_mismatch("میں ہر صبح Metformin, Remepro اور Atorvastatin لیتا ہوں", "ur") is False


def test_script_mismatch_flags_an_all_latin_transcript():
    assert script_mismatch("I take metformin every morning", "ur") is True


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
    result = await pipeline.run_turn(session, "patient", _ONE_SECOND)

    assert result.translated_text == "translated"
