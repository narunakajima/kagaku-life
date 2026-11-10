"""診断（指示 2026-11-10-016）: プールの NHK 記事を一覧する。"""
import json
p = json.load(open("news_pool.json"))["items"]
print(len(p), sorted(p[0].keys()))
for x in p:
    s = (x.get("source", "") + "|" + x.get("outlet", "") + "|".join(x.get("sources") or []))
    if "NHK" in s:
        print(x["id"], x.get("source"), "/", x.get("outlet"), x.get("source_kind"), x["title"][:50], "|", (x.get("url") or x.get("gnews_link") or "")[:70])
