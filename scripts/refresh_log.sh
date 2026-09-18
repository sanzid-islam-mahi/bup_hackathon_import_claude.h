#!/bin/bash
# Refresh LOG.md from current git history.
# Run this if puku-cli hooks aren't configured: bash scripts/refresh_log.sh
set -e
cd "$(dirname "$0")/.."

LOG="LOG.md"
TMP=$(mktemp)

# Header
cat > "$TMP" <<EOF
# GridWise — Collaborator Log

> Live change log for the team.
> Auto-refresh: \`bash scripts/refresh_log.sh\`
> Source of truth: \`git log --name-only\` over the last 50 commits.

---

EOF

# Recent commits with changed files
git log --name-only --pretty=format:'### %ad %h %s' --date=short -50 >> "$TMP" 2>/dev/null || echo "(no commits yet)" >> "$TMP"

# Decisions section (manual — preserved at bottom)
cat >> "$TMP" <<'EOF'

---

## How to use this log

- **For the team:** Run `bash scripts/refresh_log.sh` any time to regenerate from git history.
- **For judges / outsiders:** This file shows what's been built and when.
- **For puku-cli users:** A `PostToolUse` hook (in `.puku-cli/settings.json`) appends per-edit entries. See `scripts/log_hook.sh`.

## Stack & Decisions (manual)

| Item | Value |
|------|-------|
| LLM | Groq `openai/gpt-oss-120b` |
| Backup LLM | Gemini `gemini-flash-lite-latest` |
| Framework | FastAPI |
| Optimizer | TBD (greedy first, scipy LP later) |
| Deploy target | TBD (Render/ngrok) |
| Time budget | 4 hours (7 PM – 11 PM) |

EOF

mv "$TMP" "$LOG"
echo "LOG.md refreshed at $(date +%H:%M:%S)"
