#!/bin/bash
# puku-cli PostToolUse hook for Edit|Write|MultiEdit.
# Appends a one-line entry to LOG.md so the collaborator sees what's changing.
# Triggered automatically by puku-cli after each file edit.
set -e

LOG="/home/sanzid/competitions/bup-hackathon/gridwise/LOG.md"
TS=$(date +%H:%M:%S)

# Read stdin (puku-cli pipes tool input as JSON)
INPUT=$(cat)

# Extract the tool name and file paths using simple grep/sed (no jq dependency)
TOOL=$(echo "$INPUT" | grep -oE '"tool_name"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed -E 's/.*"([^"]+)".*/\1/')
[ -z "$TOOL" ] && TOOL=$(echo "$INPUT" | grep -oE '"name"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed -E 's/.*"([^"]+)".*/\1/')

FILE=$(echo "$INPUT" | grep -oE '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed -E 's/.*"([^"]+)".*/\1/')
[ -z "$FILE" ] && FILE=$(echo "$INPUT" | grep -oE '"path"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed -E 's/.*"([^"]+)".*/\1/')

# Skip if no file detected (e.g., hook fired on a non-file tool)
[ -z "$FILE" ] && exit 0

# Relative path for readability
REL="${FILE#/home/sanzid/competitions/bup-hackathon/gridwise/}"

# Append to LOG.md
printf "## %s — %s\n- file: \`%s\`\n\n" "$TS" "${TOOL:-edit}" "$REL" >> "$LOG"
