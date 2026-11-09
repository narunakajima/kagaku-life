#!/usr/bin/env python3
"""news_candidates.json に series_candidate_info を当てた該当件数（読み取りのみ。ファイルは書かない）。
  python3 kl_series_hits.py
"""
import json
from collections import Counter
import kl_news_scan as k

d = json.load(open(k.BASE_DIR / "news_candidates.json", encoding="utf-8"))
cands = d if isinstance(d, list) else d.get("items", [])
cnt = Counter()
for c in cands:
    if not isinstance(c, dict):
        continue
    si = k.series_candidate_info(c)
    if si:
        cnt[si["series_id"]] += 1
        print(si["series_id"], "|", c.get("genre"), "|", c.get("title", "")[:60], "|", "・".join(si["milestones"]))
print("候補総数", len(cands), dict(cnt))
