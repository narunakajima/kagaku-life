#!/usr/bin/env python3
"""一次資料URL確認の見直し（handoff 2026-11-12-007）の試験。ネットワーク・ファイルは使わない。
  python3 kl_test_primary_recheck.py
"""
import kl_news_scan as k

ok = True


def check(name, cond):
    global ok
    print(("OK  " if cond else "NG  ") + name)
    ok = ok and cond


def r404(url, final=""):
    d = {"url": url, "ok": False, "status": "HTTP 404", "http404": 404}
    if final:
        d.update(final_url=final, redirects=[f"302 {final}"])
    return d


k.RECHECK_404_WAIT = 0.0
U = "https://ring.com/products/drone-cam"

# --- alt_locale_urls ---
alts = k.alt_locale_urls(U)
check("alt: /us/en が候補に入る", "https://ring.com/us/en/products/drone-cam" in alts)
check("alt: 元のURLは含まない", U not in alts)
alts2 = k.alt_locale_urls("https://ring.com/jp/ja/products/drone-cam")
check("alt: /jp/ja/ を外した形が先頭", alts2[0] == U)

# --- recheck_404: 全部404 ---
calls = []


def all404(u, h):
    calls.append((u, h.get("Accept-Language")))
    return r404(u)


res = k.recheck_404(U, r404(U, "https://ring.com/jp/ja/products/drone-cam"), [], fetch=all404)
check("全部404 → ok=False のまま", res["ok"] is False)
check("全部404 → 試行が記録される（初回＋再試行＋別地域）", len(res["attempts"]) >= 4 and res["attempts"][0]["final_url"].endswith("/jp/ja/products/drone-cam"))
check("全部404 → 英語のAccept-Languageでも試した", any(a == "en-US,en;q=0.9" for _, a in calls))
check("全部404 → 同じURLを時間をおいて再試行した", sum(1 for u, _ in calls if u == U) >= 2)

# --- recheck_404: 英語ヘッダで開ける ---
res = k.recheck_404(U, r404(U), [], fetch=lambda u, h: {"url": u, "ok": True, "status": "HTTP 200"} if h.get("Accept-Language", "").startswith("en-US") else r404(u))
check("英語ヘッダで開けた → ok=True・URLは元のまま", res["ok"] is True and res["url"] == U and "alt_url" not in res)

# --- recheck_404: 別地域URLだけ開ける ---
res = k.recheck_404(U, r404(U), [], fetch=lambda u, h: {"url": u, "ok": True, "status": "HTTP 200"} if "/us/en/" in u else r404(u))
check("別地域URLで開けた → ok=True・alt_url が付く", res["ok"] is True and res["alt_url"] == "https://ring.com/us/en/products/drone-cam")

# --- verify_candidate: 別地域URLで差し替え ---
real_check = k.check_primary_url
k.check_primary_url = lambda url, timeout=15, anchors=None, headers=None: (
    {"url": url, "ok": True, "status": "HTTP 200「Drone Cam | Ring」", "anchor_hit": True} if "/us/en/" in url else r404(url))


class P:
    def wait(self, u):
        pass


c = {"id": "x", "title": "t", "jp_title_anchor": ["Ring Drone Cam"], "primary_sources": [{"kind": "official_page", "url": U}]}
k.verify_candidate(c, P())
check("verify: 別地域URLで確認済みになり差し替わる", c["primary_verified"] is True and c["primary_sources"][0]["repaired_url"].endswith("/us/en/products/drone-cam")
      and c["primary_sources"][0]["repair_method"] == "locale-alt")
check("verify: primary_check に元のURLと試行が残る", c["primary_check"][0]["orig_url"] == U and len(c["primary_check"][0]["attempts"]) >= 2)
check("verify: 履歴が残る", len(c["primary_history"]) == 1)

# --- verify_candidate: 全部404（初めて）→ False、ゲートで落ちる ---
k.check_primary_url = lambda url, timeout=15, anchors=None, headers=None: r404(url)
c2 = {"id": "y", "title": "t2", "primary_sources": [{"kind": "official_page", "url": U}]}
k.verify_candidate(c2, P())
check("全URL404（初回確認）→ primary_verified=False（原則は維持）", c2["primary_verified"] is False)
check("全URL404 → ゲート理由に一次資料が入る", any(g.startswith("一次資料") for g in k.gate_reasons(c2, {})))

# --- 食い違い: 前回 True → 今回 全404 → None（要確認）＋ conflict、ゲートで落ちない ---
c3 = {"id": "z", "title": "t3", "primary_sources": [{"kind": "official_page", "url": U}], "primary_verified": True,
      "primary_verified_at": "2026-11-12T08:51:30",
      "primary_check": [{"url": U, "ok": True, "status": "HTTP 200「Drone Cam | Ring」"}]}
k.verify_candidate(c3, P())
check("食い違い → primary_verified は None（無言で落とさない）", c3["primary_verified"] is None)
check("食い違い → ゲート理由に一次資料が入らない", not any(g.startswith("一次資料") for g in k.gate_reasons(c3, {})))
cf = c3.get("primary_conflict") or {}
check("食い違い → 両方の結果（時刻・状態）を記録", cf.get("before", {}).get("at") == "2026-11-12T08:51:30"
      and cf["before"]["urls"][0]["status"].startswith("HTTP 200") and cf["after"]["urls"][0]["status"].startswith("HTTP 404"))
check("食い違い → 表示行に前と後が出る", any("前:" in x for x in k.conflict_lines(c3)) and any("後:" in x for x in k.conflict_lines(c3)))
check("食い違い → _primary_line に出る", "食い違い" in k._primary_line(c3))
# もう一度404でも conflict は残り None のまま
k.verify_candidate(c3, P())
check("食い違い → 再確認でも404なら None のまま・conflict 維持", c3["primary_verified"] is None and c3.get("primary_conflict"))
# 開けたら解消
k.check_primary_url = lambda url, timeout=15, anchors=None, headers=None: {"url": url, "ok": True, "status": "HTTP 200", "anchor_hit": True}
k.verify_candidate(c3, P())
check("食い違い → 開ければ True・conflict 解消", c3["primary_verified"] is True and "primary_conflict" not in c3)
k.check_primary_url = real_check

# --- ゲート落ちの理由つき表示 ---
row = {"c": c2, "gate": ["一次資料URLが実在しない（全URLが404）"], "interest": 10}
check("primary_gate_dropped: 一次資料だけが理由の候補を拾う", [r["c"]["id"] for r in k.primary_gate_dropped([dict(row, c=dict(c2, status="available"))])] == ["y"])
check("primary_gate_dropped: 他の理由もある候補は拾わない", not k.primary_gate_dropped([dict(row, c=dict(c2, status="available"), gate=["検証<3", "一次資料URLが実在しない"])]))
check("primary_drop_text に状態と確認時刻", "HTTP 404" in k.primary_drop_text(c2))

print("\nALL OK" if ok else "\nFAILED")
raise SystemExit(0 if ok else 1)
