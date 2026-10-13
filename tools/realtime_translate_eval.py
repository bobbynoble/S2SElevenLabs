"""Automated reliability and latency check for ElevenLabs Realtime Translate.

Same connection protocol as tools/realtime_tester (WAV-wrapped 16 kHz PCM chunks, end_of_stream),
but scripted: speech is generated with the app's own TTS and streamed in real time (100 ms
chunks), followed by trailing silence, so every run is repeatable and comparable.

For each run it records whether a translation arrived, how complete it was (content words of the
original found in a Claude back-translation), and the delay from the end of speech to the first
translated text and first translated audio. Every raw event is saved for bug reports.

Not part of the pipeline or pytest -- makes real ElevenLabs and Anthropic calls:

    python tools/realtime_translate_eval.py

Uses ELEVENLABS_BASE_URL from .env to pick the realtime host (EU workspace -> EU host).
Output: logs/realtime_translate_eval/{results.csv,events.jsonl}
"""

from __future__ import annotations

import asyncio
import base64
import csv
import io
import json
import os
import re
import sys
import time
import wave
from pathlib import Path

import websockets
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")
sys.path.insert(0, str(REPO_ROOT / "server"))
sys.stdout.reconfigure(encoding="utf-8")

from src import elevenlabs_client as el  # noqa: E402
from src import translator  # noqa: E402

KEY = os.environ["ELEVENLABS_API_KEY"]
VOICE = os.environ["ELEVENLABS_DEFAULT_VOICE_ID"]
WS_HOST = os.getenv("ELEVENLABS_BASE_URL", "https://api.elevenlabs.io").replace("https://", "wss://")
OUT = REPO_ROOT / "logs" / "realtime_translate_eval"
CHUNK = 3200  # 100 ms of 16 kHz 16-bit mono
TRAILING_SILENCE_S = 4.0
WAIT_AFTER_EOS_S = 12.0

# The first three are the exact sentences from the truncation report sent to ElevenLabs.
ENGLISH = [
    "Hello there, my name is Robert and I am calling to make an appointment.",
    "I have hurt my head and I need to see someone.",
    "Good morning. How can I help you?",
    "Do you have any allergies to medicines?",
]
# Receptionist (English) -> patient language
TARGETS = ["pl", "fr", "ar", "pa", "ur", "ps", "so", "sw", "ha", "lg", "rw", "luo", "twi"]
# Patient language -> English: one medical sentence per language, translated by the app's own
# translator first, then spoken with the app's TTS.
REVERSE = ["pl", "so", "sw", "ha", "lg", "luo", "twi"]
REVERSE_SENTENCE = "I have had chest pain since last night and I feel dizzy."

STOP = set("the a an and or to of in on for is am are i my me you your we it that this there have has had "
           "do does can any with since at be been feel".split())
# The EU workspace allows 3 concurrent requests in total (shared with the live app), so
# sessions run one at a time -- a parallel run comes back as "rate_limited", not as a real result.
_sem = asyncio.Semaphore(1)


