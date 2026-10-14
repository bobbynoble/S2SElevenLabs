"""Compares two Claude models as the translation step for the languages currently routed to Opus.

Each candidate model is called exactly as server/src/translator.py calls it (same system prompt,
same prompt, same refusal / commentary / script checks), only with the model chosen explicitly.

For every language and medical phrase:
  * Receptionist -> patient: English is translated into the language by each model. Meaning is
    checked twice: on the text (back-translated to English by a fixed reference model), and after
    the full spoken path the patient would hear (app TTS -> Scribe -> back-translation).
  * Patient -> receptionist: both models' translations are used as the patient's words, and each
    model translates them back into English for the receptionist.
A fixed judge model scores each English result against the original: 2 = same meaning,
1 = minor loss, 0 = wrong; it also flags errors that could cause clinical harm.

Not part of the pipeline or pytest -- makes real Anthropic and ElevenLabs calls:

    python tools/translation_model_eval.py

Output: logs/translation_model_eval/results.csv
"""

from __future__ import annotations

import asyncio
import csv
import json
import statistics
import sys
import time
from pathlib import Path

import anthropic
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")
sys.path.insert(0, str(REPO_ROOT / "server"))
sys.stdout.reconfigure(encoding="utf-8")

from src import elevenlabs_client as el  # noqa: E402
from src import translator  # noqa: E402
from src.languages import english_name_for, script_mismatch  # noqa: E402

CANDIDATES = ["claude-sonnet-5", "claude-opus-5-5"]
REFERENCE = "claude-opus-5-5"  # back-translator and judge, identical for both candidates
LANGUAGES = ["so", "sw", "ha", "lg", "rw", "luo", "twi"]
PHRASES = [
    "Do you have any allergies to medicines?",
    "I have had chest pain since last night and I feel dizzy.",
    "I fell today and hit my head.",
    "Take one tablet twice a day after food.",
    "Are you pregnant, or could you be pregnant?",
    "I've been having thoughts of ending my life.",
    "My child has had a high fever for three days.",
    "Please wait here, the nurse will call your name.",
]
OUT = REPO_ROOT / "logs" / "translation_model_eval"

_client = anthropic.AsyncAnthropic()
_llm = asyncio.Semaphore(6)
_el = asyncio.Semaphore(2)  # EU workspace allows 3 concurrent requests, shared with the live app


async def translate_with(model: str, text: str, src: str, dst: str) -> tuple[str, float]:
    """translator.translate(), with the model chosen explicitly. Returns (text, seconds)."""
    prompt = f"Translate the following text from {english_name_for(src)} to {english_name_for(dst)}:\n\n{text}"
    async with _llm:
        t = time.monotonic()
        resp = await _client.messages.create(model=model, max_tokens=1024, system=translator.SYSTEM_PROMPT,
                                             messages=[{"role": "user", "content": prompt}])
        took = time.monotonic() - t
    if getattr(resp, "stop_reason", None) == "refusal":
        raise translator.TranslationError("refusal")
    out = next((b.text for b in resp.content if b.type == "text"), "").strip()
    if not out or translator._looks_like_commentary(out) or script_mismatch(out, dst):
        raise translator.TranslationError(f"rejected output: {out[:80]}")
    return out, took


async def judge(original: str, candidate: str) -> dict:
    prompt = (
        "You are checking a hospital interpreter's work. Compare the ORIGINAL English with the "
        "RESULT English (which went through translation and back). Score meaning: 2 = same meaning, "
        "1 = minor loss or awkwardness but a receptionist/patient would act the same way, 0 = wrong or "
        "important information missing. Set harmful=true if the difference could plausibly lead to "
        "clinical harm (wrong dose, missed symptom, missed risk). Reply with JSON only: "
        '{"score": 0|1|2, "harmful": true|false, "note": "<10 words"}\n\n'
        f"ORIGINAL: {original}\nRESULT: {candidate}"
    )
    async with _llm:
        resp = await _client.messages.create(model=REFERENCE, max_tokens=200,
                                             messages=[{"role": "user", "content": prompt}])
    text = next((b.text for b in resp.content if b.type == "text"), "{}")
    try:
        return json.loads(text[text.find("{"): text.rfind("}") + 1])
    except ValueError:
        return {"score": 0, "harmful": False, "note": "judge parse error"}


async def spoken_round_trip(text: str, lang: str) -> str:
    async with _el:
        pcm = b"".join([c async for c in el.synthesize_stream(text, language=lang)])
        res = await el.transcribe(pcm, language_hint=lang)
    return res.text


