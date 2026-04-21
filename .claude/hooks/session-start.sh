#!/usr/bin/env bash
# SessionStart hook — runs once when a Claude Code session opens.
# Prints a brief status banner to the transcript. Exit 0 always.
set -u

cd "$CLAUDE_PROJECT_DIR" 2>/dev/null || exit 0

branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "-")
head=$(git rev-parse --short HEAD 2>/dev/null || echo "-")
dirty=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')

cat <<EOF
Weftlyflow session started.
  branch: $branch ($head)   dirty-files: $dirty
  bible:  /IMPLEMENTATION_BIBLE.md
  memory: /home/nishantgupta/.claude/projects/-home-nishantgupta-Desktop-ng8/memory/
EOF

exit 0
