import pytest

from elevenlabs.core.api_error import ApiError

from src import elevenlabs_client


class _FakeWord:
    def __init__(self, logprob, type="word"):
        self.logprob = logprob
        self.type = type


class _FakeSTTResponse:
    def __init__(self, text="", language_code=None, words=None):
        self.text = text
        self.language_code = language_code
        self.words = words


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

    async def stream(self, voice_id, **kwargs):
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


async def test_transcribe_captures_min_word_logprob(monkeypatch):
    words = [_FakeWord(-0.02), _FakeWord(-0.4), _FakeWord(-0.995)]
    fake_stt = _FakeSpeechToText(response=_FakeSTTResponse(text="hi", words=words))
    monkeypatch.setattr(elevenlabs_client, "_client", _FakeClient(stt=fake_stt))

    result = await elevenlabs_client.transcribe(b"\x00\x01" * 50)

    assert result.min_word_logprob == pytest.approx(-0.995)
    assert result.low_confidence is True


async def test_transcribe_ignores_non_word_entries_for_confidence(monkeypatch):
    words = [_FakeWord(-0.02), _FakeWord(-0.995, type="audio_event")]
    fake_stt = _FakeSpeechToText(response=_FakeSTTResponse(text="hi", words=words))
    monkeypatch.setattr(elevenlabs_client, "_client", _FakeClient(stt=fake_stt))

    result = await elevenlabs_client.transcribe(b"\x00\x01" * 50)

    assert result.min_word_logprob == pytest.approx(-0.02)
    assert result.low_confidence is False


async def test_transcribe_without_words_has_no_confidence_signal(monkeypatch):
    fake_stt = _FakeSpeechToText(response=_FakeSTTResponse(text="hi", words=None))
    monkeypatch.setattr(elevenlabs_client, "_client", _FakeClient(stt=fake_stt))

    result = await elevenlabs_client.transcribe(b"\x00\x01" * 50)

    assert result.min_word_logprob is None
    assert result.low_confidence is False


async def test_transcribe_raises_on_api_error(monkeypatch):
    error = ApiError(status_code=500, body="upstream error")
    fake_stt = _FakeSpeechToText(error=error)
    monkeypatch.setattr(elevenlabs_client, "_client", _FakeClient(stt=fake_stt))

    with pytest.raises(elevenlabs_client.ElevenLabsError):
        await elevenlabs_client.transcribe(b"\x00\x00")


async def _collect(stream):
    return b"".join([chunk async for chunk in stream])


async def test_synthesize_stream_requires_voice_id(monkeypatch):
    monkeypatch.setattr(elevenlabs_client, "ELEVENLABS_DEFAULT_VOICE_ID", "")

    with pytest.raises(elevenlabs_client.ElevenLabsError):
        await _collect(elevenlabs_client.synthesize_stream("hello"))


async def test_synthesize_stream_yields_audio_chunks(monkeypatch):
    fake_tts = _FakeTextToSpeech(chunks=[b"pcm-", b"chunk-", b"bytes"])
    monkeypatch.setattr(elevenlabs_client, "_client", _FakeClient(tts=fake_tts))
    monkeypatch.setattr(elevenlabs_client, "ELEVENLABS_DEFAULT_VOICE_ID", "voice-123")

    audio = await _collect(elevenlabs_client.synthesize_stream("hello"))

    assert audio == b"pcm-chunk-bytes"
    voice_id, _kwargs = fake_tts.calls[0]
    assert voice_id == "voice-123"


async def test_synthesize_stream_uses_default_model_for_unlisted_language(monkeypatch):
    fake_tts = _FakeTextToSpeech(chunks=[b"audio"])
    monkeypatch.setattr(elevenlabs_client, "_client", _FakeClient(tts=fake_tts))
    monkeypatch.setattr(elevenlabs_client, "ELEVENLABS_DEFAULT_VOICE_ID", "voice-123")

    await _collect(elevenlabs_client.synthesize_stream("hello", language="en"))

    _voice_id, kwargs = fake_tts.calls[0]
    assert kwargs["model_id"] == elevenlabs_client.TTS_MODEL_ID
    assert kwargs["optimize_streaming_latency"] == elevenlabs_client.TTS_STREAMING_LATENCY


async def test_synthesize_stream_uses_extended_model_for_extended_language(monkeypatch):
    fake_tts = _FakeTextToSpeech(chunks=[b"audio"])
    monkeypatch.setattr(elevenlabs_client, "_client", _FakeClient(tts=fake_tts))
    monkeypatch.setattr(elevenlabs_client, "ELEVENLABS_DEFAULT_VOICE_ID", "voice-123")

    await _collect(elevenlabs_client.synthesize_stream("hello", language="ur"))

    _voice_id, kwargs = fake_tts.calls[0]
    assert kwargs["model_id"] == elevenlabs_client.TTS_EXTENDED_MODEL_ID
    # eleven_v3 rejects this param outright (confirmed live: 400 unsupported_model).
    assert "optimize_streaming_latency" not in kwargs


async def test_synthesize_stream_raises_on_api_error(monkeypatch):
    error = ApiError(status_code=400, body="bad request")
    fake_tts = _FakeTextToSpeech(error=error)
    monkeypatch.setattr(elevenlabs_client, "_client", _FakeClient(tts=fake_tts))
    monkeypatch.setattr(elevenlabs_client, "ELEVENLABS_DEFAULT_VOICE_ID", "voice-123")

    with pytest.raises(elevenlabs_client.ElevenLabsError):
        await _collect(elevenlabs_client.synthesize_stream("hello"))


def test_estimated_cost_usd_combines_stt_and_tts():
    monkeypatch_stt = elevenlabs_client.STT_PRICE_PER_SECOND
    monkeypatch_tts = elevenlabs_client.TTS_PRICE_PER_CHAR

    cost = elevenlabs_client.estimated_cost_usd(stt_seconds=3600, tts_characters=1_000_000)

    assert cost == pytest.approx(3600 * monkeypatch_stt + 1_000_000 * monkeypatch_tts)


def test_estimated_cost_usd_zero_usage_is_zero():
    assert elevenlabs_client.estimated_cost_usd(stt_seconds=0, tts_characters=0) == 0
