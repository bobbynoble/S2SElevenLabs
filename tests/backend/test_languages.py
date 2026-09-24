from src.languages import (
    SUPPORTED_LANGUAGES,
    english_name_for,
    get_language,
    is_supported,
    is_tts_supported,
)


def test_language_codes_are_unique():
    codes = [lang.code for lang in SUPPORTED_LANGUAGES]
    assert len(codes) == len(set(codes))


def test_every_language_has_required_fields():
    for lang in SUPPORTED_LANGUAGES:
        assert lang.code
        assert lang.english_name
        assert lang.native_name


def test_english_is_supported_and_tts_supported():
    assert is_supported("en")
    assert is_tts_supported("en")


def test_unknown_code_is_not_supported():
    assert not is_supported("xx")
    assert get_language("xx") is None
    assert not is_tts_supported("xx")
    assert english_name_for("xx") == "xx"


def test_extended_model_languages_have_tts_support():
    for code in ("pa", "ur", "bn", "so", "fa", "ps", "vi", "sw", "ha", "lg", "rw", "luo", "twi"):
        lang = get_language(code)
        assert lang is not None
        assert lang.stt_supported is True
        assert lang.tts_supported is True


def test_tigrinya_is_stt_only():
    lang = get_language("ti")
    assert lang is not None
    assert lang.stt_supported is True
    assert lang.tts_supported is False


def test_languages_with_known_stt_accuracy_problems_are_flagged():
    # Sourced from ElevenLabs' own published Scribe WER tiers (so/ur/ps) and live testing on
    # this app (pa failed on a real speaker, ti returns unrelated text) -- see languages.py.
    for code in ("pa", "ur", "so", "ps", "ti", "lg", "rw", "luo", "twi"):
        lang = get_language(code)
        assert lang is not None
        assert lang.stt_low_confidence is True


def test_reliable_languages_are_not_flagged():
    for code in ("en", "pl", "fr", "bn", "fa", "vi", "sw", "ha"):
        lang = get_language(code)
        assert lang is not None
        assert lang.stt_low_confidence is False
