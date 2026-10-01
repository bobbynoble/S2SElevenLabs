"""Per-turn orchestration: speech-to-text -> translate. Text-to-speech is streamed separately
by websocket_handler once translation is done, rather than being buffered here, so the listener
can start hearing the reply as soon as the first audio chunk arrives."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from . import elevenlabs_client, translator
from .languages import english_name_for, script_mismatch
from .models import ErrorCode, Speaker
from .session_manager import Session

logger = logging.getLogger(__name__)

MIN_TURN_SECONDS = 0.5
_NO_SPEECH_MESSAGE = "No speech heard -- hold the button down while you speak."
# Scribe's sound labels, e.g. "[clicking]"; tag_audio_events is off, this is the backstop.
_AUDIO_EVENT_TAG = re.compile(r"\[[^\]]*\]")

# Confirmed live (Luganda, Scribe Medical): "Leero nnagudde" (today I fell) came back as "Leero
# nna good day" -- English sound-alikes, confident logprobs, translated as "Today I'm having a
# good day". Two common English words in a row inside a non-English transcript is the tell; a
# single loanword ("result", "X-ray") is normal. Tested on 9 real Luganda turns and 168
# translations across 14 Latin-script languages: flagged only that one. Words of 3+ letters,
# since shorter ones collide with other languages ("na", "mu", "ni").
_COMMON_ENGLISH = frozenset("""
the and you that was for are with his they this have from one had word but not what all were when
your can said there use each which she how their will other about out many then them these some her
would make like him into time has look two more write see number way could people than first water
been call who its now find long down day did get come made may part over new sound take only little
work know place year live back give most very after thing our just name good sentence man think say
great where help through much before line right too mean old any same tell boy follow came want show
also around form three small set put end does another well large must big even such because turn here
why ask went men read need land different home move try kind hand picture again change off play spell
air away animal house point page letter mother answer found study still learn should world high every
near add food between own below country plant last school father keep tree never start city earth eye
light thought head under story saw left few while along might close something seem next hard open
example begin life always those both paper together got group often run important until children side
feet car mile night walk white sea began grow took river four carry state once book hear stop without
second later miss idea enough eat face watch far really almost let above girl sometimes mountain cut
young talk soon list song being leave family today feel pain hurt fell fall sick doctor nurse
please thank thanks morning evening tonight yesterday tomorrow week fine okay yes having doing going
""".split())


def _has_english_run(text: str) -> bool:
    words = re.findall(r"[a-z]+", text.lower())
    return any(a in _COMMON_ENGLISH and b in _COMMON_ENGLISH for a, b in zip(words, words[1:]))


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
    min_word_logprob: float | None = None


def _langs_for(session: Session, speaker: Speaker) -> tuple[str, str]:
    if speaker == "patient":
        return session.patient_language or "en", session.receptionist_language
    return session.receptionist_language, session.patient_language or "en"


async def run_turn(session: Session, speaker: Speaker, audio_bytes: bytes) -> TurnResult:
    source_lang, target_lang = _langs_for(session, speaker)

    # Confirmed live: testers set both sides to Hausa (and separately both to English), and the
    # app silently echoed every turn back untranslated. Refuse up front, before paying for STT.
    if source_lang == target_lang:
        raise PipelineError(
            "same_language",
            f"Both people are set to {english_name_for(source_lang)}, so there's nothing to translate. "
            "End this session and start again: the reception screen picks the receptionist's own "
            "language, and the patient picks theirs on the patient screen.",
        )

    # A quick tap on a phone sends a few hundred ms of button-click noise (seen live: three
    # "[clicking]" turns translated and sent to reception in one Luganda session).
    if len(audio_bytes) < MIN_TURN_SECONDS * elevenlabs_client.PCM_SAMPLE_RATE_HZ * 2:
        raise PipelineError("no_speech", _NO_SPEECH_MESSAGE)

    try:
        transcript = await elevenlabs_client.transcribe(audio_bytes, language_hint=source_lang)
    except elevenlabs_client.ElevenLabsError as exc:
        raise PipelineError("stt_failed", str(exc)) from exc

    heard = _AUDIO_EVENT_TAG.sub("", transcript.text).strip()
    if not heard:
        raise PipelineError("no_speech", _NO_SPEECH_MESSAGE)

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
    if script_mismatch(heard, source_lang):
        logger.warning("Turn [%s]: STT transcript script doesn't match expected language", source_lang)
        raise PipelineError(
            "stt_low_confidence",
            "Didn't catch that clearly -- please try again.",
        )
    if source_lang != "en" and _has_english_run(heard):
        logger.warning("Turn [%s]: English words in a non-English transcript, likely misheard", source_lang)
        raise PipelineError(
            "stt_low_confidence",
            "Didn't catch that clearly -- please try again.",
        )

    try:
        translated_text = await translator.translate(heard, source_lang, target_lang)
    except translator.TranslationError as exc:
        raise PipelineError("translation_failed", str(exc)) from exc

    return TurnResult(
        original_text=heard,
        original_lang=source_lang,
        translated_text=translated_text,
        translated_lang=target_lang,
        min_word_logprob=transcript.min_word_logprob,
    )
