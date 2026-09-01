import pytest

from elevenlabs.core.api_error import ApiError

from src import elevenlabs_client


class _FakeSTTResponse:
    def __init__(self, text="", language_code=None):
        self.text = text
        self.language_code = language_code


class _FakeSpeechToText:
    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error
        self.calls = []

    async def convert(self, **kwargs):
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        return self._response


class _FakeTextToSpeech:
    def __init__(self, chunks=None, error=None):
        self._chunks = chunks or []
        self._error = error
        self.calls = []

    async def convert(self, voice_id, **kwargs):
        self.calls.append((voice_id, kwargs))
        if self._error:
            raise self._error
        for chunk in self._chunks:
            yield chunk


class _FakeClient:
    def __init__(self, stt=None, tts=None):
        self.speech_to_text = stt
        self.text_to_speech = tts


async def test_transcribe_sends_wav_file_and_language_hint(monkeypatch):
    fake_stt = _FakeSpeechToText(response=_FakeSTTResponse(text="hello", language_code="en"))
    monkeypatch.setattr(elevenlabs_client, "_client", _FakeClient(stt=fake_stt))

    result = await elevenlabs_client.transcribe(b"\x00\x01" * 50, language_hint="en")

    assert result.text == "hello"
    assert result.detected_language == "en"
    kwargs = fake_stt.calls[0]
    assert kwargs["language_code"] == "en"
    assert kwargs["file"][2] == "audio/wav"


async def test_transcribe_raises_on_api_error(monkeypatch):
    error = ApiError(status_code=500, body="upstream error")
    fake_stt = _FakeSpeechToText(error=error)
    monkeypatch.setattr(elevenlabs_client, "_client", _FakeClient(stt=fake_stt))

    with pytest.raises(elevenlabs_client.ElevenLabsError):
        await elevenlabs_client.transcribe(b"\x00\x00")


async def test_synthesize_requires_voice_id(monkeypatch):
    monkeypatch.setattr(elevenlabs_client, "ELEVENLABS_DEFAULT_VOICE_ID", "")

    with pytest.raises(elevenlabs_client.ElevenLabsError):
        await elevenlabs_client.synthesize("hello")


async def test_synthesize_returns_audio_bytes(monkeypatch):
    fake_tts = _FakeTextToSpeech(chunks=[b"fake-", b"mp3-", b"bytes"])
    monkeypatch.setattr(elevenlabs_client, "_client", _FakeClient(tts=fake_tts))
    monkeypatch.setattr(elevenlabs_client, "ELEVENLABS_DEFAULT_VOICE_ID", "voice-123")

    audio = await elevenlabs_client.synthesize("hello")

    assert audio == b"fake-mp3-bytes"
    voice_id, _kwargs = fake_tts.calls[0]
    assert voice_id == "voice-123"


async def test_synthesize_uses_default_model_for_unlisted_language(monkeypatch):
    fake_tts = _FakeTextToSpeech(chunks=[b"audio"])
    monkeypatch.setattr(elevenlabs_client, "_client", _FakeClient(tts=fake_tts))
    monkeypatch.setattr(elevenlabs_client, "ELEVENLABS_DEFAULT_VOICE_ID", "voice-123")

    await elevenlabs_client.synthesize("hello", language="en")

    _voice_id, kwargs = fake_tts.calls[0]
    assert kwargs["model_id"] == elevenlabs_client.TTS_MODEL_ID


async def test_synthesize_uses_extended_model_for_extended_language(monkeypatch):
    fake_tts = _FakeTextToSpeech(chunks=[b"audio"])
    monkeypatch.setattr(elevenlabs_client, "_client", _FakeClient(tts=fake_tts))
    monkeypatch.setattr(elevenlabs_client, "ELEVENLABS_DEFAULT_VOICE_ID", "voice-123")

    await elevenlabs_client.synthesize("hello", language="ur")

    _voice_id, kwargs = fake_tts.calls[0]
    assert kwargs["model_id"] == elevenlabs_client.TTS_EXTENDED_MODEL_ID


async def test_synthesize_raises_on_api_error(monkeypatch):
    error = ApiError(status_code=400, body="bad request")
    fake_tts = _FakeTextToSpeech(error=error)
    monkeypatch.setattr(elevenlabs_client, "_client", _FakeClient(tts=fake_tts))
    monkeypatch.setattr(elevenlabs_client, "ELEVENLABS_DEFAULT_VOICE_ID", "voice-123")

    with pytest.raises(elevenlabs_client.ElevenLabsError):
        await elevenlabs_client.synthesize("hello")
