#!/usr/bin/env python3
"""
Mine YouTube/Google autocomplete suggestions for a set of seed keywords in a
given language/country. Free, no API key, no ToS issue (this is the same
public endpoint that powers the actual search-box suggestions).

Usage:
  python3 autocomplete-mine.py --hl pt-BR --gl BR "gerador de tags" "extrator de tags do youtube" "verificador de ranking do youtube"
  python3 autocomplete-mine.py --hl id-ID --gl ID "cara membuat tag youtube" "pembuat tag youtube"
  python3 autocomplete-mine.py --hl hi-IN --gl IN "youtube tag generator" "youtube tag जनरेटर"

Output: one Markdown block per seed, ready to paste into a
seo/KEYWORD-RESEARCH-*.md file, same format as the existing EN research doc.
"""
import argparse
import json
import sys
import time
import urllib.parse
import urllib.request

ENDPOINT = "https://suggestqueries.google.com/complete/search"


def fetch_suggestions(seed: str, hl: str, gl: str, ds: str = "yt") -> list[str]:
    params = {"client": "firefox", "ds": ds, "q": seed, "hl": hl, "gl": gl}
    url = f"{ENDPOINT}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data[1] if len(data) > 1 else []


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("seeds", nargs="+", help="Seed keywords/phrases to expand")
    ap.add_argument("--hl", default="en", help="Language code (e.g. pt-BR, id-ID, hi-IN, tr-TR)")
    ap.add_argument("--gl", default="US", help="Country code (e.g. BR, ID, IN, TR)")
    ap.add_argument("--ds", default="yt", help="Dataset: 'yt' for YouTube suggestions, omit/'' for general Google web suggestions")
    ap.add_argument("--delay", type=float, default=0.6, help="Seconds between requests (be polite)")
    args = ap.parse_args()

    for seed in args.seeds:
        try:
            suggestions = fetch_suggestions(seed, args.hl, args.gl, args.ds)
        except Exception as e:
            print(f"## \"{seed}\"\n\n(fetch failed: {e})\n", file=sys.stderr)
            continue

        print(f'## "{seed}" ({args.hl}/{args.gl})\n')
        if not suggestions:
            print("(no suggestions returned)\n")
        else:
            for s in suggestions:
                print(f"- {s}")
            print()
        time.sleep(args.delay)


if __name__ == "__main__":
    main()
