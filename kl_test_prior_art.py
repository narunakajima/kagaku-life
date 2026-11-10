#!/usr/bin/env python3
"""先行事例チェック・本命の絶対基準（handoff 2026-11-11-001）の試験。ファイルは書かない（news_candidates.json は読むだけ）。
  python3 kl_test_prior_art.py          # 単体の試験＋ 11/11 の候補プールでの再計算（1Password 候補の扱い）
"""
import copy

import kl_news_scan as k

ok = True


def check(name, cond):
    global ok
    print(("OK  " if cond else "NG  ") + name)
    ok = ok and cond


PA = k.PRIOR_ART_VERSION


def pa(status="realized", exc=False, line="", confirmed="", ev=None):
    return {"version": PA, "status": status, "evidence": ev if ev is not None else [{"service": "Muse", "feature": "Secure Vault"}],
            "reason": "r", "novelty_exception": exc, "novelty_line": line, "novelty_line_primary": bool(confirmed),
            "novelty_confirmed_by": confirmed}


def row(i, genre, interest, wonder, lane="本命", prior=None, **kw):
    c = {"id": i, "genre": genre, "title": i, "summary": "", "series_fit": 3, "audience_fit": 4, "promise": 4, "tangible": 3,
         "primary_verified": True, "status": "available", "buzz_measured": 3, "surprise_line": "s", "wonder": wonder,
         "interest_version": k.INTEREST_VERSION}
    if prior:
        c["prior_art"] = prior
    c.update(kw)
    return {"c": c, "fresh": 3, "gate": [], "lane": lane, "core": 30, "core_est": 30, "tb": 0, "interest": k.interest(c),
            "old": 0, "series": i}


# --- 状態の判定 ---
check("未判定 → unchecked・通す", k.prior_art_state({"wonder": 4}) == "unchecked" and k.prior_art_ok({"wonder": 4}))
check("古い版 → unchecked", k.prior_art_state({"prior_art": dict(pa(), version="old")}) == "unchecked")
check("not_realized → clear・通す", k.prior_art_state({"prior_art": pa("not_realized")}) == "clear")
check("realized（例外なし）→ excluded・入れない", k.prior_art_state({"prior_art": pa()}) == "realized_excluded"
      and not k.prior_art_ok({"prior_art": pa()}))
held = {"prior_art": pa(exc=True, line="大手が足並み"), "primary_verified": True}
check("例外を主張しても確認者がいなければ held・入れない", k.prior_art_state(held) == "realized_held" and not k.prior_art_ok(held))
conf = {"prior_art": pa(exc=True, line="大手5社が同じ規格に合意", confirmed="kl-planner"), "primary_verified": True}
check("確認者あり＋一次資料の実在確認済み → exception・通す", k.prior_art_state(conf) == "realized_exception" and k.prior_art_ok(conf))
conf2 = dict(conf, primary_verified=None)
check("一次資料が要確認なら例外は認めない", k.prior_art_state(conf2) == "realized_held")
check("確認者あり・1行が空 → held", k.prior_art_state({"prior_art": pa(exc=True, line="", confirmed="x"), "primary_verified": True}) == "realized_held")

# --- 驚きの上限 ---
check("実現済みの驚きは上限2", k.wonder_eff({"wonder": 4, "prior_art": pa()}) == 2)
check("例外が認められれば上限なし", k.wonder_eff(dict(conf, wonder=4)) == 4)
check("実現済みでなければ上限なし", k.wonder_eff({"wonder": 4, "prior_art": pa("not_realized")}) == 4)
check("面白さに反映（驚き4→2で −2）", k.interest({"wonder": 4, "audience_fit": 4, "tangible": 3, "prior_art": pa()})
      == k.interest({"wonder": 4, "audience_fit": 4, "tangible": 3}) - 2)

# --- 運営確認済みの先行事例の照合 ---
one_pw = {"title": "1Password、AIエージェントがログインするためのツールを発表",
          "headline_claim": "AIにパスワードを教えずにログインを任せられる", "actual_content": ""}
check("known: 1Password 候補に一致", (k.known_prior_art(one_pw) or {}).get("id") == "agent_login_without_seeing_password")
check("known: 無関係な候補は一致しない", k.known_prior_art({"title": "AIエージェントが倉庫で働く", "headline_claim": "", "actual_content": ""}) is None)

