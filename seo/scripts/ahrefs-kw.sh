#!/usr/bin/env bash
# Pulls real Ahrefs keyword-generator data (volume band + KD) for one or more
# seed keywords, via the user's own logged-in Chrome (opencli) — the same way
# a human would use the free tool, one query at a time, at human pace. This
# rides the free tool's own rate limit (~6-7 queries/day/session), it does
# not attempt to defeat it.
#
# Usage:
#   ahrefs-kw.sh <country-code> "<keyword1>" ["<keyword2>" ...]
#   ahrefs-kw.sh us "youtube tag generator" "youtube title generator"
#
# Output: one clean table per keyword, printed as it's fetched (so you get
# partial results immediately even if a later query gets rate-limited).

set -uo pipefail

COUNTRY="${1:?usage: ahrefs-kw.sh <country-code> \"<keyword>\" [\"<keyword2>\" ...]}"
shift
KEYWORDS=("$@")
if [[ ${#KEYWORDS[@]} -eq 0 ]]; then
  echo "usage: ahrefs-kw.sh <country-code> \"<keyword>\" [\"<keyword2>\" ...]" >&2
  exit 1
fi

PROFILE="${OPENCLI_PROFILE:-sxc3me7b}"
SESSION="${OPENCLI_SESSION:-ahrefs-kw}"
PARSER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/ahrefs-kw-parse.py"

fetch_one() {
  local keyword="$1"
  local enc
  enc=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$keyword")
  local url="https://ahrefs.com/keyword-generator/?country=${COUNTRY}&input=${enc}"

  opencli --profile "$PROFILE" browser "$SESSION" open "$url" >/dev/null 2>&1
  sleep 3

  local raw
  raw=$(opencli --profile "$PROFILE" browser "$SESSION" eval \
    "(() => { const el = Array.from(document.querySelectorAll('*')).find(e => e.textContent.startsWith('Keyword ideas for') && e.children.length < 30); return el ? el.textContent.split('Turn a keyword')[0] : 'NO_RESULTS'; })()" \
    2>/dev/null | grep -v "^\s*$" | grep -v "Update available" | grep -v "npm install")

  echo "=== \"$keyword\" ($COUNTRY) ==="

  if [[ -z "$raw" ]]; then
    echo "(empty response — Chrome may not be reachable; run 'opencli doctor')"
    return 1
  fi
  if [[ "$raw" == *"NO_RESULTS"* ]]; then
    echo "(no keyword-ideas block found on the page)"
    return 1
  fi
  if [[ "$raw" == *"Sign up"* && "$raw" != *"Keyword ideas for"* ]]; then
    echo "(looks rate-limited/gated — Ahrefs is showing a signup wall instead of results. Stop here for today; free-tier daily limit is ~6-7 queries/session.)"
    return 2
  fi

  echo "$raw" | python3 "$PARSER"
  echo
}

hit_gate=0
for kw in "${KEYWORDS[@]}"; do
  fetch_one "$kw"
  status=$?
  if [[ $status -eq 2 ]]; then
    hit_gate=1
    break
  fi
  sleep 2
done

if [[ $hit_gate -eq 1 ]]; then
  echo "Stopped early: hit the free-tier gate. Remaining keywords not queried." >&2
  exit 2
fi
