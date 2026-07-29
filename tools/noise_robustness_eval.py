"""Synthetic noise-robustness evaluation for the ElevenLabs speech-to-text step.

Not part of the production pipeline or the pytest suite -- this makes real ElevenLabs API
calls (cost + latency), so it's a standalone script you run manually:

    python tools/noise_robustness_eval.py

For each test sentence it synthesizes clean speech via ElevenLabs TTS requesting raw PCM
output (so no MP3 decoding is needed), mixes in a synthetic hospital-reception soundscape --
HVAC rumble, hiss, an occasional monitor beep, and looped background chatter (itself
ElevenLabs-synthesized speech, since overlapping speech is a harder stressor for STT than
tones or noise) -- and runs each mix back through the same transcribe() call the app uses in
production. Results are scored against the known ground-truth text after normalizing spoken
number words and abbreviations, so the score reflects real transcription errors rather than
"10" vs "ten" style formatting differences.
"""

from __future__ import annotations

import array
import asyncio
import math
import random
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

import httpx
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")
sys.path.insert(0, str(REPO_ROOT / "server"))

from src import elevenlabs_client  # noqa: E402

SAMPLE_RATE = elevenlabs_client.PCM_SAMPLE_RATE_HZ

TEST_SENTENCES = [
    "I have an appointment with Doctor Garcia at ten o'clock.",
    "Yes, it's the third of June, nineteen eighty.",
]

CHATTER_PHRASE = (
    "Can you sign here please, that's brilliant, take a seat over there and someone "
    "will call you shortly."
)

# Each level is (label, component weights for the synthetic ambience, overall noise-to-speech
# loudness ratio). Weights are relative -- only their proportions to each other matter within
# a level; the trailing number controls how loud the whole mix is relative to the speech.
NOISE_LEVELS = [
    ("clean", {}, 0.0),
    ("quiet corridor", {"rumble": 1.0, "hiss": 0.5}, 0.2),
    ("busy reception", {"rumble": 0.6, "hiss": 0.5, "beep": 0.4, "chatter": 1.0}, 0.5),
    ("tannoy + trolley", {"rumble": 0.5, "hiss": 0.4, "beep": 0.9, "chatter": 1.3}, 0.75),
]


# ── Speech synthesis ──────────────────────────────────────────────────────────


async def synthesize_pcm(text: str) -> bytes:
    """Ask ElevenLabs for raw 16-bit PCM speech directly -- avoids decoding MP3."""
    voice = elevenlabs_client.ELEVENLABS_DEFAULT_VOICE_ID
    if not voice:
        raise elevenlabs_client.ElevenLabsError("ELEVENLABS_DEFAULT_VOICE_ID is not set.")
    async with httpx.AsyncClient(
        base_url=elevenlabs_client.ELEVENLABS_BASE_URL,
        headers={"xi-api-key": elevenlabs_client.ELEVENLABS_API_KEY},
        timeout=30.0,
    ) as client:
        response = await client.post(
            f"/v1/text-to-speech/{voice}",
            json={"text": text, "model_id": elevenlabs_client.TTS_MODEL_ID},
            params={"output_format": f"pcm_{SAMPLE_RATE}"},
        )
    if response.status_code != 200:
        raise elevenlabs_client.ElevenLabsError(
            f"ElevenLabs TTS (PCM) failed ({response.status_code}): {response.text}"
        )
    return response.content


def _pcm_bytes_to_array(pcm_bytes: bytes) -> array.array:
    samples = array.array("h")
    samples.frombytes(pcm_bytes[: len(pcm_bytes) - (len(pcm_bytes) % 2)])
    return samples


# ── Synthetic ambience components ────────────────────────────────────────────


def _rms(samples: array.array) -> float:
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples))


def _rumble_track(n: int) -> array.array:
    return array.array(
        "h",
        (int(4000 * math.sin(2 * math.pi * 80 * i / SAMPLE_RATE)) for i in range(n)),
    )


def _hiss_track(n: int) -> array.array:
    return array.array("h", (int(random.uniform(-1, 1) * 4000) for _ in range(n)))


def _beep_track(n: int) -> array.array:
    out = array.array("h", (0 for _ in range(n)))
    for i in range(n):
        t = i / SAMPLE_RATE
        if (t % 2.2) < 0.15:
            out[i] = int(math.sin(2 * math.pi * 1000 * t) * 5000)
    return out


