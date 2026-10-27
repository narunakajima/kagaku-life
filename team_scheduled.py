#!/usr/bin/env python3
"""月次評価（管理担当のアナリティクス）を、毎週月曜に iMac で自動実行する。

samurai-chronicles / kagaku-life / lamp-whisper の3リポジトリで同じファイルを使う（中身をそろえること）。
毎週月曜に launchd が3リポジトリの `run` を起動し、各リポジトリは team/schedule.json を見て
「今日が自分の評価日（第N月曜）で、前月分がまだ」のときだけ、Claude Code を非対話（claude -p）で動かして
月次のアナリティクスのコマンドを最後まで実行させる。それ以外の月曜は何もしない。

  python3 team_scheduled.py install     # iMac で1回だけ。launchd に毎週月曜 08:07 の起動を登録する
  python3 team_scheduled.py uninstall   # 登録を外す
  python3 team_scheduled.py check       # 前提（claude・ドライブ・トークン）を確かめる
  python3 team_scheduled.py run [--force] [--dry-run]   # launchd が呼ぶ。--force は日付に関係なく今月の評価を実行

ログ: ~/Library/Logs/claude-team/{リポジトリ名}-{日時}-{コマンド}.log
結果: 通知センターに通知し、~/Library/Logs/claude-team/{リポジトリ名}-runs.jsonl に記録する。
"""
import argparse
import json
import os
import plistlib
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.name
TEAM_DIR = ROOT / "team"
SCHEDULE = TEAM_DIR / "schedule.json"
EVALUATIONS = TEAM_DIR / "evaluations"
LOG_DIR = Path.home() / "Library" / "Logs" / "claude-team"
RUNS_LOG = LOG_DIR / f"{REPO}-runs.jsonl"   # リポジトリの外に置く（未コミットの変更を残して次回の git pull を止めないため）
AGENT_LABEL = f"com.naru.team-analytics.{REPO}"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{AGENT_LABEL}.plist"
JST = timezone(timedelta(hours=9))
TEAM_START = "2026-10"          # 担当者制を始めた月。これより前の月は評価しない

RUN_HOST = "naru-iMac.local"      # 二重に走らないよう、iMac だけで動かす
RUN_HOUR, RUN_MINUTE = 8, 7       # 毎週月曜 08:07 JST（Mac が眠っていれば起きたときに走る）
TIMEOUT_SEC = 3 * 60 * 60         # ブラウザの再認証待ちなどで止まったときの上限
MODEL = "sonnet"                  # メイン（進行担当）。解釈と評価は管理担当（Opus のサブエージェント）が行う
ALLOWED_TOOLS = "Bash,Read,Edit,Write,Glob,Grep,Agent,WebFetch,WebSearch"
NEEDS = {  # check で存在を確かめるファイル（無くても run は止めない）
    "samurai-chronicles": ["~/.claude/secrets/yt_token_sc_reporting.json", "~/.claude/secrets/yt_token_sc.json",
                           "~/.claude/secrets/yt_token_learn_reporting.json", "~/.claude/secrets/yt_token_learn.json",
                           "~/Library/CloudStorage/GoogleDrive-naru.nakajima@gmail.com/マイドライブ/samurai-chronicles/analytics/raw"],
    "kagaku-life": ["~/.claude/secrets/yt_token_kl_reporting.json", "~/.claude/secrets/yt_token_kl.json",
                    "~/Library/CloudStorage/GoogleDrive-naru.nakajima@gmail.com/マイドライブ/Kagaku-Life/analytics/raw"],
    "lamp-whisper": ["~/.claude/secrets/yt_token_lw_reporting.json", "~/.claude/secrets/yt_comment_token.json",
                     "~/Library/CloudStorage/GoogleDrive-naru.nakajima@gmail.com/マイドライブ/Lanps-Whisper/analytics/raw"],
}

