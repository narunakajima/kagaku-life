#!/usr/bin/env python3
"""kl_stop_check.py — Stop フック。制作中に「止まってはいけない状態」で応答を終えようとしたら止める。

背景（2026-11-19、kl059。編集長ケビンの提案4aを、なるさんが承認）: メインの会話は自分が止まったことを感知できず、
「次は〇〇」と書くだけで応答を終えて止まる、承認の結果ファイルを読まない、といった漏れが起きた。
.claude/settings.json の Stop フックから呼ばれ、kl_report.py が書く team/session_state.json を確かめる。

止める条件（どれかに当たったら {"decision":"block","reason":…} を返す。止めない場合は何も出さず exit 0）:
  1. 案件が進行中（active_case あり）で、未読の承認の結果ファイル（/tmp/lw-approval/{案件}-*.json の
     status=approved で、承認の取り込み印より新しい）がある → 先に結果ファイルを読む
  2. 案件が進行中で waiting=none かつ pending_next がある → 次の工程を今実行する（「次は〇〇」と書いて終えない）
  3. 案件が進行中で waiting=approval なのに、承認の監視プロセスが動いておらず、結果ファイルも無い
     → 監視を張り直す（時間切れ後の張り直し忘れの防止）

止めない（正しく待っている）場合: 案件なし／状態が6時間以上更新されていない（古い）／waiting が bg・agent
（呼び出し中の担当者・走っているバックグラウンド作業を待っている）／waiting=approval で監視が動作中／
stop_hook_active（ループ防止。同じ応答の2回目以降は止めない）。

誤って止めたときの逃げ道: python3 kl_report.py step … --waiting bg|agent で、待っている先を明示する。
"""
import glob
import json
import subprocess
import sys
import time
from pathlib import Path

STATE = Path(__file__).resolve().parent / "team" / "session_state.json"
STALE_SEC = 6 * 3600


def block(reason):
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    sys.exit(0)


def watcher_running(case):
    try:
        out = subprocess.run(["pgrep", "-fl", "approval-watch.py"], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return True  # 確かめられないときは止めない
    return case in out


def main():
    try:
        hook = json.load(sys.stdin)
    except Exception:
        hook = {}
    if hook.get("stop_hook_active"):
        return 0
    try:
        s = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return 0
    case = s.get("active_case") or ""
    if not case:
        return 0
    if time.time() - float(s.get("updated_at", 0)) > STALE_SEC:
        return 0

    consumed = float(s.get("approval_consumed_at", 0))
    for f in glob.glob(f"/tmp/lw-approval/{case}-*.json"):
        if f.endswith(".timeout.txt"):
            continue
        try:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
            mtime = Path(f).stat().st_mtime
        except Exception:
            continue
        if d.get("status") == "approved" and mtime > consumed:
            block(f"未読の承認があります。応答を終える前に、結果ファイル {f} を Read し、answer（upload=yes の有無を含む）を"
                  f"取り込んで、受領を #cc-reports に投稿し、`python3 kl_report.py consumed --case {case}` を実行してください。")

    waiting = s.get("waiting", "none")
    nxt = (s.get("pending_next") or "").strip()
    if waiting == "none" and nxt:
        block(f"案件 {case} は進行中で、次の工程「{nxt}」がまだ実行されていません（最後の報告: {s.get('last_step')}）。"
              f"「次は〇〇」と書いて応答を終えると、ここで止まります。次の工程をこの応答の中で実行してください。"
              f"本当に待つ必要があるなら、`python3 kl_report.py step … --waiting bg|agent` で待つ先を明示してください。")
    if waiting == "approval" and not watcher_running(case):
        block(f"案件 {case} は承認待ちですが、承認の監視（approval-watch.py）が動いていません（時間切れで終了した可能性）。"
              f"結果ファイルが無いことを確かめ、#cc-inbox を自分で読み、無ければ監視を張り直してください。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