async def forward_case(model: str, lang: str, phrase: str) -> dict:
    row = {"direction": "receptionist->patient", "model": model, "lang": lang, "phrase": phrase}
    try:
        out, took = await translate_with(model, phrase, "en", lang)
        back_text, _ = await translate_with(REFERENCE, out, lang, "en")
        heard = await spoken_round_trip(out, lang)
        back_heard, _ = (await translate_with(REFERENCE, heard, lang, "en")) if heard.strip() else ("", 0)
        j_text, j_heard = await asyncio.gather(judge(phrase, back_text), judge(phrase, back_heard))
        row.update(ok=True, seconds=round(took, 2), output=out, back_text=back_text, heard=heard,
                   back_heard=back_heard, text_score=j_text.get("score"), text_harmful=j_text.get("harmful"),
                   text_note=j_text.get("note"), heard_score=j_heard.get("score"),
                   heard_harmful=j_heard.get("harmful"), heard_note=j_heard.get("note"))
    except Exception as exc:
        row.update(ok=False, error=f"{type(exc).__name__}: {str(exc)[:150]}", text_score=0, heard_score=0)
    return row


async def reverse_case(model: str, lang: str, phrase: str, patient_text: str, source_model: str) -> dict:
    row = {"direction": "patient->receptionist", "model": model, "lang": lang, "phrase": phrase,
           "patient_text_from": source_model, "output": patient_text}
    try:
        en, took = await translate_with(model, patient_text, lang, "en")
        j = await judge(phrase, en)
        row.update(ok=True, seconds=round(took, 2), back_text=en, text_score=j.get("score"),
                   text_harmful=j.get("harmful"), text_note=j.get("note"))
    except Exception as exc:
        row.update(ok=False, error=f"{type(exc).__name__}: {str(exc)[:150]}", text_score=0)
    return row


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"Forward: {len(CANDIDATES) * len(LANGUAGES) * len(PHRASES)} translations (+ spoken round trips)...")
    fwd = await asyncio.gather(*(forward_case(m, l, p) for m in CANDIDATES for l in LANGUAGES for p in PHRASES))

    # Patient side: use BOTH candidates' wording as the patient's words, so neither model is only
    # ever reading its own phrasing back.
    rev_jobs = []
    for r in fwd:
        if r.get("ok"):
            for m in CANDIDATES:
                rev_jobs.append(reverse_case(m, r["lang"], r["phrase"], r["output"], r["model"]))
    print(f"Reverse: {len(rev_jobs)} translations...")
    rev = await asyncio.gather(*rev_jobs)
    rows = fwd + rev

    fields = ["direction", "model", "lang", "phrase", "ok", "error", "seconds", "text_score", "text_harmful",
              "text_note", "heard_score", "heard_harmful", "heard_note", "patient_text_from", "output",
              "back_text", "heard", "back_heard"]
    with (OUT / "results.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    def summary(rs, key):
        n = len(rs)
        scores = [r.get(key) or 0 for r in rs]
        harm = sum(1 for r in rs if r.get(key.replace("score", "harmful")))
        fails = sum(1 for r in rs if not r.get("ok"))
        secs = [r["seconds"] for r in rs if r.get("ok")]
        return (f"{sum(1 for s in scores if s == 2):>3}/{n} exact  {sum(scores) / (2 * n):>5.0%}  "
                f"harmful {harm:>2}  failed {fails:>2}  median {statistics.median(secs) if secs else 0:>4.1f}s")

    for label, rs_all, key in (("RECEPTIONIST -> PATIENT (text)", fwd, "text_score"),
                               ("RECEPTIONIST -> PATIENT (after speech round trip)", fwd, "heard_score"),
                               ("PATIENT -> RECEPTIONIST (text)", rev, "text_score")):
        print(f"\n{label}")
        print(f"{'lang':5} " + "  |  ".join(f"{m:>16}" for m in CANDIDATES))
        for lang in LANGUAGES + ["ALL"]:
            cells = []
            for m in CANDIDATES:
                rs = [r for r in rs_all if r["model"] == m and (lang == "ALL" or r["lang"] == lang)]
                cells.append(summary(rs, key))
            print(f"{lang:5} " + "  |  ".join(cells))
    print(f"\nFull results: {OUT / 'results.csv'}")


if __name__ == "__main__":
    asyncio.run(main())
