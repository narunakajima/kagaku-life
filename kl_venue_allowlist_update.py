"""
kl_venue_allowlist_update.py — 許可リスト（reputable_venues.json）更新スクリプト

stage2_screened.json を読み、Geminiが個別レビューして venue_assessment: "reputable"
と判定した掲載誌（＝まだ許可リストに入っておらず、自動passではなく実際にGeminiが
判断したもの）を集計し、許可リストへの追加候補を提示する。

デフォルトは提案のみ（reputable_venues.jsonは書き換えない）。--apply を付けた場合のみ
実際に追記する。プレプリントの掲載先（arXiv等）は対象外（CLAUDE.md STAGE2の方針により、
プレプリントは常にGemini個別レビューに回すべきで、許可リストに載せて自動pass化しては
いけないため）。

使い方:
  python3 kl_venue_allowlist_update.py               # 追加候補を表示するのみ
  python3 kl_venue_allowlist_update.py --apply        # 承認した候補をreputable_venues.jsonに追記
  python3 kl_venue_allowlist_update.py --min-count 2  # 提案の最低出現回数（デフォルト1）
"""

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
INPUT_PATH = BASE_DIR / "stage2_screened.json"
ALLOWLIST_PATH = BASE_DIR / "reputable_venues.json"


def is_reputable_venue(venue: str, keywords: list) -> bool:
    v = (venue or "").lower()
    return any(kw in v for kw in keywords)


def main():
    parser = argparse.ArgumentParser(description="許可リスト更新（stage2_screened.jsonの実績から提案）")
    parser.add_argument("--apply", action="store_true", help="提案をreputable_venues.jsonに実際に追記する")
    parser.add_argument("--min-count", type=int, default=1, help="提案に必要な最低出現回数（pass+flag合計、デフォルト1）")
    parser.add_argument(
        "--min-pass",
        type=int,
        default=0,
        help="提案に必要な最低pass件数（デフォルト0=flagのみでも可）。1以上にするとflagのみの掲載誌"
        "（venueはreputableと判定されたが個別論文は他の理由でflagだった）を除外できる",
    )
    args = parser.parse_args()

    if not INPUT_PATH.exists():
        print(f"❌ {INPUT_PATH} がありません。先に kl_paper_screen.py を実行してください", file=sys.stderr)
        sys.exit(1)

    allowlist = json.loads(ALLOWLIST_PATH.read_text())
    keywords = allowlist["keywords"]

    screened = json.loads(INPUT_PATH.read_text())

    # venue -> {"pass_count": N, "flag_count": N, "titles": [...]}
    candidates = {}
    for cat in screened["categories"].values():
        for paper in cat["papers"]:
            if paper.get("is_preprint"):
                continue
            venue = (paper.get("venue") or "").strip()
            if not venue or is_reputable_venue(venue, keywords):
                continue
            stage2 = paper.get("stage2") or {}
            if stage2.get("venue_note", "").find("自動pass") != -1:
                continue  # 念のため：許可リストヒットは対象外（通常ここには来ない）
            if stage2.get("venue_assessment") != "reputable":
                continue
            entry = candidates.setdefault(venue, {"pass_count": 0, "flag_count": 0, "titles": []})
            if stage2.get("overall") == "pass":
                entry["pass_count"] += 1
            elif stage2.get("overall") == "flag":
                entry["flag_count"] += 1
            entry["titles"].append(paper.get("title", "")[:60])

    # 信頼度の高い順（pass回数優先）に並べ、min-count/min-pass未満は除外
    ranked = [
        (venue, info)
        for venue, info in candidates.items()
        if (info["pass_count"] + info["flag_count"]) >= args.min_count
        and info["pass_count"] >= args.min_pass
    ]
    ranked.sort(key=lambda x: (x[1]["pass_count"], x[1]["flag_count"]), reverse=True)

    if not ranked:
        print("追加候補はありませんでした（許可リスト外でGeminiがreputableと判定した掲載誌なし）。")
        return

    print(f"許可リスト追加候補: {len(ranked)}件（Geminiが個別レビューでreputableと判定した掲載誌）\n")
    for venue, info in ranked:
        print(f"  [{info['pass_count']}pass/{info['flag_count']}flag] {venue}")
        for t in info["titles"][:2]:
            print(f"      例: {t}")

    if not args.apply:
        print("\n[提案のみ] --apply を付けて実行すると reputable_venues.json に追記します。")
        return

    added = 0
    for venue, _info in ranked:
        kw = venue.lower()
        if kw not in keywords:
            keywords.append(kw)
            added += 1
    allowlist["keywords"] = keywords
    ALLOWLIST_PATH.write_text(json.dumps(allowlist, ensure_ascii=False, indent=2) + "\n")
    print(f"\n✅ {added}件を reputable_venues.json に追記しました。")


if __name__ == "__main__":
    main()
