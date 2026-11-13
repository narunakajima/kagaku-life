#!/usr/bin/env python3
"""予備採点（検索なし）の取りこぼし率の実測（指示 2026-11-13-002）。

既存の採点済み候補（news_candidates.json）に、本番と同じ予備採点（kl_news_scan.prelim_judge）をかけ、
「本採点でゲートを通った候補のうち、予備採点で落ちる割合」を出す。課金: 検索なしの Gemini 呼び出しを 件数/PRELIM_BATCH 回。

ゲート通過の定義（時間で変わる鮮度と、使用済みの一次資料は除く）:
  status が excluded でない / 検証>=4 / 一次資料URLが実在しない(False)でない / stake>=4 / 顧客事例でない / NHK政治でない
結果は prelim_measure_result.json に保存（再実行すると続きから）。

使い方: python3 kl_prelim_measure.py [--limit N]
"""
import argparse
import json
import sys
from pathlib import Path

import kl_news_scan as ns

OUT = Path(__file__).parent / "prelim_measure_result.json"


def gate_pass(c: dict) -> bool:
    if c.get("status") == "excluded":
        return False
    r = ns.gate_reasons(c, {})
    r = [x for x in r if not x.startswith("鮮度")]
    return not r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    items = json.loads(ns.CANDIDATES_JSON.read_text(encoding="utf-8"))["items"]
    if args.limit:
        items = items[:args.limit]
    res = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    todo = [c for c in items if c["id"] not in res]
    print(f"対象{len(items)}件、未測定{len(todo)}件")
    if todo:
        concerns = json.loads(ns.CONCERNS_JSON.read_text(encoding="utf-8"))["concerns"]
        ctxt = "\n".join(f"- {c['id']}: {c['label']}" for c in concerns)
        client, types = ns._gemini()
        past = ns.past_episodes_brief()
        step = 120
        for s in range(0, len(todo), step):
            part = todo[s:s + step]
            js = ns.prelim_judge(client, types, part, past, ctxt)
            for c, j in zip(part, js):
                res[c["id"]] = j
            OUT.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
            print(f"  {min(s + step, len(todo))}/{len(todo)}")
    n_none = sum(1 for c in items if not res.get(c["id"]))
    gp = [c for c in items if gate_pass(c)]

    def dropped(c, dup):
        ok, _, _ = ns.prelim_decision(res.get(c["id"]), check_duplicate=dup and c.get("status") != "used")
        return not ok
    print(f"\n判定が取れなかった: {n_none}件（通す扱い）")
    print(f"全{len(items)}件: 予備で落ちる {sum(dropped(c, True) for c in items)}件（stakeだけなら {sum(dropped(c, False) for c in items)}件）")
    print(f"ゲート通過 {len(gp)}件（{len(gp) / max(1, len(items)):.1%}）")
    for label, dup in (("stake+投資+重複（本番の条件）", True), ("stakeと投資のみ", False)):
        miss = [c for c in gp if dropped(c, dup)]
        print(f"取りこぼし［{label}］: {len(miss)}/{len(gp)} = {len(miss) / max(1, len(gp)):.1%}")
        for c in miss[:15]:
            j = res.get(c["id"]) or {}
            print(f"   - stake本採点{ns.stake(c)} 予備{ns.stake(j)} dup={j.get('duplicate_of_past')} inv={j.get('investment_related')} {c['title'][:50]}")
    # しきい値別（stakeのみ）
    for t in (2, 3, 4):
        m = sum(1 for c in gp if ns.stake(res.get(c["id"]) or {"life_relevance": 5}) < t)
        d = sum(1 for c in items if ns.stake(res.get(c["id"]) or {"life_relevance": 5}) < t)
        print(f"  stake>={t} で通す場合: 取りこぼし {m}/{len(gp)} = {m / max(1, len(gp)):.1%}、全体で落ちる割合 {d / len(items):.1%}")
    # 通過後の本採点件数の目安: 予備を通ったもののうちゲート通過
    passed = [c for c in items if not dropped(c, True)]
    print(f"予備を通る {len(passed)}件（{len(passed) / len(items):.1%}）、うちゲート通過 {sum(gate_pass(c) for c in passed)}件")


if __name__ == "__main__":
    sys.exit(main())
