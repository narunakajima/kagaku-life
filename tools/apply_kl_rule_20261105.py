#!/usr/bin/env python3
"""KL確認ルール恒常化 適用スクリプト（2026-11-05）。ユーザーが Terminal で実行する。

(a) repos.json: kagaku-life の設定で .claude/ 配下の編集を許可し、指示文に STEP 11 読み替えを足す
(b) .claude/commands/kl-new.md: STEP 11 の恒常ルールと、矛盾箇所の読み替え文言を反映し、commit・push

使い方:
  python3 tools/apply_kl_rule_20261105.py --repos-json <repos.json のパス> --dry-run   # 確認だけ
  python3 tools/apply_kl_rule_20261105.py --repos-json <repos.json のパス>             # 適用
  python3 tools/apply_kl_rule_20261105.py --skip-repos-json                            # (b)のみ

安全策: バックアップ（*.bak-20261105）／置換対象が無ければその項目は変更せず中断／冪等／(b)は最後に git add・commit・push。
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
KLNEW = REPO / ".claude/commands/kl-new.md"
BAK = ".bak-20261105"

RULE = """**【恒常ルール（2026-11-05、ユーザー決定。kl052 で採用した運用を恒常化）】**
- 確認ページ（STEP11）のユーザー確認は省略する。`kl_review_gen.py` で確認ページを生成し、管理担当 `kl-manager` が内容（画像・ナレーション・BGM・サムネイル）を確認して、進行の可否を判断する。
- 細部の判断（画の明るさ、画面バッジの文言、機体の大きさなど）は、管理担当・担当者の判断で決める。
- ユーザーの確認は、完成した動画の確認の1回のみ（`/kl-upload` の前）。
- 以下の STEP 11 の「ユーザーの確認を得る」「OKが得られたら」は「`kl-manager` の進行可の判断が出たら」と読み替える。
- 他の STEP にある「STEP 11 でユーザー確認」は同様に読み替える（5.6 の次点案・6.7 の相談・STEP 7 の zoom_anchor・読み QA の確認・台本修正指示）。
- STAGE 4 のストーリー案のユーザー確認など、STEP 11 と無関係の確認工程は変えない。

