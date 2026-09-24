from types import SimpleNamespace

import pytest

from src import translator


class _FakeMessages:
    def __init__(self, response):
        self._response = response
        self.last_kwargs = None

    async def create(self, **kwargs):
        self.last_kwargs = kwargs
        return self._response


class _FakeAnthropicClient:
    def __init__(self, response):
        self.messages = _FakeMessages(response)


async def test_translate_calls_claude_with_language_names(monkeypatch):
    response = SimpleNamespace(content=[SimpleNamespace(type="text", text=" Cześć ")])
    fake_client = _FakeAnthropicClient(response)
    monkeypatch.setattr(translator.anthropic, "AsyncAnthropic", lambda: fake_client)

    result = await translator.translate("Hello", "en", "pl")

    assert result == "Cześć"
    prompt = fake_client.messages.last_kwargs["messages"][0]["content"]
    assert "English" in prompt
    assert "Polish" in prompt


async def test_translate_uses_language_specific_model_for_either_side(monkeypatch):
    response = SimpleNamespace(content=[SimpleNamespace(type="text", text="Hello")])
    fake_client = _FakeAnthropicClient(response)
    monkeypatch.setattr(translator.anthropic, "AsyncAnthropic", lambda: fake_client)
    monkeypatch.setattr(translator, "_LANGUAGE_MODELS", {"so": "strong-model"})

    await translator.translate("Salaan", "so", "en")
    assert fake_client.messages.last_kwargs["model"] == "strong-model"

    await translator.translate("Cześć", "pl", "en")
    assert fake_client.messages.last_kwargs["model"] == translator.ANTHROPIC_MODEL


async def test_translate_skips_api_call_for_identical_languages(monkeypatch):
    def fail_client():
        raise AssertionError("Should not construct a client for identical source/target languages")

    monkeypatch.setattr(translator.anthropic, "AsyncAnthropic", fail_client)

    result = await translator.translate("Hello", "en", "en")

    assert result == "Hello"


async def test_translate_raises_on_policy_refusal(monkeypatch):
    response = SimpleNamespace(
        stop_reason="refusal",
        content=[SimpleNamespace(type="text", text="I can't help with that.")],
    )
    fake_client = _FakeAnthropicClient(response)
    monkeypatch.setattr(translator.anthropic, "AsyncAnthropic", lambda: fake_client)

    with pytest.raises(translator.TranslationError):
        await translator.translate("Hello", "en", "pl")


async def test_translate_raises_on_commentary_instead_of_translation(monkeypatch):
    response = SimpleNamespace(
        stop_reason="end_turn",
        content=[SimpleNamespace(
            type="text",
            text=(
                "I'm having difficulty with this text as it appears to contain Cyrillic "
                "characters mixed with Punjabi content. Could you please provide the text in "
                "standard Punjabi script (Gurmukhi)?"
            ),
        )],
    )
    fake_client = _FakeAnthropicClient(response)
    monkeypatch.setattr(translator.anthropic, "AsyncAnthropic", lambda: fake_client)

    with pytest.raises(translator.TranslationError):
        await translator.translate("garbled input", "pa", "en")


async def test_translate_raises_on_self_correcting_commentary(monkeypatch):
    response = SimpleNamespace(
        stop_reason="end_turn",
        content=[SimpleNamespace(
            type="text",
            text="Por favor, siéntese.\n\nWait, let me provide the correct Spanish translation:\n\nTome asiento.",
        )],
    )
    fake_client = _FakeAnthropicClient(response)
    monkeypatch.setattr(translator.anthropic, "AsyncAnthropic", lambda: fake_client)

    with pytest.raises(translator.TranslationError):
        await translator.translate("Please take a seat.", "en", "es")


async def test_translate_raises_when_output_is_in_wrong_script(monkeypatch):
    # Urdu script returned for a Punjabi (Gurmukhi) request, as seen live.
    response = SimpleNamespace(
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text="براہ کرم بیٹھ جائیں، ایک نرس جلد ہی آپ کا نام پکاریں گی۔")],
    )
    fake_client = _FakeAnthropicClient(response)
    monkeypatch.setattr(translator.anthropic, "AsyncAnthropic", lambda: fake_client)

    with pytest.raises(translator.TranslationError):
        await translator.translate("Please take a seat.", "en", "pa")


async def test_translate_skips_api_call_for_empty_text(monkeypatch):
    def fail_client():
        raise AssertionError("Should not construct a client for empty text")

    monkeypatch.setattr(translator.anthropic, "AsyncAnthropic", fail_client)

    result = await translator.translate("   ", "en", "pl")

    assert result == ""