def wav(pcm: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(pcm)
    return buf.getvalue()


def content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z']+", text.lower()) if w not in STOP and len(w) > 2}


def completeness(source_en: str, back_en: str) -> float:
    want = content_words(source_en)
    got = content_words(back_en)
    # light stemming so "medicines"/"medicine", "calling"/"call" still match
    stem = lambda w: re.sub(r"(ing|es|s|ed)$", "", w)
    got_stems = {stem(w) for w in got}
    return round(sum(1 for w in want if stem(w) in got_stems) / len(want), 2) if want else 0.0


async def speak(text: str, lang: str) -> bytes:
    return b"".join([c async for c in el.synthesize_stream(text, language=lang)])


async def run_session(src: str, dst: str, pcm: bytes) -> dict:
    url = (f"{WS_HOST}/v1/translate/realtime?target_language={dst}&source_language={src}"
           f"&voice_id={VOICE}&output_format=pcm_16000")
    events, translations, audio_bytes = [], [], 0
    t_end_speech = t_text = t_audio = None
    error = ""
    t0 = time.monotonic()
    try:
        async with websockets.connect(url, additional_headers={"xi-api-key": KEY}, open_timeout=15) as ws:
            async def reader():
                nonlocal audio_bytes, t_text, t_audio
                try:
                    await _read(ws)
                except websockets.exceptions.ConnectionClosed:
                    pass  # session ended by the server without a close frame

            async def _read(ws):
                nonlocal audio_bytes, t_text, t_audio
                async for raw in ws:
                    ev = json.loads(raw)
                    now = round(time.monotonic() - t0, 3)
                    if "data" in ev:
                        audio_bytes += len(base64.b64decode(ev["data"]))
                        t_audio = t_audio or now
                        events.append({"t": now, "audio_bytes": len(ev["data"])})
                        continue
                    events.append({"t": now, **ev})
                    if ev.get("message_type") == "rate_limited":
                        raise RuntimeError("rate_limited: " + ev.get("error", "")[:120])
                    if ev.get("message_type") == "translation":
                        translations.append(ev.get("text", ""))
                        t_text = t_text or now
            rt = asyncio.create_task(reader())
            for i in range(0, len(pcm), CHUNK):
                await ws.send(json.dumps({"message_type": "input_audio_chunk",
                                          "audio_base_64": base64.b64encode(wav(pcm[i:i + CHUNK])).decode()}))
                await asyncio.sleep(0.1)
            t_end_speech = time.monotonic() - t0
            for _ in range(int(TRAILING_SILENCE_S * 10)):
                await ws.send(json.dumps({"message_type": "input_audio_chunk",
                                          "audio_base_64": base64.b64encode(wav(b"\0" * CHUNK)).decode()}))
                await asyncio.sleep(0.1)
            await ws.send(json.dumps({"message_type": "end_of_stream"}))
            try:
                await asyncio.wait_for(rt, WAIT_AFTER_EOS_S)
            except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
                pass
            if not rt.done():
                rt.cancel()
            elif rt.exception():
                raise rt.exception()
    except websockets.exceptions.ConnectionClosed:
        pass  # server ending the session after end_of_stream without a close frame
    except Exception as exc:  # recorded per run
        error = f"{type(exc).__name__}: {str(exc)[:200]}"
    final = [e.get("text", "") for e in events if e.get("message_type") == "final_transcript"]
    session = next((e.get("session_id") for e in events if e.get("message_type") == "session_started"), "")
    rel = lambda t: round(t - t_end_speech, 2) if (t is not None and t_end_speech is not None) else None
    return {"session_id": session, "transcript": " ".join(final), "translation": " ".join(translations),
            "segments": len(translations), "audio_s": round(audio_bytes / 32000, 1),
            "text_after_speech_s": rel(t_text), "audio_after_speech_s": rel(t_audio),
            "error": error, "events": events}


async def one(direction: str, src: str, dst: str, source_text: str, source_en: str, pcm: bytes) -> dict:
    async with _sem:
        r = await run_session(src, dst, pcm)
    back = r["translation"] if dst == "en" else (
        await translator.translate(r["translation"], dst, "en") if r["translation"].strip() else "")
    r.update(direction=direction, src=src, dst=dst, source_text=source_text, source_en=source_en,
             back_translation=back, completeness=completeness(source_en, back))
    print(f"  {src}->{dst:4} {r['completeness']:>4}  text {r['text_after_speech_s']}s  "
          f"{(r['translation'] or '(NO TRANSLATION)')[:70]}{'  ERR ' + r['error'] if r['error'] else ''}", flush=True)
    return r


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"Realtime host: {WS_HOST}")
    jobs = []
    en_audio = {s: await speak(s, "en") for s in ENGLISH}
    for dst in TARGETS:
        for s in ENGLISH:
            jobs.append(one("receptionist", "en", dst, s, s, en_audio[s]))
    for src in REVERSE:
        text = await translator.translate(REVERSE_SENTENCE, "en", src)
        jobs.append(one("patient", src, "en", text, REVERSE_SENTENCE, await speak(text, src)))
    print(f"Running {len(jobs)} Realtime Translate sessions...")
    rows = await asyncio.gather(*jobs)

    with (OUT / "events.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({k: r[k] for k in ("session_id", "src", "dst", "source_text", "events")},
                               ensure_ascii=False) + "\n")
    fields = ["direction", "src", "dst", "session_id", "completeness", "segments", "text_after_speech_s",
              "audio_after_speech_s", "audio_s", "error", "source_text", "transcript", "translation",
              "back_translation"]
    with (OUT / "results.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    print(f"\n{'pair':9} {'runs':>4} {'none':>5} {'partial':>8} {'complete':>9} {'median text delay':>18}")
    for key in dict.fromkeys((r["src"], r["dst"]) for r in rows):
        rs = [r for r in rows if (r["src"], r["dst"]) == key]
        none = sum(1 for r in rs if not r["translation"].strip())
        full = sum(1 for r in rs if r["completeness"] >= 0.8)
        delays = sorted(r["text_after_speech_s"] for r in rs if r["text_after_speech_s"] is not None)
        med = delays[len(delays) // 2] if delays else None
        print(f"{key[0]}->{key[1]:5} {len(rs):>4} {none:>5} {len(rs) - none - full:>8} {full:>9} "
              f"{(str(med) + 's') if med is not None else '-':>18}")
    print(f"\nResults: {OUT / 'results.csv'}\nRaw events: {OUT / 'events.jsonl'}")


if __name__ == "__main__":
    asyncio.run(main())
