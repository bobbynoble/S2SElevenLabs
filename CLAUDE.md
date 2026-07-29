# CLAUDE.md

This file provides guidance to AI assistants (Claude and others) working in this repository.

## Repository Status

Active development. This repository contains a live speech-to-speech multilingual interpreter
app for hospital reception desks, built on the ElevenLabs API (speech-to-text + text-to-speech)
with Claude (Anthropic API) performing the text-translation step in between.

## Repository Overview

**Name:** S2SElevenLabs
**Owner:** bobbynoble
**Branch Convention:** Feature branches use the format `claude/<description>-<session-id>`

## Project Setup

- **Backend:** Python 3.11+, FastAPI + Uvicorn, WebSockets
- **Frontend:** Vue 3 + Composition API + Vite
- **Speech:** ElevenLabs API (Scribe STT + multilingual TTS)
- **Translation:** Claude via the Anthropic Python SDK
- **Database:** None — sessions are held in-memory, server-side (single backend process; see
  `server/src/session_manager.py`)
- **Deployment target:** Azure UK South (NHS UK data-residency requirement) — see `infra/`

## Hard Architectural Constraints (do not violate these)

- **The browser is a dumb front end.** It captures microphone audio and plays back synthesized
  audio, and nothing else. No speech-to-text, translation, or text-to-speech logic may ever run
  in browser JavaScript — all of it lives in the FastAPI backend.
- **No third-party real-time media server.** The audio/caption relay is a plain WebSocket handled
  entirely by our own backend (no LiveKit, Pipecat, or similar), so we control exactly where audio
  and text are processed — required for UK data residency.
- **UK data residency.** Vendor API base URLs (`ELEVENLABS_BASE_URL`, `ANTHROPIC_BASE_URL`) are
  configurable via environment variables specifically so a UK/EU-resident endpoint can be swapped
  in once confirmed with each vendor. See the README's "Compliance notes" before treating any
  environment as production-ready for real patient data.

## Development Workflow

### Branch Strategy

- **Main branch:** `main` — protected, no direct pushes
- **Feature branches:** `claude/<feature-description>-<session-id>` for AI-assisted work
- **Human feature branches:** `feature/<description>` or `<username>/<description>`
- Always create a new branch for changes; never commit directly to `main`

### Commit Conventions

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short description>
```

**Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

### Pull Requests

- Keep PRs focused and small (one logical change per PR)
- Include a clear description of what changed and why
- Ensure all checks pass before requesting review

## Code Quality Standards

- **Simplicity first:** write the minimum code needed to solve the problem
- **No premature abstractions:** don't create helpers/utilities for one-time use
- **No speculative features:** only implement what is currently needed
- **Avoid backwards-compat hacks:** remove unused code instead of commenting it out
- **No unnecessary comments:** only add comments where logic is non-obvious
- Never commit secrets, API keys, or credentials — use environment variables
- Validate input at system boundaries (WebSocket messages, REST request bodies)
- Only add error handling for scenarios that can actually occur

## Directory Structure

```
/
├── server/
│   ├── src/
│   │   ├── main.py               # FastAPI app — REST + WS routes, CORS, lifespan
│   │   ├── models.py             # pydantic schemas incl. WS message discriminated union
│   │   ├── session_manager.py    # session create/lookup/expiry/reconnect state
│   │   ├── websocket_handler.py  # WS routes: framing, turn buffering, dispatch
│   │   ├── pipeline.py           # per-turn orchestration: STT -> translate -> TTS
│   │   ├── elevenlabs_client.py  # ElevenLabs transcribe()/synthesize()
│   │   ├── translator.py         # Claude-based translate()
│   │   ├── languages.py          # supported languages, single source of truth
│   │   └── qr.py                 # join-URL + PNG QR generation
│   ├── requirements.txt
│   └── Dockerfile
├── client/
│   └── src/
│       ├── views/                # Kiosk, PatientJoin, Receptionist
│       ├── components/           # LanguagePicker, QRCodeDisplay, CaptionPanel, MicButton, ...
│       ├── composables/          # useSession, useMicCapture, useAudioPlayback
│       ├── api.js                # REST client
│       └── ws.js                 # WebSocket client
├── tests/backend/                # pytest suite
├── infra/bicep/                  # Azure UK South deployment scaffold
├── .env.example
└── docker-compose.yml
```

## Testing

- **Test runner:** pytest
- **Test file convention:** `tests/backend/test_*.py`

```bash
cd server
pip install -r requirements.txt
pytest ../tests/backend
```

Always run tests before committing. Fix failures before pushing.

## AI Assistant Guidelines

- Read before editing: always read the relevant files before modifying them
- Minimal changes: make only the changes necessary for the task
- No scope creep: don't refactor or "improve" code that wasn't part of the request
- Don't add docstrings/comments to code you didn't change
- Don't introduce new dependencies without explicit need
- Develop on the designated feature branch; push with `-u`; never force-push to shared branches
