"""試験（指示 2026-11-10-016 の2）: YouTube の「英語では熱いが日本語では薄い」差の判定・加点・ガードを確かめる。
YouTube Data API のキーが無い環境では実データを取れないため、
(A) 判定ロジックの単体試験（模擬の動画一覧）と、
(B) 直近の候補の実データ（日本の独立媒体 nj・英語の独立媒体 nf・fit・ゲートは kl_diag_buzz_foreign.py の 2026-11-10 の実測）に
    「英語で熱く日本語で薄い」模擬の YouTube 測定値を当てたときの注目度・本命判定の変化、
を出す。(B) の YouTube の数値は模擬（実測ではない）。
使い方: python3 kl_test_yt_gap.py"""
import os
import sys
from datetime import datetime, timedelta, timezone

import kl_news_scan as ns

ok = True


def check(name, cond):
    global ok
    print(("OK  " if cond else "NG  ") + name)
    ok = ok and cond


def vid(title, ch, views, days_ago=1):
    d = (datetime.now(timezone.utc) - timedelta(days=days_ago)).date().isoformat()
    return {"title": title, "channel_id": ch, "views": views, "published": d}


# ---------- (A) 単体 ----------
EN_A = ["neo"]
en_vids = [vid("1X NEO robot unboxing", "c1", 400_000), vid("NEO home robot review", "c2", 90_000, 2),
           vid("1X NEO vs Figure", "c3", 60_000, 3), vid("Is NEO worth $20k?", "c4", 30_000, 5),
           vid("Neon lights DIY", "c5", 900_000), vid("ネオ ロボット", "c6", 10_000)]
en = ns.count_yt(en_vids, "en", EN_A)
check("英語: neon・かな見出しは数えない（4本・4ch）", en["videos"] == 4 and en["channels"] == 4)
ja = ns.count_yt([vid("1X NEOが発売 家庭用ロボット", "j1", 3_000)], "ja", EN_A, ["ホームロボット"])
check("日本語: 英字の固有名詞を含む日本語見出しを数える", ja["videos"] == 1 and ja["views"] == 3000)
g = ns.yt_gap(en, ja, foreign_media=5)
check("英熱い・日薄い・ニュースあり → 差あり", g["gap"] and g["gap_log"] >= ns.YT_GAP_MIN_LOG)
check("英語のニュースが2媒体なら差なし（YouTube だけの話題）", not ns.yt_gap(en, ja, 2)["gap"])
viral = ns.count_yt([vid("1X NEO robot", "c1", 5_000_000)], "en", EN_A)
check("1本のバイラルだけ（1ch）は差なし", not ns.yt_gap(viral, ja, 5)["gap"])
old = ns.count_yt([vid("NEO robot %d" % i, "c%d" % i, 50_000, 12) for i in range(5)], "en", EN_A)
check("直近7日の動画が無い（もう熱くない）は差なし", not ns.yt_gap(old, ja, 5)["gap"])
ja_hot = ns.count_yt([vid("1X NEO 解説 %d" % i, "j%d" % i, 200_000) for i in range(4)], "ja", EN_A)
check("日本語も既に広がっている（4ch・再生が同程度）は差なし", not ns.yt_gap(en, ja_hot, 5)["gap"])
yt_cap = ns.count_yt([vid("1X NEO robot %d" % i, "c%d" % i, 9_000_000) for i in range(3)], "en", EN_A)
check("1本あたり再生数は上限で頭打ち", yt_cap["views"] == 3 * ns.YT_VIEW_CAP)

r = ns.apply_yt_gap({"buzz_measured": 3, "buzz_jp_measured": 3}, en, ja, 5)
check("日本だけ3 → 差ありで+1=4（上限4）", r["buzz_measured"] == 4 and r["buzz_yt_bonus"] == 1)
r = ns.apply_yt_gap({"buzz_measured": 4, "buzz_jp_measured": 4}, en, ja, 5)
check("すでに4なら上げない（5は日本の報道が広がった候補だけ）", r["buzz_measured"] == 4 and r["buzz_yt_bonus"] == 0)
r = ns.apply_yt_gap({"buzz_measured": 3, "buzz_jp_measured": 1}, en, ja, 5)
check("日本1・海外メディアで既に3 → YouTube は足さない（合計の持ち上げは日本+2まで）", r["buzz_measured"] == 3 and r["buzz_yt_bonus"] == 0)
r = ns.apply_yt_gap({"buzz_measured": 2, "buzz_jp_measured": 1}, en, ja, 5)
check("日本1・合算2 → YouTube で3（入口を越える＝buzz_yt_boost）", r["buzz_measured"] == 3 and r["buzz_yt_boost"])

