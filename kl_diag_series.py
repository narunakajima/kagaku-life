#!/usr/bin/env python3
"""定点観測シリーズ候補（series_candidate_info）が出ない原因の切り分け（2026-11-10、handoff 2026-11-10-012）。読み取りのみ・保存しない。
news_pool.json（収集した生の記事）と news_candidates.json（採点済み）から、ウォッチ対象の語・節目の語に当たるものを全て拾い、
候補ごとに『どの入口条件で落ちたか』を出す。注目度の算定（日本語の独立媒体数）と、海外発かどうかの目安も並べる。

使い方: python3 kl_diag_series.py [--since YYYY-MM-DD（記事の日付の下限。既定 2026-11-01）]"""
import argparse
import json
import re

import kl_news_scan as ks

JP = re.compile(r"[぀-ヿ]")


def rule_match(text: str):
    """全シリーズについて、(series_id, target, milestones)。target だけ合う場合は milestones が空。"""
    out = []
    for s in ks._series_list():
        rule = ks.SERIES_RULES[s["series_id"]]
        names = [t.get("name", "") for t in s.get("watch_targets", [])]
        for n, pat in rule["targets"].items():
            if any(x.startswith(n) for x in names) and re.search(pat, text):
                ms = [m for m, p in rule["milestones"].items() if re.search(p, text, re.I)]
                out.append((s["series_id"], n, ms))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-11-01")
    a = ap.parse_args()
    cands = ks.load_candidates()
    items = cands["items"]
    ks.refresh_topic_ages(items)
    used = ks.used_source_urls(items)
    series_ids = {s["series_id"]: s for s in ks._series_list()}
    by_url = {c.get("url"): c for c in items}
    by_id = {c["id"]: c for c in items}

    pool = json.loads(ks.POOL_JSON.read_text(encoding="utf-8")) if hasattr(ks, "POOL_JSON") else {"items": []}
    print(f"プール（news_pool.json）{len(pool.get('items', []))}件、採点済み候補 {len(items)}件。記事の日付 {a.since} 以降のウォッチ対象ヒット:")
    n_pool_hit = n_cand_hit = n_series = 0
    for p in pool.get("items", []):
        if (p.get("published") or "") < a.since:
            continue
        text = p.get("title", "") + " " + (p.get("summary") or "")
        ms = rule_match(text)
        if not ms:
            continue
        n_pool_hit += 1
        hit = by_id.get(p["id"]) or next((by_id[i] for i in (p.get("dup_ids") or []) if i in by_id), None)
        print(f"\n[プール] {p['published']} {p.get('source')} 〈{p.get('source_kind')}〉 {p['title'][:70]}")
        print(f"   ウォッチ語: {[(m[1], m[2]) for m in ms]}  → 採点済み: {'あり ' + hit['id'] + ' ' + hit['title'][:30] if hit else 'なし（未採点）'}"
              f" / 採点の優先区分 {ks.scoring_priority(p)[:2]}・日本語媒体{ks.jp_outlet_count(p)}・ジャンル判定 {ks.pool_genre(p)}")
    print(f"\nプールのヒット {n_pool_hit}件\n")
    print("=== 採点済み候補（全 status）でのヒット ===")
    for c in sorted(items, key=lambda x: x.get("first_seen_at") or x.get("scored_at") or ""):
        d = ks._article_day(c)
        if d < a.since:
            continue
        text = c.get("title", "") + " " + (c.get("summary") or "")
        ms = rule_match(text)
        if not ms:
            continue
        n_cand_hit += 1
        info = ks.series_candidate_info(c)
        why = []
        if info is None:
            for sid, tg, mm in ms:
                s = series_ids[sid]
                if c.get("genre") not in (s.get("candidate_genres") or [s.get("genre")]):
                    why.append(f"{sid}: ジャンル不一致（{c.get('genre')}）")
                elif ks.SERIES_RULES[sid]["series_fit_gate"] and c.get("series_fit") is not None and ks._clamp5(c["series_fit"]) < 3:
                    why.append(f"{sid}: series_fit={c.get('series_fit')}<3")
                elif not mm:
                    why.append(f"{sid}: 節目の語なし（ウォッチ語 {tg} のみ）")
        else:
            n_series += 1
        gate = ks.gate_reasons(c, used) if c.get("status") == "available" else []
        fresh = ks.freshness_score(ks.fresh_date(c))
        bm = c.get("buzz_measured")
        title = c.get("title", "")
        print(f"\n{c['id']} [{c.get('status')}] 記事{d} 初回{(c.get('first_seen_at') or c.get('scored_at') or '')[:10]} genre={c.get('genre')} {title[:60]}")
        print(f"   ウォッチ語×節目: {[(m[1], m[2]) for m in ms]} / series_candidate_info: {'該当 ' + info['name'] if info else 'なし'} {why}")
        print(f"   入口: 旬(freshness)={fresh}(要3以上) 検証={c.get('verifiability')}(要4) 暮らし/仕事={ks.stake(c)}(要4) 一次資料={c.get('primary_verified')} "
              f"ゲート={gate or '通過'}")
        print(f"   注目度: buzz_measured={bm} 日本語独立媒体={c.get('buzz_outlets')} Yahoo={c.get('yahoo')} 履歴={len(c.get('buzz_history') or [])}回 / "
              f"見出しは{'日本語' if JP.search(title) else '英語（海外発）'} 媒体={[e.get('outlet') for e in (c.get('buzz_evidence') or [])]}")
        print(f"   ベスト3条件: 視聴者fit={ks.fit(c)}(要3) 手応えpromise={ks.promise(c)}(要3) 驚き1行={ks.surprise_ok(c)} 提示済み={ks.presented_days(c)} "
              f"面白さ={ks.interest(c)} 答え合わせ型={ks.is_l2_type(c)}")
    print(f"\n採点済み候補のヒット {n_cand_hit}件、うち series_candidate_info 該当 {n_series}件")


