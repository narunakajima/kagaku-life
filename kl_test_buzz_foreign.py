#!/usr/bin/env python3
"""注目度の海外分（2026-11-10、handoff 2026-11-10-013）の試験。ファイルは書き換えない（保存関数を差し替える）。
python3 kl_test_buzz_foreign.py"""
import copy
import sys

import kl_news_scan as ks

NG = []


def check(name, ok):
    print(("OK  " if ok else "NG  ") + name)
    if not ok:
        NG.append(name)


# 1. 合成: 従来より下がらない・海外だけは最大4・Yahoo!は日本の媒体2以上のときだけ
for nj in range(0, 12):
    for nf in (0, 1, 2, 5, 10, 11, 30, 100):
        for y in (False, True):
            r = ks.combine_foreign(nj, y, nf)
            jp = next(s for lo, s in ks.BUZZ_TIERS if nj >= lo)
            if y and nj >= ks.BUZZ_YAHOO_BONUS_MIN_OUTLETS:
                jp = min(5, jp + 1)
            if r["buzz_measured"] < jp or r["buzz_jp_measured"] != jp:
                check(f"下がらない nj={nj} nf={nf} yahoo={y}", False)
check("合成: 全組み合わせで従来より下がらない", not NG)
check("海外だけ nf=4 → 2（入口に届かない）", ks.combine_foreign(0, False, 4)["buzz_measured"] == 2)
check("海外だけ nf=5 → 3（入口、boost）", (lambda r: r["buzz_measured"] == 3 and r["buzz_foreign_boost"])(ks.combine_foreign(0, False, 5)))
check("海外だけ nf=100 → 最大4", ks.combine_foreign(0, False, 100)["buzz_measured"] == 4)
check("日本4・海外100 → 5", ks.combine_foreign(4, False, 100)["buzz_measured"] == 5)
check("日本が既に3以上なら boost にならない", not ks.combine_foreign(3, False, 30)["buzz_foreign_boost"])
check("Yahoo!は日本の媒体1では付かない（海外分で付かない）", ks.combine_foreign(1, True, 30)["buzz_measured"] == 4)

# 2. 海外の見出し照合は語境界（been・neon・2003 に当たらない）
items = [{"title": "He has been to Amazon", "outlet": "A", "host": "a.com", "date": ""},
         {"title": "Neon sign in 2003", "outlet": "B", "host": "b.com", "date": ""},
         {"title": "Amazon Bee wristband announced", "outlet": "C", "host": "c.com", "date": ""}]
check("count_foreign: 'bee' は been に当たらない", ks.count_foreign(items, ["amazon", "bee"]) == 1)
check("count_foreign: 'neo' は neon に当たらない", ks.count_foreign(items, ["neo"]) == 0)
check("count_foreign: '03' は 2003 に当たらない", ks.count_foreign(items, ["03"]) == 0)

# 3. 汎用語だけの検索語は海外を測らない
check("汎用語（ChatGPT）は測らない", ks.foreign_query({"jp_news_query": "ChatGPT 音声"})[0] == "")
check("日本語だけの検索語は測らない", ks.foreign_query({"jp_news_query": "国立がん研究センター レゴラフェニブ"})[0] == "")
check("固有名（1X NEO）は測る", ks.foreign_query({"jp_news_query": "1X NEO"})[0] == "1X NEO")

# 4. classify のガード: 海外分で入口を越えた候補は fit<4 なら本命にならない
base = {"id": "t1", "title": "x", "status": "available", "buzz_measured": 3, "buzz_jp_measured": 1, "buzz_outlets": 0,
        "buzz_foreign_boost": True, "verifiability": 5, "freshness": 5, "life_relevance": 5, "work_relevance": 5,
        "published": ks._today(), "announced_on": ks._today(), "hype_gap": 3, "debate": 3}
lo, hi = dict(base, audience_fit=3), dict(base, id="t2", audience_fit=5)
rows = {r["c"]["id"]: r for r in ks.classify([lo, hi])}
check("fit3 の海外ブーストは本命にならない", rows["t1"]["lane"] != "本命")
check("fit5 の海外ブーストは本命になる", rows["t2"]["lane"] == "本命")

# 5. dedupe: head が未計測・兄弟が海外ブーストのとき、海外の欄も一緒に写る（印が落ちてガードをすり抜けない）
head = dict(base, id="h1", title="head story", buzz_measured=None, primary_verified=True, surprise_line="s", audience_fit=3)
for k in ("buzz_jp_measured", "buzz_outlets_foreign", "buzz_foreign_boost", "buzz_outlets"):
    head.pop(k, None)
sib = dict(base, id="h2", title="sibling story", audience_fit=3, buzz_outlets_foreign=8, buzz_query_en="X")
head["dup_ids"] = ["h2"]
store = {"items": [head, sib]}
saved = {}
orig = (ks.load_candidates, ks._save_candidates)
ks.load_candidates = lambda: copy.deepcopy(store)
ks._save_candidates = lambda c: saved.update(c)
try:
    ks.cmd_dedupe(dry_run=False)
finally:
    ks.load_candidates, ks._save_candidates = orig
res = {c["id"]: c for c in saved.get("items", [])}
h = res.get("h1", {})
check("dedupe: 統合された", res.get("h2", {}).get("status") == ks.STATE_MERGED)
check("dedupe: 海外の欄が一緒に写った", h.get("buzz_foreign_boost") is True and h.get("buzz_jp_measured") == 1
      and h.get("buzz_outlets_foreign") == 8)
# head が自分の実測を持つときは写さない（下がらない）
head2 = dict(base, id="h3", title="head story 2", buzz_measured=3, buzz_outlets=4, primary_verified=True, surprise_line="s", audience_fit=3)
for k in ("buzz_jp_measured", "buzz_outlets_foreign", "buzz_foreign_boost"):
    head2.pop(k, None)
sib2 = dict(base, id="h4", title="sibling story 2", buzz_outlets_foreign=8)
head2["dup_ids"] = ["h4"]
store = {"items": [head2, sib2]}
saved.clear()
ks.load_candidates = lambda: copy.deepcopy(store)
ks._save_candidates = lambda c: saved.update(c)
try:
    ks.cmd_dedupe(dry_run=False)
finally:
    ks.load_candidates, ks._save_candidates = orig
h = {c["id"]: c for c in saved.get("items", [])}.get("h3", {})
check("dedupe: head が実測済みなら海外の欄を写さない", h.get("buzz_measured") == 3 and "buzz_foreign_boost" not in h)

print(f"\nNG {len(NG)}件")
sys.exit(1 if NG else 0)
