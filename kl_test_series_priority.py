#!/usr/bin/env python3
"""シリーズ候補の優先枠（handoff 2026-11-09-011）の試験。ファイルは書かない。
  python3 kl_test_series_priority.py
"""
import copy
import kl_news_scan as k

ok = True


def check(name, cond):
    global ok
    print(("OK  " if cond else "NG  ") + name)
    ok = ok and cond


base = {"genre": "humanoid", "title": "", "summary": "", "series_fit": 4}
t = lambda **kw: dict(base, **kw)

check("1X NEO 価格 → 該当", bool(k.series_candidate_info(t(title="1X NEOの価格が発表、月499ドル"))))
check("ウォッチ対象でない → 非該当", k.series_candidate_info(t(title="新興企業のヒューマノイドが出荷開始")) is None)
check("節目なし → 非該当", k.series_candidate_info(t(title="Tesla Optimusの開発者インタビュー")) is None)
check("ジャンル違い → 非該当", k.series_candidate_info(t(genre="ai", title="1X NEO price")) is None)
check("series_fit 2 → 非該当", k.series_candidate_info(t(title="1X NEO price", series_fit=2)) is None)
si = k.series_candidate_info(t(title="Figure 03 begins shipping to homes"))
check("Figure 03 出荷 → 第2回候補", bool(si) and si["no"] == 2 and si["name"] == "人型ロボ定点観測")

# best3: 優先枠は ok（入口条件を通った面白さ順）からだけ選ぶ
def row(i, genre, interest, lane="本命", title="x", **kw):
    c = {"id": i, "genre": genre, "title": title, "summary": "", "series_fit": 4, "audience_fit": 4, "promise": 4,
         "primary_verified": True, "status": "available", "buzz_measured": 3, "surprise_line": "s"}
    c.update(kw)
    return {"c": c, "fresh": 3, "gate": [], "lane": lane, "core": 30, "core_est": 30, "tb": 0, "interest": interest,
            "old": 0, "series": i}


rows = [row("a", "ai", 15, title="AI A"), row("b", "medical", 14, title="Med B"),
        row("c", "food_health", 13, title="Food C"),
        row("h", "humanoid", 9, title="1X NEO 出荷開始、価格は2万ドル")]
picks, _ = k.best3(copy.deepcopy(rows))
ids = [p["c"]["id"] for p in picks]
check("優先枠: 面白さが低くても入る（3件のうち1件）", "h" in ids and len(ids) == 3)

rows_gate = copy.deepcopy(rows)
rows_gate[-1]["lane"] = "注目度低"          # 入口条件（本命）を通らない
picks, _ = k.best3(rows_gate)
check("入口条件を通らないシリーズ候補は入らない", "h" not in [p["c"]["id"] for p in picks])

rows_prom = copy.deepcopy(rows)
rows_prom[-1]["c"]["promise"] = 2           # 手応え不足
picks, _ = k.best3(rows_prom)
check("手応え不足のシリーズ候補は入らない", "h" not in [p["c"]["id"] for p in picks])

picks, _ = k.best3(copy.deepcopy(rows))
lines = [ln for p in picks for ln in k._slot_lines(p) if "シリーズ候補" in ln]
check("表示: シリーズ名と第2回候補", len(lines) == 1 and "人型ロボ定点観測" in lines[0] and "第2回候補" in lines[0])
print(lines)

# 管理担当の指摘 B: 日本語表記
check("「1X社」「NEOが」に一致", bool(k.series_candidate_info(t(title="1X社の家庭用ロボNEOが出荷開始"))))
check("「Figure社」に一致", bool(k.series_candidate_info(t(title="Figure社が価格を発表、2万ドル"))))
check("「Figure」だけの一般語は不一致", k.series_candidate_info(t(title="Figure out the price"))is None)
# 指摘 C: 価格語は広すぎない
check("「1兆円」だけでは価格改定にならない", k.series_candidate_info(t(title="Tesla Optimus 時価総額1兆円の話")) is None)
for ttl in ("Figure社が6億7500万ドルを調達", "Figure AI raises $1 billion", "Unitree、59億ドル規模のIPO", "Figure AI raises $1.5B"):
    check(f"資金調達は価格改定にならない: {ttl}", k.series_candidate_info(t(title=ttl)) is None)
check("「2万ドル」は価格", bool(k.series_candidate_info(t(title="1X NEO、2万ドルで予約開始"))))
check("「$20,000」は価格", bool(k.series_candidate_info(t(title="1X NEO now $20,000"))))

# 指摘 A: 優先枠が humanoid を使っても、新規優先枠は次の新規候補を試す（誤った「新規候補なし」を出さない）
import datetime as _dt
now = _dt.datetime.now().isoformat()
rowsA = [row("h", "humanoid", 9, title="1X NEO 出荷開始、価格は2万ドル"),
         row("n1", "humanoid", 15, title="別の人型ロボ", first_seen_at=now, topic_first_date=_dt.date.today().isoformat()),
         row("n2", "medical", 8, title="新規の医療", first_seen_at=now, topic_first_date=_dt.date.today().isoformat()),
         row("x", "ai", 14, title="AI X"), row("y", "food_health", 13, title="Food Y")]
picks, _ = k.best3(copy.deepcopy(rowsA))
ids = [p["c"]["id"] for p in picks]
print(ids, "new_note=", repr(k.new_note(picks)))
check("優先枠＋新規優先枠が両立（新規候補なしと出ない）", "h" in ids and k.new_note(picks) == "")
raise SystemExit(0 if ok else 1)
