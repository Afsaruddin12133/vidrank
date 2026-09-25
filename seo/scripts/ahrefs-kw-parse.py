#!/usr/bin/env python3
"""Parse the raw concatenated text block from ahrefs-kw.sh into clean rows.

Usage: ahrefs-kw.sh "keyword" us | python3 ahrefs-kw-parse.py
"""
import re
import sys

text = sys.stdin.read().strip()

# Drop the header up to the last "UpdatedUpdated" (table header repeats once
# per column due to the sort-arrow icon rendering as a duplicate text node).
m = re.search(r"UpdatedUpdated(.*)$", text, re.S)
body = m.group(1) if m else text

# Each row is <keyword><KD><volume><date>, no delimiters. KD is one of a
# fixed vocabulary; volume is "<100", ">N", or a bare number with commas;
# date is "N Month", "N days", "about N hours/minutes", etc.
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
UNITS = "days?|hours?|minutes?|weeks?|months?|years?"
# Ahrefs' free tier only ever shows one of these fixed volume bands (never an
# arbitrary exact number) — matching a closed set instead of generic \d+ is
# what avoids swallowing the day-of-month digits that immediately follow with
# no separator in the source (e.g. ">100" + "22 August" renders as "10022 August").
KD = r"(?:Easy|Medium|Hard|N/A)"
VOL = r"(?:<100|>100,?000|>10,?000|>1,?000|>100)"
DATE = rf"(?:about\s+\d+\s+(?:{UNITS}))|(?:\d+\s+(?:{UNITS}))|(?:\d{{1,2}}\s+(?:{MONTHS}))"

row_re = re.compile(rf"(.+?)({KD})({VOL})({DATE})")

rows = []
pos = 0
for mm in row_re.finditer(body):
    kw, kd, vol, date = mm.groups()
    rows.append((kw.strip(), kd, vol, date.strip()))
    pos = mm.end()

if not rows:
    print("(could not parse — raw text below)\n")
    print(text[:2000])
    sys.exit(1)

print(f"{'Keyword':<50} {'KD':<8} {'Volume':<10} Updated")
print("-" * 85)
for kw, kd, vol, date in rows:
    print(f"{kw:<50} {kd:<8} {vol:<10} {date}")
