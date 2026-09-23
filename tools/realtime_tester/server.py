"""Standalone Realtime Translate tester.

Separate from the main hospital app entirely -- runs on its own port so it can be used
alongside the production app (which is back on Scribe -> Claude -> TTS) purely to gather
evidence on Realtime Translate's reliability across languages. Not wired into any of the
main app's session/turn/clinical-coding logic.

Relays browser mic audio to ElevenLabs' Realtime Translate WebSocket
(wss://api.elevenlabs.io/v1/translate/realtime) and relays every event back to the browser,
logging each one with a timestamp so a truncated/dropped translation can be pulled straight
from the console output as evidence.

Run: pip install -r requirements.txt && python server.py
Then open http://localhost:8020
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import wave
from pathlib import Path

import websockets
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Reuse the main app's .env rather than duplicating the API key/voice ID in a second file.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("realtime_tester")

ELEVENLABS_API_KEY = os.environ["ELEVENLABS_API_KEY"]
ELEVENLABS_DEFAULT_VOICE_ID = os.environ["ELEVENLABS_DEFAULT_VOICE_ID"]

# Sending end_of_stream the instant the button is released reproduces the truncation bug more
# aggressively than the main app does (which waits this long first) -- match that mitigation
# here so a stalled translation reflects the engine's own limit, not an artificially fast cutoff.
TRAILING_SILENCE_SECONDS = float(os.getenv("REALTIME_TRAILING_SILENCE_SECONDS", "4"))

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI()
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


def _realtime_url(target_language: str) -> str:
    return (
        "wss://api.elevenlabs.io/v1/translate/realtime"
        f"?target_language={target_language}&source_language=en"
        f"&voice_id={ELEVENLABS_DEFAULT_VOICE_ID}"
        "&output_format=pcm_16000"
    )


def _pcm16_to_wav(pcm_bytes: bytes, sample_rate: int = 16000) -> bytes:
    """Each audio_base_64 chunk must be a self-contained decodable file, not headerless PCM --
    confirmed live: headerless chunks get a bare "input_error" on every single one, and the
    docs' own example payload decodes to a RIFF/WAVE header."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    return buffer.getvalue()


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    target_language = websocket.query_params.get("target_language", "es")
    log_prefix = f"[{target_language}]"

    try:
        async with websockets.connect(
            _realtime_url(target_language),
            additional_headers={"xi-api-key": ELEVENLABS_API_KEY},
        ) as upstream:
            logger.info("%s connected to Realtime Translate", log_prefix)

            async def pump_upstream_to_browser() -> None:
                async for raw in upstream:
                    event = json.loads(raw)
                    if "data" in event:
                        audio_bytes = base64.b64decode(event["data"])
                        logger.info("%s audio chunk (%d bytes)", log_prefix, len(audio_bytes))
                        await websocket.send_bytes(audio_bytes)
                        continue
                    logger.info("%s %s", log_prefix, event)
                    await websocket.send_json(event)

            pump_task = asyncio.create_task(pump_upstream_to_browser())
            try:
                while True:
                    message = await websocket.receive()
                    if message["type"] == "websocket.disconnect":
                        break
                    audio_bytes = message.get("bytes")
                    if audio_bytes is not None:
                        wav_bytes = _pcm16_to_wav(audio_bytes)
                        try:
                            await upstream.send(
                                json.dumps(
                                    {
                                        "message_type": "input_audio_chunk",
                                        "audio_base_64": base64.b64encode(wav_bytes).decode(),
                                    }
                                )
                            )
                        except websockets.exceptions.ConnectionClosed:
                            # A trailing chunk can arrive from the browser just after the
                            # upstream session already ended (confirmed live) -- same
                            # already-closed race as end_of_stream below, just on the other
                            # message type. Nothing meaningful to forward at that point.
                            logger.info("%s dropped a trailing audio chunk -- session already closed", log_prefix)
                        continue
                    text = message.get("text")
                    if text is not None and json.loads(text).get("type") == "end":
                        logger.info(
                            "%s end requested, waiting %.0fs before end_of_stream", log_prefix, TRAILING_SILENCE_SECONDS
                        )
                        await asyncio.sleep(TRAILING_SILENCE_SECONDS)
                        try:
                            await upstream.send(json.dumps({"message_type": "end_of_stream"}))
                            logger.info("%s end_of_stream sent", log_prefix)
                        except websockets.exceptions.ConnectionClosed:
                            # Confirmed live: ElevenLabs sometimes closes the session on its own
                            # during this wait, before we get to send end_of_stream at all --
                            # translation/audio had already stalled by that point either way.
                            logger.info(
                                "%s upstream already closed the session before end_of_stream", log_prefix
                            )
            finally:
                pump_task.cancel()
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001 -- surfaced to the tester UI, not swallowed
        logger.exception("%s relay failed", log_prefix)
        try:
            await websocket.send_json({"message_type": "relay_error", "error": str(exc)})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8020)
