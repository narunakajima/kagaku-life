#!/usr/bin/env python3
"""チームの目標（視聴者の獲得・高評価の獲得）の月次評価用に、動画ごとの再生・高評価・コメント数を取る。

Reporting API の集計（kl_analytics_report.py）には高評価の数が無いため、
YouTube Data API（videos.list の statistics）で補う。認証はコメント返信用のスクリプトのものを流用する。
管理担当（kl-manager）の月次評価（/kl-analytics の「チーム評価」）で使う。

  /usr/bin/python3 team_stats.py                       # 全動画（新しい順）
  /usr/bin/python3 team_stats.py --since 2026-10-01    # 公開日で絞る
  /usr/bin/python3 team_stats.py --json

数値は取得した時点の累計。公開からの日数（age_days）が違う動画どうしは、そのまま比べない。
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def kl_service():
    from kl_comment_reply import youtube
    return youtube()


def kl_episode_map() -> dict:
    """動画ID → (エピソード, 本編/Shorts)。"""
    out = {}
    for path in sorted((ROOT / "episodes").glob("kl*.json")):
        try:
            ep = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for key, kind in (("youtube_url", "本編"), ("shorts_url", "Shorts")):
            m = re.search(r"(?:youtu\.be/|v=|shorts/)([\w-]{11})", ep.get(key) or "")
            if m:
                out[m.group(1)] = (path.stem, kind)
    return out


# (表示名, 認証, 動画ID→エピソードの対応)
CHANNELS = [
    ("幸せな未来のサイエンス", kl_service, kl_episode_map),
]


def uploads(yt) -> list:
    ch = yt.channels().list(part="contentDetails", mine=True).execute()["items"][0]
    playlist = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, token = [], None
    while True:
        r = yt.playlistItems().list(part="contentDetails", playlistId=playlist, maxResults=50,
                                    pageToken=token).execute()
        ids += [it["contentDetails"]["videoId"] for it in r.get("items", [])]
        token = r.get("nextPageToken")
        if not token:
            return ids


def stats(yt, ids: list) -> list:
    rows = []
    for i in range(0, len(ids), 50):
        r = yt.videos().list(part="snippet,statistics,status", id=",".join(ids[i:i + 50])).execute()
        rows += r.get("items", [])
    return rows


def collect(since: str) -> list:
    now = datetime.now(timezone.utc)
    out = []
    for label, service, mapper in CHANNELS:
        try:
            yt = service()
        except Exception as e:  # 認証できないチャンネルは飛ばし、理由を残す
            print(f"警告: {label} の認証に失敗したため飛ばします: {e}", file=sys.stderr)
            continue
        epmap = mapper()
        for v in stats(yt, uploads(yt)):
            sn, st = v["snippet"], v.get("statistics", {})
            published = v.get("status", {}).get("publishAt") or sn.get("publishedAt", "")
            if since and published[:10] < since:
                continue
            pub_dt = datetime.fromisoformat(published.replace("Z", "+00:00")) if published else now
            if pub_dt > now:
                continue  # 公開予約中
            views = int(st.get("viewCount", 0))
            likes = int(st.get("likeCount", 0))
            episode, kind = epmap.get(v["id"], ("", ""))
            out.append({
                "channel": label, "video_id": v["id"], "episode": episode, "kind": kind,
                "title": sn.get("title", ""), "published": published[:10],
                "age_days": (now - pub_dt).days, "views": views, "likes": likes,
                "like_rate": round(likes / views, 4) if views else None,
                "comments": int(st.get("commentCount", 0)),
            })
    return sorted(out, key=lambda r: r["published"], reverse=True)


def main() -> None:
    p = argparse.ArgumentParser(description="動画ごとの再生・高評価・コメント数")
    p.add_argument("--since", default="", help="公開日 YYYY-MM-DD 以降に絞る")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    rows = collect(args.since)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    print("| チャンネル | 回 | 種類 | 公開日 | 日数 | 再生 | 高評価 | 高評価率 | コメント | タイトル |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        rate = "-" if r["like_rate"] is None else f"{r['like_rate']:.1%}"
        print(f"| {r['channel']} | {r['episode'] or '-'} | {r['kind'] or '-'} | {r['published']} | {r['age_days']} | "
              f"{r['views']} | {r['likes']} | {rate} | {r['comments']} | {r['title'][:40]} |")


if __name__ == "__main__":
    main()
