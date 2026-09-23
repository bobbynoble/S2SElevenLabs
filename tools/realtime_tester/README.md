# Realtime Translate tester

Standalone tool for testing ElevenLabs' Realtime Translate WebSocket directly, separate from
the main app (which reverted to Scribe -> Claude -> TTS). Runs on its own port so it can be
used alongside the main app rather than instead of it.

Always translates from English into whichever target language you pick -- this isolates
per-language behaviour without needing a native speaker on the source side.

## Run

```bash
cd tools/realtime_tester
pip install -r requirements.txt
python server.py
```

Open http://localhost:8020, picks up `ELEVENLABS_API_KEY` / `ELEVENLABS_DEFAULT_VOICE_ID` from
the repo's `.env` automatically.

## Use

1. Pick a target language.
2. Hold "Hold to talk", speak an English sentence, release.
3. Watch the transcript/translation panels and the event log. The event log shows every raw
   message from ElevenLabs with a timestamp -- copy it straight into a bug report if a
   translation stalls or drops content partway through, the way it did in earlier testing.

## What this is for

Gathering evidence on Realtime Translate's reliability (particularly the segmentation/
truncation issue reported to ElevenLabs) across the app's full supported-language list, without
touching the production pipeline or needing to re-integrate Realtime into the main app to do it.
