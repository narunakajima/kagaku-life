#!/usr/bin/env python3
"""
kl_analytics_report.py — アナリティクスCSVを集計してエピソード別・カテゴリ別レポートを出力する。

前提: kl_yt_download_reports.py で Google Drive Kagaku-Life/analytics/raw/ にCSVをダウンロード済みであること。

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
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
# 2026-10-04: 保存先をGoogle Driveの同期フォルダに移した（MacBook・iMacで共有するため。
# Reporting APIは古いレポートを一定期間で消すので、どちらの端末で取得した分も1か所に残す）
GDRIVE_ROOT = (
    Path.home()
    / "Library"
    / "CloudStorage"
    / "GoogleDrive-naru.nakajima@gmail.com"
    / "マイドライブ"
    / "Kagaku-Life"
)
RAW = GDRIVE_ROOT / "analytics" / "raw"
EPISODES_DIR = BASE / "episodes"
TOPICS_QUEUE_JSON = BASE / "topics_queue.json"
CONCERNS_JSON = BASE / "viewer_concerns.json"

# 分類別ロールアップの「経過日数バイアス」対策（2026-09-08追加）。
# samurai-chroniclesのOpus監査で「累積CTR/維持率の比較は公開時期の違いに
# よるバイアスを検出できない設計だった」と判明した教訓の移植。全期間の
# 累積値をそのまま比較すると、たまたま古い話が多いカテゴリが有利になる
# ため、公開後AGE_WINDOW_DAYS日分だけを切り出して比較する。
AGE_WINDOW_DAYS = 14
# 分類別ロールアップで数値をそのまま信頼してよいとみなす最小該当話数。
# 未満の場合は数値自体は出しつつ「n不足」の注記を付ける
# （samurai-chroniclesのn<6「測定不能」表示の教訓の移植。KLはまだ話数が
# 少なくカテゴリ当たりのnがSCの閾値では厳しすぎるため、KLの規模に合わせて
# 下げている）。
MIN_GROUP_N = 3
# Shortsの比較に使う測定窓（日）。Shortsの再生は公開当日〜翌日に集中するため、本編の
# 14日より短い3日で比べる（2026-09-29追加、PIPELINE_REDESIGN.md §11）。
SHORTS_WINDOW_DAYS = 3

# YouTube Reporting API公式定義（developers.google.com/youtube/reporting/v1/
# reports/dimensions#traffic_source_type）と照合して修正した（2026-09-28、
# /kl-analytics初回実行時にOpusサブエージェントの監査で誤りが発覚。旧定義は
# ほぼ全コードが1〜2個ずれていた——例えば実際は「外部」を指すコード9を
# 「通知」と表示していた等——ため、流入経路の解釈が実態と食い違っていた）。
TRAFFIC_SRC_NAMES = {
    "0": "直接/不明", "1": "YouTube広告", "3": "ブラウズ機能",
    "4": "チャンネルページ", "5": "YT検索", "7": "関連動画",
    "8": "その他のYT機能", "9": "外部", "11": "カード/注釈",
    "14": "プレイリスト", "17": "通知", "18": "再生リストページ",
    "19": "申告済みコンテンツ", "20": "終了画面", "23": "Stories",
    "24": "Shorts", "25": "商品ページ", "26": "ハッシュタグページ",
    "27": "サウンドページ", "28": "ライブリダイレクト", "29": "Podcasts",
    "30": "リミックス動画", "31": "縦型ライブフィード",
    "32": "Shorts内関連動画",
}


def video_id(url: str) -> str:
    m = re.search(r"(?:youtu\.be/|v=)([A-Za-z0-9_-]{11})", url or "")
    return m.group(1) if m else ""


SLOT_LABELS = {"concern": "関心ごと起点", "wildcard": "ワイルドカード", "legacy": "旧方式"}


def load_episode_map():
    """video_id -> エピソード情報（episode_id・タイトル・本編/Shorts・分類・公開日）を作る。

    本編とShorts、両方のvideo_idを対象にする（analytics上はどちらも同じ
    video_idの列で報告されるため）。

    2026-09-29〜（ネタ選定パイプライン作り直し）: 分類は旧カテゴリではなく、
    topics_queue.json の domain（領域）・concern_id（関心ごと）・slot_type（選び方）で持つ。
    """
    domain_labels, concern_labels = {}, {}
    if CONCERNS_JSON.exists():
        vc = json.loads(CONCERNS_JSON.read_text(encoding="utf-8"))
        domain_labels = {k: v["label"] for k, v in vc.get("domains", {}).items()}
        concern_labels = {c["id"]: c["label"] for c in vc.get("concerns", [])}

    group_map = {}
    if TOPICS_QUEUE_JSON.exists():
        queue = json.loads(TOPICS_QUEUE_JSON.read_text(encoding="utf-8")).get("queue", [])
        for item in queue:
            eid = item.get("episode_id")
            if eid:
                cid = item.get("concern_id")
                group_map[eid] = {
                    "domain_label": domain_labels.get(item.get("domain") or "", None),
                    "concern_label": concern_labels.get(cid, "（関心ごとなし）") if cid else "（関心ごとなし）",
                    "slot_label": SLOT_LABELS.get(item.get("slot_type") or "", None),
                }
    empty = {"domain_label": None, "concern_label": None, "slot_label": None}

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
        groups = group_map.get(eid, empty)

        publish_date = None
        scheduled_at = d.get("scheduled_at") or ""
        if scheduled_at:
            try:
                publish_date = datetime.strptime(scheduled_at.split(" ")[0], "%Y-%m-%d").date()
            except ValueError:
                publish_date = None

        main_vid = video_id(d.get("youtube_url", ""))
        if main_vid:
            vid_info[main_vid] = {
                "ep": eid, "title": title, "is_shorts": False,
                **groups, "publish_date": publish_date,
            }

        shorts_vid = video_id(d.get("shorts_url", ""))
        if shorts_vid:
            vid_info[shorts_vid] = {
                "ep": eid, "title": f"{title}（Shorts）", "is_shorts": True,
                **groups, "publish_date": publish_date,
            }

    return vid_info


def _latest_data_date() -> date:
    """ダウンロード済みCSVのうち一番新しい日付（ファイル名がYYYY-MM-DD）。
    age-adjusted集計で「測定窓が完了しているか」を判定する基準に使う。"""
    dates = []
    for path in glob.glob(str(RAW / "kl-channel_combined_a3" / "*.csv")):
        try:
            dates.append(datetime.strptime(Path(path).stem, "%Y-%m-%d").date())
        except ValueError:
            continue
    return max(dates) if dates else date.today()


def aggregate(vid_info, ep_filter=None, age_window_days=None):
    """age_window_days を指定すると、各動画の公開日から window 日分だけを
    切り出して集計する（経過日数バイアス対策、CLAUDE.md/kl_analytics_report.py
    コメント参照）。公開日が不明、または最新データがまだ window 日分
    経過していない（測定窓が未完了の）動画は結果から除外する。
    """
    latest_date = _latest_data_date() if age_window_days else None

    def in_window(vid, row_date_str):
        if age_window_days is None:
            return True
        publish_date = vid_info.get(vid, {}).get("publish_date")
        if publish_date is None:
            return False
        try:
            row_date = datetime.strptime(row_date_str, "%Y%m%d").date()
        except ValueError:
            return False
        return 0 <= (row_date - publish_date).days < age_window_days

    def window_complete(vid):
        if age_window_days is None:
            return True
        publish_date = vid_info.get(vid, {}).get("publish_date")
        if publish_date is None:
            return False
        return (latest_date - publish_date).days >= age_window_days

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
                if not in_window(vid, row["date"]):
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
                if not in_window(vid, row["date"]):
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
                if not in_window(vid, row["date"]):
                    continue
                traffic_stats[vid][row["traffic_source_type"]] += int(row["views"])

    # 以前は video_stats（channel_combined_a3由来）だけをループしており、
    # 再生数が0日でこのレポートに一切行を持たない動画（例: kl006本編。
    # 再生0のため combined_a3 に該当日の行自体が生成されないが、
    # reach_basic_a1 にはインプレッションの行がある）が集計から丸ごと
    # 消えていた（2026-09-28、/kl-analytics初回実行時にOpusサブエージェントの
    # 監査で発覚）。combined_a3/reach_basic_a1どちらかにでも行があれば
    # 拾えるよう、両方のキー集合の和でループするよう修正した。
    rows = []
    for vid in set(video_stats) | set(reach_stats):
        if not window_complete(vid):
            continue
        s = video_stats.get(vid, {
            "views": 0, "watch_time_minutes": 0.0, "engaged_views": 0,
            "avg_dur_sum": 0.0, "avg_dur_pct_sum": 0.0,
        })
        info = vid_info.get(vid, {})
        views = s["views"]
        avg_dur = s["avg_dur_sum"] / views if views else 0.0
        avg_dur_pct = s["avg_dur_pct_sum"] / views if views else 0.0
        engaged_rate = s["engaged_views"] / views * 100 if views else 0.0
        r = reach_stats.get(vid, {"impressions": 0, "ctr_sum": 0})
        ctr = (r["ctr_sum"] / r["impressions"] * 100) if r["impressions"] else 0
        rows.append({
            "ep": info.get("ep", "?"),
            "title": info.get("title", "?"),
            "domain_label": info.get("domain_label"),
            "concern_label": info.get("concern_label"),
            "slot_label": info.get("slot_label"),
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


def monthly_channel_summary():
    """チャンネル全体（カテゴリ・エピソードで絞り込まない）の月次インプレッション・
    再生数。個別カテゴリ/動画の優劣を論じる前に、それがチャンネル全体の構造的な
    露出増減によるものではないかを切り分けるために使う
    （samurai-chroniclesのOpus監査で追加されたprint_monthly_channel_summaryの
    移植、2026-09-08）。--after/--beforeによる期間指定の影響を受けない
    チャンネル全期間のトレンドを常に表示する。
    """
    monthly_impr = defaultdict(int)
    monthly_views = defaultdict(int)
    for path in glob.glob(str(RAW / "kl-channel_reach_basic_a1" / "*.csv")):
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                monthly_impr[row["date"][:6]] += int(row["video_thumbnail_impressions"])
    for path in glob.glob(str(RAW / "kl-channel_combined_a3" / "*.csv")):
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                monthly_views[row["date"][:6]] += int(row["views"])
    return monthly_impr, monthly_views


def print_monthly_channel_summary():
    monthly_impr, monthly_views = monthly_channel_summary()
    print(f"\n{'='*95}\nチャンネル全体 月次露出トレンド（カテゴリ別の優劣より先に確認する前提）\n{'='*95}")
    for ym in sorted(set(monthly_impr) | set(monthly_views)):
        impr = monthly_impr.get(ym, 0)
        views = monthly_views.get(ym, 0)
        print(f"  {ym[:4]}-{ym[4:]}: インプレッション={impr:,}  再生数={views:,}")


def print_main_rollup(rows: list, adj_rows: list, key: str, title: str) -> None:
    totals = defaultdict(lambda: {
        "views": 0, "watch_time_min": 0.0, "retention_sum": 0.0, "n": 0,
        "impressions": 0, "ctr_sum": 0.0, "episodes": [],
    })
    for r in adj_rows:
        if r["is_shorts"] or not r.get(key):
            continue
        c = totals[r[key]]
        c["views"] += r["views"]
        c["watch_time_min"] += r["watch_time_min"]
        c["retention_sum"] += r["avg_dur_pct"]
        c["n"] += 1
        c["impressions"] += r["impressions"]
        c["ctr_sum"] += r["ctr_pct"] * r["impressions"]
        c["episodes"].append((r["ep"], r["views"]))

    grouped_eps = {r["ep"] for r in rows if not r["is_shorts"] and r.get(key)}
    adj_eps = {r["ep"] for r in adj_rows if not r["is_shorts"] and r.get(key)}
    excluded_n = len(grouped_eps - adj_eps)
    if not grouped_eps:
        return

    print(f"\n--- 本編 {title}（公開後{AGE_WINDOW_DAYS}日間で正規化） ---")
    if excluded_n:
        print(f"（公開日不明、または公開後まだ{AGE_WINDOW_DAYS}日経っていない{excluded_n}話は測定窓未完了のため除外）")
    if not totals:
        print("（測定窓が完了した話が無いため、まだ算出できません）")
        return
    print(f"{'分類':<22}{'話数':>5}{'再生数':>9}{'視聴分':>9}{'平均維持率%':>12}{'平均CTR%':>10}")
    for label, c in sorted(totals.items(), key=lambda x: -x[1]["views"]):
        avg_ret = c["retention_sum"] / c["n"] if c["n"] else 0
        avg_ctr = (c["ctr_sum"] / c["impressions"]) if c["impressions"] else 0
        n_note = "  ※n不足のため参考程度" if c["n"] < MIN_GROUP_N else ""
        print(f"{label:<22}{c['n']:>5}{c['views']:>9}{c['watch_time_min']:>9.1f}{avg_ret:>12.1f}{avg_ctr:>10.2f}{n_note}")
        # 内訳を併記する（2026-09-28追加）。合計が実質1本の外れ値で決まっているケースを
        # その場で見分けられるように（samurai-chroniclesの監査で指摘された対応）。
        breakdown = ", ".join(f"{ep}:{v}" for ep, v in sorted(c["episodes"], key=lambda x: -x[1]))
        dominant_ep, dominant_views = max(c["episodes"], key=lambda x: x[1])
        dominant_note = ""
        if c["views"] and dominant_views / c["views"] >= 0.7 and c["n"] > 1:
            dominant_note = f"  ※{dominant_ep}1本で{dominant_views/c['views']*100:.0f}%を占める"
        print(f"    内訳: {breakdown}{dominant_note}")


def print_shorts_rollup(shorts_rows: list, key: str, title: str) -> None:
    """Shortsを公開後SHORTS_WINDOW_DAYS日の再生数とエンゲージ率で比べる（2026-09-29追加）。
    流入の大半がShortsフィード経由で、Shortsの再生は公開直後に集中するため、題材の選び方の
    効果はまずここに出る。1本の外れ値に引っ張られないよう、再生数は中央値も併記する。"""
    groups = defaultdict(list)
    for r in shorts_rows:
        if r["is_shorts"] and r.get(key):
            groups[r[key]].append(r)
    if not groups:
        return
    print(f"\n--- Shorts {title}（公開後{SHORTS_WINDOW_DAYS}日間） ---")
    print(f"{'分類':<22}{'話数':>5}{'再生数計':>9}{'中央値':>8}{'エンゲージ率%':>13}")
    for label, lst in sorted(groups.items(), key=lambda x: -sum(r["views"] for r in x[1])):
        views = sorted(r["views"] for r in lst)
        median = views[len(views) // 2] if len(views) % 2 else (views[len(views) // 2 - 1] + views[len(views) // 2]) / 2
        total_views = sum(views)
        # エンゲージ率は再生数で重み付けした平均（engaged_views合計 / views合計）
        engaged = sum(r["engaged_rate"] * r["views"] for r in lst) / total_views if total_views else 0
        n_note = "  ※n不足のため参考程度" if len(lst) < MIN_GROUP_N else ""
        print(f"{label:<22}{len(lst):>5}{total_views:>9}{median:>8}{engaged:>13.1f}{n_note}")
        breakdown = ", ".join(f"{r['ep']}:{r['views']}" for r in sorted(lst, key=lambda x: -x["views"]))
        print(f"    内訳: {breakdown}")


def print_report(rows, traffic_stats, label, rows_age_adjusted=None, rows_shorts=None):
    print(f"\n{'='*95}\n{label}\n{'='*95}")
    # 「完了率%」は実際には engaged_views/views（エンゲージ率、Shorts的には
    # 「スワイプで飛ばされずに見られた率」）であり、視聴完了率ではなかった
    # （2026-09-28、Opusサブエージェントの監査で発覚。ラベルのみ修正）。
    print(f"{'EP':<8}{'Views':>7}{'視聴分':>9}{'平均秒':>8}{'維持率%':>9}{'エンゲージ率%':>12}{'imp':>7}{'CTR%':>7}  Title")
    for r in rows:
        ep_label = r["ep"] + ("*" if r["is_shorts"] else "")
        print(f"{ep_label:<8}{r['views']:>7}{r['watch_time_min']:>9}{r['avg_dur_sec']:>8}"
              f"{r['avg_dur_pct']:>9}{r['engaged_rate']:>12}{r['impressions']:>7}{r['ctr_pct']:>7}  {r['title'][:40]}")
    print("（* = Shorts）")

    n = len(rows)
    total_views = sum(r["views"] for r in rows)
    total_imp = sum(r["impressions"] for r in rows)
    avg_retention = sum(r["avg_dur_pct"] for r in rows) / n if n else 0
    print(f"\n動画数: {n} / 総再生数: {total_views} / 総インプレッション: {total_imp} / 平均維持率: {avg_retention:.1f}%")

    # Shortsはループ再生のため維持率が100%を超えうる（例: kl005*105%）。
    # 本編と同じ物差しで比べられないため、本編・Shortsを分けて表示する
    # （2026-09-28、Opusサブエージェントの監査で「混在させると比較にならない」
    # と指摘され対応）。
    main_rows = [r for r in rows if not r["is_shorts"]]
    shorts_rows = [r for r in rows if r["is_shorts"]]
    for group_label, group_rows in (("本編", main_rows), ("Shorts", shorts_rows)):
        if not group_rows:
            continue
        print(f"\n--- 視聴維持率トップ5（{group_label}） ---")
        for r in sorted(group_rows, key=lambda x: -x["avg_dur_pct"])[:5]:
            print(f"  {r['ep']} {r['avg_dur_pct']}% ({r['views']}views) {r['title'][:35]}")

        print(f"\n--- 視聴維持率ワースト5（{group_label}） ---")
        for r in sorted(group_rows, key=lambda x: x["avg_dur_pct"])[:5]:
            print(f"  {r['ep']} {r['avg_dur_pct']}% ({r['views']}views) {r['title'][:35]}")

    # 分類別ロールアップ（本編）。全期間の累積値ではなく、公開後AGE_WINDOW_DAYS日分だけを
    # 切り出したage-adjusted集計を使う（samurai-chroniclesのOpus監査で「累積比較は公開時期の
    # 違いによるバイアスを検出できない」と判明した教訓の移植、2026-09-08）。測定窓が
    # 完了していない直近公開分は aggregate() 側で既に除外済み。
    # 2026-09-29〜: 分類を旧カテゴリから、領域・関心ごと・選び方（関心ごと起点／ワイルドカード／
    # 旧方式）に変えた（ネタ選定パイプライン作り直し、PIPELINE_REDESIGN.md §11）。
    adj_rows = rows_age_adjusted if rows_age_adjusted is not None else rows
    for key, title in (("slot_label", "選び方別"), ("domain_label", "領域別"), ("concern_label", "関心ごと別")):
        print_main_rollup(rows, adj_rows, key, title)

    if rows_shorts is not None:
        for key, title in (("slot_label", "選び方別"), ("domain_label", "領域別")):
            print_shorts_rollup(rows_shorts, key, title)

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

    if not GDRIVE_ROOT.exists():
        print(f"❌ Google Driveの同期フォルダが見つかりません: {GDRIVE_ROOT}")
        print("   Google Drive for desktopが起動・ログイン済みか確認してください。")
        sys.exit(1)

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

    print_monthly_channel_summary()

    rows, traffic_stats = aggregate(vid_info, ep_filter)
    rows_age_adjusted, _ = aggregate(vid_info, ep_filter, age_window_days=AGE_WINDOW_DAYS)
    rows_shorts, _ = aggregate(vid_info, ep_filter, age_window_days=SHORTS_WINDOW_DAYS)
    print_report(rows, traffic_stats, label, rows_age_adjusted=rows_age_adjusted, rows_shorts=rows_shorts)


if __name__ == "__main__":
    main()
