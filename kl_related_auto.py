#!/usr/bin/env python3
"""
kl_related_auto.py — ショートの「関連動画」（同じ回の本編）を、公開直後に自動設定するタイマー用スクリプト

仕様（ユーザー承認済み、2026-11-10。指示 2026-11-10-002）:
  - 15分間隔の launchd から `run` が呼ばれる。
  - 対象 = kl_related_targets.targets()（アップロード済み・本編の公開時刻を過ぎている・related_video_set 未設定）。
  - 対象があれば、制作専用 Chrome で YouTube Studio を開き、そのショートの関連動画に同じ回の本編を設定する
    （claude -p --chrome に、関連動画の設定だけを許可した固定プロンプトで実行させる。手順は studio_related_video.js）。
  - 成功したら episodes/kl{NNN}.json の related_video_set を true にして完了を報告する。
  - 失敗したら未設定のまま残す（次のチェックで再試行）。画面ロック等で実行できないときは blocked として1回だけ報告する。

境界（広げないこと）:
  - アップロード・公開・予約公開の変更はしない。リンク先は「ショート→同じ回の本編」で固定。
  - 関連動画の設定以外の Studio 操作・設定変更、コメント返信はしない。

使い方:
  python3 kl_related_auto.py dry-run        # 対象の抽出だけ（Studio 操作なし・記録なし）
  python3 kl_related_auto.py run            # launchd が呼ぶ本体
  python3 kl_related_auto.py print-plist    # launchd の plist を表示するだけ（登録はしない）
  python3 kl_related_auto.py install        # 人が iMac で1回だけ実行: 15分間隔で登録
  python3 kl_related_auto.py uninstall

状態: ~/Library/Logs/claude-team/kagaku-life-related-auto-state.json（リポジトリの外。blocked の通知済みなど）
"""
import argparse
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import kl_related_targets as rt

ROOT = Path(__file__).resolve().parent
LOG_DIR = Path.home() / "Library" / "Logs" / "claude-team"
STATE = LOG_DIR / "kagaku-life-related-auto-state.json"
LABEL = "com.naru.kl-related-auto"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
INTERVAL_SEC = 15 * 60
TIMEOUT_SEC = 20 * 60
MODEL = "sonnet"
ALLOWED_TOOLS = "Read,mcp__claude-in-chrome__*"
FAIL_NOTIFY_AT = 3   # 同じ回が続けて失敗したらこの回数で1回だけ報告する
WEBHOOKS = ["~/.claude/secrets/slack_webhook_cc_reports.txt",
            "~/.claude/secrets/slack_webhook_team_reports_kagaku-life.txt",
            "~/.claude/secrets/slack_webhook_team_reports.txt"]
JST = timezone(timedelta(hours=9))

PROMPT = """あなたは KL のショート「関連動画」自動設定タイマーから起動されました。次の1件だけを処理します。

対象: エピソード {eid}
  ショート動画ID: {shorts}
  本編動画ID: {main}（タイトル先頭の検索語: 「{kw}」）

やること（これ以外の操作は一切しない）:
1. 制作専用 Chrome（Claude in Chrome）で https://studio.youtube.com/video/{shorts}/edit を開き、3秒待つ。
2. リポジトリの studio_related_video.js の「関数本体」を使い、検索語「{kw}」で関連動画に本編を設定する
   （手順はそのファイル冒頭のコメントのとおり。FORCE は false、STRICT は true）。
   「子ども向けか」が未選択で err:'kid-unset' が返ったら、何も変更せず status を failed（reason に kid-unset）にする。
3. 読み込み直して、関連動画が本編（ID {main}）のタイトルになっていることを確認する。

禁止: アップロード・公開・公開日時の変更、関連動画以外の設定変更、コメント返信、他の動画の編集。
Studio にログインできない・画面がロックされている・Chrome が使えない場合は、何も変更せず BLOCKED として終える。

最終行に、次のどれか1行だけを出力する（他の説明はその前に書いてよい）:
RESULT: {{"episode":"{eid}","status":"ok","related":"<設定後の関連動画タイトル>"}}
RESULT: {{"episode":"{eid}","status":"already","related":"<現在の関連動画タイトル>"}}
RESULT: {{"episode":"{eid}","status":"failed","reason":"<理由>"}}
RESULT: {{"episode":"{eid}","status":"blocked","reason":"<理由>"}}
"""


def now():
    return datetime.now(JST)


def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"blocked_notified": {}, "attempts": {}}


