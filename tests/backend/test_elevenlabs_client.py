import pytest

from src import elevenlabs_client


class _FakeResponse:
    def __init__(self, status_code, json_data=None, content=b""):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.content = content
        self.text = "upstream error"

    def json(self):
        return self._json_data


class _FakeAsyncClient:
    def __init__(self, calls, response):
        self._calls = calls
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def post(self, url, **kwargs):
        self._calls.append((url, kwargs))
        return self._response


async def test_transcribe_sends_wav_file_and_language_hint(monkeypatch):
    calls = []
    fake_response = _FakeResponse(200, json_data={"text": "hello", "language_code": "en"})
    monkeypatch.setattr(
        elevenlabs_client.httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(calls, fake_response)
    )

    result = await elevenlabs_client.transcribe(b"\x00\x01" * 50, language_hint="en")

    assert result.text == "hello"
    assert result.detected_language == "en"
    url, kwargs = calls[0]
    assert url == "/v1/speech-to-text"
    assert kwargs["data"]["language_code"] == "en"
    assert kwargs["files"]["file"][2] == "audio/wav"


async def test_transcribe_raises_on_error_status(monkeypatch):
    calls = []
    fake_response = _FakeResponse(500)
    monkeypatch.setattr(
        elevenlabs_client.httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(calls, fake_response)
    )

    with pytest.raises(elevenlabs_client.ElevenLabsError):
        await elevenlabs_client.transcribe(b"\x00\x00")


async def test_synthesize_requires_voice_id(monkeypatch):
    monkeypatch.setattr(elevenlabs_client, "ELEVENLABS_DEFAULT_VOICE_ID", "")

    with pytest.raises(elevenlabs_client.ElevenLabsError):
        await elevenlabs_client.synthesize("hello")


async def test_synthesize_returns_audio_bytes(monkeypatch):
    calls = []
    fake_response = _FakeResponse(200, content=b"fake-mp3-bytes")
    monkeypatch.setattr(
        elevenlabs_client.httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(calls, fake_response)
    )
    monkeypatch.setattr(elevenlabs_client, "ELEVENLABS_DEFAULT_VOICE_ID", "voice-123")

    audio = await elevenlabs_client.synthesize("hello")

    assert audio == b"fake-mp3-bytes"
    url, _kwargs = calls[0]
    assert url == "/v1/text-to-speech/voice-123"


async def test_synthesize_uses_default_model_for_unlisted_language(monkeypatch):
    calls = []
    fake_response = _FakeResponse(200, content=b"fake-mp3-bytes")
    monkeypatch.setattr(
        elevenlabs_client.httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(calls, fake_response)
    )
    monkeypatch.setattr(elevenlabs_client, "ELEVENLABS_DEFAULT_VOICE_ID", "voice-123")

    await elevenlabs_client.synthesize("hello", language="en")

    _url, kwargs = calls[0]
    assert kwargs["json"]["model_id"] == elevenlabs_client.TTS_MODEL_ID


async def test_synthesize_uses_extended_model_for_extended_language(monkeypatch):
    calls = []
    fake_response = _FakeResponse(200, content=b"fake-mp3-bytes")
    monkeypatch.setattr(
        elevenlabs_client.httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(calls, fake_response)
    )
    monkeypatch.setattr(elevenlabs_client, "ELEVENLABS_DEFAULT_VOICE_ID", "voice-123")

    await elevenlabs_client.synthesize("hello", language="ur")

    _url, kwargs = calls[0]
    assert kwargs["json"]["model_id"] == elevenlabs_client.TTS_EXTENDED_MODEL_ID