def _fetch_en(q: str) -> list:
    """Google ニュース RSS（英語・米国版）を1回取得（読み取りのみ。fetch_gnews の英語版）。"""
    import urllib.parse
    import urllib.request
    import xml.etree.ElementTree as ET
    url = ks.GNEWS_URL + urllib.parse.urlencode({"q": f"{q} when:14d", "hl": "en-US", "gl": "US", "ceid": "US:en"})
    raw = urllib.request.urlopen(urllib.request.Request(url, headers=ks.BROWSER_UA), timeout=20).read()
    out = []
    for it in ET.fromstring(raw).findall(".//item"):
        src = it.find("source")
        d = ks._parse_date(it.findtext("pubDate") or "")
        out.append({"title": (it.findtext("title") or "").strip(), "outlet": ((src.text if src is not None else "") or "").strip(),
                    "host": ks._host((src.get("url") if src is not None else "") or ""), "date": d.date().isoformat() if d else ""})
    return out


def _count_foreign(items: list, anchors: list) -> dict:
    """見出しが anchors の全てを含む記事の、独立媒体数（転載・PR配信を除く、日本語見出しを除く）。"""
    outlets = {}
    for it in items:
        t = it["title"].lower()
        if not all(x.lower() in t for x in anchors) or JP.search(it["title"]):
            continue
        h, name = it["host"], it["outlet"]
        if ks._host_in(h, ks.AGGREGATOR_HOSTS) or any(n.lower() in name.lower() for n in ks.AGGREGATOR_NAMES):
            continue
        if ks._host_in(h, ks.PR_WIRE_HOSTS) or any(n.lower() in name.lower() for n in ks.PR_WIRE_NAMES):
            continue
        outlets.setdefault(name or h, it)
    return {"n": len(outlets), "outlets": list(outlets)[:8]}


MEASURE = [   # (ラベル, 日本語の検索語, 日本語の見出しの語, 英語の検索語, 英語の見出しの語)
    ("Anthropic 量子計算の難問をAIが証明（11/9 GIGAZINE）", "Anthropic 量子", ["anthropic"], "Anthropic quantum computing proof unsolved", ["anthropic", "quantum"]),
    ("Figure 03 キャンパス（11/8）", "Figure 03", ["figure"], "Figure 03 humanoid campus", ["figure"]),
    ("1X NEO（ウォッチ対象・節目の確認）", "1X NEO", ["neo"], "1X NEO humanoid", ["neo"]),
    ("Tesla Optimus（ウォッチ対象）", "Optimus", ["optimus"], "Tesla Optimus", ["optimus"]),
    ("Waymo（ロボタクシー）", "Waymo", ["waymo"], "Waymo expansion", ["waymo"]),
    ("福岡空港 貨物自動運転Lv4（採点済み・シリーズ該当）", "福岡空港 自動運転", ["福岡空港"], "Fukuoka airport autonomous cargo vehicle", ["fukuoka"]),
]


def measure():
    import time
    print("=== 日本語の独立媒体数（既存の算定＝kl_news_scan.count_buzz）と、英語圏の独立媒体数（同じ除外規則・14日窓）===")
    for label, qj, aj, qe, ae in MEASURE:
        try:
            jp = ks.count_buzz(ks.fetch_gnews(qj), aj, set())
            jps = f"日本 {jp['buzz_outlets']}媒体（注目度{jp['buzz_measured']}）{[e['outlet'] for e in jp['buzz_evidence']]}"
        except Exception as e:  # noqa: BLE001
            jps = f"日本 取得失敗 {str(e)[:40]}"
        time.sleep(ks.GNEWS_INTERVAL)
        try:
            fo = _count_foreign(_fetch_en(qe), ae)
            fos = f"海外 {fo['n']}媒体 {fo['outlets']}"
        except Exception as e:  # noqa: BLE001
            fos = f"海外 取得失敗 {str(e)[:40]}"
        time.sleep(ks.GNEWS_INTERVAL)
        print(f"- {label}\n    {jps}\n    {fos}")


if __name__ == "__main__":
    import sys
    if "--measure" in sys.argv:
        measure()
    else:
        main()
