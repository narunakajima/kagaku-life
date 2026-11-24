#!/usr/bin/env python3
"""弱い週のワイルドカード（2026-11-24、なるさんの決定）の試験。ファイルは書かない・課金なし。
  python3 kl_test_wildcard.py
本命（驚き4以上・確認済み）が3本に満たない週だけ、驚き5・合い方ちょうど3の候補を「参考（ワイルドカード）」として1件まで足す。
"""
import copy
import kl_news_scan as k

ok = True


def check(name, cond):
    global ok
    print(("OK  " if cond else "NG  ") + name)
    ok = ok and cond


def row(i, genre, interest, wonder=4, fit=4, lane="本命", gate=None, **kw):
    c = {"id": i, "genre": genre, "title": f"候補{i}", "summary": "", "audience_fit": fit, "wonder": wonder, "promise": 4,
         "primary_verified": True, "status": "available", "buzz_measured": 3, "surprise_line": "誰もが、〜に驚く",
         "interest_version": k.INTEREST_VERSION, "life_relevance": 4, "work_relevance": 3}
    c.update(kw)
    return {"c": c, "fresh": 3, "gate": gate or [], "lane": lane, "core": 30, "core_est": 30, "tb": 0, "interest": interest,
            "old": 0, "series": i}


def wc(i="w", wonder=5, fit=3, gate=("暮らし・仕事<4",), lane="除外", **kw):
    return row(i, "life_tech", 11, wonder=wonder, fit=fit, lane=lane, gate=list(gate), life_relevance=2, work_relevance=2, **kw)


def honmei(n):
    gs = ["ai", "humanoid", "medical", "food_health", "life_tech"]
    return [row(f"h{j}", gs[j], 14 - j) for j in range(n)]


def weak():
    return [row("r1", "ai", 9, wonder=3), row("r2", "medical", 8, wonder=3)]


def wild_ids(picks):
    return [p["c"]["id"] for p in picks if p.get("wildcard")]


def run(rows):
    picks, _ = k.best3(copy.deepcopy(rows))
    return picks


k.WEEKLY_MODE = True

p = run(honmei(3) + weak() + [wc()])
check("本命3本の週は出ない", wild_ids(p) == [])

p = run(honmei(2) + weak() + [wc()])
check("本命2本・条件に合う候補あり → 1件出る", wild_ids(p) == ["w"])
w = [x for x in p if x.get("wildcard")][0]
check("ワイルドカードは本命に数えない（ref_only・表示ラベル）", w.get("ref_only") and w["slot"] == k.SLOT_WILDCARD)
n_honmei = sum(1 for r in p if not r.get("ref_only") and not r.get("weak_day") and not r.get("reserve"))
check("本命の数は2のまま", n_honmei == 2)
check("注記にワイルドカードと明記", any("ワイルドカード" in ln for ln in k._slot_lines(w)))

p = run(honmei(2) + weak() + [wc("w1"), wc("w2")])
check("条件に合う候補が2件でも出すのは1件まで", len(wild_ids(p)) == 1)

p = run(weak() + [wc()])
check("本命0本（弱い週）でも出る", wild_ids(p) == ["w"])

for name, extra in [("合い方2は出ない", wc(fit=2)), ("合い方4は出ない", wc(fit=4)), ("驚き4は出ない", wc(wonder=4))]:
    check(name, wild_ids(run(honmei(2) + weak() + [extra])) == [])

check("鮮度のゲート落ちは出ない", wild_ids(run(honmei(2) + [wc(gate=("鮮度<3", "暮らし・仕事<4"))])) == [])
check("宣伝のゲート落ちは出ない", wild_ids(run(honmei(2) + [wc(gate=("宣伝（顧客の導入事例）",))])) == [])
check("一次資料が要確認（None）は出ない", wild_ids(run(honmei(2) + [wc(primary_verified=None)])) == [])
check("驚きの1行が空は出ない", wild_ids(run(honmei(2) + [wc(surprise_line="")])) == [])
check("手応え2は出ない", wild_ids(run(honmei(2) + [wc(promise=2)])) == [])
check("ゲートを通った注目度低の候補も対象", wild_ids(run(honmei(2) + [wc(gate=(), lane="注目度低")])) == ["w"])
check("再評価待ちは出ない", wild_ids(run(honmei(2) + [wc(gate=(), lane=k.L2_WAIT_LANE)])) == [])
pa = {"version": k.PRIOR_ART_VERSION, "status": "realized", "novelty_exception": False}
check("先行事例あり（実現済み）は出ない（驚きが上限2になる）", wild_ids(run(honmei(2) + [wc(prior_art=pa)])) == [])
# 既に下書きに入っている候補と重ねない（同じ系列）
dup = wc(gate=(), lane="本命")
p = run(honmei(2) + [dup])
check("既に下書きに入っている候補とは重ねない", wild_ids(p) == [] and "w" in [x["c"]["id"] for x in p])

rows_ts = honmei(2) + [wc(topic_series="T1")]
rows_ts[0]["c"]["topic_series"] = "T1"
check("下書きの候補と同一ストーリー（topic_series）は重ねない", wild_ids(run(rows_ts)) == [])

k.WEEKLY_MODE = False
p = run(honmei(2) + weak() + [wc()])
check("毎晩方式（WEEKLY_MODE=False）では出ない", wild_ids(p) == [])

print("\n全件OK" if ok else "\nNG あり")
raise SystemExit(0 if ok else 1)
