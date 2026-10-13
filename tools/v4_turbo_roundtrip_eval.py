"""Round-trip comparison of eleven_v4_turbo against the TTS model each language uses today.

For every tts_supported language: translate a medical phrase from English with the app's own
translator, synthesize it with the current model AND with eleven_v4_turbo (identical text and
voice), transcribe each back with the app's own Scribe call, and back-translate to English.
A model passes for a language when the transcript closely matches the text it was given.

Not part of the production pipeline or the pytest suite -- makes real ElevenLabs and Anthropic
calls, so run it manually:

    python tools/v4_turbo_roundtrip_eval.py

Audio for every synthesis is saved under logs/v4_turbo_eval/ so it can be listened to.
"""

from __future__ import annotations

import asyncio
import csv
import difflib
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")
sys.path.insert(0, str(REPO_ROOT / "server"))
sys.stdout.reconfigure(encoding="utf-8")

from elevenlabs.core.api_error import ApiError  # noqa: E402

from src import elevenlabs_client as el  # noqa: E402
from src import translator  # noqa: E402
from src.languages import SUPPORTED_LANGUAGES  # noqa: E402

CANDIDATE_MODEL = "eleven_v4_turbo"
OUTPUT_DIR = REPO_ROOT / "logs" / "v4_turbo_eval"
PASS_SIMILARITY = 0.80

PHRASES = [
    "Do you have any allergies to medicines?",
    "Where does it hurt, and how long have you had the pain?",
]

_sem = asyncio.Semaphore(4)
_translations: dict[tuple[str, str], str] = {}


def current_model(lang: str) -> str:
    return el.TTS_EXTENDED_MODEL_ID if lang in el.EXTENDED_MODEL_LANGUAGES else el.TTS_MODEL_ID


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, normalise(a), normalise(b)).ratio()


async def synthesize(text: str, model: str) -> tuple[bytes, float, float, str]:
    """Returns (pcm, first_byte_s, total_s, note). Mirrors el.synthesize_stream's request,
    but with the model chosen explicitly."""
    kwargs = {"model_id": model, "output_format": "pcm_16000", "enable_logging": False}
    note = ""
    if model in el.STREAMING_LATENCY_MODELS:
        kwargs["optimize_streaming_latency"] = el.TTS_STREAMING_LATENCY
    for attempt in range(2):
        start = time.monotonic()
        first = None
        chunks = []
        try:
            async for chunk in el._client.text_to_speech.stream(el.ELEVENLABS_DEFAULT_VOICE_ID, text=text, **kwargs):
                if first is None:
                    first = time.monotonic() - start
                chunks.append(chunk)
            return b"".join(chunks), first or 0.0, time.monotonic() - start, note
        except ApiError as exc:
            if attempt == 0 and "optimize_streaming_latency" in kwargs and exc.status_code == 400:
                note = f"rejected optimize_streaming_latency ({exc.status_code}); retried without"
                kwargs.pop("optimize_streaming_latency")
                continue
            raise
    raise RuntimeError("unreachable")


async def run_one(lang: str, phrase_no: int, model: str) -> dict:
    async with _sem:
        target_text = _translations[(lang, PHRASES[phrase_no])]
        row = {"lang": lang, "phrase": phrase_no + 1, "model": model, "target_text": target_text}
        try:
            pcm, first_s, total_s, note = await synthesize(target_text, model)
            (OUTPUT_DIR / f"{lang}_p{phrase_no + 1}_{model}.wav").write_bytes(el._pcm16_to_wav(pcm))
            result = await el.transcribe(pcm, language_hint=lang)
            back = await translator.translate(result.text, lang, "en") if result.text.strip() else ""
            row.update(
                ok=True, note=note, first_byte_s=round(first_s, 2), total_s=round(total_s, 2),
                audio_s=round(len(pcm) / 2 / el.PCM_SAMPLE_RATE_HZ, 1),
                transcript=result.text, detected=result.detected_language,
                min_logprob=round(result.min_word_logprob, 2) if result.min_word_logprob is not None else None,
                similarity=round(similarity(target_text, result.text), 2), back_translation=back,
            )
        except Exception as exc:  # recorded per row so one failure doesn't stop the run
            row.update(ok=False, note=f"{type(exc).__name__}: {str(exc)[:200]}", similarity=0.0)
        return row


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    langs = [l.code for l in SUPPORTED_LANGUAGES if l.tts_supported]

    async def translate_one(lang: str, phrase: str) -> None:
        async with _sem:
            _translations[(lang, phrase)] = phrase if lang == "en" else await translator.translate(phrase, "en", lang)

    print(f"Translating {len(PHRASES)} phrases into {len(langs)} languages...")
    await asyncio.gather(*(translate_one(l, p) for l in langs for p in PHRASES))

    jobs = []
    for lang in langs:
        for model in dict.fromkeys([current_model(lang), CANDIDATE_MODEL]):
            for i in range(len(PHRASES)):
                jobs.append(run_one(lang, i, model))
    print(f"Running {len(jobs)} synthesize -> transcribe -> back-translate round-trips...")
    rows = await asyncio.gather(*jobs)

    out_csv = OUTPUT_DIR / "results.csv"
    fields = ["lang", "phrase", "model", "ok", "similarity", "min_logprob", "detected", "first_byte_s",
              "total_s", "audio_s", "note", "target_text", "transcript", "back_translation"]
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    print(f"\n{'lang':5} {'current model':24} {'sim':>5} {'lp':>6} {'ttfb':>5} | {'v4_turbo':8} {'sim':>5} {'lp':>6} {'ttfb':>5}  verdict")
    for lang in langs:
        def agg(model):
            rs = [r for r in rows if r["lang"] == lang and r["model"] == model]
            if not rs or not all(r["ok"] for r in rs):
                return None, None, None, "; ".join(r.get("note", "") for r in rs if not r["ok"])
            sim = min(r["similarity"] for r in rs)
            lps = [r["min_logprob"] for r in rs if r["min_logprob"] is not None]
            return sim, (min(lps) if lps else None), max(r["first_byte_s"] for r in rs), ""
        cur = current_model(lang)
        cs, cl, ct, ce = agg(cur)
        vs, vl, vt, ve = agg(CANDIDATE_MODEL)
        if vs is None:
            verdict = "v4 FAILED: " + ve
        elif vs >= PASS_SIMILARITY and (cs is None or vs >= cs - 0.05):
            verdict = "v4 OK"
        elif cs is not None and cs >= PASS_SIMILARITY:
            verdict = "KEEP CURRENT"
        else:
            verdict = "both weak - review"
        fmt = lambda s, l, t: f"{s if s is not None else '-':>5} {l if l is not None else '-':>6} {t if t is not None else '-':>5}"
        print(f"{lang:5} {cur:24} {fmt(cs, cl, ct)} | {'':8} {fmt(vs, vl, vt)}  {verdict}")
    notes = {r["note"] for r in rows if r.get("ok") and r.get("note")}
    for n in notes:
        print("note:", n)
    print(f"\nFull results: {out_csv}\nAudio: {OUTPUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
