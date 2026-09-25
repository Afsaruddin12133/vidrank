#!/usr/bin/env bash
# Bulk keyword discovery: give it several seed keywords, get back every
# related keyword DataForSEO knows about across all of them — deduped,
# sorted by volume, flagged for low-competition opportunities (KD<=20 with
# real volume). Real exact numbers, not banded guesses.
#
# Usage: keyword-discover.sh <location-code> <lang> "<seed1>" "<seed2>" ...
#   keyword-discover.sh 2840 en "youtube tag generator" "youtube title generator"
#
# Location codes: US=2840, Brazil=2076, Indonesia=2360, India=2356, Turkey=2792
# (full list: dataforseo.com/help-center/locations)
#
# Requires ~/seo-agent-worker/.run-token to exist (it already does).

set -euo pipefail

LOCATION="${1:?usage: keyword-discover.sh <location-code> <lang> \"<seed1>\" [\"<seed2>\" ...]}"
LANG_CODE="${2:?usage: keyword-discover.sh <location-code> <lang> \"<seed1>\" [\"<seed2>\" ...]}"
shift 2
SEEDS=("$@")
if [[ ${#SEEDS[@]} -eq 0 ]]; then
  echo "usage: keyword-discover.sh <location-code> <lang> \"<seed1>\" [\"<seed2>\" ...]" >&2
  exit 1
fi

TOKEN_FILE="$HOME/seo-agent-worker/.run-token"
if [[ ! -f "$TOKEN_FILE" ]]; then
  echo "missing $TOKEN_FILE" >&2
  exit 1
fi
TOKEN=$(cat "$TOKEN_FILE")

# Join seeds with | for the ?kws= param.
JOINED=$(IFS='|'; echo "${SEEDS[*]}")
ENC=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$JOINED")

curl -s "https://seo-agent.fahad288ali.workers.dev/?kws=${ENC}&location=${LOCATION}&lang=${LANG_CODE}&token=${TOKEN}" | \
  python3 -c "
import json, sys
d = json.load(sys.stdin)
if not d.get('ok'):
    print('ERROR:', d.get('error', d), file=sys.stderr)
    sys.exit(1)
print(f\"{d['total_unique_keywords']} unique keywords across {len(d['seeds'])} seeds | {d['opportunities']} flagged as opportunities (KD<=20, real volume)\")
print()
print(f\"{'Keyword':<45} {'Volume':>8} {'KD':>5}  Opp\")
print('-' * 68)
for k in d['keywords']:
    vol = k['search_volume'] if k['search_volume'] is not None else '-'
    kd = k['keyword_difficulty'] if k['keyword_difficulty'] is not None else '-'
    print(f\"{k['keyword']:<45} {str(vol):>8} {str(kd):>5}  {'★' if k['opportunity'] else ''}\")
"
