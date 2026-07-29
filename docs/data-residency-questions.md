# Data residency — questions to confirm before real patient use

**Status:** Open. This app is not currently UK-only or data-sovereign — see the "Current
state" section below. This document exists to track what needs confirming before it could
be described that way to a customer, patient, or Information Governance (IG) reviewer.

## Current state (as of this writing)

- The running instance is on a local machine, exposed via an ngrok tunnel — not deployed to
  Azure or any other hosting.
- `ELEVENLABS_BASE_URL` is set to the default global endpoint (`https://api.elevenlabs.io`).
- `ANTHROPIC_BASE_URL` is unset, so the Anthropic SDK uses its default endpoint
  (`api.anthropic.com`).
- Neither endpoint is confirmed to be UK/EU-resident. Transcribed patient speech, translated
  text, and synthesized audio all pass through these vendors' standard infrastructure,
  wherever that is actually hosted.
- There is an Azure Bicep deployment scaffold (`infra/bicep/`) with its `location` parameter
  locked to `uksouth`, but nothing has been applied to a real Azure subscription. This would
  only pin the *application's own hosting* to the UK — it does not by itself resolve the
  vendor API question below.

## Questions for ElevenLabs

1. Does the Speech-to-Text (Scribe) and Text-to-Speech (`eleven_multilingual_v2`) API offer
   a regional endpoint or deployment option that keeps audio/text processing within the UK
   or EU?
2. If not region-pinned, where is audio processed and stored — even transiently — for these
   two endpoints specifically?
3. What is the data retention policy for submitted audio and generated transcripts/audio? Is
   anything retained for model training or logging by default, and can that be disabled
   contractually?
4. Is a Data Processing Agreement available, referencing UK GDPR / the Data Protection Act
   2018, along with a sub-processor list?
5. Is there an NHS-appropriate equivalent to a Business Associate Agreement, given this
   traffic will carry patient speech?

## Questions for Anthropic

1. Does the Claude API have a UK/EU regional endpoint, or is `api.anthropic.com` always
   routed to US infrastructure regardless of the caller's location?
2. What is the data retention/training policy for API inputs? Is prompt/response content
   used for model training by default, and is there a zero-retention or enterprise tier that
   changes this?
3. Is a Data Processing Agreement available covering UK GDPR, with confirmed sub-processor
   locations?
4. Prompts here will contain transcribed patient speech — a special category of data in a
   healthcare context. Do the standard API terms treat this appropriately, or is a separate
   enterprise agreement required for healthcare use?

## Internal follow-up

- Confirm with the trust's Information Governance / DPO team whether a formal Data
  Protection Impact Assessment (DPIA) is required before any patient speech touches
  non-UK-resident third-party APIs, even transiently. In practice this is often the actual
  blocker regardless of what either vendor's answers turn out to be.

## What "done" looks like

Before this system can be described as UK-only or data-sovereign:

1. Written confirmation from both vendors on the questions above.
2. `ELEVENLABS_BASE_URL` and `ANTHROPIC_BASE_URL` pointed at whichever UK/EU-resident
   endpoints those answers make available (if any).
3. The Azure Bicep scaffold actually applied to a UK South subscription, replacing the
   current local + ngrok setup.
4. Sign-off from the trust's IG/DPO team, informed by a DPIA if one is required.
