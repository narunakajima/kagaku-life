"""先行事例チェックの対象絞り込み（指示2026-11-13-005）の動作確認。API は呼ばない（backfill_prior_art を差し替える）。
実データ（news_candidates.json）は読むだけで、保存もしない。"""
import kl_news_scan as k

d = k.load_candidates()
items = d["items"]
for c in items:
    c.pop("_t", None)
saved = []
k._save_candidates = lambda cands: saved.append(1)      # 保存しない
called = []


def fake_backfill(cands, force=False, only_ids=None):
    for c in cands:
        if c["id"] in (only_ids or []):
            called.append(c["id"])
            c["prior_art"] = {"version": k.PRIOR_ART_VERSION, "status": "not_realized", "evidence": [], "reason": "test",
                              "novelty_exception": False, "novelty_line": "", "novelty_line_primary": False}
    return len(only_ids or []), len(only_ids or [])


k.backfill_prior_art = fake_backfill
all_targets = {c["id"] for c in k.prior_art_targets(items)}
pres0 = {c["id"] for c in k.presented_candidates(k.classify(items))}
n = k.ensure_prior_art_presented(d)
pres1 = {c["id"] for c in k.presented_candidates(k.classify(items))}
left = {c["id"] for c in k.prior_art_targets(items)}
print(f"ゲート通過の未判定 {len(all_targets)}件 / 提示対象(開始時) {len(pres0)}件 / チェックした {n}件 / 提示対象(終了時) {len(pres1)}件")
assert len(called) == len(set(called)), "同じ候補を2回チェックした"
assert not (pres1 & left), "提示対象に未判定が残っている"
assert n <= len(all_targets)
assert n == 0 or saved, "保存されていない"
print("OK: 提示対象はすべてチェック済み。対象外の未判定", len(left), "件")
