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
    "Output ONLY the translation -- no commentary, no notes, no quotation marks. "
    "Even if the input is unclear, garbled, or appears to mix scripts or languages, still "
    "produce your best-effort literal translation of it. Never ask a clarifying question, "
    "never explain difficulty, and never request the text in a different format -- a hospital "
    "receptionist or patient will hear your output spoken aloud as if it came directly from "
    "the other person."
)

# Claude occasionally breaks the "output only the translation" instruction and responds
# conversationally instead -- e.g. asking for the text in a different script when the input is
# garbled. Left unchecked, that commentary gets spoken aloud to the receptionist or patient as
# if it were the other person's real words (confirmed live: a native Punjabi speaker's answer,
# mistranscribed by STT into unrelated Cyrillic text, produced a Claude response asking for
# "standard Punjabi script" instead of a translation -- which TTS then read out loud). A literal
# translation should never contain first-person commentary about the task itself, so treat any
# of these as a strong signal the response isn't a translation at all.
_COMMENTARY_MARKERS = (
    "i'm having difficulty", "i am having difficulty", "i cannot", "i can't", "i'm not able",
    "i am not able", "as an ai", "could you please provide", "please provide the text",
    "let me know if", "i need more context", "could you clarify", "translation challenging",
    "doesn't make sense", "does not make sense", "i'm unable", "i am unable",
)


def _looks_like_commentary(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _COMMENTARY_MARKERS)


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
    translated = text_block.text.strip()

    if _looks_like_commentary(translated):
        raise TranslationError(
            "Claude responded with commentary instead of a translation (likely garbled/unclear input)."
        )

    return translated
