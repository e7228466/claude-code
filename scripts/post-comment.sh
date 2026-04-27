#!/bin/bash
set -e

RESULT=$(cat /tmp/review-result.json)

# JSON から verdict を取得
VERDICT=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('verdict','unknown'))")
SUMMARY=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('summary',''))")

# emoji を設定
if [ "$VERDICT" = "approve" ]; then
  EMOJI="✅"
else
  EMOJI="❌"
fi

# comment 本文を組み立て
COMMENT="${EMOJI} **Claude Code Review**

${SUMMARY}
"

# issues を追加
ISSUES=$(echo "$RESULT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for i in d.get('issues', []):
    sev = i.get('severity','info').upper()
    f   = i.get('file','?')
    ln  = i.get('line','?')
    msg = i.get('message','')
    fix = i.get('fix','')
    print(f'- **{sev}** \`{f}\` line {ln}: {msg}')
    if fix:
        print(f'  > Fix: \`{fix}\`')
")

if [ -n "$ISSUES" ]; then
  COMMENT="${COMMENT}
### Issues found

${ISSUES}
"
fi

COMMENT="${COMMENT}
---
*Posted by Claude Code (claude.ai Pro)*"

# GitHub API で PR に comment を投稿
curl -s -X POST \
  "https://api.github.com/repos/${REPO}/issues/${PR_NUMBER}/comments" \
  -H "Authorization: Bearer ${GITHUB_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$(python3 -c "import json,sys; print(json.dumps({'body': sys.argv[1]}))" "$COMMENT")"