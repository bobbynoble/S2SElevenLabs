"""Wrapper around the official ElevenLabs SDK for the two calls this app needs:
speech-to-text (Scribe) and text-to-speech.

POC decision: uses the official `elevenlabs` SDK rather than calling the REST API directly
over httpx. The SDK's AsyncElevenLabs client accepts a custom base_url, so ELEVENLABS_BASE_URL
can still be pointed at a UK/EU-resident endpoint once confirmed with ElevenLabs -- switching
to the SDK does not give up that flexibility, which was the original reason httpx was used
directly. A single client is created at import time and reused for every call rather than
opening a fresh connection per request.
"""

from __future__ import annotations

import io
import os
import wave
from dataclasses import dataclass

from elevenlabs import AsyncElevenLabs
from elevenlabs.core.api_error import ApiError

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_BASE_URL = os.getenv("ELEVENLABS_BASE_URL", "https://api.elevenlabs.io")
ELEVENLABS_DEFAULT_VOICE_ID = os.getenv("ELEVENLABS_DEFAULT_VOICE_ID", "")
STT_MODEL_ID = os.getenv("ELEVENLABS_STT_MODEL_ID", "scribe_v1")
TTS_MODEL_ID = os.getenv("ELEVENLABS_TTS_MODEL_ID", "eleven_multilingual_v2")
TTS_EXTENDED_MODEL_ID = os.getenv("ELEVENLABS_TTS_EXTENDED_MODEL_ID", "eleven_v3")

# Languages eleven_multilingual_v2 doesn't cover but eleven_v3 does -- confirmed by
# round-tripping generated audio back through Scribe STT and getting the original text back.
# eleven_v3 is noticeably slower per call, so it's used only for these, not as the default.
EXTENDED_MODEL_LANGUAGES = {"pa", "ur", "bn", "so", "fa", "ps", "vi"}

PCM_SAMPLE_RATE_HZ = 16000

_client = AsyncElevenLabs(api_key=ELEVENLABS_API_KEY, base_url=ELEVENLABS_BASE_URL)


@dataclass
class TranscriptResult:
    text: str
    detected_language: str | None


class ElevenLabsError(Exception):
    pass


def _pcm16_to_wav(pcm_bytes: bytes, sample_rate: int = PCM_SAMPLE_RATE_HZ) -> bytes:
    """Wrap headerless 16-bit mono PCM (as sent by the browser's AudioWorklet) in a WAV
    container, since the STT endpoint expects a recognized audio file format."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    return buffer.getvalue()


async def transcribe(pcm_audio: bytes, language_hint: str | None = None) -> TranscriptResult:
    wav_bytes = _pcm16_to_wav(pcm_audio)
    kwargs = {"model_id": STT_MODEL_ID, "file": ("turn.wav", wav_bytes, "audio/wav")}
    if language_hint:
        kwargs["language_code"] = language_hint

    try:
        response = await _client.speech_to_text.convert(**kwargs)
    except ApiError as exc:
        raise ElevenLabsError(f"ElevenLabs STT failed ({exc.status_code}): {exc.body}") from exc

    return TranscriptResult(
        text=getattr(response, "text", "") or "",
        detected_language=getattr(response, "language_code", None),
    )


async def synthesize(text: str, language: str | None = None, voice_id: str | None = None) -> bytes:
    voice = voice_id or ELEVENLABS_DEFAULT_VOICE_ID
    if not voice:
        raise ElevenLabsError("No ElevenLabs voice_id configured (ELEVENLABS_DEFAULT_VOICE_ID).")

    model_id = TTS_EXTENDED_MODEL_ID if language in EXTENDED_MODEL_LANGUAGES else TTS_MODEL_ID

    try:
        chunks = [
            chunk
            async for chunk in _client.text_to_speech.convert(
                voice, text=text, model_id=model_id, output_format="mp3_44100_128"
            )
        ]
    except ApiError as exc:
        raise ElevenLabsError(f"ElevenLabs TTS failed ({exc.status_code}): {exc.body}") from exc

    return b"".join(chunks)
