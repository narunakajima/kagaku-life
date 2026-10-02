"""
kl_related_targets.py — Shortsの「関連動画」（本編）設定の対象を洗い出す／完了を記録する

YouTube Studio の関連動画の選択画面には「公開済みの動画」しか出ないため、予約公開中の
本編はアップロード直後には設定できない。そこで /kl-upload のたびに、
「本編の公開日時を過ぎていて、まだ設定していないエピソード」をまとめて対象にする。
完了したかどうかは episodes/kl{NNN}.json の related_video_set で管理する。

使い方:
  python3 kl_related_targets.py                 # 対象を一覧表示
  python3 kl_related_targets.py --json          # 同じ内容をJSONで表示
  python3 kl_related_targets.py --mark kl021 kl022   # 設定完了を記録（related_video_set: true）
  python3 kl_related_targets.py --mark-all-published # 公開済みを全て完了として記録（初期化用）
"""
import argparse
import glob
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).parent
EPISODES_DIR = BASE_DIR / "episodes"
JST = timezone(timedelta(hours=9))
# 選択画面の検索に使う、タイトル先頭の文字数
SEARCH_CHARS = 8


def video_id(url: str) -> str:
    m = re.search(r"(?:youtu\.be/|v=|shorts/)([A-Za-z0-9_-]{11})", url or "")
    return m.group(1) if m else ""


def search_keyword(title: str) -> str:
    # 先頭の括弧・引用符は検索で邪魔になるので外す
    t = re.sub(r"^[『「“”\"'\s]+", "", title or "")
    return t[:SEARCH_CHARS]


def is_public(ep: dict, now: datetime) -> bool:
    sched = ep.get("scheduled_at")
    if not sched:
        return False
    when = datetime.strptime(sched, "%Y-%m-%d %H:%M").replace(tzinfo=JST)
    return when <= now


def load_all():
    for f in sorted(glob.glob(str(EPISODES_DIR / "kl*.json"))):
        path = Path(f)
        yield path, json.loads(path.read_text(encoding="utf-8"))


def targets(now: datetime):
    rows = []
    for path, ep in load_all():
        if not (ep.get("youtube_url") and ep.get("shorts_url")):
            continue
        if ep.get("related_video_set"):
            continue
        if not is_public(ep, now):
            continue
        rows.append({
            "episode_id": ep["episode_id"],
            "main_id": video_id(ep["youtube_url"]),
            "shorts_id": video_id(ep["shorts_url"]),
            "search": search_keyword(ep.get("youtube_title", "")),
            "title": ep.get("youtube_title", ""),
        })
    return rows


def mark(episode_ids, only_published: bool = False, now: datetime = None):
    n = 0
    for path, ep in load_all():
        eid = ep.get("episode_id")
        if only_published:
            ok = bool(ep.get("youtube_url") and ep.get("shorts_url") and is_public(ep, now))
        else:
            ok = eid in episode_ids
        if not ok or ep.get("related_video_set"):
            continue
        ep["related_video_set"] = True
        with open(path, "w", encoding="utf-8") as f:
            json.dump(ep, f, ensure_ascii=False, indent=2)
        print(f"  ✓ {eid}: related_video_set = true")
        n += 1
    print(f"{n}件を記録しました")


def main():
    ap = argparse.ArgumentParser(description="Shorts関連動画の設定対象を管理する")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--mark", nargs="+", metavar="EPISODE")
    ap.add_argument("--mark-all-published", action="store_true")
    args = ap.parse_args()
    now = datetime.now(JST)

    if args.mark:
        mark(set(args.mark))
        return
    if args.mark_all_published:
        mark(set(), only_published=True, now=now)
        return

    rows = targets(now)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    if not rows:
        print("設定が必要なShortsはありません（公開済みの分はすべて設定済み）")
        return
    print(f"関連動画を設定するShorts: {len(rows)}件")
    for r in rows:
        print(f"  {r['episode_id']}  shorts={r['shorts_id']}  本編={r['main_id']}  検索語「{r['search']}」")


if __name__ == "__main__":
    sys.exit(main())
