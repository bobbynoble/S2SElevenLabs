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
"""

from __future__ import annotations

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
    LanguageInfo(code="pa", english_name="Punjabi", native_name="ਪੰਜਾਬੀ", stt_supported=True, tts_supported=True),
    LanguageInfo(code="ur", english_name="Urdu", native_name="اردو", stt_supported=True, tts_supported=True),
    LanguageInfo(code="bn", english_name="Bengali", native_name="বাংলা", stt_supported=True, tts_supported=True),
    LanguageInfo(code="so", english_name="Somali", native_name="Soomaali", stt_supported=True, tts_supported=True),
    LanguageInfo(code="fa", english_name="Farsi/Dari", native_name="فارسی", stt_supported=True, tts_supported=True),
    LanguageInfo(code="ps", english_name="Pashto", native_name="پښتو", stt_supported=True, tts_supported=True),
    LanguageInfo(code="vi", english_name="Vietnamese", native_name="Tiếng Việt", stt_supported=True, tts_supported=True),
    # Confirmed NOT reliable even with eleven_v3 -- STT round-trip returns unrelated text.
    LanguageInfo(code="ti", english_name="Tigrinya", native_name="ትግርኛ", stt_supported=True, tts_supported=False),
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
