#!/usr/bin/env python3
"""KL進捗記録ルール恒常化 適用スクリプト（2026-11-06）。ユーザーが Terminal で実行する。

.claude/commands/kl-new.md の冒頭（「## 定数（スクリプト一覧）」の直前）に
「## 進捗の記録（2026-11-06〜、ユーザー決定）」の節を挿入し、git add・commit・push する。

使い方:
  python3 tools/apply_progress_rule_20261106.py --dry-run   # 確認だけ（ファイルは変更しない）
  python3 tools/apply_progress_rule_20261106.py             # 適用

安全策: バックアップ（kl-new.md.bak-20261106）／挿入位置が特定できなければ変更せず中断／
挿入済みなら何もしない（冪等）／反映後は kl-new.md だけを git add・commit・push。
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
KLNEW = REPO / ".claude/commands/kl-new.md"
BAK = KLNEW.with_name(KLNEW.name + ".bak-20261106")

HEADING = "## 進捗の記録（2026-11-06〜、ユーザー決定）"
SECTION = HEADING + """
制作中は、ステップの区切りごとに、その時点の成果物と進捗メモをコミットして push する。進捗メモは `handoff/progress/` にエピソード単位のファイルで残し、どのステップまで終わって次に何をするかを書く。これは Muse（メイン）が GitHub 経由で制作の進捗を確認できるようにするためで、セッション・無人を問わず適用する。

---

"""
# 既存のルール節は無いため、最初のステップ（定数・STEP 0）の説明より前に入れる。
ANCHOR = "## 定数（スクリプト一覧）\n"


def run(*a):
    return subprocess.run(a, cwd=REPO, check=True, capture_output=True, text=True).stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    text = KLNEW.read_text(encoding="utf-8")
    if HEADING in text:
        print("変更なし（挿入済み）")
        return
    if text.count(ANCHOR) != 1:
        sys.exit(f"中断: 挿入位置 {ANCHOR.strip()!r} が1件に特定できません。変更していません。")
    new = text.replace(ANCHOR, SECTION + ANCHOR)
    print("挿入予定の節:\n" + SECTION)
    if a.dry_run:
        print("(dry-run) 変更していません")
        return
    if not BAK.exists():
        shutil.copy2(KLNEW, BAK)
        print(f"バックアップ: {BAK}")
    KLNEW.write_text(new, encoding="utf-8")
    rel = ".claude/commands/kl-new.md"
    run("git", "add", rel)
    run("git", "commit", "-m",
        "kl: 進捗の記録ルール（ステップごとに commit・push、handoff/progress/）を kl-new.md に恒常化\n\n"
        "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>", "--", rel)
    try:
        run("git", "push")
    except subprocess.CalledProcessError:
        run("git", "pull", "--rebase")
        run("git", "push")
    print("commit・push 完了")


if __name__ == "__main__":
    main()
