#!/usr/bin/env python3
"""news_sources.json の series 付き検索語が、収集量・ノイズにどう効くかの実測（2026-11-10、handoff 2026-11-10-015）。
読み取りのみ（Google ニュースを検索語ごとに1回取得。間隔 GNEWS_INTERVAL）。news_pool.json・news_candidates.json は書かない。
検索語ごとに: 取得件数 / 取り込み件数（上限適用後）/ うちシリーズの語（ウォッチ対象×節目）に当たる件数 / 現在のプールに無い新規件数 /
                 新規のうち見出しの簡易分類（pool_genre）が番組の分野外（不明）になる件数（ノイズの目安）。"""
import json
import time
from datetime import datetime, timedelta, timezone

import kl_news_scan as ks


def main():
    cfg = json.loads(ks.SOURCES_JSON.read_text(encoding="utf-8"))
    since = (datetime.now(timezone.utc) - timedelta(days=21)).date().isoformat()
    cap = int(cfg.get("gnews_series_max_per_query", 12))
    pool_titles = {p["title"] for p in ks._load_pool_items()}
    qs = [q for q in cfg["gnews_queries"] if q.get("series")]
    tot = {"got": 0, "kept": 0, "hit": 0, "new": 0, "new_unknown": 0, "new_hit": 0}
    print(f"series 付き検索語 {len(qs)}件（取り込み上限 {cap}/語、窓 {ks.GNEWS_COLLECT_WINDOW}日）。現在のプール {len(pool_titles)}件と比較")
    for n, gq in enumerate(qs):
        if n:
            time.sleep(ks.GNEWS_INTERVAL)
        try:
            items = ks.fetch_gnews(gq["q"], window_days=ks.GNEWS_COLLECT_WINDOW)
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️ {gq['q']}: 取得失敗 {e}")
            continue
        items = [i for i in sorted(items, key=lambda x: x["date"], reverse=True) if i["date"] and i["date"] >= since][:cap]
        rows = [{"title": i["title"], "summary": f"{i['title']}（{i['outlet'] or i['host']}）", "genre_hint": gq["genre"],
                 "published": i["date"]} for i in items]
        hit = [r for r in rows if ks.pool_series_info(r)]
        new = [r for r in rows if r["title"] not in pool_titles]
        new_unknown = []   # pool_genre は検索語のジャンルにフォールバックするため「分野不明」は測れない（ノイズは語に当たる率で見る）
        new_hit = [r for r in new if ks.pool_series_info(r)]
        print(f"  [{gq['series'][:12]}] {gq['q']!r}: 取得{len(items)} シリーズ語に当たる{len(hit)} 新規{len(new)}（うち語に当たる{len(new_hit)}・分野不明{len(new_unknown)}）")
        for r in new_hit[:2]:
            print(f"        ★新規 {r['published']} {r['title'][:60]}")
        for r in new[:0]:
            pass
        tot["got"] += len(items)
        tot["hit"] += len(hit)
        tot["new"] += len(new)
        tot["new_hit"] += len(new_hit)
        tot["new_unknown"] += len(new_unknown)
    print(f"\n合計: 取り込み{tot['got']}件 / シリーズ語に当たる{tot['hit']}件 / プールに無い新規{tot['new']}件"
          f"（うちシリーズ語に当たる{tot['new_hit']}件、分野不明{tot['new_unknown']}件）")
    print(f"収集全体（現在のプール {len(pool_titles)}件）に対する新規の割合: {tot['new'] / max(len(pool_titles), 1):.0%}。"
          f"新規のうち分野を絞る Gemini の判定（collect）を通る前の数")


if __name__ == "__main__":
    main()
