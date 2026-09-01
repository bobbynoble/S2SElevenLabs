"""Measures real end-to-end latency of ElevenLabs' Dubbing API, to check whether it could
replace the Claude translation step (see server/src/translator.py's docstring, which currently
rules it out on the grounds that Dubbing is "batch/file-oriented and too slow for live
turn-taking").

Not part of the production pipeline or the pytest suite -- makes real ElevenLabs API calls
(cost + latency), so it's a standalone script you run manually:

    python tools/dubbing_latency_probe.py

Synthesizes a short English test phrase via ElevenLabs TTS (so the probe doesn't depend on a
pre-recorded sample file), submits it to the Dubbing API for translation into Spanish, then
polls until the project reaches a terminal status -- timing the whole submit-to-ready window,
which is the number that actually matters for a press-and-hold conversational turn.
"""

from __future__ import annotations

import asyncio
import io
import sys
import time
import wave
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")
sys.path.insert(0, str(REPO_ROOT / "server"))

from src import elevenlabs_client  # noqa: E402

TEST_PHRASE = "What brings you in today? Please take a seat, the nurse will call you shortly."
SOURCE_LANG = "en"
TARGET_LANG = "es"

POLL_INTERVAL_SECONDS = 4
POLL_TIMEOUT_SECONDS = 360
TERMINAL_STATUSES = {"dubbed", "dubbing_failed", "failed"}


def _mp3_bytes_to_wav(mp3_bytes: bytes) -> bytes:
    """The Dubbing API wants a real audio file; ElevenLabs' TTS output (mp3_44100_128) already
    qualifies, so this just labels it -- kept as a hook in case a WAV re-wrap is ever needed."""
    return mp3_bytes


async def main() -> None:
    print(f"Synthesizing a {len(TEST_PHRASE)}-char test phrase via ElevenLabs TTS...")
    t_synth_start = time.monotonic()
    audio_bytes = await elevenlabs_client.synthesize(TEST_PHRASE, language=SOURCE_LANG)
    t_synth = time.monotonic() - t_synth_start
    print(f"  done in {t_synth:.1f}s ({len(audio_bytes)} bytes)\n")

    client = elevenlabs_client._client  # reuse the app's configured AsyncElevenLabs client

    print(f"Submitting to Dubbing API: {SOURCE_LANG} -> {TARGET_LANG}...")
    t_submit_start = time.monotonic()
    response = await client.dubbing.create(
        file=("probe.mp3", io.BytesIO(_mp3_bytes_to_wav(audio_bytes)), "audio/mpeg"),
        name="latency-probe",
        source_lang=SOURCE_LANG,
        target_lang=TARGET_LANG,
        num_speakers=1,
        watermark=False,
    )
    t_submit = time.monotonic() - t_submit_start
    dubbing_id = response.dubbing_id
    print(f"  submitted in {t_submit:.1f}s, dubbing_id={dubbing_id!r}\n")

    print("Polling for completion (this is the number that matters)...")
    t_poll_start = time.monotonic()
    status = None
    while True:
        elapsed = time.monotonic() - t_poll_start
        if elapsed > POLL_TIMEOUT_SECONDS:
            print(f"  gave up after {elapsed:.0f}s (timeout) -- last status: {status!r}")
            break

        meta = await client.dubbing.get(dubbing_id=dubbing_id)
        status = getattr(meta, "status", None)
        print(f"  t+{elapsed:5.1f}s  status={status!r}")

        if status in TERMINAL_STATUSES:
            break
        await asyncio.sleep(POLL_INTERVAL_SECONDS)

    t_total = time.monotonic() - t_submit_start
    print()
    print("=" * 60)
    print(f"TTS synth time:            {t_synth:6.1f}s  (not part of the Dubbing path itself)")
    print(f"Dubbing submit call:       {t_submit:6.1f}s")
    print(f"Dubbing submit -> ready:   {t_total:6.1f}s")
    print(f"Final status:              {status!r}")
    print("=" * 60)
    print(
        "Compare t_total above to the Claude translate() call, which is typically well under "
        "2s -- that's the real basis for the 'too slow for live turn-taking' conclusion."
    )


if __name__ == "__main__":
    asyncio.run(main())
