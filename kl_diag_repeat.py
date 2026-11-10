#!/usr/bin/env python3
"""news_candidates.json の git 履歴から、指定語を含む候補の提示履歴（presented_on・status）を各コミット時点で並べる診断（読み取りのみ）。
使い方: python3 kl_diag_repeat.py PHP "Echo Time" --commits 0231e77 4b3011b ..."""
import argparse, json, subprocess

ap = argparse.ArgumentParser()
ap.add_argument("words", nargs="+")
ap.add_argument("--commits", nargs="+", required=True)
a = ap.parse_args()
for h in a.commits:
    d = json.loads(subprocess.check_output(["git", "show", f"{h}:news_candidates.json"]))
    print("==", h, subprocess.check_output(["git", "log", "-1", "--format=%ad %s", "--date=iso", h]).decode().strip())
    for c in d["items"]:
        t = c.get("title", "")
        if any(w in t for w in a.words):
            print(" ", c["id"], c.get("status"), c.get("presented_on"), "merged_into=", c.get("merged_into"),
                  "art=", c.get("published"), "seen=", (c.get("first_seen_at") or "")[:16], t[:50])