# --- ベスト3 ---
base = [row("a", "ai", 0, 5, wonder_note=1), row("b", "medical", 0, 4), row("c", "food_health", 0, 3)]
picks, _ = k.best3(copy.deepcopy(base))
check("先行事例なし: 3件・先頭は驚き5", len(picks) == 3 and picks[0]["c"]["id"] == "a" and not any(p.get("weak_day") for p in picks))

rows1 = copy.deepcopy(base)
rows1[0] = row("a", "ai", 0, 5, prior=pa())          # 驚き5 → 上限2、実現済みなので入らない
picks, _ = k.best3(rows1)
check("実現済みの候補はベスト3に入らない", "a" not in [p["c"]["id"] for p in picks])
check("1位は驚き4以上の候補（b）", picks[0]["c"]["id"] == "b")

rows2 = [row("w1", "ai", 0, 3), row("w2", "medical", 0, 3), row("w3", "food_health", 0, 2)]
picks, _ = k.best3(rows2)
check("驚き3以下だけの日: 順位なしの参考＋『本命なし・弱い日』", len(picks) == 3 and all(p.get("weak_day") for p in picks)
      and k.WEAK_DAY_LABEL in k.weak_day_note(picks))
print("   表示例:", k.weak_day_note(picks))
print("   各カード:", [ln for ln in k._slot_lines(picks[0]) if "弱い日" in ln])

# 弱い候補が3件中の先頭にいても、強い候補が競合で漏れていれば入れ替えて1位にする
rows3 = [row("s1", "ai", 0, 3), row("s2", "medical", 0, 3), row("s3", "food_health", 0, 3), row("x", "humanoid", 0, 5)]
rows3[3]["interest"] = 5 + 4 + 3 - 6      # 並びでは弱い（面白さが低い）が驚き5
picks, _ = k.best3(rows3)
check("強い候補が漏れていたら入れ替えて1位に", picks[0]["c"]["id"] == "x" and len(picks) == 3)

picks, _ = k.best3([row("h", "ai", 0, 5, prior=pa(exc=True, line="x"))])
check("例外が未確認の候補だけの日: ベスト3なし（保留）", picks == [])
check("保留として拾える", [r["c"]["id"] for r in k.prior_art_rows([row("h", "ai", 0, 5, prior=pa(exc=True, line="x"))], ("realized_held",))] == ["h"])

# --- 狭い想定視聴者 ---
check("狭い: 会社の経営者が驚く", k.narrow_audience({"surprise_line": "会社の経営者が、AIがパスワードを見ずにログインすることに驚く"}))
check("狭くない: 60代の視聴者", not k.narrow_audience({"surprise_line": "ネットを使う人が、AIに暗証を渡さず任せられることに驚く"}))

# --- 11/11 の候補プールで再計算（読み取りのみ）---
print("\n===== 11/11 の候補プールでの再計算（1Password 候補） =====")
items = k.load_candidates()["items"]
target = [c for c in items if "1Password、AIエージェントがログインするためのツールを発表" in c.get("title", "") and c.get("status") == "available"]
if not target:
    print("（候補が available でない/見つからない: 現在の状態では再計算の対象外）")
else:
    c0 = target[0]
    print("prior_art:", c0.get("prior_art"))
    for label, mutate in (("変更前の扱い（prior_art なし）", lambda c: c.pop("prior_art", None)), ("変更後の扱い（prior_art あり）", lambda c: None)):
        its = copy.deepcopy(items)
        c = next(x for x in its if x["id"] == c0["id"])
        mutate(c)
        rows = k.classify(its)
        r = next((r for r in rows if r["c"]["id"] == c0["id"]), None)
        picks, _ = k.best3(rows)
        print(f"-- {label}: 面白さ {r['interest']}＝驚き{k.wonder_eff(r['c'])}（素の驚き {r['c'].get('wonder')}）＋視聴者{k.fit(r['c'])}＋見せる{k._neutral3(r['c'], 'tangible')}"
              f"／lane={r['lane']}／状態={k.prior_art_state(r['c'])}／ベスト3に入る={c0['id'] in [p['c']['id'] for p in picks]}")
        print("   ベスト3:", [(p["c"]["title"][:28], p["c"].get("wonder"), "weak" if p.get("weak_day") else "") for p in picks])
        print("   weak_day_note:", k.weak_day_note(picks) or "（なし）")
raise SystemExit(0 if ok else 1)