# ---------- (B) 実データ（nj・nf・fit・ゲート）× 模擬の YouTube ----------
EN_HOT = {"videos": 12, "channels": 8, "views": 900_000, "recent7": 6}
JA_THIN = {"videos": 1, "channels": 1, "views": 4_000}
# (見出し, 日本の独立媒体 nj, 英語の独立媒体 nf, audience_fit, 現在のゲート)  ※ kl_diag_buzz_foreign.py の 2026-11-10 の実測
REAL = [("APOE4（アルツハイマーのリスク遺伝子）", 0, 5, 3, "鮮度<3"),
        ("XTEND ペイロード特許", 1, 21, 2, "鮮度<3・暮らし仕事<4"),
        ("OpenAI GPT-6", 6, 65, 4, "鮮度<3"),
        ("NVIDIA Isaac ROS 5.0", 1, 7, 2, "鮮度<3・暮らし仕事<4"),
        ("Gemini agent（企業向け）", 3, 7, 5, "鮮度<3"),
        ("retatrutide 第3相", 1, 19, 2, "鮮度<3"),
        ("Amazon Bee 新デバイス", 2, 5, 5, "鮮度<3"),
        ("Figure 03（日本4・海外5。fit は未確認＝5と仮定）", 4, 5, 5, "鮮度1・暮らし仕事3"),
        ("Tesla Optimus（日本4・海外25。fit は未確認＝5と仮定）", 4, 25, 5, "—"),
        ("1X NEO（日本0・海外2）", 0, 2, 5, "—")]
print("\n(B) 実データの nj・nf・fit に、模擬の YouTube（英8ch/90万再生/直近7日6本・日1ch/4千再生）を当てる")
print("    列: 見出し ｜ 日本のみ → 海外メディア込み(013) → YouTube込み ｜ fit ｜ 本命相当か（注目≥3 かつ fit≥4。鮮度などの他ゲートは別）")
for title, nj, nf, fit, gate in REAL:
    jp_only = ns.combine_foreign(nj, False, 0)["buzz_measured"]
    r = ns.combine_foreign(nj, False, nf)
    news_m = r["buzz_measured"]
    ns.apply_yt_gap(r, EN_HOT, JA_THIN, nf)
    final = r["buzz_measured"]
    # classify と同じ規則: fit が足りなければ YouTube 加点を外し、海外ブーストなら日本のみの値で枠を決める
    eff = final if fit >= ns.FOREIGN_BOOST_MIN_FIT else max(1, final - r["buzz_yt_bonus"])
    lane_news = news_m >= 3 and (fit >= ns.FOREIGN_BOOST_MIN_FIT or r["buzz_jp_measured"] >= 3)
    lane_final = eff >= 3 and (fit >= ns.FOREIGN_BOOST_MIN_FIT or r["buzz_jp_measured"] >= 3)
    mark = "◎新たに本命相当" if (lane_final and not lane_news) else ("（変化なし）" if lane_final == lane_news else "？")
    print("    - %s ｜ %d → %d → %d ｜ fit%d ｜ 本命相当 %s→%s %s ｜ 他ゲート: %s" %
          (title, jp_only, news_m, final, fit, "○" if lane_news else "×", "○" if lane_final else "×", mark, gate))
    if fit < ns.FOREIGN_BOOST_MIN_FIT:
        check("低fit(%d)は YouTube 加点で本命相当にならない: %s" % (fit, title[:16]), not lane_final or lane_final == lane_news)
    check("YouTube 込みは海外メディア込みより下がらず、日本のみ+2・4を超えない: %s" % title[:16],
          final >= news_m and final <= max(news_m, min(ns.YT_GAP_CAP, r["buzz_jp_measured"] + ns.YT_TOTAL_LIFT_MAX)))

# 低 fit の classify 経由の確認（実装そのもの）
base = {"id": "t1", "status": "available", "title": "t", "announced_on": datetime.now().date().isoformat(), "buzz_measured": 4,
        "buzz_yt_bonus": 1, "buzz_jp_measured": 2, "audience_fit": 3, "verifiability": 5, "life_relevance": 5, "work_relevance": 5,
        "hype_gap": 3, "debate": 3, "primary_sources": [], "series": "t1", "genre": "ai", "jp_news_query": "x"}
try:
    row = ns.classify([dict(base)])[0]
    row_hi = ns.classify([dict(base, id="t2", series="t2", audience_fit=5)])[0]
    check("classify: fit3 は YouTube 分(+1)を外した値で core を出す（fit5 は含める）",
          row["core"] is not None and row_hi["core"] is not None and row["core"] == row["fresh"] * 3 * 3 and row_hi["core"] == row_hi["fresh"] * 4 * 5)
except Exception as e:  # noqa: BLE001
    check("classify の確認が例外: %r" % e, False)

if not os.environ.get("YOUTUBE_API_KEY_KL"):
    r = {"buzz_measured": 3, "buzz_outlets_foreign": 6, "buzz_query_en": "x"}
    ns.measure_yt({"jp_news_query": "x"}, r, [5])
    check("キー未設定なら measure_yt は何も足さない（従来どおり）", "buzz_yt" not in r)

print("\n" + ("全OK" if ok else "NGあり"))
sys.exit(0 if ok else 1)
