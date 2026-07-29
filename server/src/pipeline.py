"""Per-turn orchestration: speech-to-text -> translate -> text-to-speech."""

from __future__ import annotations

from dataclasses import dataclass

from . import elevenlabs_client, translator
from .languages import is_tts_supported
from .models import ErrorCode, Speaker
from .session_manager import Session


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
    audio: bytes | None


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

    try:
        translated_text = await translator.translate(transcript.text, source_lang, target_lang)
    except translator.TranslationError as exc:
        raise PipelineError("translation_failed", str(exc)) from exc

    audio: bytes | None = None
    if is_tts_supported(target_lang):
        try:
            audio = await elevenlabs_client.synthesize(translated_text, language=target_lang)
        except elevenlabs_client.ElevenLabsError as exc:
            raise PipelineError("tts_failed", str(exc)) from exc

    return TurnResult(
        original_text=transcript.text,
        original_lang=source_lang,
        translated_text=translated_text,
        translated_lang=target_lang,
        audio=audio,
    )
