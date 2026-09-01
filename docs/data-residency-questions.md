# Data residency — questions to confirm before real patient use

**Status:** Open. This app is not currently UK-only or data-sovereign — see the "Current
state" section below. This document exists to track what needs confirming before it could
be described that way to a customer, patient, or Information Governance (IG) reviewer.

## Current state (as of this writing)

- The running instance is on a local machine, exposed via an ngrok tunnel — not deployed to
  Azure or any other hosting.
- `ELEVENLABS_BASE_URL` is set to the default global endpoint (`https://api.elevenlabs.io`).
- `ANTHROPIC_BASE_URL` is unset, so the Anthropic SDK uses its default endpoint
  (`api.anthropic.com`) — now confirmed **not** UK/EU-resident (see Anthropic section below).
  A genuine regional guarantee would mean switching to Claude via AWS Bedrock (`eu-west-1` /
  `eu-central-1`) or Vertex AI's EU regions instead of the direct API.
- ElevenLabs' regional options are still unconfirmed. Transcribed patient speech, translated
  text, and synthesized audio all pass through these vendors' standard infrastructure,
  wherever that is actually hosted.
- There is an Azure Bicep deployment scaffold (`infra/bicep/`) with its `location` parameter
  locked to `uksouth`, but nothing has been applied to a real Azure subscription. This would
  only pin the *application's own hosting* to the UK — it does not by itself resolve the
  vendor API question below.

## ElevenLabs — still open

1. Does the Speech-to-Text (Scribe) and Text-to-Speech (`eleven_multilingual_v2`, and
   `eleven_v3` for the 7 languages v2 doesn't cover) API offer a regional endpoint or
   deployment option that keeps audio/text processing within the UK or EU?
2. If not region-pinned, where is audio processed and stored — even transiently — for these
   two endpoints specifically?
3. What is the data retention policy for submitted audio and generated transcripts/audio? Is
   anything retained for model training or logging by default, and can that be disabled
   contractually?
4. Is a Data Processing Agreement available, referencing UK GDPR / the Data Protection Act
   2018, along with a sub-processor list?
5. Is there an NHS-appropriate equivalent to a Business Associate Agreement, given this
   traffic will carry patient speech?

## Anthropic — answered (from published docs/DPA, 2026-07-29)

Researched from Anthropic's public documentation and DPA terms — **not a substitute for
legal/compliance sign-off**, and not yet a written confirmation from Anthropic's own account
team for this specific NHS use case (see Q4).

1. **UK/EU regional endpoint?** No. The direct `api.anthropic.com` API does not offer
   UK/EU-region processing — its only routing control is `inference_geo` (`us` or `global`),
   and `global` may run in Europe but isn't guaranteed to. Assume direct-API traffic is
   processed on US infrastructure. A genuine regional guarantee would mean routing via a
   hyperscaler instead: AWS Bedrock (`eu-west-1` Ireland, `eu-central-1` Frankfurt) or Vertex
   AI's EU regions, where the platform's own regional guarantee applies. Microsoft Foundry is
   **not** an equivalent option today — that residency guarantee is listed as "coming 2026"
   with no firm date.
2. **Retention / training.** Commercial Terms (which cover the API) prohibit training on
   inputs unless separately opted in (e.g. Development Partner Program — an active choice, not
   default). Standard retention deletes API inputs/outputs within 30 days, except for
   longer-retention features (e.g. Files API), an alternate agreement, or content flagged for
   a Usage Policy violation (up to 2 years, classifier scores up to 7 years). A **zero data
   retention (ZDR)** tier exists for eligible Enterprise customers, approved per-organization
   via Sales (not self-serve), but only covers the Messages/Token Counting APIs — not Batch,
   Files API, or Managed Agents.
3. **DPA / sub-processors.** Yes — incorporated into the Commercial Terms: Article 28 processor
   terms, EU SCCs (Modules 2 and 3), and a UK International Data Transfer Addendum satisfying
   the UK GDPR transfer requirement for data going to the US. Sub-processors are pre-authorized
   with 15 days' notice of new ones (right to object); pull the current list directly from
   `anthropic.com/subprocessors` rather than relying on a secondhand summary. Anthropic holds
   ISO/IEC 27001:2022, ISO/IEC 42001:2023, and SOC 2 Type I/II.
4. **Healthcare / special category data — the actual open item.** The standard DPA covers
   personal data generally but isn't a healthcare-specific agreement. Anthropic does offer a
   BAA (Business Associate Agreement) on top of the Enterprise tier, but that's a **US HIPAA**
   instrument — it doesn't map onto UK GDPR special-category-data handling or NHS frameworks
   (DCB0129/0160, DSPT, DTAC), which run on the DPA + UK Addendum instead. Patient speech
   transcripts are special category data under UK GDPR. Before relying on this: get (a)
   confirmation of which sub-processors/regions the data actually transits, (b) the DPA/UK
   Addendum executed under the actual commercial agreement in use, (c) ideally a ZDR
   arrangement, or the 30-day standard retention explicitly documented in the DPIA, and (d)
   **written confirmation from the Anthropic account team that healthcare-context special
   category data is in scope for this specific commercial agreement** — the public docs don't
   spell out NHS-specific handling, so this has to be confirmed directly, not inferred.

## Internal follow-up

- Confirm with the trust's Information Governance / DPO team whether a formal Data
  Protection Impact Assessment (DPIA) is required before any patient speech touches
  non-UK-resident third-party APIs, even transiently. In practice this is often the actual
  blocker regardless of what either vendor's answers turn out to be.

## What "done" looks like

Before this system can be described as UK-only or data-sovereign:

1. ElevenLabs: written answers to the questions above (still outstanding).
2. Anthropic: public-docs research done (above) — still need (a) a decision on whether to
   route via Bedrock/Vertex EU for an actual regional guarantee, since the direct API doesn't
   offer one, and (b) written confirmation from the Anthropic account team that this specific
   commercial agreement covers healthcare-context special category data.
3. `ELEVENLABS_BASE_URL` and `ANTHROPIC_BASE_URL` (or a Bedrock/Vertex-based client swap for
   Claude) pointed at whichever UK/EU-resident option is actually confirmed.
4. The Azure Bicep scaffold actually applied to a UK South subscription, replacing the
   current local + ngrok setup.
5. Sign-off from the trust's IG/DPO team, informed by a DPIA if one is required, and
   legal/compliance sign-off on the Anthropic findings above (they are research, not legal
   advice).
