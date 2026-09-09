"""
kl_shortlist_add.py — stage4_ranked.json の採点結果を topics_shortlist.json に追記する

2026-09-06追加。背景: STAGE0で新規にSTAGE1〜4を実行した場合、その結果
（`stage4_ranked.json`）を`topics_shortlist.json`へ追記する作業はこれまで
オーケストレーター（Claude）が手作業でコピーする運用だった。Fable監査で、
2026-08-20/22時点の在庫46件に`score_breakdown`が一切無いことが判明し、
原因はこの手作業コピーの漏れだった（`stage4_version`のような新フィールドを
後から追加しても、手コピーの手順自体は更新されない限りコピーされない）。

このスクリプトは`stage4_ranked.json`（`kl_paper_interest_score.py`の出力）を
機械的に`topics_shortlist.json`のスキーマへ変換して追記する。フィールドの
取りこぼしをコード側で固定することで、今後同じ種類の漏れが起きないようにする。

使い方:
  python3 kl_shortlist_add.py                 # stage4_ranked.json の all_scored 全件を追記
  python3 kl_shortlist_add.py --top-only       # stage5_candidates（上位N件）のみ追記
  python3 kl_shortlist_add.py --dry-run        # 追記件数の確認のみ

paperId が既にtopics_shortlist.jsonに存在するエントリは追記しない（重複防止）。
stage4が失敗（`_fallback: True`、= stage4_versionが付与されていない）の
エントリはデフォルトでは追記せず警告する（スコアが無い候補が紛れ込むのを防ぐ）。
"""

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).parent
STAGE4_PATH = BASE_DIR / "stage4_ranked.json"
SHORTLIST_PATH = BASE_DIR / "topics_shortlist.json"


def atomic_write(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    os.replace(tmp, path)


def to_shortlist_entry(scored: dict, today: str) -> dict:
    stage4 = scored.get("stage4", {})
    return {
        "paperId": scored.get("paperId"),
        "title": scored.get("title"),
        "year": scored.get("year"),
        "venue": scored.get("venue"),
        "doi": scored.get("doi"),
        "authors": scored.get("authors"),
        "is_preprint": scored.get("is_preprint"),
        "category": scored.get("category"),
        "category_label": scored.get("category_label"),
        "overall_score": scored.get("overall_score"),
        "score_breakdown": {
            "wonder_score": stage4.get("wonder_score", 0),
            "transformation_score": stage4.get("transformation_score", 0),
            "life_relevance_score": stage4.get("life_relevance_score", 0),
            "surprise_score": stage4.get("surprise_score", 0),
            "persona_fit_score": stage4.get("persona_fit_score", 0),
        },
        "market_status": stage4.get("market_status", ""),
        "novel_delta": stage4.get("novel_delta", ""),
        "behavioral_familiarity": stage4.get("behavioral_familiarity", ""),
        "behavioral_familiarity_note": stage4.get("behavioral_familiarity_note", ""),
        "demonstrated_capability": stage4.get("demonstrated_capability", ""),
        "future_scene_sketch": stage4.get("future_scene_sketch", ""),
        "deja_vu_note": stage4.get("deja_vu_note", ""),
        "deja_vu_level": stage4.get("deja_vu_level", ""),
        "deja_vu_context_upto": scored.get("deja_vu_context_upto", ""),
        "hook_idea": stage4.get("hook_idea", ""),
        "example_protagonist": stage4.get("example_protagonist", {}),
        "stage4_version": scored.get("stage4_version"),
        "status": "available",
        "used_in": None,
        "considered_at": today,
    }


def main():
    parser = argparse.ArgumentParser(description="stage4_ranked.jsonをtopics_shortlist.jsonへ機械的に追記する")
    parser.add_argument("--top-only", action="store_true", help="stage5_candidates（上位N件）のみ追記する")
    parser.add_argument("--dry-run", action="store_true", help="追記件数の確認のみ")
    parser.add_argument(
        "--include-failed",
        action="store_true",
        help="stage4が失敗した（stage4_versionが無い）エントリも追記する（デフォルトでは除外）",
    )
    args = parser.parse_args()

    if not STAGE4_PATH.exists():
        print(f"❌ {STAGE4_PATH} がありません。先に kl_paper_interest_score.py を実行してください", file=sys.stderr)
        sys.exit(1)
    if not SHORTLIST_PATH.exists():
        print(f"❌ {SHORTLIST_PATH} がありません", file=sys.stderr)
        sys.exit(1)

    stage4_data = json.loads(STAGE4_PATH.read_text())
    candidates = stage4_data["stage5_candidates"] if args.top_only else stage4_data["all_scored"]

    shortlist_data = json.loads(SHORTLIST_PATH.read_text())
    existing_ids = {e.get("paperId") for e in shortlist_data["shortlist"] if e.get("paperId")}

    today = date.today().isoformat()
    to_add = []
    skipped_dup = 0
    skipped_failed = 0

    for scored in candidates:
        pid = scored.get("paperId")
        if not pid:
            continue
        if pid in existing_ids:
            skipped_dup += 1
            continue
        if not scored.get("stage4_version") and not args.include_failed:
            skipped_failed += 1
            continue
        to_add.append(to_shortlist_entry(scored, today))
        existing_ids.add(pid)

    print(f"追記対象: {len(to_add)}件（重複でスキップ: {skipped_dup}件、stage4失敗でスキップ: {skipped_failed}件）")
    for e in to_add:
        print(f"  [{e['overall_score']}] {e['category_label']} — {e['title'][:60]}")

    if args.dry_run:
        print("\n--dry-run のため書き込みは行いません")
        return

    if not to_add:
        print("追記するエントリはありません")
        return

    shortlist_data["shortlist"].extend(to_add)
    shortlist_data["total_shortlist"] = len(shortlist_data["shortlist"])
    shortlist_data["last_updated"] = today
    atomic_write(SHORTLIST_PATH, shortlist_data)
    print(f"\n✅ {len(to_add)}件を{SHORTLIST_PATH}に追記しました")


if __name__ == "__main__":
    main()