PROMPT = """あなたは {team} の進行担当です。今日は{name}の月次評価の日で、これは自動実行です（ユーザーはその場にいません）。
`.claude/commands/{command}.md` を読み、その手順どおりに {month} 分の月次評価（アナリティクス → 管理担当による解釈と担当の評価 →
改善アクション → ノートへの書き出し）を最後まで行ってください。自動実行なので、次を守ること:

- ユーザーの承認が要る変更（CLAUDE.md・手順書・担当の定義・名簿・制作ルールの設定ファイル）は反映しない。
  評価ファイルの「ユーザーの承認が要る提案」に残す（承認の段階は、ユーザーが後で行う）
- 管理担当が自分で変えてよいもの（team/evaluations/・team/notebooks/・team/scorecards.jsonl・team/actions.jsonl）は書いてよい
- トークンの失効などでブラウザでの再認証が必要になったら、その処理は待たずに止め、何をすれば続けられるかを報告に書く
  （取れたデータだけで評価を続けられるなら続け、評価ファイルに「データ不足」と明記する）
- 最後に、変更をコミットしてプッシュする（今のブランチ。CLAUDE.md のマシン判定どおり hostname を確かめる）
- 最後の出力は、結果の要約を日本語で3〜8行（評価ファイルのパス、担当ごとの総合評価、新しい改善アクションの数、ユーザーの承認が要る提案の数、止まった処理があればその理由）
"""


def now() -> datetime:
    return datetime.now(JST)


def nth_monday(year: int, month: int, n: int):
    first = datetime(year, month, 1, tzinfo=JST)
    return (first + timedelta(days=(7 - first.weekday()) % 7 + 7 * (n - 1))).date()


