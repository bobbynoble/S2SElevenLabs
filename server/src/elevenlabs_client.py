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
STT_MODEL_ID = os.getenv("ELEVENLABS_STT_MODEL_ID", "scribe_v2")
# Scribe returns a log-probability per transcribed word (range (-inf, 0], closer to 0 is more
# confident). Calibrated live against two real failures caught in testing: a Somali round-trip
# that silently dropped "what happened today?" had its worst word at -0.995, and a Punjabi
# round-trip that hallucinated the English word "online" scored it at -0.875 -- while every
# correctly-transcribed word across both languages, including legitimately quiet/short ones,
# stayed at -0.52 or better. -0.6 sits in the gap between those two groups.
STT_LOW_CONFIDENCE_LOGPROB = float(os.getenv("ELEVENLABS_STT_LOW_CONFIDENCE_LOGPROB", "-0.6"))
TTS_MODEL_ID = os.getenv("ELEVENLABS_TTS_MODEL_ID", "eleven_multilingual_v2")
TTS_EXTENDED_MODEL_ID = os.getenv("ELEVENLABS_TTS_EXTENDED_MODEL_ID", "eleven_v3")

# Languages eleven_multilingual_v2 doesn't cover but eleven_v3 does -- confirmed by
# round-tripping generated audio back through Scribe STT and getting the original text back.
# eleven_v3 is noticeably slower per call, so it's used only for these, not as the default.
EXTENDED_MODEL_LANGUAGES = {"pa", "ur", "bn", "so", "fa", "ps", "vi", "sw", "ha", "lg", "rw", "luo", "twi"}

PCM_SAMPLE_RATE_HZ = 16000

# Both calls below send enable_logging=False (ElevenLabs Zero Retention Mode, Enterprise-only):
# patient audio and text are held only in memory for the request and never stored. Without it,
# every request was confirmed live to land in the account's history, stored in the US by default.

# From this workspace's own Enterprise API pricing (Subscription.docx): Scribe v2 STT is
# $0.22/hour, Multilingual v2 and v3 TTS are both $100/1M characters.
STT_PRICE_PER_SECOND = float(os.getenv("ELEVENLABS_STT_PRICE_PER_HOUR", "0.22")) / 3600
TTS_PRICE_PER_CHAR = float(os.getenv("ELEVENLABS_TTS_PRICE_PER_1M_CHARS", "100.00")) / 1_000_000

# 0-4; higher trades a little pronunciation accuracy for lower time-to-first-audio-chunk.
# Not accepted by eleven_v3 at all (see synthesize_stream).
TTS_STREAMING_LATENCY = int(os.getenv("ELEVENLABS_TTS_STREAMING_LATENCY", "2"))

_client = AsyncElevenLabs(api_key=ELEVENLABS_API_KEY, base_url=ELEVENLABS_BASE_URL)


@dataclass
class TranscriptResult:
    text: str
    detected_language: str | None
    min_word_logprob: float | None = None

    @property
    def low_confidence(self) -> bool:
        return self.min_word_logprob is not None and self.min_word_logprob < STT_LOW_CONFIDENCE_LOGPROB


class ElevenLabsError(Exception):
    pass


def estimated_cost_usd(stt_seconds: float, tts_characters: int) -> float:
    return stt_seconds * STT_PRICE_PER_SECOND + tts_characters * TTS_PRICE_PER_CHAR


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
    kwargs = {"model_id": STT_MODEL_ID, "file": ("turn.wav", wav_bytes, "audio/wav"), "enable_logging": False}
    if language_hint:
        kwargs["language_code"] = language_hint

    try:
        response = await _client.speech_to_text.convert(**kwargs)
    except ApiError as exc:
        raise ElevenLabsError(f"ElevenLabs STT failed ({exc.status_code}): {exc.body}") from exc

    word_logprobs = [
        w.logprob for w in getattr(response, "words", None) or [] if getattr(w, "type", None) == "word"
    ]

    return TranscriptResult(
        text=getattr(response, "text", "") or "",
        detected_language=getattr(response, "language_code", None),
        min_word_logprob=min(word_logprobs) if word_logprobs else None,
    )


async def synthesize_stream(text: str, language: str | None = None, voice_id: str | None = None):
    """Yields raw 16-bit PCM chunks as ElevenLabs generates them, rather than collecting the
    whole reply before returning anything -- confirmed live that the streaming endpoint starts
    delivering audio in ~0.5-0.7s versus 2-4s+ to wait for the full non-streaming convert()
    response, which is most of a turn's felt delay once STT/translation are done. Callers
    forward each chunk to the listener as it arrives instead of buffering the whole thing."""
    voice = voice_id or ELEVENLABS_DEFAULT_VOICE_ID
    if not voice:
        raise ElevenLabsError("No ElevenLabs voice_id configured (ELEVENLABS_DEFAULT_VOICE_ID).")

    model_id = TTS_EXTENDED_MODEL_ID if language in EXTENDED_MODEL_LANGUAGES else TTS_MODEL_ID
    kwargs = {"model_id": model_id, "output_format": "pcm_16000", "enable_logging": False}
    # eleven_v3 rejects this param outright (confirmed live: 400 unsupported_model) -- it's only
    # meaningful for the faster default model.
    if model_id != TTS_EXTENDED_MODEL_ID:
        kwargs["optimize_streaming_latency"] = TTS_STREAMING_LATENCY

    try:
        async for chunk in _client.text_to_speech.stream(voice, text=text, **kwargs):
            yield chunk
    except ApiError as exc:
        raise ElevenLabsError(f"ElevenLabs TTS failed ({exc.status_code}): {exc.body}") from exc
