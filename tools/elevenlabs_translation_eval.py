"""Benchmarks ElevenLabs' Dubbing API as a translation step, compared against the Claude-based
translate() this app actually uses (see server/src/translator.py).

ElevenLabs has no plain text-translation endpoint -- the only relevant capability is Dubbing,
which is audio-in/audio-out and asynchronous (create a dub, poll until done, fetch the result).
To translate text through it, this script has to: synthesize the source text to speech via
ElevenLabs TTS, submit that audio to Dubbing, poll for completion, then pull the translated text
back out of the dub's transcript. That round-trip is what translator.py's docstring already
flags as "too slow for live turn-taking" -- this script exists to put a real number on that
claim and to eyeball the resulting translation quality, not to propose swapping the pipeline.

Not part of the production pipeline or the pytest suite -- makes real ElevenLabs and Anthropic
API calls (each phrase burns Dubbing API credits), so it's a standalone script you run manually:

    python tools/elevenlabs_translation_eval.py

Dubbed audio for each phrase is saved under logs/elevenlabs_dubbing_eval/ so you can listen to
it; each dub is deleted from the ElevenLabs account after its results are fetched.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")
sys.path.insert(0, str(REPO_ROOT / "server"))

sys.stdout.reconfigure(encoding="utf-8")

from elevenlabs import AsyncElevenLabs  # noqa: E402
from elevenlabs.core.api_error import ApiError  # noqa: E402

from src import translator  # noqa: E402
from src.elevenlabs_client import synthesize  # noqa: E402

OUTPUT_DIR = REPO_ROOT / "logs" / "elevenlabs_dubbing_eval"

# Kept small on purpose -- each phrase/language pair costs Dubbing API credits and takes roughly
# 30-90s to complete. Extend these once you've confirmed the approach is worth the cost.
PHRASES = [
    "Please take a seat, the doctor will call you in a few minutes.",
    "Do you have any allergies we should know about?",
]
TARGET_LANGUAGES = ["es", "pl"]

POLL_INTERVAL_S = 3
POLL_TIMEOUT_S = 180

_client = AsyncElevenLabs(
    api_key=os.getenv("ELEVENLABS_API_KEY", ""),
    base_url=os.getenv("ELEVENLABS_BASE_URL", "https://api.elevenlabs.io"),
)


class DubbingFailed(Exception):
    pass


async def _wait_for_dub(dubbing_id: str) -> None:
    deadline = time.monotonic() + POLL_TIMEOUT_S
    while time.monotonic() < deadline:
        status = await _client.dubbing.get(dubbing_id)
        if status.status == "dubbed":
            return
        if status.status == "failed":
            raise DubbingFailed(status.error or "dubbing failed with no error detail")
        await asyncio.sleep(POLL_INTERVAL_S)
    raise DubbingFailed(f"timed out after {POLL_TIMEOUT_S}s waiting for dub {dubbing_id}")


async def translate_via_elevenlabs(text: str, source_lang: str, target_lang: str) -> tuple[str, bytes]:
    """Returns (translated_text, dubbed_audio_bytes). Raises DubbingFailed/ApiError on failure."""
    source_audio = await synthesize(text, language=source_lang)

    created = await _client.dubbing.create(
        file=("phrase.mp3", source_audio, "audio/mpeg"),
        source_lang=source_lang,
        target_lang=target_lang,
        num_speakers=1,
        # This account's plan requires the watermark on Dubbing output; it doesn't affect the
        # translated text or timing this script is measuring.
        watermark=True,
    )
    dubbing_id = created.dubbing_id

    try:
        await _wait_for_dub(dubbing_id)

        transcript = await _client.dubbing.transcript.get_transcript_for_dub(
            dubbing_id, target_lang, format_type="json"
        )
        translated_text = " ".join(u.text for u in transcript.utterances).strip()

        audio_chunks = [chunk async for chunk in _client.dubbing.audio.get(dubbing_id, target_lang)]
        dubbed_audio = b"".join(audio_chunks)
    finally:
        try:
            await _client.dubbing.delete(dubbing_id)
        except ApiError:
            pass  # best-effort cleanup; not worth failing the eval over

    return translated_text, dubbed_audio


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    failures = []

    for phrase in PHRASES:
        print(f"EN: {phrase!r}")
        for lang in TARGET_LANGUAGES:
            claude_start = time.monotonic()
            try:
                claude_text = await translator.translate(phrase, "en", lang)
                claude_elapsed = time.monotonic() - claude_start
            except translator.TranslationError as exc:
                failures.append((phrase, lang, "claude", str(exc)))
                print(f"  [{lang}] claude:     REFUSED/ERROR: {exc}")
                claude_text = None
                claude_elapsed = None

            eleven_start = time.monotonic()
            try:
                eleven_text, eleven_audio = await translate_via_elevenlabs(phrase, "en", lang)
                eleven_elapsed = time.monotonic() - eleven_start
                audio_path = OUTPUT_DIR / f"{lang}_{abs(hash(phrase))}.mp3"
                audio_path.write_bytes(eleven_audio)
            except (DubbingFailed, ApiError) as exc:
                failures.append((phrase, lang, "elevenlabs", str(exc)))
                print(f"  [{lang}] elevenlabs: FAILED: {exc}")
                eleven_text = None
                eleven_elapsed = None
                audio_path = None

            if claude_text is not None:
                print(f"  [{lang}] claude:     {claude_elapsed:5.1f}s  {claude_text!r}")
            if eleven_text is not None:
                print(f"  [{lang}] elevenlabs: {eleven_elapsed:5.1f}s  {eleven_text!r}")
                print(f"  [{lang}] elevenlabs audio saved to {audio_path}")
        print()

    print("=" * 70)
    if failures:
        print(f"{len(failures)} failure(s):")
        for phrase, lang, engine, err in failures:
            print(f"  {phrase!r} -> {lang} ({engine}): {err}")
    else:
        print("No failures. Compare the claude/elevenlabs timings and text above, and listen")
        print(f"to the saved audio under {OUTPUT_DIR} to judge translation quality.")


if __name__ == "__main__":
    asyncio.run(main())
