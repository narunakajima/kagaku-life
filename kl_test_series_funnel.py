#!/usr/bin/env python3
"""handoff 2026-11-10-015 の試験（ファイルは書かない）。
  python3 kl_test_series_funnel.py          # 擬似データだけ（課金なし）
  python3 kl_test_series_funnel.py --live   # 加えて、実例（福岡空港レベル4・Anthropic 量子計算）で現在のデータを使う（Gemini を最大1回呼ぶ）
"""
import copy
import json
import sys

import kl_news_scan as k

ok = True


def check(name, cond):
    global ok
    print(("OK  " if cond else "NG  ") + name)
    ok = ok and cond


def pool_item(i, title, source="Googleニュース（x）／媒体", kind="media", genre_hint="ai", pub="2026-11-09"):
    return {"id": i, "title": title, "summary": title, "source": source, "source_kind": kind, "published": pub,
            "genre_hint": genre_hint, "outlet": "媒体", "gnews_link": "http://x", "sources": ["媒体"]}


# ---- 2. 採点キューの優先 ----
todo = [pool_item(f"g{n}", f"一般のAI記事{n}") for n in range(30)]
todo += [pool_item("q", "Anthropicの非公開AIモデルで18年間未解決だった量子計算の難問が証明される", source="GIGAZINE", kind="media"),
         pool_item("w", "Waymoが東京で完全無人の運行エリアを拡大", genre_hint="life_tech"),
         pool_item("w2", "ロボタクシーの事故でサービス停止", genre_hint="life_tech"),
         pool_item("w3", "ドローン配送のレベル4飛行で法改正", genre_hint="life_tech"),
         pool_item("w4", "配送ロボの自動配送が全国で開始、レベル4", genre_hint="life_tech")]
sel = k.select_for_scoring(copy.deepcopy(todo), [], 15, verbose=False)
ids = [p["id"] for p in sel]
check("GIGAZINE（娯楽寄り）でもシリーズ候補（量子計算の証明）が採点対象に入る", "q" in ids)
check("採点の件数は top を超えない（15件枠は変わらない）", len(ids) == 15)
prio = k.pick_series_priority(copy.deepcopy(todo))
pids = [p["id"] for _, p in prio]
check("シリーズ優先は最大 SERIES_SCORE_RESERVE 件", len(pids) <= k.SERIES_SCORE_RESERVE)
check("1シリーズ最大 SERIES_SCORE_PER_SERIES 件（自動運転は2件まで）", sum(1 for i in pids if i.startswith("w")) <= k.SERIES_SCORE_PER_SERIES)
check("優先で使うのは15件のうち最大4件、通常枠は最低11件が残る（優先から漏れたシリーズ記事も通常枠では普通に競う）",
      len(ids) - len(pids) >= 15 - k.SERIES_SCORE_RESERVE)
sel0 = k.select_for_scoring([p for p in copy.deepcopy(todo) if p["id"].startswith("g")], [], 15, verbose=False)
check("シリーズ候補が無い日は従来どおり15件", len(sel0) == 15)
check("優先は先頭に並ぶ", ids[0] in ("q", "w", "w2", "w3", "w4"))

# ---- 3. 驚きの1行の再試行 ----
base = {"id": "f1", "title": "貨物の搬送車両で自動運転「レベル4」福岡空港", "genre": "life_tech", "status": "available",
        "interest_version": k.INTEREST_VERSION, "surprise_line": "", "verifiability": 5, "life_relevance": 4, "work_relevance": 4,
        "published": k._today(), "primary_sources": [], "summary": "s"}
c_empty = copy.deepcopy(base)
c_ok = dict(copy.deepcopy(base), id="f2", surprise_line="空港の貨物担当が、無人車が荷物を運ぶことに驚く")
c_old = dict(copy.deepcopy(base), id="f3", interest_version="old")
c_max = dict(copy.deepcopy(base), id="f4", surprise_retry=[{"ok": False}, {"ok": False}])
c_gate = dict(copy.deepcopy(base), id="f5", verifiability=2)
tg = k.surprise_retry_targets([c_empty, c_ok, c_old, c_max, c_gate])
check("再試行の対象: 入口通過・版が新しい・1行が空・上限未満だけ", [c["id"] for c in tg] == ["f1"])


class Resp:
    def __init__(self, t): self.text = t


class Models:
    def __init__(self, texts): self.texts = list(texts)
    def generate_content(self, **kw): return Resp(self.texts.pop(0))


class Client:
    def __init__(self, texts): self.models = Models(texts)


