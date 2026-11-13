#!/usr/bin/env python3
"""思考量 low の安全確認（2026-11-13 指示007）。候補 N 件を、思考量の既定（旧）と low（新）で score_item し直して比べる。
本番データ（news_candidates.json）は書き換えない。結果は thinking_compare_result.json に書く。

使い方: python3 kl_thinking_compare.py [--n 20]
"""
import argparse
import json
import time

import kl_news_scan as ns

FIELDS = ["life_relevance", "work_relevance", "audience_fit", "verifiability", "hype_gap", "debate", "promise", "wonder"]


def gate(v, published):
    """本ゲートの主要条件のみ再現: stake>=GATE_MIN_LIFE かつ verifiability>=GATE_MIN_VERIFIABILITY かつ一次資料あり・投資でない。"""
    st = max(ns._clamp5(v.get("life_relevance")), ns._clamp5(v.get("work_relevance")))
    ok = (st >= ns.GATE_MIN_LIFE and int(v.get("verifiability") or 0) >= ns.GATE_MIN_VERIFIABILITY
          and bool(v.get("primary_sources")) and not v.get("investment_related"))
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    a = ap.parse_args()
    cands = ns.load_candidates()["items"]
    cands = [c for c in cands if c.get("title") and c.get("scored_at")]
    cands.sort(key=lambda c: c.get("scored_at", ""), reverse=True)
    sel = cands[:a.n]
    concerns = json.loads(ns.CONCERNS_JSON.read_text(encoding="utf-8"))["concerns"]
    ctxt = "\n".join(f"- {c['id']}: {c['label']}" for c in concerns)
    client, types = ns._gemini()
    past = ns.past_episodes_brief()
    from google.genai import types as T
    print("ThinkingConfig fields:", list(T.ThinkingConfig.model_fields))
    print("thinking config(new):", ns._thinking(types) if True else None)
    rows = []
    for c in sel:
        row = {"title": c["title"], "id": c["id"]}
        for label, flag in (("old", False), ("new", True)):
            ns.THINKING_LOW = flag
            t0 = time.time()
            v = ns.score_item(client, types, c, past, ctxt)
            dt = time.time() - t0
            if "_error" in v:
                row[label] = {"error": v["_error"][:100], "sec": round(dt, 1)}
            else:
                sc, _ = ns.overall(v, c.get("published", ""))
                row[label] = {"score": sc, "gate": gate(v, c.get("published", "")), "sec": round(dt, 1),
                              **{k: v.get(k) for k in FIELDS}}
            time.sleep(1)
        rows.append(row)
        print(row["title"][:50], row["old"].get("score"), row["new"].get("score"),
              row["old"].get("gate"), row["new"].get("gate"), row["old"].get("sec"), row["new"].get("sec"), flush=True)
    ok = [r for r in rows if "score" in r["old"] and "score" in r["new"]]
    flips = [r for r in ok if r["old"]["gate"] != r["new"]["gate"]]
    diffs = [abs(r["old"]["score"] - r["new"]["score"]) for r in ok]
    fd = {k: sum(1 for r in ok if r["old"].get(k) != r["new"].get(k)) for k in FIELDS}
    big = [r for r in ok if abs(r["old"]["score"] - r["new"]["score"]) >= 0.5]
    summ = {"n": len(rows), "compared": len(ok), "errors": len(rows) - len(ok), "gate_flips": len(flips),
            "mean_abs_score_diff": round(sum(diffs) / len(diffs), 3) if diffs else None,
            "max_abs_score_diff": max(diffs) if diffs else None, "score_diff_ge_0.5": len(big),
            "field_diff_counts": fd,
            "sec_old": round(sum(r["old"]["sec"] for r in ok), 1), "sec_new": round(sum(r["new"]["sec"] for r in ok), 1)}
    print(json.dumps(summ, ensure_ascii=False, indent=2))
    (ns.BASE_DIR / "thinking_compare_result.json").write_text(
        json.dumps({"summary": summ, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
