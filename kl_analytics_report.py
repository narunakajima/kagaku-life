#!/usr/bin/env python3
"""
kl_analytics_report.py — アナリティクスCSVを集計してエピソード別・カテゴリ別レポートを出力する。

前提: kl_yt_download_reports.py で analytics/raw/ にCSVをダウンロード済みであること。

カテゴリ別集計は、CLAUDE.md STAGE1の「12話到達後にkl_analytics_report.pyの分析結果を
踏まえてweightとクエリ語彙を見直す」運用のために追加した（LWのエピソード別レポートには
ない、kagaku-life固有の集計）。

使い方:
    python3 kl_analytics_report.py                 # 全期間
    python3 kl_analytics_report.py --after kl004    # 指定エピソード以降のみ
    python3 kl_analytics_report.py --before kl004   # 指定エピソード未満のみ
"""
import argparse
import csv
import glob
import json
import re
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
RAW = BASE / "analytics" / "raw"
EPISODES_DIR = BASE / "episodes"
TOPICS_QUEUE_JSON = BASE / "topics_queue.json"

TRAFFIC_SRC_NAMES = {
    "0": "YT検索", "1": "関連動画", "3": "外部", "4": "直接/不明",
    "5": "登録者フィード", "9": "通知", "14": "プレイリスト",
    "17": "ブラウズ機能", "18": "ショート/フィード", "20": "検索(ショート)",
    "24": "ショートフィード",
}


def video_id(url: str) -> str:
    m = re.search(r"(?:youtu\.be/|v=)([A-Za-z0-9_-]{11})", url or "")
    return m.group(1) if m else ""


def load_episode_map():
    """video_id -> (episode_id, title, is_shorts, category, category_label) を作る。

    本編とShorts、両方のvideo_idを対象にする（analytics上はどちらも同じ
    video_idの列で報告されるため）。
    """
    cat_map = {}
    if TOPICS_QUEUE_JSON.exists():
        queue = json.loads(TOPICS_QUEUE_JSON.read_text(encoding="utf-8")).get("queue", [])
        for item in queue:
            eid = item.get("episode_id")
            if eid:
                cat_map[eid] = (item.get("category"), item.get("category_label"))

    vid_info = {}
    for p in sorted(EPISODES_DIR.glob("kl[0-9]*.json")):
        if p.stat().st_size == 0:
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        eid = d.get("episode_id", p.stem)
        title = d.get("youtube_title") or d.get("episode_title", "")
        category, category_label = cat_map.get(eid, (None, None))

        main_vid = video_id(d.get("youtube_url", ""))
        if main_vid:
            vid_info[main_vid] = {
                "ep": eid, "title": title, "is_shorts": False,
                "category": category, "category_label": category_label,
            }

        shorts_vid = video_id(d.get("shorts_url", ""))
        if shorts_vid:
            vid_info[shorts_vid] = {
                "ep": eid, "title": f"{title}（Shorts）", "is_shorts": True,
                "category": category, "category_label": category_label,
            }

    return vid_info


def aggregate(vid_info, ep_filter=None):
    video_stats = defaultdict(lambda: {
        "views": 0, "watch_time_minutes": 0.0, "engaged_views": 0,
        "avg_dur_sum": 0.0, "avg_dur_pct_sum": 0.0,
    })
    for path in glob.glob(str(RAW / "kl-channel_combined_a3" / "*.csv")):
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                vid = row["video_id"]
                if ep_filter and not ep_filter(vid_info.get(vid, {}).get("ep")):
                    continue
                s = video_stats[vid]
                views = int(row["views"])
                s["views"] += views
                s["watch_time_minutes"] += float(row["watch_time_minutes"])
                s["engaged_views"] += int(row["engaged_views"])
                s["avg_dur_sum"] += float(row["average_view_duration_seconds"]) * views
                s["avg_dur_pct_sum"] += float(row["average_view_duration_percentage"]) * views

    reach_stats = defaultdict(lambda: {"impressions": 0, "ctr_sum": 0.0})
    for path in glob.glob(str(RAW / "kl-channel_reach_basic_a1" / "*.csv")):
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                vid = row["video_id"]
                if ep_filter and not ep_filter(vid_info.get(vid, {}).get("ep")):
                    continue
                imp = int(row["video_thumbnail_impressions"])
                ctr = float(row["video_thumbnail_impressions_ctr"])
                r = reach_stats[vid]
                r["impressions"] += imp
                r["ctr_sum"] += ctr * imp

    traffic_stats = defaultdict(lambda: defaultdict(int))
    for path in glob.glob(str(RAW / "kl-channel_traffic_source_a3" / "*.csv")):
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                vid = row["video_id"]
                if ep_filter and not ep_filter(vid_info.get(vid, {}).get("ep")):
                    continue
                traffic_stats[vid][row["traffic_source_type"]] += int(row["views"])

    rows = []
    for vid, s in video_stats.items():
        if s["views"] == 0:
            continue
        info = vid_info.get(vid, {})
        avg_dur = s["avg_dur_sum"] / s["views"]
        avg_dur_pct = s["avg_dur_pct_sum"] / s["views"]
        engaged_rate = s["engaged_views"] / s["views"] * 100
        r = reach_stats.get(vid, {"impressions": 0, "ctr_sum": 0})
        ctr = (r["ctr_sum"] / r["impressions"] * 100) if r["impressions"] else 0
        rows.append({
            "ep": info.get("ep", "?"),
            "title": info.get("title", "?"),
            "category": info.get("category"),
            "category_label": info.get("category_label"),
            "is_shorts": info.get("is_shorts", False),
            "vid": vid,
            "views": s["views"],
            "watch_time_min": round(s["watch_time_minutes"], 1),
            "avg_dur_sec": round(avg_dur, 1),
            "avg_dur_pct": round(avg_dur_pct, 1),
            "engaged_rate": round(engaged_rate, 1),
            "impressions": r["impressions"],
            "ctr_pct": round(ctr, 2),
        })
    rows.sort(key=lambda x: -x["views"])
    return rows, traffic_stats


