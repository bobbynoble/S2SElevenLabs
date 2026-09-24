"""Per-turn orchestration: speech-to-text -> translate. Text-to-speech is streamed separately
by websocket_handler once translation is done, rather than being buffered here, so the listener
can start hearing the reply as soon as the first audio chunk arrives."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from . import elevenlabs_client, translator
from .languages import script_mismatch
from .models import ErrorCode, Speaker
from .session_manager import Session

logger = logging.getLogger(__name__)


class PipelineError(Exception):
    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class TurnResult:
    original_text: str
    original_lang: str
    translated_text: str
    translated_lang: str


def _langs_for(session: Session, speaker: Speaker) -> tuple[str, str]:
    if speaker == "patient":
        return session.patient_language or "en", session.receptionist_language
    return session.receptionist_language, session.patient_language or "en"


async def run_turn(session: Session, speaker: Speaker, audio_bytes: bytes) -> TurnResult:
    source_lang, target_lang = _langs_for(session, speaker)

    try:
        transcript = await elevenlabs_client.transcribe(audio_bytes, language_hint=source_lang)
    except elevenlabs_client.ElevenLabsError as exc:
        raise PipelineError("stt_failed", str(exc)) from exc

    # A garbled transcript translates and speaks fluently either way -- there's nothing in the
    # translated text itself to signal that the words going in were wrong. Confirmed live: a
    # Somali "what happened today?" mistranscribed into nonsense came back out as a fluent but
    # completely unrelated English sentence, with no sign anything had gone wrong. Catching it
    # here, before translation, stops that from reaching the other side silently.
    if transcript.low_confidence:
        logger.warning("Turn [%s]: low-confidence STT (min_word_logprob=%s)", source_lang, transcript.min_word_logprob)
        raise PipelineError(
            "stt_low_confidence",
            "Didn't catch that clearly -- please try again.",
        )
    if script_mismatch(transcript.text, source_lang):
        logger.warning("Turn [%s]: STT transcript script doesn't match expected language", source_lang)
        raise PipelineError(
            "stt_low_confidence",
            "Didn't catch that clearly -- please try again.",
        )

    try:
        translated_text = await translator.translate(transcript.text, source_lang, target_lang)
    except translator.TranslationError as exc:
        raise PipelineError("translation_failed", str(exc)) from exc

    # TEMPORARY: logged for live quality/accuracy monitoring during testing -- remove once
    # that's done, since this puts transcribed speech content into plain-text logs.
    logger.info(
        "TURN %s [%s->%s] original=%r translated=%r",
        speaker, source_lang, target_lang, transcript.text, translated_text,
    )

    return TurnResult(
        original_text=transcript.text,
        original_lang=source_lang,
        translated_text=translated_text,
        translated_lang=target_lang,
    )
