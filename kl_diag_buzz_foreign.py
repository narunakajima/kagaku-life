#!/usr/bin/env python3
"""注目度に海外メディアを取り入れた影響の検証（2026-11-10、handoff 2026-11-10-013）。保存しない（読み取りと Google ニュース RSS の取得のみ）。

直近の採点済み・実測済みの available 候補について、英語圏の独立媒体数を測り、新旧の注目度・枠（本命など）・ベスト3の下書きを比べる。
使い方: python3 kl_diag_buzz_foreign.py [--max N] [--sleep 2.5]"""
import argparse
import copy
import time

import kl_news_scan as ks

# 調査 2026-11-10-012 の実測（日本の独立媒体数, 海外の独立媒体数）。ウォッチ対象・節目の確認用
WATCH = [("Anthropic 量子計算の難問をAIが証明（11/9 GIGAZINE）", 4, 2), ("Figure 03 キャンパス（11/8）", 4, 5),
         ("1X NEO", 0, 2), ("Tesla Optimus", 4, 25), ("Waymo", 25, 36), ("福岡空港 貨物自動運転Lv4", 7, 1)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=200)
    ap.add_argument("--sleep", type=float, default=ks.GNEWS_INTERVAL)
    a = ap.parse_args()

    print("=== A. 調査012の実測に新しい合成を当てた表（日本nj・海外nf → 旧 / 新）===")
    for label, nj, nf in WATCH:
        old = ks.combine_foreign(nj, False, 0)["buzz_measured"]
        r = ks.combine_foreign(nj, False, nf)
        print(f"- {label}: 日本{nj}・海外{nf} → 旧{old} / 新{r['buzz_measured']}{'（海外分で入口超え）' if r['buzz_foreign_boost'] else ''}")

    cands = ks.load_candidates()["items"]
    ks.refresh_topic_ages(cands)
    base = [c for c in cands if c.get("status") == "available" and c.get("buzz_measured") is not None and c.get("jp_news_query")]
    base.sort(key=lambda c: c.get("first_seen_at") or "", reverse=True)
    base = base[:a.max]
    print(f"\n=== B. 実測済みの available 候補 {len(base)}件に海外分を測る（英語の検索語が作れるものだけ）===")
    new = {}
    nq = 0
    for c in base:
        q, anc = ks.foreign_query(c)
        if not q:
            continue
        nq += 1
        try:
            nf = ks.count_foreign(ks.fetch_gnews_en(q), anc, ks.issuer_hosts(c))
        except ks.GNewsError as e:
            print(f"  ⚠️ {c['id']} 取得失敗 {e}")
            time.sleep(a.sleep)
            continue
        time.sleep(a.sleep)
        new[c["id"]] = (q, nf)
    print(f"英語の検索語あり {nq}件、測れた {len(new)}件")

    # 新しい値を付けたコピーで classify し直す（保存しない）
    new_c = copy.deepcopy(cands)
    for c in new_c:
        if c["id"] in new:
            nj = c.get("buzz_outlets") or 0
            c.update(ks.combine_foreign(nj, bool(c.get("yahoo")), new[c["id"]][1]))
    old_rows = {r["c"]["id"]: r for r in ks.classify(copy.deepcopy(cands))}
    new_rows_l = ks.classify(new_c)
    new_rows = {r["c"]["id"]: r for r in new_rows_l}

    print("\n=== C. 新旧の違い（注目度 or 枠が変わった候補）===")
    changed = 0
    for cid, (q, nf) in new.items():
        o, n = old_rows.get(cid), new_rows.get(cid)
        if not o or not n:
            continue
        co, cn = o["c"], n["c"]
        if co["buzz_measured"] != cn["buzz_measured"] or o["lane"] != n["lane"]:
            changed += 1
            print(f"- {cid} 日本{cn.get('buzz_outlets')}・海外{nf}（{q!r}） 注目 {co['buzz_measured']}→{cn['buzz_measured']} 枠 {o['lane']}→{n['lane']} "
                  f"fit{ks.fit(cn)} 面白さ{n['interest']} 驚き1行{'あり' if ks.surprise_ok(cn) and cn.get('surprise_line') else 'なし'} "
                  f"鮮度{n['fresh']} 提示{len(ks.presented_days(cn))}日 {cn['title'][:42]}")
    print(f"変わった候補 {changed}件")

    print("\n=== D. 海外分で入口を越えた候補（buzz_foreign_boost）の内訳 ===")
    for cid, n in new_rows.items():
        c = n["c"]
        if c.get("buzz_foreign_boost"):
            o = old_rows[cid]
            print(f"- {cid} 日本{c.get('buzz_outlets')}・海外{c.get('buzz_outlets_foreign')} 注目{c['buzz_jp_measured']}→{c['buzz_measured']} "
                  f"枠{o['lane']}→{n['lane']} fit{ks.fit(c)}（要{ks.FOREIGN_BOOST_MIN_FIT}）面白さ{n['interest']} ゲート{n['gate'] or '通過'} {c['title'][:40]}")

    def b3(rows):
        try:
            picks = ks.best3(list(rows.values()))
        except Exception as e:  # noqa: BLE001
            return f"best3 失敗 {e}"
        return picks

    print("\n=== E. ベスト3の下書き（旧／新）===")
    for name, rows in (("旧", old_rows), ("新", new_rows)):
        res = b3(rows)
        picks = res[0] if isinstance(res, tuple) else res
        print(f"[{name}]")
        if isinstance(picks, str):
            print("  " + picks)
            continue
        for r in picks:
            print(f"  {r.get('slot')} {r['c']['id']} 注目{r['c'].get('buzz_measured')} 日本{r['c'].get('buzz_outlets')}・海外{r['c'].get('buzz_outlets_foreign')} {r['c']['title'][:40]}")

    print("\n=== F. 本命枠の件数（旧→新）===")
    from collections import Counter
    co, cn = Counter(r["lane"] for r in old_rows.values()), Counter(r["lane"] for r in new_rows.values())
    for k in sorted(set(co) | set(cn)):
        print(f"  {k}: {co.get(k, 0)} → {cn.get(k, 0)}")


if __name__ == "__main__":
    main()