def print_report(rows, traffic_stats, label):
    print(f"\n{'='*95}\n{label}\n{'='*95}")
    print(f"{'EP':<8}{'Views':>7}{'視聴分':>9}{'平均秒':>8}{'維持率%':>9}{'完了率%':>9}{'imp':>7}{'CTR%':>7}  Title")
    for r in rows:
        ep_label = r["ep"] + ("*" if r["is_shorts"] else "")
        print(f"{ep_label:<8}{r['views']:>7}{r['watch_time_min']:>9}{r['avg_dur_sec']:>8}"
              f"{r['avg_dur_pct']:>9}{r['engaged_rate']:>9}{r['impressions']:>7}{r['ctr_pct']:>7}  {r['title'][:40]}")
    print("（* = Shorts）")

    n = len(rows)
    total_views = sum(r["views"] for r in rows)
    total_imp = sum(r["impressions"] for r in rows)
    avg_retention = sum(r["avg_dur_pct"] for r in rows) / n if n else 0
    print(f"\n動画数: {n} / 総再生数: {total_views} / 総インプレッション: {total_imp} / 平均維持率: {avg_retention:.1f}%")

    if rows:
        print("\n--- 視聴維持率トップ5 ---")
        for r in sorted(rows, key=lambda x: -x["avg_dur_pct"])[:5]:
            print(f"  {r['ep']} {r['avg_dur_pct']}% ({r['views']}views) {r['title'][:35]}")

        print("\n--- 視聴維持率ワースト5 ---")
        for r in sorted(rows, key=lambda x: x["avg_dur_pct"])[:5]:
            print(f"  {r['ep']} {r['avg_dur_pct']}% ({r['views']}views) {r['title'][:35]}")

    # カテゴリ別ロールアップ（本編のみ対象。Shortsはカテゴリ判断のノイズになりやすいため除外）
    cat_totals = defaultdict(lambda: {"views": 0, "watch_time_min": 0.0, "retention_sum": 0.0, "n": 0, "impressions": 0, "ctr_sum": 0.0})
    for r in rows:
        if r["is_shorts"] or not r["category_label"]:
            continue
        c = cat_totals[r["category_label"]]
        c["views"] += r["views"]
        c["watch_time_min"] += r["watch_time_min"]
        c["retention_sum"] += r["avg_dur_pct"]
        c["n"] += 1
        c["impressions"] += r["impressions"]
        c["ctr_sum"] += r["ctr_pct"] * r["impressions"]

    if cat_totals:
        print("\n--- カテゴリ別ロールアップ（本編のみ、STAGE1 weight見直しの参考用） ---")
        print(f"{'カテゴリ':<22}{'話数':>5}{'総再生数':>9}{'総視聴分':>9}{'平均維持率%':>12}{'平均CTR%':>10}")
        for label, c in sorted(cat_totals.items(), key=lambda x: -x[1]["views"]):
            avg_ret = c["retention_sum"] / c["n"] if c["n"] else 0
            avg_ctr = (c["ctr_sum"] / c["impressions"]) if c["impressions"] else 0
            print(f"{label:<22}{c['n']:>5}{c['views']:>9}{c['watch_time_min']:>9.1f}{avg_ret:>12.1f}{avg_ctr:>10.2f}")

    src_total = defaultdict(int)
    for vid, d in traffic_stats.items():
        for src, v in d.items():
            src_total[src] += v
    total_src = sum(src_total.values())
    if total_src:
        print("\n--- トラフィックソース ---")
        for src, v in sorted(src_total.items(), key=lambda x: -x[1]):
            name = TRAFFIC_SRC_NAMES.get(src, f"unknown({src})")
            print(f"  {name:<15} {v:>6} views ({v/total_src*100:.1f}%)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--after", help="このエピソード番号以降のみ集計（例: kl004）")
    parser.add_argument("--before", help="このエピソード番号未満のみ集計")
    args = parser.parse_args()

    vid_info = load_episode_map()

    def norm(ep):
        if not ep:
            return None
        m = re.search(r"(\d+)", ep)
        return m.group(1).zfill(3) if m else None

    after = norm(args.after) if args.after else None
    before = norm(args.before) if args.before else None

    if after or before:
        def ep_filter(ep):
            n = norm(ep)
            if n is None:
                return False
            if after and n < after:
                return False
            if before and n >= before:
                return False
            return True
        label = f"期間指定: after={args.after or '-'} before={args.before or '-'}"
    else:
        ep_filter = None
        label = "全期間"

    rows, traffic_stats = aggregate(vid_info, ep_filter)
    print_report(rows, traffic_stats, label)


if __name__ == "__main__":
    main()
