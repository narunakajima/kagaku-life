#!/usr/bin/env python3
"""提示「最大2日」ルールの再現試験（2026-11-10、handoff 2026-11-10-012）。保存しない・git の履歴を読むだけ。
指定コミットの news_candidates.json を出発点に、毎朝の nightly（dedupe → slack の下書き＋提示の記録）を日付を進めてメモリ上で回し、
ベスト3と答え合わせ候補の一覧に、どの候補が何日載ったかを出す。「同じ候補が3日目に出ない」ことの検証用。
（鮮度など「今日」に依存する計算は実際の今日のまま。提示日・棚上げの動きだけを進める）

使い方: python3 kl_test_news_repeat_replay.py <コミット> <開始日 YYYY-MM-DD> <日数> [語...]
  語を付けると、その語を見出しに含む候補の載った日を最後に並べる。"""
import contextlib
import copy
import io
import json
import subprocess
import sys
from datetime import date, timedelta

import kl_news_scan as ks


def main():
    commit, start, n = sys.argv[1], date.fromisoformat(sys.argv[2]), int(sys.argv[3])
    words = sys.argv[4:]
    state = json.loads(subprocess.check_output(["git", "show", f"{commit}:news_candidates.json"]))
    state = copy.deepcopy(state)
    ks.load_candidates = lambda: state
    ks._save_candidates = lambda c: None
    by = {c["id"]: c for c in state["items"]}
    shown = {}      # id -> [(日, 場所)]
    for i in range(n):
        day = (start + timedelta(days=i)).isoformat()
        ks._today = lambda d=day: d
        with contextlib.redirect_stdout(io.StringIO()):
            ks.cmd_dedupe(dry_run=False)
        rows = ks.classify(state["items"])
        picks, _ = ks.best3(rows)
        before = {c["id"]: set(ks.presented_days(c)) for c in state["items"]}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ks.cmd_slack("", True)     # 提示の記録は cmd_slack 内（保存だけ差し替え済み）
        after = {c["id"]: set(ks.presented_days(c)) for c in state["items"]}
        newly = [cid for cid in after if after[cid] != before[cid]]
        pick_ids = [p["c"]["id"] for p in picks]
        print(f"== {day}: ベスト3 {len(picks)}件 / 今日の記録 {len(newly)}件")
        for cid in newly:
            where = "ベスト3" if cid in pick_ids else "答え合わせ一覧"
            shown.setdefault(cid, []).append((day[5:], where))
            print(f"   {where:<8} {cid} 提示{len(after[cid])}日 {by[cid]['title'][:44]}")
    print("\n== 3日以上載った候補（0件なら合格）")
    over = {k: v for k, v in shown.items() if len(v) > ks.PRESENT_MAX_DAYS}
    for cid, v in over.items():
        print("  NG", cid, by[cid]["title"][:44], v)
    print(f"  {len(over)}件（載った候補 {len(shown)}件）")
    for w in words:
        print(f"\n== 『{w}』を含む候補の載った日")
        for cid, v in shown.items():
            if w in by[cid]["title"]:
                print(f"  {cid} [{by[cid].get('status')}] {v} {by[cid]['title'][:44]}")


if __name__ == "__main__":
    main()
