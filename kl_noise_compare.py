#!/usr/bin/env python3
"""モデル揺らぎ（ノイズ基準）の測定（2026-11-15 指示001）。本番データは書き換えない。有効化・本番設定の変更はしない。

  score  : 指示2026-11-13-007 の候補20件（thinking_compare_result.json の id）を、旧設定（思考量デフォルト）で独立に2回採点し直し、
           あわせて low で1回採点して実トークン数（思考・出力）を記録する。結果 noise_score_result.json
  tag    : 保存済み入力で現行 Flash を2回実行し、2回同士・旧ラベルとの一致率を出す。結果 noise_tag_result.json
  enrich : 発表種別について50件で同様に行う。結果 noise_enrich_result.json

使い方: python3 kl_noise_compare.py score|tag|enrich
"""
import json
import sys
import time
from pathlib import Path

import kl_news_scan as ns
import kl_light_compare as lc
import kl_thinking_compare as tc

BASE = Path(__file__).parent


class _Models:
    def __init__(self, inner, log):
        self._inner, self._log = inner, log

    def generate_content(self, *a, **k):
        r = self._inner.generate_content(*a, **k)
        u = getattr(r, "usage_metadata", None)
        if u is not None:
            self._log.append({"prompt": getattr(u, "prompt_token_count", 0) or 0,
                              "out": getattr(u, "candidates_token_count", 0) or 0,
                              "think": getattr(u, "thoughts_token_count", 0) or 0,
                              "tool": getattr(u, "tool_use_prompt_token_count", 0) or 0})
        return r

    def __getattr__(self, n):
        return getattr(self._inner, n)


class _Client:
    def __init__(self, inner, log):
        self._inner = inner
        self.models = _Models(inner.models, log)

    def __getattr__(self, n):
        return getattr(self._inner, n)


def tot(log):
    return {k: sum(x[k] for x in log) for k in ("prompt", "out", "think", "tool")} | {"calls": len(log)}


def cmd_score():
    prev = json.loads((BASE / "thinking_compare_result.json").read_text(encoding="utf-8"))["rows"]
    ids = [r["id"] for r in prev]
    allc = {c["id"]: c for c in ns.load_candidates()["items"]}
    sel = [allc[i] for i in ids if i in allc]
    print("対象", len(sel), "/", len(ids), flush=True)
    concerns = json.loads(ns.CONCERNS_JSON.read_text(encoding="utf-8"))["concerns"]
    ctxt = "\n".join(f"- {c['id']}: {c['label']}" for c in concerns)
    client0, types = ns._gemini()
    past = ns.past_episodes_brief()
    runs = {}
    for label, flag in (("old_a", False), ("old_b", False), ("low", True)):
        log = []
        client = _Client(client0, log)
        ns.THINKING_LOW = flag
        rows, t0 = {}, time.time()
        for c in sel:
            t1 = time.time()
            v = ns.score_item(client, types, c, past, ctxt)
            dt = time.time() - t1
            if "_error" in v:
                rows[c["id"]] = {"error": v["_error"][:100], "sec": round(dt, 1)}
            else:
                sc, _ = ns.overall(v, c.get("published", ""))
                rows[c["id"]] = {"score": sc, "gate": tc.gate(v, c.get("published", "")), "sec": round(dt, 1),
                                 **{k: v.get(k) for k in tc.FIELDS}}
            time.sleep(1)
        runs[label] = {"rows": rows, "sec": round(time.time() - t0, 1), "tokens": tot(log)}
        print(label, "done", runs[label]["sec"], runs[label]["tokens"], flush=True)
        (BASE / "noise_score_result.json").write_text(json.dumps({"runs": runs}, ensure_ascii=False, indent=2), encoding="utf-8")

    def cmp(a, b):
        ra, rb = runs[a]["rows"], runs[b]["rows"]
        ok = [i for i in ra if "score" in ra[i] and i in rb and "score" in rb[i]]
        d = [abs(ra[i]["score"] - rb[i]["score"]) for i in ok]
        return {"compared": len(ok), "errors": len(sel) - len(ok),
                "gate_flips": sum(1 for i in ok if ra[i]["gate"] != rb[i]["gate"]),
                "mean_abs_diff": round(sum(d) / len(d), 3) if d else None, "max_abs_diff": round(max(d), 3) if d else None,
                "diff_ge_0.5": sum(1 for x in d if x >= 0.5),
                "field_diff": {k: sum(1 for i in ok if ra[i].get(k) != rb[i].get(k)) for k in tc.FIELDS},
                "sec": [runs[a]["sec"], runs[b]["sec"]]}
    summ = {"old_a_vs_old_b": cmp("old_a", "old_b"), "old_a_vs_low": cmp("old_a", "low"), "old_b_vs_low": cmp("old_b", "low")}
    (BASE / "noise_score_result.json").write_text(json.dumps({"summary": summ, "runs": runs}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summ, ensure_ascii=False, indent=1))


