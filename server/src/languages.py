"""Single source of truth for supported languages. The frontend fetches this list
via GET /api/languages rather than duplicating it client-side.

tts_supported reflects ElevenLabs' documented eleven_multilingual_v2 language coverage as of
this codebase's writing. Several high-demand NHS interpreting languages are NOT confirmed to
have ElevenLabs voice support (flagged below) -- those languages still get full live text
captions from the pipeline, just no synthesized voice reply. Verify current ElevenLabs
language/voice coverage before treating any tts_supported=True entry as production-confirmed.

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
    # Flagged: not confirmed in ElevenLabs' documented TTS voice coverage -- verify before relying
    # on synthesized voice replies for these. STT (Scribe) coverage is broader and likely supports them.
    LanguageInfo(code="pa", english_name="Punjabi", native_name="ਪੰਜਾਬੀ", stt_supported=True, tts_supported=False),
    LanguageInfo(code="ur", english_name="Urdu", native_name="اردو", stt_supported=True, tts_supported=False),
    LanguageInfo(code="bn", english_name="Bengali", native_name="বাংলা", stt_supported=True, tts_supported=False),
    LanguageInfo(code="so", english_name="Somali", native_name="Soomaali", stt_supported=True, tts_supported=False),
    LanguageInfo(code="fa", english_name="Farsi/Dari", native_name="فارسی", stt_supported=True, tts_supported=False),
    LanguageInfo(code="ps", english_name="Pashto", native_name="پښتو", stt_supported=True, tts_supported=False),
    LanguageInfo(code="ti", english_name="Tigrinya", native_name="ትግርኛ", stt_supported=True, tts_supported=False),
    LanguageInfo(code="vi", english_name="Vietnamese", native_name="Tiếng Việt", stt_supported=True, tts_supported=False),
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
