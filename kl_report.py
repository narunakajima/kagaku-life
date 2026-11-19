#!/usr/bin/env python3
"""kl_report.py — 工程の締め（Slack報告の文面づくり＋状態の記録＋チームログ）を1つの操作にする。

背景（2026-11-19、kl059）: 報告の漏れ・「次は〇〇」と書いて応答を終える停止・承認の結果ファイルの読み忘れが続いた。
決まりを文章で書くだけでは守られないため、(1) 報告の文面を毎回この形で作る、(2) 「何を報告したか・次に何をするか・
何を待っているか」を状態ファイルに残す、(3) 応答を終えるとき kl_stop_check.py（Stop フック）がその状態を確かめる、
という形にした（編集長ケビンの提案を、なるさんが2026-11-19に承認）。

Slack への投稿そのものは、セッションの Slack ツール（スレッドに返信できる）で行う。このスクリプトは投稿しない
（webhook はスレッドに返信できず、スレッドを分けてしまうため）。出力された1行を、そのまま投稿する。

使い方:
  python3 kl_report.py start  --case kl060
      制作の開始。状態を初期化する（thread_ts は --thread-ts で渡すと記録）。
  python3 kl_report.py step   --case kl060 --step "8 音声生成" --by ダニエル --next "STEP9 テロップ" \
        [--state ok] [--eta 20分] [--needs-user なし] [--ref パス] [--note "結果: …"] \
        [--waiting none|bg|agent|approval] [--log-agent kl-coordinator --log-result ok]
      step_done の1行を表示し、状態に「報告済み・次の工程・待ち」を記録する。--log-agent を付けると
      team_log.py add も同時に実行する（報告と記録を1つの操作に）。
      --waiting は、応答を終えたあと何を待つか。none（既定）は「次の工程を今すぐ実行する」の意味で、
      この状態で応答を終えようとすると Stop フックが止める。
  python3 kl_report.py decision --case kl060 --step "12 完成動画の確認" --needs-user "…" [--ref …]
      needs_decision の1行を表示し、状態を waiting=approval にする（承認待ちで止まってよい）。
  python3 kl_report.py consumed --case kl060
      承認の結果ファイルを読んで取り込んだ印を付ける（Stop フックの「未読の承認あり」を解除）。
  python3 kl_report.py done   --case kl060
      案件の完成。状態を閉じる（以後 Stop フックは何も止めない）。
  python3 kl_report.py show
      現在の状態を表示する。
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "team" / "session_state.json"


def load():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save(d):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    d["updated_at"] = time.time()
    STATE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def line(case, event, step, by, state, nxt, eta, needs_user, ref):
    return (f"from=claude-code / project=KL / case={case} / event={event} / step={step} / by={by} / "
            f"state={state} / next={nxt} / eta={eta} / needs_user={needs_user} / ref={ref}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("start"); p.add_argument("--case", required=True); p.add_argument("--thread-ts", default="")
    p = sub.add_parser("step")
    p.add_argument("--case", required=True); p.add_argument("--step", required=True)
    p.add_argument("--by", default="ダニエル"); p.add_argument("--next", dest="nxt", required=True)
    p.add_argument("--state", default="ok"); p.add_argument("--eta", default="-")
    p.add_argument("--needs-user", default="なし"); p.add_argument("--ref", default="なし")
    p.add_argument("--note", default="")
    p.add_argument("--waiting", choices=["none", "bg", "agent", "approval"], default="none")
    p.add_argument("--log-agent", default=""); p.add_argument("--log-result", default="ok")
    p = sub.add_parser("decision")
    p.add_argument("--case", required=True); p.add_argument("--step", required=True)
    p.add_argument("--by", default="ダニエル"); p.add_argument("--needs-user", required=True)
    p.add_argument("--ref", default="なし"); p.add_argument("--note", default="")
    p = sub.add_parser("consumed"); p.add_argument("--case", required=True)
    p = sub.add_parser("done"); p.add_argument("--case", required=True)
    sub.add_parser("show")
    a = ap.parse_args()

    if a.cmd == "show":
        print(json.dumps(load(), ensure_ascii=False, indent=2))
        return 0

    s = load()
    if a.cmd == "start":
        s = {"active_case": a.case, "thread_ts": a.thread_ts, "waiting": "none", "pending_next": "",
             "last_step": "開始", "last_reported_at": time.time(), "approval_consumed_at": time.time()}
        save(s)
        print(f"状態を開始: {a.case}")
        return 0

    if s.get("active_case") not in (None, "", a.case) and a.cmd != "done":
        print(f"⚠ 状態の案件は {s.get('active_case')} です。{a.case} に切り替えます", file=sys.stderr)
    s["active_case"] = a.case

    if a.cmd == "step":
        msg = line(a.case, "step_done", a.step, a.by, a.state, a.nxt, a.eta, a.needs_user, a.ref)
        if a.note:
            msg += "\n" + a.note
        s.update({"last_step": a.step, "last_reported_at": time.time(), "pending_next": a.nxt,
                  "waiting": a.waiting})
        save(s)
        if a.log_agent:
            subprocess.run([sys.executable, str(ROOT / "team_log.py"), "add", "--agent", a.log_agent,
                            "--episode", a.case, "--step", a.step, "--result", a.log_result],
                           cwd=str(ROOT), check=False)
        print("▼ これを #cc-reports の案件スレッドに投稿し、あわせて #cc-inbox を読むこと")
        print(msg)
        if a.waiting == "none":
            print(f"▼ 次の工程「{a.nxt}」を、この応答の中で今すぐ実行すること（書いて終えない）")
        return 0

    if a.cmd == "decision":
        msg = line(a.case, "needs_decision", a.step, a.by, "判断待ち", "ご回答後に反映", "-", a.needs_user, a.ref)
        if a.note:
            msg += "\n" + a.note
        s.update({"last_step": a.step, "last_reported_at": time.time(), "pending_next": "承認待ち",
                  "waiting": "approval", "decision_posted_at": time.time()})
        save(s)
        print("▼ これを #cc-reports の案件スレッドに投稿 → 承認の監視（approval-watch.py）を起動 → その完了通知を待つ")
        print(msg)
        return 0

    if a.cmd == "consumed":
        s.update({"approval_consumed_at": time.time(), "waiting": "none"})
        save(s)
        print("承認を取り込み済みにしました（次の工程を実行すること）")
        return 0

    if a.cmd == "done":
        msg = line(a.case, "done", "完了", "ダニエル", "ok", "公開日に公開", "-", "なし", "なし")
        save({"active_case": "", "waiting": "none", "pending_next": "", "last_step": "完了",
              "last_reported_at": time.time(), "approval_consumed_at": time.time()})
        print("▼ done を #cc-reports に投稿すること（本文に結果を書く）")
        print(msg)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
