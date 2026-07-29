"""Text-translation step, run between ElevenLabs STT and ElevenLabs TTS. Uses Claude rather than
ElevenLabs' own Dubbing API, which is batch/file-oriented and too slow for live turn-taking."""

from __future__ import annotations

import os

import anthropic

from .languages import english_name_for

ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")

SYSTEM_PROMPT = (
    "You are a precise reception/medical interpreter for a hospital front desk. "
    "Translate the given text exactly, preserving meaning and tone. "
    "Output ONLY the translation -- no commentary, no notes, no quotation marks."
)


class TranslationError(Exception):
    pass


async def translate(text: str, source_lang: str, target_lang: str) -> str:
    if not text.strip():
        return ""
    if source_lang == target_lang:
        return text

    client = anthropic.AsyncAnthropic()
    prompt = (
        f"Translate the following text from {english_name_for(source_lang)} "
        f"to {english_name_for(target_lang)}:\n\n{text}"
    )
    try:
        response = await client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError as exc:
        raise TranslationError(str(exc)) from exc

    # Claude's own safety classifiers can intervene mid-generation and stop the response
    # short of an actual translation. Left unchecked, whatever partial/refusal text came back
    # would get spoken to the patient or receptionist as if it were a real reply -- a genuinely
    # dangerous failure mode if the original content was something urgent. Surface it as a
    # clear error instead of silently passing it through.
    if getattr(response, "stop_reason", None) == "refusal":
        raise TranslationError("Claude declined to translate this content (policy refusal).")

    text_block = next((b for b in response.content if b.type == "text"), None)
    if text_block is None:
        raise TranslationError("Claude returned no text content for the translation.")
    return text_block.text.strip()
