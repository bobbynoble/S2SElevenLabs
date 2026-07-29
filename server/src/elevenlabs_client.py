"""Thin wrapper around the ElevenLabs REST API for the two calls this app needs:
speech-to-text (Scribe) and text-to-speech (multilingual v2).

Uses httpx directly (rather than the ElevenLabs SDK) so ELEVENLABS_BASE_URL can be pointed at a
UK/EU-resident endpoint, once confirmed with ElevenLabs, without depending on SDK support for a
custom base URL. Endpoint shapes reflect ElevenLabs' documented v1 REST API as of this codebase's
writing -- reverify against current docs before relying on this in production, since these are
called out in the project plan as not independently verified in this session.
"""

from __future__ import annotations

import io
import os
import wave
from dataclasses import dataclass

import httpx

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


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=ELEVENLABS_BASE_URL,
        headers={"xi-api-key": ELEVENLABS_API_KEY},
        timeout=30.0,
    )


async def transcribe(pcm_audio: bytes, language_hint: str | None = None) -> TranscriptResult:
    wav_bytes = _pcm16_to_wav(pcm_audio)
    data = {"model_id": STT_MODEL_ID}
    if language_hint:
        data["language_code"] = language_hint

    async with _client() as client:
        response = await client.post(
            "/v1/speech-to-text",
            data=data,
            files={"file": ("turn.wav", wav_bytes, "audio/wav")},
        )
    if response.status_code != 200:
        raise ElevenLabsError(f"ElevenLabs STT failed ({response.status_code}): {response.text}")

    body = response.json()
    return TranscriptResult(
        text=body.get("text", ""),
        detected_language=body.get("language_code"),
    )


async def synthesize(text: str, language: str | None = None, voice_id: str | None = None) -> bytes:
    voice = voice_id or ELEVENLABS_DEFAULT_VOICE_ID
    if not voice:
        raise ElevenLabsError("No ElevenLabs voice_id configured (ELEVENLABS_DEFAULT_VOICE_ID).")

    model_id = TTS_EXTENDED_MODEL_ID if language in EXTENDED_MODEL_LANGUAGES else TTS_MODEL_ID

    async with _client() as client:
        response = await client.post(
            f"/v1/text-to-speech/{voice}",
            json={"text": text, "model_id": model_id},
            params={"output_format": "mp3_44100_128"},
        )
    if response.status_code != 200:
        raise ElevenLabsError(f"ElevenLabs TTS failed ({response.status_code}): {response.text}")

    return response.content
