#!/usr/bin/env python3
"""同一ネタ繰り返し対策（2026-11-08）の試験。news_candidates.json を読むだけ（保存しない）。
提示日を進めながら、dedupe → ベスト3 → 提示の記録 を数日分メモリ上で回し、どの候補が何日載り、いつ棚上げされるかを出す。

使い方: python3 kl_test_news_repeat.py [開始日 YYYY-MM-DD（既定: 明日）] [日数（既定: 5）]
（鮮度など「今日」に依存する計算は実際の今日のまま。提示日・棚上げの動きだけを進める）"""
import copy
import sys
from datetime import date, timedelta

import kl_news_scan as ks


def main():
    start = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today() + timedelta(days=1)
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    state = copy.deepcopy(ks.load_candidates())
    ks.load_candidates = lambda: state
    ks._save_candidates = lambda c: None
    out = {}
    before = {c["id"]: c.get("status") for c in state["items"]}
    for i in range(n):
        day = (start + timedelta(days=i)).isoformat()
        ks._today = lambda d=day: d
        print(f"\n===== {day} の朝 =====")
        ks.cmd_dedupe(dry_run=False)
        rows = ks.classify(state["items"])
        picks, _ = ks.best3(rows)
        print(f"-- ベスト3（{len(picks)}件）。{ks.new_note(picks) or '新規候補あり'}")
        for p in picks:
            c = p["c"]
            print(f"   {c['id']} 〈{p['slot']}〉{'🆕' if ks.is_new_candidate(c) else '  '} {c['title'][:44]}（提示済み {len(ks.presented_days(c))}日）")
            out.setdefault(c["id"], []).append(day)
            c["presented_on"] = sorted(set(ks.presented_days(c)) | {day})
    print("\n===== 載った日 =====")
    by = {c["id"]: c for c in state["items"]}
    for cid, days in out.items():
        print(f"   {cid} {by[cid]['title'][:40]}: {','.join(d[5:] for d in days)}（status={by[cid].get('status')}）")
    # 巻き添えの検査: 模擬の間に status が変わった候補のうち、一度も下書きに載っていないもの（兄弟として棚上げされたもの）
    changed = [c for c in state["items"] if c.get("status") != before[c["id"]] and c["id"] not in out]
    print(f"\n===== 巻き添えの検査: 載っていないのに状態が変わった候補 {len(changed)}件（載った候補 {len(out)}件）=====")
    for c in changed:
        print(f"   {c['id']} [{before[c['id']]}→{c.get('status')}] {c.get('shelved_reason') or c.get('merged_reason') or ''} | {c['title'][:44]}")
    for w in sys.argv[3:]:
        print(f"\n===== 兄弟の確認: {w} =====")
        story_check(state, w)


def story_check(state, words):
    """指定の語を見出しに含む候補の状態とストーリー（topic_series）を出す。兄弟が同じストーリーにまとまっているかを見る。"""
    import re
    for c in state["items"]:
        if re.search(words, c.get("title", "")) and c.get("status") in ("available", "shelved", "merged", "used"):
            print(f"   {c['id']} [{c['status']}] ts={c.get('topic_series')} {_day(c)} {c['title'][:44]}")


def _day(c):
    return (c.get("announced_on") or c.get("published") or "")[:10]


if __name__ == "__main__":
    main()
