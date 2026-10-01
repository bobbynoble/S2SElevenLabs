"""Summarises remote tester activity from the backend's metadata-only log (server/logs/backend.log
and its rotated copies) as a Markdown section for the Interpreter Testing Tracker doc. Prints the
section to stdout; tools/update_testing_tracker.ps1 runs this daily and has Claude paste it in.

Only sessions created through the public link (origin=remote) are counted, so local test runs
are left out. The log holds no conversation content, so neither does this report.

    python tools/tester_activity_report.py
"""

from __future__ import annotations

import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "server"))
sys.stdout.reconfigure(encoding="utf-8")

from src.languages import english_name_for  # noqa: E402

LOG_DIR = REPO_ROOT / "server" / "logs"
DAYS_SHOWN = 14

CREATED = re.compile(r"^(\d{4}-\d{2}-\d{2}) [\d:,]+ INFO \S+ — Session (\w+) created origin=(\w+)")
TURN = re.compile(
    r"^(\d{4}-\d{2}-\d{2}) [\d:,]+ INFO \S+ — turn session=(\w+) speaker=\w+ langs=(\w+)->(\w+) "
    r"audio_s=[\d.]+ outcome=(\w+) min_logprob=\S+ process_s=([\d.]+)"
)
TRANSLATED = {"ok", "ok_caption_only"}
ASKED_TO_REPEAT = {"stt_low_confidence"}
NO_SPEECH = {"no_speech", "same_language"}


def read_log_lines() -> list[str]:
    files = sorted(LOG_DIR.glob("backend.log*"), key=lambda p: p.stat().st_mtime)
    return [line for f in files for line in f.read_text(encoding="utf-8", errors="replace").splitlines()]


def main() -> None:
    remote: dict[str, str] = {}  # session prefix -> date created
    turns = []
    for line in read_log_lines():
        if m := CREATED.match(line):
            if m.group(3) == "remote":
                remote[m.group(2)] = m.group(1)
        elif m := TURN.match(line):
            turns.append(m.groups())

    days: dict[str, dict] = defaultdict(lambda: {"sessions": set(), "spoke": set(), "turns": [], "langs": Counter()})
    for session, day in remote.items():
        days[day]["sessions"].add(session)
    for day, session, source, target, outcome, process_s in turns:
        if session not in remote:
            continue
        d = days[day]
        d["sessions"].add(session)
        d["spoke"].add(session)
        d["turns"].append((outcome, float(process_s)))
        for code in (source, target):
            if code != "en":
                d["langs"][english_name_for(code)] += 1

    now = datetime.now().strftime("%d %b %Y %H:%M")
    print("## Tester activity\n")
    print(
        f"Updated automatically each evening from the server log, which records timings and outcomes "
        f"but never what was said. Last updated {now}. Counts only sessions started through the public "
        f"link; the last {DAYS_SHOWN} days with activity are shown, newest first.\n"
    )
    if not days:
        print("No tester activity recorded yet.")
        return

    print("| Date | Sessions | Sessions with a turn | Turns | Languages | Translated | Asked to repeat "
          "| No speech or setup | Errors | Median time to translation (s) |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for day in sorted(days, reverse=True)[:DAYS_SHOWN]:
        d = days[day]
        outcomes = Counter(o for o, _ in d["turns"])
        translated = sum(outcomes[o] for o in TRANSLATED)
        repeat = sum(outcomes[o] for o in ASKED_TO_REPEAT)
        no_speech = sum(outcomes[o] for o in NO_SPEECH)
        errors = len(d["turns"]) - translated - repeat - no_speech
        timed = [s for o, s in d["turns"] if o in TRANSLATED]
        median = f"{statistics.median(timed):.1f}" if timed else "-"
        langs = ", ".join(f"{name} ({n})" for name, n in d["langs"].most_common()) or "-"
        label = datetime.strptime(day, "%Y-%m-%d").strftime("%d %b %Y")
        print(f"| {label} | {len(d['sessions'])} | {len(d['spoke'])} | {len(d['turns'])} | {langs} | "
              f"{translated} | {repeat} | {no_speech} | {errors} | {median} |")


if __name__ == "__main__":
    main()
