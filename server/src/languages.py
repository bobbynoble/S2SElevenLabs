"""Single source of truth for supported languages. The frontend fetches this list
via GET /api/languages rather than duplicating it client-side.

tts_supported was originally set from ElevenLabs' documented eleven_multilingual_v2 language
coverage. Seven languages below (see elevenlabs_client.py's _EXTENDED_MODEL_LANGUAGES) are
synthesized via the newer eleven_v3 model instead, since v2 doesn't cover them -- confirmed by
round-tripping generated audio back through Scribe STT and getting the original text back, not
just by checking the model's documented language list. Tigrinya is the one exception: eleven_v3
accepts a Tigrinya request and returns audio, but the STT round-trip comes back as unrelated
words, so it stays tts_supported=False pending an actually-confirmed model/voice.

stt_supported is True for all entries: ElevenLabs Scribe documents much broader language
coverage than the TTS models.

stt_low_confidence flags languages where transcription is known to be unreliable, so this isn't
just tribal knowledge sitting in a chat log -- sourced from two things:
  1. ElevenLabs' own published Scribe v2 word-error-rate tiers
     (elevenlabs.io/docs/overview/capabilities/speech-to-text#supported-languages) -- Somali,
     Urdu, and Pashto all sit in their worst published tier, "Moderate, >25-50% WER".
  2. Live testing on this app: Pashto failed a round-trip test outright (transcribed clean
     synthetic audio as "[outro jingle]", i.e. didn't recognize it as speech at all); Punjabi
     round-trips fine on clean synthetic audio but failed completely on a real native speaker
     (garbled into unrelated Cyrillic text) -- a reminder that a clean round-trip test doesn't
     prove real-world reliability, only that config/audio format are correct.
Tigrinya isn't in ElevenLabs' rated list at all and is already excluded from tts_supported, but
carries the same flag here since the underlying problem is STT, not TTS.
"""

from __future__ import annotations

import re

from .models import LanguageInfo

SUPPORTED_LANGUAGES: list[LanguageInfo] = [
    LanguageInfo(code="en", english_name="English", native_name="English", stt_supported=True, tts_supported=True),
    LanguageInfo(code="pl", english_name="Polish", native_name="Polski", stt_supported=True, tts_supported=True),
    LanguageInfo(code="ro", english_name="Romanian", native_name="Română", stt_supported=True, tts_supported=True),
    LanguageInfo(code="ar", english_name="Arabic", native_name="العربية", stt_supported=True, tts_supported=True),
    LanguageInfo(code="pt", english_name="Portuguese", native_name="Português", stt_supported=True, tts_supported=True),
    LanguageInfo(code="es", english_name="Spanish", native_name="Español", stt_supported=True, tts_supported=True),
    LanguageInfo(code="fr", english_name="French", native_name="Français", stt_supported=True, tts_supported=True),
    LanguageInfo(code="zh", english_name="Mandarin Chinese", native_name="中文", stt_supported=True, tts_supported=True),
    LanguageInfo(code="tr", english_name="Turkish", native_name="Türkçe", stt_supported=True, tts_supported=True),
    # Synthesized via eleven_v3 (not the default eleven_multilingual_v2) -- round-trip verified.
    # pa: Good WER tier, but failed completely on a real native speaker -- see module docstring.
    LanguageInfo(code="pa", english_name="Punjabi", native_name="ਪੰਜਾਬੀ", stt_supported=True, tts_supported=True, stt_low_confidence=True),
    # ur: ElevenLabs' own "Moderate, >25-50% WER" tier.
    LanguageInfo(code="ur", english_name="Urdu", native_name="اردو", stt_supported=True, tts_supported=True, stt_low_confidence=True),
    LanguageInfo(code="bn", english_name="Bengali", native_name="বাংলা", stt_supported=True, tts_supported=True),
    # so: ElevenLabs' own "Moderate, >25-50% WER" tier -- matches this app's own live findings.
    LanguageInfo(code="so", english_name="Somali", native_name="Soomaali", stt_supported=True, tts_supported=True, stt_low_confidence=True),
    LanguageInfo(code="fa", english_name="Farsi/Dari", native_name="فارسی", stt_supported=True, tts_supported=True),
    # ps: ElevenLabs' own "Moderate, >25-50% WER" tier; failed outright in live testing.
    LanguageInfo(code="ps", english_name="Pashto", native_name="پښتو", stt_supported=True, tts_supported=True, stt_low_confidence=True),
    LanguageInfo(code="vi", english_name="Vietnamese", native_name="Tiếng Việt", stt_supported=True, tts_supported=True),
    # Confirmed NOT reliable even with eleven_v3 -- STT round-trip returns unrelated text.
    LanguageInfo(code="ti", english_name="Tigrinya", native_name="ትግርኛ", stt_supported=True, tts_supported=False, stt_low_confidence=True),
]

_BY_CODE: dict[str, LanguageInfo] = {lang.code: lang for lang in SUPPORTED_LANGUAGES}


def get_language(code: str) -> LanguageInfo | None:
    return _BY_CODE.get(code)


def is_supported(code: str) -> bool:
    return code in _BY_CODE


def is_tts_supported(code: str) -> bool:
    lang = _BY_CODE.get(code)
    return bool(lang and lang.tts_supported)


def english_name_for(code: str) -> str:
    lang = _BY_CODE.get(code)
    return lang.english_name if lang else code


# Per-word confidence doesn't catch every failure: confirmed live that Scribe can mishear
# Punjabi speech as Hindi and transcribe it fluently in Devanagari instead of Gurmukhi --
# "ਆਉਣ ਲਈ ਧੰਨਵਾਦ" (Gurmukhi) came back as "धन्यवाद" (Devanagari) with unremarkable per-word
# confidence, since the model isn't uncertain, it's just answering a different question. Only
# covers scripts distinct enough from Latin that a wrong-language transcript is detectable this
# way; Latin-script languages share too much of the same alphabet for this check to help there.
# Also applied to translator output: confirmed live that Claude can answer a Punjabi request in
# Urdu script and then append its own self-correction ("Wait, let me provide the correct
# Punjabi translation..."), all of which TTS would read aloud.
_SCRIPT_PATTERNS: dict[str, re.Pattern[str]] = {
    "ar": re.compile(r"[؀-ۿ]"),
    "fa": re.compile(r"[؀-ۿ]"),
    "ur": re.compile(r"[؀-ۿ]"),
    "ps": re.compile(r"[؀-ۿ]"),
    "pa": re.compile(r"[਀-੿]"),
    "bn": re.compile(r"[ঀ-৿]"),
    "zh": re.compile(r"[一-鿿]"),
    "ti": re.compile(r"[ሀ-፿]"),
}
_MIN_ALPHA_CHARS_FOR_SCRIPT_CHECK = 5
_MIN_EXPECTED_SCRIPT_RATIO = 0.4


def script_mismatch(text: str, lang_code: str) -> bool:
    pattern = _SCRIPT_PATTERNS.get(lang_code)
    if pattern is None:
        return False
    alpha_chars = [c for c in text if c.isalpha()]
    if len(alpha_chars) < _MIN_ALPHA_CHARS_FOR_SCRIPT_CHECK:
        return False
    expected = sum(1 for c in alpha_chars if pattern.match(c))
    return (expected / len(alpha_chars)) < _MIN_EXPECTED_SCRIPT_RATIO