def save_state(st):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def post(text):
    for f in WEBHOOKS:
        p = Path(os.path.expanduser(f))
        if p.exists():
            body = json.dumps({"text": text}, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(p.read_text().strip(), data=body,
                                         headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    return r.status == 200
            except Exception as exc:
                print(f"Slack 投稿失敗: {exc}", file=sys.stderr)
                return False
    print("警告: Slack の Webhook ファイルが見つからない（報告できない）", file=sys.stderr)
    return False


def screen_locked():
    try:
        out = subprocess.run(["ioreg", "-n", "Root", "-d1", "-a"], capture_output=True, text=True, timeout=20).stdout
        return "CGSSessionScreenIsLocked" in out and re.search(
            r"CGSSessionScreenIsLocked</key>\s*<true/>", out) is not None
    except Exception:
        return False


def parse_result(out):
    m = None
    for m in re.finditer(r"^RESULT:\s*(\{.*\})\s*$", out or "", re.M):
        pass
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None


def title_matches(related, title):
    a, b = re.sub(r"\s+", "", related or ""), re.sub(r"\s+", "", title or "")
    return bool(a) and bool(b) and (b in a or a in b)


def process(t, st, claude):
    eid = t["episode_id"]
    if screen_locked():
        return {"status": "blocked", "reason": "画面ロック中"}
    prompt = PROMPT.format(eid=eid, shorts=t["shorts_id"], main=t["main_id"], kw=t["search"])
    cmd = [claude, "-p", prompt, "--model", MODEL, "--chrome", "--allowedTools", ALLOWED_TOOLS]
    log = LOG_DIR / f"kagaku-life-related-{eid}-{now():%Y%m%d-%H%M}.log"
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_SEC, cwd=ROOT)
        out = res.stdout
    except subprocess.TimeoutExpired:
        out = ""
        log.write_text("timeout", encoding="utf-8")
        return {"status": "failed", "reason": "タイムアウト"}
    log.write_text(out, encoding="utf-8")
    r = parse_result(out)
    if not r or r.get("episode") != eid:
        return {"status": "failed", "reason": "結果を読み取れない（ログ: %s）" % log}
    return r


def cmd_dry_run(_a):
    rows = rt.targets(now())
    if not rows:
        print("対象なし（公開済みの分はすべて設定済み、または本編が未公開）")
        return
    print(f"対象 {len(rows)}件（Studio操作なし・記録なし）")
    for r in rows:
        print(f"  {r['episode_id']}  shorts={r['shorts_id']} → 本編={r['main_id']}  検索語「{r['search']}」")


def cmd_run(_a):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    rows = rt.targets(now())
    if not rows:
        return
    claude = shutil.which("claude") or os.environ.get("CLAUDE_BIN", "")
    st = load_state()
    for t in rows:
        eid = t["episode_id"]
        if not claude:
            r = {"status": "blocked", "reason": "claude コマンドが見つからない"}
        else:
            r = process(t, st, claude)
        s = r.get("status")
        if s in ("ok", "already") and not title_matches(r.get("related", ""), t["title"]):
            r = {"status": "failed", "reason": f"関連動画のタイトルが本編と一致しない: {r.get('related')}"}
            s = "failed"
        if s in ("ok", "already"):
            rt.mark({eid})
            st["blocked_notified"].pop(eid, None)
            st["attempts"].pop(eid, None)
            post(f"✅ *KL 関連動画の自動設定*: {eid} のショート（{t['shorts_id']}）に本編（{t['main_id']}）を設定しました。"
                 f"関連動画: {r.get('related', '')}")
        elif s == "blocked":
            if not st["blocked_notified"].get(eid):
                if post(f"⏸ *KL 関連動画の自動設定 blocked*: {eid} を設定できません（{r.get('reason')}）。"
                        "未設定のまま残し、15分ごとの再試行は続けます（この通知は1回だけ）。"):
                    st["blocked_notified"][eid] = now().isoformat()
        else:
            st["attempts"][eid] = st["attempts"].get(eid, 0) + 1
            print(f"{eid}: 失敗（{r.get('reason')}）。未設定のまま次回再試行")
            if st["attempts"][eid] == FAIL_NOTIFY_AT:
                post(f"⚠️ *KL 関連動画の自動設定*: {eid} が{FAIL_NOTIFY_AT}回続けて失敗しています（{r.get('reason')}）。"
                     "未設定のまま再試行は続けます（この通知は1回だけ）。")
    save_state(st)


def plist_dict():
    claude = shutil.which("claude") or ""
    path_env = os.pathsep.join(dict.fromkeys([str(Path(claude).parent) if claude else "/opt/homebrew/bin",
                                               "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"]))
    return {
        "Label": LABEL,
        "ProgramArguments": [sys.executable, str(ROOT / "kl_related_auto.py"), "run"],
        "WorkingDirectory": str(ROOT),
        "StartInterval": INTERVAL_SEC,
        "EnvironmentVariables": {"PATH": path_env, "CLAUDE_BIN": claude, "HOME": str(Path.home())},
        "StandardOutPath": str(LOG_DIR / "kagaku-life-related-auto-launchd.log"),
        "StandardErrorPath": str(LOG_DIR / "kagaku-life-related-auto-launchd.log"),
    }


def cmd_print_plist(_a):
    print(plistlib.dumps(plist_dict()).decode())


def cmd_install(_a):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["launchctl", "unload", str(PLIST)], capture_output=True)
    PLIST.write_bytes(plistlib.dumps(plist_dict()))
    res = subprocess.run(["launchctl", "load", str(PLIST)], capture_output=True, text=True)
    if res.returncode:
        sys.exit(f"launchctl load に失敗: {res.stderr}")
    print(f"登録しました: 15分間隔（{PLIST}）")


def cmd_uninstall(_a):
    subprocess.run(["launchctl", "unload", str(PLIST)], capture_output=True)
    PLIST.unlink(missing_ok=True)
    print("登録を外しました")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in [("dry-run", cmd_dry_run), ("run", cmd_run), ("print-plist", cmd_print_plist),
                     ("install", cmd_install), ("uninstall", cmd_uninstall)]:
        sub.add_parser(name).set_defaults(fn=fn)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