"""

# (旧文字列, 新文字列)。新文字列が既にあれば済み。旧文字列が1件でなければ中断。
EDITS = [
    ("## STEP 11 — 静止画・ナレーション・BGMのユーザー確認 → Google Driveへ格納\n\n",
     "## STEP 11 — 静止画・ナレーション・BGMの確認（管理担当 kl-manager が判断）→ Google Driveへ格納\n\n" + RULE),
    ("5. 次点の案は、STEP 11 の確認ページで制作者に見せてよい（制作者は、気に入った案があればアップロード前に差し替えられる）",
     "5. 次点の案は、STEP 11 の確認ページに載せ、結果ファイルにも書いておく（2026-11-05〜、STEP 11 は管理担当が判断するため制作者の事前確認はない。"
     "制作者は、完成動画の確認のときに気に入った案があれば、アップロード前に差し替えられる）"),
    ("Opusでも直らない場合に限り、\nSTEP11の確認でユーザーに諮る。",
     "Opusでも直らない場合に限り、\n管理担当 `kl-manager` に諮って判断する（無人実行では、直らなければ結果を「要確認」にして理由を書く。2026-11-05〜）。"),
    ("**要相談は新しい確認ステップにせず、STEP11のユーザー確認に選択肢付きで含める。**",
     "**要相談は新しい確認ステップにせず、STEP11 の管理担当 `kl-manager` の判断に、選択肢付きで含める（2026-11-05〜）。**"),
    ("OKになった「後」まで待つこと（2026-08-25改訂）。**",
     "OKになった「後」まで待つこと（2026-08-25改訂）。2026-11-05〜は「STEP11 で `kl-manager` の進行可の判断が出た後」と読み替える。**"),
    ("表示された行は STEP 11 で必ず耳で確認し、",
     "表示された行は STEP 11 で必ず確認し（2026-11-05〜は、管理担当 `kl-manager` が `reading_qa.json` の該当行を確認して判断する。"
     "人の「耳で確認」は完成動画の確認のときに任意で行う）、"),
    ("制作者が台本を確かめるのは STEP11 の確認ページ。そこで修正の指示を受けて台詞を直したときだけ、変更後の台詞をテキストで見せる",
     "制作者が台本を確かめるのは、完成動画の確認のとき（2026-11-05〜、STEP11 の確認ページは管理担当が判断する）。"
     "そこで修正の指示を受けて台詞を直したときだけ、変更後の台詞をテキストで見せる"),
    ("OKが得られたら、まずSTEP7のzoom_anchor判定を実行してから",
     "OKが得られたら（2026-11-05〜は `kl-manager` の進行可の判断が出たら）、まずSTEP7のzoom_anchor判定を実行してから"),
]

PROMPT_ADD = ("【STEP 11 の読み替え（ユーザー決定、2026-11-05）】kl-new.md の STEP 11 の『ユーザーの確認』は、"
              "管理担当 kl-manager の進行可の判断に読み替えて進める（確認ページは生成して kl-manager に確認させる）。"
              "ユーザーの確認は完成動画の1回のみ（公開前）。")
ALLOW_ADD = [".claude/commands/", ".claude/agents/"]


def run(*a):
    return subprocess.run(a, cwd=REPO, check=True, capture_output=True, text=True).stdout


def backup(p):
    b = p.with_name(p.name + BAK)
    if not b.exists():
        shutil.copy2(p, b)
        print(f"バックアップ: {b}")


def apply_klnew(dry):
    text = KLNEW.read_text(encoding="utf-8")
    new, todo = text, []
    for old, nw in EDITS:
        if nw in new:
            print(f"[済] {old[:30]!r}")
        elif new.count(old) == 1:
            new = new.replace(old, nw)
            todo.append(old[:30])
        else:
            sys.exit(f"中断: 置換対象が見つからない（または複数）: {old[:50]!r}\n手順書は変更していません。")
    if not todo:
        print("(b) 変更なし（反映済み）")
        return False
    print(f"(b) 変更予定 {len(todo)} 件: {todo}")
    if dry:
        return False
    backup(KLNEW)
    KLNEW.write_text(new, encoding="utf-8")
    return True


def find_entry(data):
    """repos.json の構造が未確認のため、kagaku-life を含む dict を探す。"""
    hits = []

    def walk(o, path):
        if isinstance(o, dict):
            if any("kagaku-life" in v for v in o.values() if isinstance(v, str)) or any("kagaku-life" in k for k in o):
                hits.append((path, o))
            for k, v in o.items():
                walk(v, path + [k])
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, path + [i])

    walk(data, [])
    return hits


def apply_repos(path, dry):
    p = Path(path).expanduser()
    data = json.loads(p.read_text(encoding="utf-8"))
    hits = find_entry(data)
    if not hits:
        sys.exit("中断: repos.json に kagaku-life の設定が見つかりません。変更していません。")
    ppath, ent = hits[-1]
    print("対象の設定:", ppath)
    print(json.dumps(ent, ensure_ascii=False, indent=2)[:2000])
    changed = []
    akey = next((k for k in ent if isinstance(ent[k], list)
                 and any(s in k.lower() for s in ("allow", "write", "edit", "path"))), None)
    if akey is None:
        sys.exit("中断: 編集許可のリスト（allow/write/edit/path を含むキー）が見つかりません。"
                 "上の設定を Muse に見せてください。変更していません。")
    pkey = next((k for k, v in ent.items() if isinstance(v, str) and "完了の閉じ方" in v), None)
    if pkey is None:
        sys.exit("中断: 指示文（『完了の閉じ方』を含む文字列）が見つかりません。変更していません。")
    for a in ALLOW_ADD:
        if a not in ent[akey]:
            ent[akey].append(a)
            changed.append(f"{akey} += {a}")
    if PROMPT_ADD not in ent[pkey]:
        ent[pkey] = ent[pkey].rstrip() + "\n" + PROMPT_ADD
        changed.append(f"{pkey} に STEP 11 読み替えを追記")
    if not changed:
        print("(a) 変更なし（反映済み）")
        return
    print("(a) 変更予定:", changed)
    if dry:
        return
    backup(p)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("(a) repos.json を更新しました")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repos-json")
    ap.add_argument("--skip-repos-json", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not a.skip_repos_json:
        if not a.repos_json:
            sys.exit("--repos-json を指定（または --skip-repos-json）")
        apply_repos(a.repos_json, a.dry_run)
    if apply_klnew(a.dry_run):
        rel = ".claude/commands/kl-new.md"
        run("git", "add", rel)
        run("git", "commit", "-m",
            "kl: STEP 11 の確認を管理担当の判断に恒常化（kl-new.md の読み替えを整理）\n\n"
            "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>")
        try:
            run("git", "push")
        except subprocess.CalledProcessError:
            run("git", "pull", "--rebase")
            run("git", "push")
        print("(b) commit・push 完了")


if __name__ == "__main__":
    main()
