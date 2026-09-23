# S2SElevenLabs — Hospital Reception Speech-to-Speech Interpreter

A live, multilingual speech-to-speech interpreter for hospital reception desks. A patient scans a
QR code with their own phone, picks their language, and has a real-time spoken conversation with
the receptionist — each party hears (and reads) the other translated into their own language.

The browser is a "dumb" front end: it only captures microphone audio and plays back synthesized
audio. All speech-to-text, translation, and text-to-speech happens server-side.

## Stack

- **Backend:** Python 3.11+, FastAPI + Uvicorn, WebSockets for the live audio/caption relay
- **Speech (STT + TTS):** ElevenLabs API
- **Translation:** Claude (Anthropic API)
- **Clinical coding:** Claude (Anthropic API), post-session only — see "How it works" below
- **Frontend:** Vue 3 + Composition API + Vite
- **Deployment target:** Azure UK South (Container Apps) — see `infra/`

## Common Commands

```bash
# Backend
cd server
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8010

# Backend tests
cd server
pytest ../tests/backend

# Frontend
cd client
npm install
npm run dev

# Both, local dev
docker-compose up

# API docs
open http://localhost:8010/docs
```

## Environment Setup

1. Copy `.env.example` to `.env` (never commit `.env`)
2. Set `ELEVENLABS_API_KEY` — required
3. Set `ANTHROPIC_API_KEY` — required (used for the translation step and post-session clinical coding)
4. Set `SESSION_API_KEY` — optional; when set, `POST /api/sessions` requires `X-API-Key: <value>`
5. Set `CORS_ORIGINS` — optional; defaults to `*`
6. Set `CLINICAL_CODING_ENABLED` — optional; defaults to `true`, set to `false` to skip the
   post-session clinical coding step entirely

## Directory Structure

```
/
├── server/           # FastAPI backend — WebSocket relay, ElevenLabs + Anthropic clients
├── client/            # Vue 3 frontend — kiosk, patient, and receptionist screens
├── tests/backend/     # pytest suite for the backend
├── infra/             # Azure UK South deployment scaffold (Bicep) — not deployed by this repo
└── docker-compose.yml # local dev, both containers
```

## How it works

1. The receptionist opens the **Kiosk** screen and starts a new session ("New Patient"). The
   backend issues a short-lived, single-use QR code.
2. The patient scans the QR with their own phone, which opens the **Patient** screen — no app
   install required — and picks their spoken language.
3. The receptionist picks their own language (defaults to English) once the patient joins.
4. Each party speaks in turns (press-and-hold the mic button). Per turn, the backend:
   - transcribes the speaker's audio (ElevenLabs Scribe),
   - translates the text (Claude) into the listener's language,
   - synthesizes speech in the listener's language (ElevenLabs multilingual TTS),
   - sends both a caption (original + translated text, to both screens) and the synthesized
     audio (to the listener only).
5. Either party can end the session; the kiosk then produces a fresh QR for the next patient.
6. When the receptionist ends the session, the backend reports the session's estimated ElevenLabs
   API cost (STT seconds + TTS characters) to the receptionist, then sends the full transcript to
   a local clinical-coding step (a curated ICD-10 reference set + Claude) and returns suggested
   codes for review. This step never runs before the session ends, and its result goes to the
   receptionist only.

## Compliance notes (read before deploying for real NHS use)

This app is built to keep all processing inside our own backend and the UK, but two vendor-side
questions are **not resolved by this codebase** and must be confirmed before production use:

- **ElevenLabs data residency:** `ELEVENLABS_BASE_URL` defaults to ElevenLabs' global API endpoint.
  Confirm with ElevenLabs whether a UK/EU-resident processing endpoint is available for this
  account, and point `ELEVENLABS_BASE_URL` at it before go-live.
- **Anthropic data residency:** the standard `api.anthropic.com` endpoint is not itself a
  UK-region-pinned product. Before production use, confirm a suitable arrangement directly with
  Anthropic (e.g. an enterprise data-processing agreement), or consider routing the translation
  step via a UK-region cloud offering (e.g. AWS Bedrock's London region) instead. An
  `ANTHROPIC_BASE_URL` override is provided so this can be changed without a code rewrite.
- **Language voice coverage:** Tigrinya (see `server/src/languages.py`) has no confirmed ElevenLabs
  TTS voice — round-trip testing (synthesize, then transcribe back) showed the audio doesn't
  actually say the input text. It still gets full live text captions, just no synthesized voice
  reply. The other 16 supported languages are confirmed working, including 7 (Punjabi, Urdu,
  Bengali, Somali, Farsi/Dari, Pashto, Vietnamese) that use `eleven_v3` rather than the default
  `eleven_multilingual_v2`, which doesn't cover them.

## Testing

- **Test runner:** pytest
- **Test file convention:** `tests/backend/test_*.py`
- Backend tests mock the ElevenLabs and Anthropic clients — they verify session/WebSocket/protocol
  logic, not live vendor behavior. Full audio-pipeline testing (STT/translation/TTS quality and
  latency, real-device mic/playback behavior) requires real API keys and manual testing, which
  this repo cannot fabricate.

Always run tests before committing. Fix failures before pushing.
