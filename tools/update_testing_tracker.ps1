# Daily refresh of the "Tester activity" section in the Interpreter Testing Tracker doc.
# Builds the section from the backend's metadata-only log (tools/tester_activity_report.py),
# then runs Claude Code headless, allowed only the Docs tools, to paste it into the doc.
# Scheduled via Windows Task Scheduler ("Interpreter testing tracker refresh"); output is
# appended to server/logs/tracker_update.log.

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$docId = 'adc63dfd-2673-482d-922a-ec269c2ed822'
$log = Join-Path $repo 'server\logs\tracker_update.log'

$section = (& python (Join-Path $repo 'tools\tester_activity_report.py') | Out-String).Trim()

$prompt = @"
Update the Claude Doc with id $docId (the "Interpreter Testing Tracker"). In its only tab,
replace the whole "## Tester activity" section -- its heading and every block after it up to,
but not including, the next "## " heading -- with exactly the Markdown between the markers
below, sent as markdown. Change nothing else in the doc and do not create a new doc. If the
section is missing, insert it immediately before the "## Quality by language" heading.
Finish with one line: "done", or what went wrong.

---BEGIN SECTION---
$section
---END SECTION---
"@

$tools = 'ToolSearch mcp__claude_ai_Claude_Docs__guide mcp__claude_ai_Claude_Docs__read mcp__claude_ai_Claude_Docs__update mcp__claude_ai_Claude_Docs__batch'
Set-Location $repo
$result = $prompt | & claude -p --allowedTools $tools 2>&1 | Out-String
Add-Content -Path $log -Value ("{0}  {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm'), $result.Trim()) -Encoding utf8