def _tile_track(track: array.array, n: int) -> array.array:
    """Loop `track` (e.g. a chatter clip) end-to-end until it's at least `n` samples long."""
    if not track:
        return array.array("h", (0 for _ in range(n)))
    reps = (n // len(track)) + 1
    tiled = array.array("h", track.tolist() * reps)
    return tiled[:n]


def build_ambience(n_samples: int, chatter: array.array | None, weights: dict[str, float]) -> array.array:
    if not weights:
        return array.array("h", (0 for _ in range(n_samples)))
    rumble = _rumble_track(n_samples)
    hiss = _hiss_track(n_samples)
    beep = _beep_track(n_samples)
    chat = _tile_track(chatter, n_samples) if chatter else array.array("h", (0 for _ in range(n_samples)))
    out = array.array("h", (0 for _ in range(n_samples)))
    for i in range(n_samples):
        v = (
            weights.get("rumble", 0) * rumble[i]
            + weights.get("hiss", 0) * hiss[i]
            + weights.get("beep", 0) * beep[i]
            + weights.get("chatter", 0) * chat[i]
        )
        out[i] = max(-32767, min(32767, int(v)))
    return out


def mix(speech: array.array, noise: array.array, level: float) -> bytes:
    if level <= 0:
        return speech.tobytes()
    speech_rms = _rms(speech)
    noise_rms = _rms(noise) or 1.0
    gain = (speech_rms * level) / noise_rms
    mixed = array.array("h", (0 for _ in range(len(speech))))
    for i in range(len(speech)):
        v = speech[i] + noise[i % len(noise)] * gain
        mixed[i] = max(-32767, min(32767, int(v)))
    return mixed.tobytes()


# ── Scoring ───────────────────────────────────────────────────────────────────

_ONES = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}
_TEENS = {
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_ORDINAL_WORDS = {
    "first": "1", "second": "2", "third": "3", "fourth": "4", "fifth": "5", "sixth": "6",
    "seventh": "7", "eighth": "8", "ninth": "9", "tenth": "10", "eleventh": "11",
    "twelfth": "12", "thirteenth": "13", "fourteenth": "14", "fifteenth": "15",
    "sixteenth": "16", "seventeenth": "17", "eighteenth": "18", "nineteenth": "19",
    "twentieth": "20", "thirtieth": "30",
}


def _word_value(word: str) -> int | None:
    return _ONES.get(word, _TEENS.get(word, _TENS.get(word)))


def normalize(text: str) -> str:
    """Reduce spoken-number and abbreviation variation so scoring reflects real
    transcription errors, not "Dr." vs "Doctor" / "10" vs "ten" formatting noise."""
    text = text.lower()
    text = re.sub(r"\bdr\.?\b", "doctor", text)
    text = text.replace("o'clock", "").replace("oclock", "")
    text = re.sub(r"[^\w\s-]", " ", text)
    text = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()

    tokens = text.split()
    out: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in _ORDINAL_WORDS:
            out.append(_ORDINAL_WORDS[tok])
            i += 1
            continue
        if tok in _TEENS and i + 1 < len(tokens) and tokens[i + 1] in _TENS:
            out.append(f"{_TEENS[tok]}{_TENS[tokens[i + 1]]:02d}")
            i += 2
            continue
        if tok in _TENS and i + 1 < len(tokens) and tokens[i + 1] in _ONES:
            out.append(str(_TENS[tok] + _ONES[tokens[i + 1]]))
            i += 2
            continue
        val = _word_value(tok)
        out.append(str(val) if val is not None else tok)
        i += 1
    return " ".join(out)


def similarity(expected: str, actual: str) -> float:
    return SequenceMatcher(None, normalize(expected), normalize(actual)).ratio()


# ── Runner ────────────────────────────────────────────────────────────────────


async def main() -> None:
    print(f"Voice: {elevenlabs_client.ELEVENLABS_DEFAULT_VOICE_ID}  STT model: {elevenlabs_client.STT_MODEL_ID}\n")

    chatter: array.array | None = None
    try:
        print("Synthesizing background chatter clip...")
        chatter_pcm = await synthesize_pcm(CHATTER_PHRASE)
        chatter = _pcm_bytes_to_array(chatter_pcm)
        print(f"  ok ({len(chatter) / SAMPLE_RATE:.1f}s)\n")
    except elevenlabs_client.ElevenLabsError as exc:
        print(f"  could not synthesize chatter, continuing without it: {exc}\n")

    by_level: dict[str, list[float]] = {}

    for sentence in TEST_SENTENCES:
        print(f"Sentence: {sentence!r}")
        try:
            pcm_bytes = await synthesize_pcm(sentence)
        except elevenlabs_client.ElevenLabsError as exc:
            print(f"  Could not synthesize clean speech: {exc}\n")
            continue

        speech = _pcm_bytes_to_array(pcm_bytes)

        for label, weights, level in NOISE_LEVELS:
            noise = build_ambience(len(speech), chatter, weights)
            mixed_bytes = mix(speech, noise, level)
            try:
                transcript = await elevenlabs_client.transcribe(mixed_bytes, language_hint="en")
                sim = similarity(sentence, transcript.text)
                by_level.setdefault(label, []).append(sim)
                print(f"  [{label:17s}] similarity={sim:.2f}  -> {transcript.text!r}")
            except elevenlabs_client.ElevenLabsError as exc:
                by_level.setdefault(label, []).append(0.0)
                print(f"  [{label:17s}] ERROR: {exc}")
        print()

    print("=" * 70)
    print("Summary -- average similarity to ground truth (1.0 = exact match)")
    print("=" * 70)
    for label, _, _ in NOISE_LEVELS:
        sims = by_level.get(label, [])
        avg = sum(sims) / len(sims) if sims else 0.0
        print(f"{label:20s} {avg:.2f}  ({len(sims)} sample(s))")


if __name__ == "__main__":
    asyncio.run(main())
