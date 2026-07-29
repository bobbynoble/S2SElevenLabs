from types import SimpleNamespace

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


async def test_translate_skips_api_call_for_identical_languages(monkeypatch):
    def fail_client():
        raise AssertionError("Should not construct a client for identical source/target languages")

    monkeypatch.setattr(translator.anthropic, "AsyncAnthropic", fail_client)

    result = await translator.translate("Hello", "en", "en")

    assert result == "Hello"


async def test_translate_skips_api_call_for_empty_text(monkeypatch):
    def fail_client():
        raise AssertionError("Should not construct a client for empty text")

    monkeypatch.setattr(translator.anthropic, "AsyncAnthropic", fail_client)

    result = await translator.translate("   ", "en", "pl")

    assert result == ""
