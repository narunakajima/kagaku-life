#!/usr/bin/env python3
"""軽い工程の Flash-Lite 切り替え前の新旧比較（2026-11-14 指示008）。

保存済みの news_candidates.json（旧モデル=Flash が付けた genre/health・announcement_type・series・jp_title_anchor）を
入力にして、同じ入力で新モデル（Flash-Lite）を実行し直し、分類結果の一致率を測る。本番データは書き換えない
（一時ファイルにコピーして実行）。結果は light_compare_result.json。
collect の分野の絞り込みは、落とした側の入力・結果が保存されていない（news_pool.json は残した分だけ）ため比較できない。

使い方: python3 kl_light_compare.py [--max-enrich 50]
"""
import argparse
import copy
import json
import tempfile
from pathlib import Path

import kl_news_scan as ns
import kl_gemini_model as gm

OUT = Path(__file__).parent / "light_compare_result.json"


def pct(a, b):
    return round(100.0 * a / b, 1) if b else None


def run_tag(items):
    tmp = Path(tempfile.mkdtemp()) / "cands.json"
    d = {"items": copy.deepcopy(items)}
    for c in d["items"]:
        c.pop("genre", None)
        c.pop("health", None)
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    ns.CANDIDATES_JSON = tmp
    ns.cmd_tag()
    return {c["id"]: c for c in json.loads(tmp.read_text(encoding="utf-8"))["items"]}


def run_enrich(items):
    tmp = Path(tempfile.mkdtemp()) / "cands.json"
    d = {"items": copy.deepcopy(items)}
    for c in d["items"]:
        for k in ("jp_news_query", "jp_title_anchor", "announcement_type", "series"):
            c.pop(k, None)
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    ns.CANDIDATES_JSON = tmp
    ns.refresh_topic_ages = lambda *a, **k: None
    ns.backfill_work = lambda *a, **k: (0, 0)
    ns.backfill_audience = lambda *a, **k: (0, 0)
    ns.retry_surprise = lambda *a, **k: None
    ns.report_stall = lambda *a, **k: None
    ns._gate_pool = lambda cands: [c for c in cands if c.get("status") == "available"]
    try:
        ns.cmd_enrich(True)
    except SystemExit:
        pass
    return {c["id"]: c for c in json.loads(tmp.read_text(encoding="utf-8"))["items"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-enrich", type=int, default=50)
    a = ap.parse_args()
    ns.LIGHT_MODEL_ON = True
    print("light model:", ns._light_model())
    base = ns.load_candidates()["items"]
    res = {"model_new": ns._light_model(), "model_old": ns.MODEL}

    tag_in = [c for c in base if c.get("genre") and c.get("title")]
    new = run_tag(tag_in)
    g_ok = sum(1 for c in tag_in if new[c["id"]].get("genre") == c["genre"])
    h_ok = sum(1 for c in tag_in if bool(new[c["id"]].get("health")) == bool(c.get("health")))
    both = sum(1 for c in tag_in if new[c["id"]].get("genre") == c["genre"]
               and bool(new[c["id"]].get("health")) == bool(c.get("health")))
    res["tag"] = {"n": len(tag_in), "genre_match": g_ok, "health_match": h_ok, "both_match": both,
                  "genre_pct": pct(g_ok, len(tag_in)), "both_pct": pct(both, len(tag_in)),
                  "mismatch": [{"title": c["title"][:50], "old": [c["genre"], c.get("health")],
                                "new": [new[c["id"]].get("genre"), new[c["id"]].get("health")]}
                               for c in tag_in if new[c["id"]].get("genre") != c["genre"]
                               or bool(new[c["id"]].get("health")) != bool(c.get("health"))]}

    en_in = [c for c in base if c.get("jp_news_query") and c.get("announcement_type") and c.get("status") == "available"]
    en_in = en_in[:a.max_enrich]
    newe = run_enrich(en_in)
    t_ok = sum(1 for c in en_in if newe[c["id"]].get("announcement_type") == c["announcement_type"])
    s_ok = sum(1 for c in en_in if newe[c["id"]].get("series") == c.get("series"))
    anc_ok = sum(1 for c in en_in if set(newe[c["id"]].get("jp_title_anchor") or []) & set(c.get("jp_title_anchor") or []))
    got = sum(1 for c in en_in if newe[c["id"]].get("jp_news_query"))
    res["enrich"] = {"n": len(en_in), "got_query": got, "type_match": t_ok, "type_pct": pct(t_ok, len(en_in)),
                     "series_match": s_ok, "series_pct": pct(s_ok, len(en_in)),
                     "anchor_overlap": anc_ok, "anchor_pct": pct(anc_ok, len(en_in)),
                     "type_mismatch": [{"title": c["title"][:50], "old": c["announcement_type"],
                                        "new": newe[c["id"]].get("announcement_type")}
                                       for c in en_in if newe[c["id"]].get("announcement_type") != c["announcement_type"]]}
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: {x: y for x, y in v.items() if "mismatch" not in x} for k, v in res.items()
                      if isinstance(v, dict)}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
