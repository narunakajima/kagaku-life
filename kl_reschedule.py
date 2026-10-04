"""
kl_reschedule.py — 予約公開中のエピソードの公開日時を変える／予約の一覧を見る（2026-10-04追加）

ニュース起点の回（source_type: news）は旬が短いため、制作から公開までを3日以内にする
（CLAUDE.md「ニュース起点のネタ選定」）。予約の列が埋まっているときは、旧方式の在庫の回を後ろへずらして
ニュース回を前に入れる。そのための道具。YouTube側の publishAt（本編・Shortsとも）と
episodes/kl{NNN}.json の scheduled_at を同時に書き換える。公開済み（public）の動画は変えない。

使い方:
  python3 kl_reschedule.py list
  python3 kl_reschedule.py move --episode kl026 --to "2026-10-27 19:00"
  python3 kl_reschedule.py bump --episode kl033 --at "2026-10-08 19:00"
     → kl033 を 10/8 19:00 に入れ、その枠にいた回から順に、空いている次の枠（火・木・土 19:00）へ1つずつ後ろへずらす

変更後は kl_build_site.py を実行してコミットする（/kl-upload STEP6 と同じ）。
"""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

from kl_sns_up import JST, PUBLISH_HOUR_JST, PUBLISH_WEEKDAYS, get_youtube_client, parse_publish_at

BASE_DIR = Path(__file__).parent
MUTABLE = ["privacyStatus", "publishAt", "license", "embeddable", "publicStatsViewable",
           "selfDeclaredMadeForKids", "containsSyntheticMedia"]


def load(ep_id):
    p = BASE_DIR / "episodes" / f"{ep_id}.json"
    return p, json.loads(p.read_text(encoding="utf-8"))


def video_ids(ep):
    out = []
    for k in ("youtube_url", "shorts_url"):
        if ep.get(k):
            out.append(re.search(r"([\w-]{11})$", ep[k]).group(1))
    return out


def set_publish(yt, ep_id, when: str):
    p, ep = load(ep_id)
    ids = video_ids(ep)
    if not ids:
        sys.exit(f"❌ {ep_id} はまだアップロードされていません（scheduled_at は /kl-upload で決まります）")
    for vid in ids:
        cur = yt.videos().list(part="status", id=vid).execute()["items"][0]["status"]
        if cur["privacyStatus"] != "private":
            sys.exit(f"❌ {ep_id} の {vid} は {cur['privacyStatus']} です（公開済みは変えない）")
        st = {m: cur[m] for m in MUTABLE if m in cur}
        st["publishAt"] = parse_publish_at(when)
        yt.videos().update(part="status", body={"id": vid, "status": st}).execute()
    ep["scheduled_at"] = when
    ep.pop("publish_hold", None)  # 保留中の回に日時を入れたら、保留を解く
    p.write_text(json.dumps(ep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✓ {ep_id}: {when}")


def scheduled():
    rows = []
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    for p in sorted((BASE_DIR / "episodes").glob("kl*.json")):
        ep = json.loads(p.read_text(encoding="utf-8"))
        if ep.get("scheduled_at") and ep["scheduled_at"] > now:
            rows.append((ep["scheduled_at"], ep["episode_id"], ep.get("format", "monologue"),
                         ep.get("source_type", "paper"), ep.get("youtube_title", "")))
    return sorted(rows)


def next_slot(after: str, taken: set) -> str:
    t = datetime.strptime(after, "%Y-%m-%d %H:%M") + timedelta(days=1)
    t = t.replace(hour=PUBLISH_HOUR_JST, minute=0)
    while t.weekday() not in PUBLISH_WEEKDAYS or t.strftime("%Y-%m-%d") in taken:
        t += timedelta(days=1)
    return t.strftime("%Y-%m-%d %H:%M")


def main():
    ap = argparse.ArgumentParser(description="予約公開の日時を変える")
    ap.add_argument("command", choices=["list", "move", "bump"])
    ap.add_argument("--episode")
    ap.add_argument("--to")
    ap.add_argument("--at")
    args = ap.parse_args()
    if args.command == "list":
        for when, ep_id, fmt, src, title in scheduled():
            print(f"{when}  {ep_id}  [{fmt}/{src}]  {title[:40]}")
        return
    yt = get_youtube_client()
    if args.command == "move":
        set_publish(yt, args.episode, args.to)
        return
    # bump: 指定枠に入れ、玉突きで後ろへずらす
    rows = scheduled()
    occupant = {when: ep_id for when, ep_id, *_ in rows}
    taken = {w[:10] for w in occupant}
    plan = [(args.episode, args.at)]
    cur_when, cur_ep = args.at, occupant.get(args.at)
    taken.discard(args.at[:10])
    while cur_ep and cur_ep != args.episode:
        nxt = next_slot(cur_when, {d for d in taken if d != cur_when[:10]})
        plan.append((cur_ep, nxt))
        cur_when, cur_ep = nxt, occupant.get(nxt)
    print("変更予定:")
    for ep_id, when in plan:
        print(f"  {ep_id} → {when}")
    for ep_id, when in reversed(plan):
        set_publish(yt, ep_id, when)


if __name__ == "__main__":
    main()