def team_name() -> str:
    for line in (TEAM_DIR / "coordinator.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("team:"):
            return line.split(":", 1)[1].strip()
    return REPO


def notify(title: str, message: str) -> None:
    script = f'display notification {json.dumps(message)} with title {json.dumps(title)} sound name "Glass"'
    subprocess.run(["osascript", "-e", script], check=False, capture_output=True)


def record(row: dict) -> None:
    with RUNS_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": now().isoformat(timespec="seconds"), **row}, ensure_ascii=False) + "\n")


def run_cmd(cmd: list, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, **kw)


def due_evaluations(force: bool) -> list:
    today = now().date()
    prev = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    out = []
    if prev < TEAM_START:
        return out
    for e in json.loads(SCHEDULE.read_text(encoding="utf-8")).get("evaluations", []):
        if (EVALUATIONS / e["file"].format(month=prev)).exists():
            continue
        if force or today == nth_monday(today.year, today.month, int(e["nth_monday"])):
            out.append({**e, "month": prev})
    return out


def cmd_run(args) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if socket.gethostname() != RUN_HOST and not args.any_host:
        print(f"{RUN_HOST} 以外では実行しない（二重実行を防ぐため）。--any-host で上書きできる")
        return
    pull = run_cmd(["git", "pull", "--rebase", "--autostash"])
    if pull.returncode != 0:
        msg = f"git pull に失敗したので月次評価を始めませんでした: {pull.stderr.strip()[:200]}"
        record({"repo": REPO, "result": "error", "message": msg})
        notify(f"{REPO} 月次評価", msg)
        sys.exit(1)
    todo = due_evaluations(args.force)
    if not todo:
        print("今日は評価日ではないか、前月分はもう済んでいる")
        return
    claude = shutil.which("claude") or os.environ.get("CLAUDE_BIN", "")
    if not claude:
        msg = "claude コマンドが見つからないので月次評価を始めませんでした（install をやり直してください）"
        record({"repo": REPO, "result": "error", "message": msg})
        notify(f"{REPO} 月次評価", msg)
        sys.exit(1)
    for e in todo:
        prompt = PROMPT.format(team=team_name(), name=e["name"], command=e["command"].lstrip("/"), month=e["month"])
        log = LOG_DIR / f"{REPO}-{now():%Y%m%d-%H%M}-{e['command'].lstrip('/')}.log"
        cmd = [claude, "-p", prompt, "--model", MODEL, "--allowedTools", ALLOWED_TOOLS]
        if args.dry_run:
            print(f"[dry-run] {e['name']}（{e['month']} 分）: {' '.join(cmd[:2])} ... > {log}")
            continue
        try:
            res = run_cmd(cmd, timeout=TIMEOUT_SEC)
            out, ok = res.stdout, res.returncode == 0
        except subprocess.TimeoutExpired as exc:
            out, ok = (exc.stdout or "") if isinstance(exc.stdout, str) else "", False
            out += f"\n（{TIMEOUT_SEC // 3600} 時間で打ち切りました。ブラウザの再認証待ちで止まった可能性があります）"
        log.write_text(out, encoding="utf-8")
        done = (EVALUATIONS / e["file"].format(month=e["month"])).exists()
        result = "done" if ok and done else "incomplete"
        summary = out.strip().splitlines()[-1] if out.strip() else "出力なし"
        record({"repo": REPO, "evaluation": e["name"], "month": e["month"], "result": result, "log": str(log)})
        notify(f"{e['name']} 月次評価（{e['month']} 分）",
               ("完了: " if result == "done" else "未完了（ログを確認）: ") + summary[:120])


def cmd_check(_args) -> None:
    ok = True
    print(f"マシン: {socket.gethostname()}（実行するのは {RUN_HOST}）")
    claude = shutil.which("claude")
    print(f"claude: {claude or '見つからない'}")
    ok &= bool(claude)
    for item in NEEDS.get(REPO, []):
        path = Path(os.path.expanduser(item))
        try:
            exists = path.exists() and (not path.is_dir() or any(True for _ in path.iterdir()))
        except PermissionError:
            exists = False
        print(f"{'OK ' if exists else 'NG '} {item}")
        ok &= exists
    print(f"launchd: {'登録済み' if PLIST.exists() else '未登録'}（{PLIST}）")
    for e in json.loads(SCHEDULE.read_text(encoding="utf-8")).get("evaluations", []):
        today = now().date()
        day = nth_monday(today.year, today.month, int(e["nth_monday"]))
        if day < today:
            nm = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
            day = nth_monday(nm.year, nm.month, int(e["nth_monday"]))
        print(f"次の評価: {e['name']} {day}（{e['command']}）")
    print("前提はそろっている" if ok else "NG の項目を直してください（ドライブが NG なら、team/TEAM.md「自動実行」の「フルディスクアクセス」を確認）")


def cmd_install(_args) -> None:
    claude = shutil.which("claude")
    if not claude:
        print("エラー: claude コマンドが見つかりません。ターミナルで `which claude` を確かめてください", file=sys.stderr)
        sys.exit(1)
    path_env = os.pathsep.join(dict.fromkeys([str(Path(claude).parent), "/opt/homebrew/bin", "/usr/local/bin",
                                               "/usr/bin", "/bin", "/usr/sbin", "/sbin"]))
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    plist = {
        "Label": AGENT_LABEL,
        "ProgramArguments": [sys.executable, str(ROOT / "team_scheduled.py"), "run"],
        "WorkingDirectory": str(ROOT),
        "StartCalendarInterval": {"Weekday": 1, "Hour": RUN_HOUR, "Minute": RUN_MINUTE},
        "EnvironmentVariables": {"PATH": path_env, "CLAUDE_BIN": claude, "HOME": str(Path.home())},
        "StandardOutPath": str(LOG_DIR / f"{REPO}-launchd.log"),
        "StandardErrorPath": str(LOG_DIR / f"{REPO}-launchd.log"),
    }
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["launchctl", "unload", str(PLIST)], capture_output=True)
    PLIST.write_bytes(plistlib.dumps(plist))
    res = subprocess.run(["launchctl", "load", str(PLIST)], capture_output=True, text=True)
    if res.returncode != 0:
        print(f"エラー: launchctl load に失敗しました: {res.stderr}", file=sys.stderr)
        sys.exit(1)
    print(f"登録しました: 毎週月曜 {RUN_HOUR:02d}:{RUN_MINUTE:02d}（{PLIST}）。python: {sys.executable}")


def cmd_uninstall(_args) -> None:
    subprocess.run(["launchctl", "unload", str(PLIST)], capture_output=True)
    if PLIST.exists():
        PLIST.unlink()
    print("登録を外しました")


def main() -> None:
    p = argparse.ArgumentParser(description="月次評価の自動実行（毎週月曜、iMac）")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--force", action="store_true", help="日付に関係なく、前月分が未実施の評価を実行する")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--any-host", action="store_true")
    r.set_defaults(func=cmd_run)
    sub.add_parser("check").set_defaults(func=cmd_check)
    sub.add_parser("install").set_defaults(func=cmd_install)
    sub.add_parser("uninstall").set_defaults(func=cmd_uninstall)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
