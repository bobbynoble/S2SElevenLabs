from types import SimpleNamespace

import pytest

from src import clinical_coding


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


def _fake_response(text):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


async def test_get_clinical_code_returns_parsed_suggestions(monkeypatch):
    response = _fake_response(
        """{"suggestions": [{"code": "R51", "system": "ICD-10", "description": "Headache",
        "justification": "Patient reports headache", "confidence": "high", "review_flag": null}],
        "coding_notes": "Single presenting complaint."}"""
    )
    fake_client = _FakeAnthropicClient(response)
    monkeypatch.setattr(clinical_coding.anthropic, "AsyncAnthropic", lambda: fake_client)

    result = await clinical_coding.get_clinical_code("Patient: I have a bad headache")

    assert len(result.suggestions) == 1
    suggestion = result.suggestions[0]
    assert suggestion.code == "R51"
    assert suggestion.system == "ICD-10"
    assert suggestion.confidence == "high"
    assert result.coding_notes == "Single presenting complaint."

    # The candidate list passed to Claude should include the headache code, retrieved by keyword.
    prompt = fake_client.messages.last_kwargs["messages"][0]["content"]
    assert "R51" in prompt
    assert "Headache" in prompt


async def test_get_clinical_code_strips_markdown_code_fences(monkeypatch):
    response = _fake_response('```json\n{"suggestions": [{"code": "R05", "system": "ICD-10"}]}\n```')
    fake_client = _FakeAnthropicClient(response)
    monkeypatch.setattr(clinical_coding.anthropic, "AsyncAnthropic", lambda: fake_client)

    result = await clinical_coding.get_clinical_code("Patient: I have a cough")

    assert result.suggestions[0].code == "R05"


async def test_get_clinical_code_raises_on_policy_refusal(monkeypatch):
    response = SimpleNamespace(
        stop_reason="refusal",
        content=[SimpleNamespace(type="text", text="I can't help with that.")],
    )
    fake_client = _FakeAnthropicClient(response)
    monkeypatch.setattr(clinical_coding.anthropic, "AsyncAnthropic", lambda: fake_client)

    with pytest.raises(clinical_coding.ClinicalCodingError):
        await clinical_coding.get_clinical_code("some note")


async def test_get_clinical_code_raises_on_invalid_json(monkeypatch):
    response = _fake_response("not valid json")
    fake_client = _FakeAnthropicClient(response)
    monkeypatch.setattr(clinical_coding.anthropic, "AsyncAnthropic", lambda: fake_client)

    with pytest.raises(clinical_coding.ClinicalCodingError):
        await clinical_coding.get_clinical_code("some note")


async def test_get_clinical_code_raises_on_empty_suggestions(monkeypatch):
    response = _fake_response('{"suggestions": []}')
    fake_client = _FakeAnthropicClient(response)
    monkeypatch.setattr(clinical_coding.anthropic, "AsyncAnthropic", lambda: fake_client)

    with pytest.raises(clinical_coding.ClinicalCodingError):
        await clinical_coding.get_clinical_code("some note")


async def test_get_clinical_code_raises_on_suggestion_missing_fields(monkeypatch):
    response = _fake_response('{"suggestions": [{"description": "no code here"}]}')
    fake_client = _FakeAnthropicClient(response)
    monkeypatch.setattr(clinical_coding.anthropic, "AsyncAnthropic", lambda: fake_client)

    with pytest.raises(clinical_coding.ClinicalCodingError):
        await clinical_coding.get_clinical_code("some note")


def test_retrieve_candidates_matches_by_keyword():
    candidates = clinical_coding._retrieve_candidates("Patient reports a severe headache since yesterday")
    codes = [code for code, _, _ in candidates]
    assert "R51" in codes


def test_retrieve_candidates_falls_back_to_full_set_when_no_keyword_match():
    candidates = clinical_coding._retrieve_candidates("xyzzy unrelated gibberish note")
    assert len(candidates) == clinical_coding.MAX_CANDIDATES


def test_retrieve_candidates_respects_systems_filter():
    candidates = clinical_coding._retrieve_candidates("headache", systems=["SNOMED"])
    assert candidates == []