orig = k._gemini
orig_sleep = k.time.sleep
k.time.sleep = lambda s: None
try:
    c1 = copy.deepcopy(c_empty)
    k._gemini = lambda: (Client(['{"surprise_line": "空港の貨物担当が、無人車が夜通し荷物を運ぶことに驚く", "reason": ""}']), None)
    n, got = k.retry_surprise([c1])
    check("再試行で付けば surprise_line が入り、surprise_ok になる", got == 1 and k.surprise_ok(c1) and c1["surprise_retry"][0]["ok"])
    c2 = copy.deepcopy(c_empty)
    k._gemini = lambda: (Client(['{"surprise_line": "", "reason": "一次資料に驚く点の記載なし"}']), None)
    n, got = k.retry_surprise([c2])
    check("それでも空なら理由を記録し、surprise_ok は偽のまま（基準は緩めない）",
          got == 0 and not k.surprise_ok(c2) and c2["surprise_hold_reason"] == "一次資料に驚く点の記載なし")
    k._gemini = lambda: (Client(['{"surprise_line": "", "reason": "x"}']), None)
    k.retry_surprise([c2])
    check("通算2回で打ち止め（3回目は対象外）", k.surprise_retry_targets([c2]) == [])
finally:
    k._gemini = orig
    k.time.sleep = orig_sleep


def row(c, lane="本命", interest=10):
    return {"c": c, "fresh": 3, "gate": [], "lane": lane, "core": 30, "core_est": 30, "tb": 0, "interest": interest, "old": 0, "series": c["id"]}


c_hold = dict(copy.deepcopy(base), id="h1", audience_fit=4, promise=4, surprise_hold_reason="理由", primary_verified=True,
              buzz_measured=5, announcement_type="policy")
rows = [row(c_hold)]
picks, _ = k.best3(copy.deepcopy(rows))
check("驚きが空の候補はベスト3に入らない（基準は不変）", picks == [])
check("保留の一覧には出る", [r["c"]["id"] for r in k.held_for_surprise(rows)] == ["h1"])
c_hold_ok = dict(c_hold, surprise_line="誰かが何かに驚く")
check("1行が付けばベスト3に入る", len(k.best3([row(c_hold_ok)])[0]) == 1)

# ---- 追跡記録 ----
rows2 = [row(dict(c_hold, title="貨物の搬送車両で自動運転レベル4の運行を開始", surprise_line="", id="s1"))]
funnel = k.series_funnel(rows2, [], [pool_item("p9", "Waymoが運行エリアを拡大", genre_hint="life_tech")], rows2[0:0] + [rows2[0]["c"]])
st = {e["id"]: e for e in funnel}
check("追跡: 採点済みで保留の候補は stage3・理由つき", st.get("s1", {}).get("stage") == 3 and "保留" in st["s1"]["stopped"])
check("追跡: 未採点のプール記事は stage1", st.get("p9", {}).get("stage") == 1 and "未採点" in st["p9"]["stopped"])
print(k.funnel_note(funnel))

# ---- 実例（現在のデータ） ----
if "--live" in sys.argv:
    print("\n=== 実例（現在のデータ。鮮度で当時と変わる部分あり）===")
    items = k.load_candidates()["items"]
    k.refresh_topic_ages(items)
    fk = next((c for c in items if c["id"].startswith("c86a513ce7")), None)
    if fk:
        used = k.used_source_urls(items)
        print(f"福岡空港: status={fk.get('status')} gate={k.gate_reasons(fk, used)} surprise_line={fk.get('surprise_line')!r} "
              f"retry={fk.get('surprise_retry')} series={bool(k.series_candidate_info(fk))}")
        print("  再試行の対象になる:", fk in k.surprise_retry_targets(items))
        c = copy.deepcopy(fk)
        n, got = k.retry_surprise([c])     # 保存しない
        print(f"  再試行の結果（保存しない）: 付いた={got} 行={c.get('surprise_line')!r} 保留理由={c.get('surprise_hold_reason')!r}")
    pool = k._load_pool_items()
    known = {c["id"] for c in items}
    todo = [p for p in pool if p["id"] not in known and not (set(p.get("dup_ids") or []) & known)]
    qa = [p for p in todo if "量子" in p["title"] and "証明" in p["title"]]
    print("Anthropic 量子計算: 未採点のプール記事", [p["title"][:40] for p in qa])
    sel = k.select_for_scoring(todo, items, 15, verbose=False)
    print("  今日の採点15件に入る:", any(p in sel for p in qa), "／優先枠:", [(si["name"], p["title"][:30]) for si, p in k.pick_series_priority(todo)])
raise SystemExit(0 if ok else 1)