def cmd_tag():
    ns.LIGHT_MODEL_ON = False
    ns.THINKING_LOW = False
    base = ns.load_candidates()["items"]
    tag_in = [c for c in base if c.get("genre") and c.get("title")]
    r1, r2 = lc.run_tag(tag_in), lc.run_tag(tag_in)
    n = len(tag_in)

    def same(x, y, c):
        return x[c["id"]].get("genre") == y[c["id"]].get("genre")

    def both(x, y, c):
        return same(x, y, c) and bool(x[c["id"]].get("health")) == bool(y[c["id"]].get("health"))
    old = {c["id"]: c for c in tag_in}
    res = {"model": ns.MODEL, "n": n,
           "run1_vs_run2_genre": sum(same(r1, r2, c) for c in tag_in), "run1_vs_run2_both": sum(both(r1, r2, c) for c in tag_in),
           "run1_vs_old_genre": sum(same(r1, old, c) for c in tag_in), "run1_vs_old_both": sum(both(r1, old, c) for c in tag_in),
           "run2_vs_old_genre": sum(same(r2, old, c) for c in tag_in), "run2_vs_old_both": sum(both(r2, old, c) for c in tag_in)}
    res["pct"] = {k: round(100.0 * v / n, 1) for k, v in res.items() if k.startswith("run")}
    (BASE / "noise_tag_result.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1))


def cmd_enrich():
    ns.LIGHT_MODEL_ON = False
    ns.THINKING_LOW = False
    base = ns.load_candidates()["items"]
    en_in = [c for c in base if c.get("jp_news_query") and c.get("announcement_type") and c.get("status") == "available"][:50]
    r1, r2 = lc.run_enrich(en_in), lc.run_enrich(en_in)
    n = len(en_in)
    old = {c["id"]: c for c in en_in}

    def t(x, c):
        return x[c["id"]].get("announcement_type")
    res = {"model": ns.MODEL, "n": n,
           "run1_vs_run2": sum(t(r1, c) == t(r2, c) for c in en_in),
           "run1_vs_old": sum(t(r1, c) == t(old, c) for c in en_in),
           "run2_vs_old": sum(t(r2, c) == t(old, c) for c in en_in),
           "got_query_run1": sum(bool(r1[c["id"]].get("jp_news_query")) for c in en_in),
           "got_query_run2": sum(bool(r2[c["id"]].get("jp_news_query")) for c in en_in)}
    res["pct"] = {k: round(100.0 * v / n, 1) for k, v in res.items() if k.startswith("run")}
    res["mismatch_run1_run2"] = [{"title": c["title"][:50], "r1": t(r1, c), "r2": t(r2, c), "old": t(old, c)}
                                 for c in en_in if t(r1, c) != t(r2, c)]
    (BASE / "noise_enrich_result.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if "mismatch" not in k}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    {"score": cmd_score, "tag": cmd_tag, "enrich": cmd_enrich}[sys.argv[1]]()
