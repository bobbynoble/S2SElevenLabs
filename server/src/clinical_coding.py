"""Local clinical-code suggestion: given the finished conversation note, retrieve candidate codes
from a small curated reference set (SQLite, in-memory, seeded at import time) and ask Claude to
select/rank/justify from those candidates.

Runs entirely on this device -- no external service, no Azure. Reuses the same Anthropic
client/key already configured for translation (see translator.py). Replaces an earlier
integration with a separate clinical-coding-bot service whose Azure OpenAI/Search backend was
down; this reference set is a small hand-picked list of common reception presenting complaints,
not a complete or clinically-authoritative code set.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass

import anthropic

ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
MAX_CANDIDATES = 10

SYSTEM_PROMPT = """You are a senior clinical coder with expertise in ICD-10-CM, OPCS-4, SNOMED CT, and HCC risk adjustment.

Given a clinical note and a list of candidate codes retrieved from a reference database, your task is to:
1. Select the most appropriate codes for the encounter, from the candidate list only -- do not
   invent codes outside it.
2. Rank them by relevance (most specific first).
3. For each code, copy its "code" and "system" values exactly as given in the candidate list.
4. For each code provide a brief clinical justification.
5. Flag any codes that need human review with "REVIEW: <reason>".

Return ONLY valid JSON in this exact structure, no commentary and no markdown code fences:
{
  "suggestions": [
    {
      "code": "string",
      "system": "string",
      "description": "string",
      "justification": "string",
      "confidence": "high|medium|low",
      "review_flag": "string or null"
    }
  ],
  "coding_notes": "string"
}"""

# code, system, description, keywords (space-separated, matched against the note's own words)
_REFERENCE_CODES = [
    ("R51", "ICD-10", "Headache", "headache migraine head pain"),
    ("J02.9", "ICD-10", "Acute pharyngitis, unspecified", "sore throat pharyngitis throat"),
    ("R05", "ICD-10", "Cough", "cough coughing"),
    ("R50.9", "ICD-10", "Fever, unspecified", "fever temperature hot feverish"),
    ("R10.9", "ICD-10", "Unspecified abdominal pain", "abdominal stomach belly pain ache"),
    ("M54.5", "ICD-10", "Low back pain", "back pain lower backache"),
    ("R07.9", "ICD-10", "Chest pain, unspecified", "chest pain tightness"),
    ("R06.02", "ICD-10", "Shortness of breath", "breathless breathing breath short"),
    ("R42", "ICD-10", "Dizziness and giddiness", "dizzy dizziness lightheaded vertigo"),
    ("R11.0", "ICD-10", "Nausea", "nausea vomiting sick nauseous"),
    ("R21", "ICD-10", "Rash and other nonspecific skin eruption", "rash skin eruption itchy spots"),
    ("H92.09", "ICD-10", "Otalgia, unspecified ear", "earache ear infection"),
    ("R30.0", "ICD-10", "Dysuria", "urinary painful urination burning urine"),
    ("F41.9", "ICD-10", "Anxiety disorder, unspecified", "anxiety anxious panic worried stressed"),
    ("T14.8", "ICD-10", "Other injury of unspecified body region", "injury cut laceration wound fall"),
    ("S52.90", "ICD-10", "Unspecified fracture of forearm", "fracture broken arm bone"),
    ("T78.40", "ICD-10", "Allergy, unspecified", "allergic allergy reaction swelling hives"),
    ("H57.1", "ICD-10", "Ocular pain", "eye pain sore"),
    ("K08.8", "ICD-10", "Toothache", "toothache tooth dental"),
    ("R19.7", "ICD-10", "Diarrhea, unspecified", "diarrhea loose stools"),
    ("K59.00", "ICD-10", "Constipation, unspecified", "constipation constipated"),
    ("M25.50", "ICD-10", "Pain in unspecified joint", "joint knee shoulder hip pain"),
    ("R53.83", "ICD-10", "Fatigue", "fatigue tired exhausted tiredness"),
    ("G47.00", "ICD-10", "Insomnia, unspecified", "insomnia sleep sleeping"),
    ("Z34.90", "ICD-10", "Encounter for supervision of normal pregnancy", "pregnant pregnancy antenatal"),
    ("Z71.9", "ICD-10", "Counseling, unspecified", "enquiry advice medication query"),
    ("Z00.00", "ICD-10", "General adult medical examination", "checkup examination appointment"),
]

_db = sqlite3.connect(":memory:", check_same_thread=False)
_db.execute(
    "CREATE TABLE clinical_codes (code TEXT, system TEXT, description TEXT, keywords TEXT)"
)
_db.executemany(
    "INSERT INTO clinical_codes (code, system, description, keywords) VALUES (?, ?, ?, ?)",
    _REFERENCE_CODES,
)
_db.commit()


@dataclass
class ClinicalCodeSuggestion:
    code: str
    system: str
    description: str | None
    justification: str | None
    confidence: str | None
    review_flag: str | None


@dataclass
class ClinicalCodingResult:
    suggestions: list[ClinicalCodeSuggestion]
    coding_notes: str | None


class ClinicalCodingError(Exception):
    pass


def _retrieve_candidates(note: str, systems: list[str] | None = None) -> list[tuple[str, str, str]]:
    words = set(re.findall(r"[a-z]+", note.lower()))

    query = "SELECT code, system, description, keywords FROM clinical_codes"
    params: list[str] = []
    if systems:
        query += f" WHERE system IN ({','.join('?' for _ in systems)})"
        params.extend(systems)

    rows = _db.execute(query, params).fetchall()

    scored = sorted(
        ((len(words & set(keywords.split())), code, system, description) for code, system, description, keywords in rows),
        key=lambda row: row[0],
        reverse=True,
    )
    matched = [row for row in scored if row[0] > 0][:MAX_CANDIDATES]
    top = matched or scored[:MAX_CANDIDATES]
    return [(code, system, description) for _, code, system, description in top]


def _extract_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


async def get_clinical_code(note: str, systems: list[str] | None = None) -> ClinicalCodingResult:
    candidates = _retrieve_candidates(note, systems=systems)
    if not candidates:
        raise ClinicalCodingError("No candidate codes in the local reference set match the given systems filter.")

    candidate_text = "\n".join(f"- [{system}] {code}: {description}" for code, system, description in candidates)
    user_message = (
        f"CLINICAL NOTE:\n{note}\n\n"
        f"CANDIDATE CODES FROM REFERENCE DATABASE:\n{candidate_text}\n\n"
        "Please select and rank the appropriate codes."
    )

    client = anthropic.AsyncAnthropic()
    try:
        response = await client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
    except anthropic.APIError as exc:
        raise ClinicalCodingError(f"Clinical coding request failed: {exc}") from exc

    if getattr(response, "stop_reason", None) == "refusal":
        raise ClinicalCodingError("Claude declined to suggest clinical codes for this content (policy refusal).")

    text_block = next((b for b in response.content if b.type == "text"), None)
    if text_block is None:
        raise ClinicalCodingError("Claude returned no text content for the clinical coding suggestion.")

    try:
        data = json.loads(_extract_json(text_block.text))
    except ValueError as exc:
        raise ClinicalCodingError(f"Clinical coding response was not valid JSON: {exc}") from exc

    raw_suggestions = data.get("suggestions") if isinstance(data, dict) else None
    if not isinstance(raw_suggestions, list) or not raw_suggestions:
        raise ClinicalCodingError(f"Clinical coding response had no suggestions: {data!r}")

    suggestions = []
    for item in raw_suggestions:
        code = item.get("code")
        system = item.get("system")
        if not code or not system:
            raise ClinicalCodingError(f"Clinical coding suggestion missing code/system: {item!r}")
        suggestions.append(
            ClinicalCodeSuggestion(
                code=code,
                system=system,
                description=item.get("description"),
                justification=item.get("justification"),
                confidence=item.get("confidence"),
                review_flag=item.get("review_flag"),
            )
        )
    return ClinicalCodingResult(suggestions=suggestions, coding_notes=data.get("coding_notes"))
