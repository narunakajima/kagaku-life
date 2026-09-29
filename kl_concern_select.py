"""
kl_concern_select.py — くらしを変える科学 STAGE0 次に扱う関心ごとを提案する

2026-09-29追加（ネタ選定パイプライン作り直し、PIPELINE_REDESIGN.md §6）。
viewer_concerns.json の関心ごとと、topics_queue.json の直近のエピソードから、
選定ルールを満たす関心ごとを当事者の広さ・前回からの間隔の順に提案する。

選定ルール（viewer_concerns.json の rules）:
- 連続する window 話（5話）のうち、健康系（体の不調・病気の予防・毎日の調子）は
  max_health_per_window 話（2話）まで
- ワイルドカード（関心ごとを持たず意外性で選ぶ回）は wildcard_per_window 話（1話）まで。
  直近 window-1 話に1話も無ければ「この回をワイルドカードにできる」と表示する
- 同じ関心ごとは min_gap_same_concern 話（8話）以内に繰り返さない

最後に扱った回は viewer_concerns.json に持たせず、topics_queue.json の concern_id から
毎回計算する（状態の二重管理を避けるため）。旧方式の回（slot_type: legacy）も、
concern_id・domain が付いていれば同じように数える。

使い方:
  python3 kl_concern_select.py          # 次の回の候補を上位3つ提案
  python3 kl_concern_select.py --all    # 全関心ごとの状態を一覧表示
"""

import argparse
import json
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
CONCERNS_PATH = BASE_DIR / "viewer_concerns.json"
QUEUE_PATH = BASE_DIR / "topics_queue.json"
SHORTLIST_PATH = BASE_DIR / "topics_shortlist.json"


def episode_number(eid: str) -> int:
    m = re.fullmatch(r"kl(\d{3})", eid or "")
    return int(m.group(1)) if m else -1


def main():
    parser = argparse.ArgumentParser(description="STAGE0 次に扱う関心ごとを提案する")
    parser.add_argument("--all", action="store_true", help="全関心ごとの状態を一覧表示する")
    parser.add_argument("--top", type=int, default=3, help="提案する件数（デフォルト3）")
    args = parser.parse_args()

    data = json.loads(CONCERNS_PATH.read_text())
    rules = data["rules"]
    domains = data["domains"]
    concerns = [c for c in data["concerns"] if c.get("active", True)]
    concern_by_id = {c["id"]: c for c in data["concerns"]}

    queue = json.loads(QUEUE_PATH.read_text())["queue"]
    queue = sorted((e for e in queue if episode_number(e.get("episode_id")) >= 0),
                   key=lambda e: episode_number(e["episode_id"]))
    next_num = (episode_number(queue[-1]["episode_id"]) + 1) if queue else 1
    next_id = f"kl{next_num:03d}"

    missing = [e["episode_id"] for e in queue if not e.get("domain")]
    if missing:
        print(f"⚠️ domain が未設定のエピソードがあります（健康系の数を正しく数えられません）: {', '.join(missing)}", file=sys.stderr)

    def is_health(e: dict) -> bool:
        return bool(domains.get(e.get("domain") or "", {}).get("is_health"))

    window = rules["window"]
    recent = queue[-(window - 1):] if window > 1 else []
    health_used = sum(1 for e in recent if is_health(e))
    wildcard_used = sum(1 for e in recent if e.get("slot_type") == "wildcard")
    health_left = rules["max_health_per_window"] - health_used
    wildcard_left = rules["wildcard_per_window"] - wildcard_used

    last_covered = {}
    for e in queue:
        cid = e.get("concern_id")
        if cid:
            last_covered[cid] = e["episode_id"]

    inventory = {}
    if SHORTLIST_PATH.exists():
        for e in json.loads(SHORTLIST_PATH.read_text()).get("shortlist", []):
            if e.get("status") == "available":
                inventory[e.get("concern_id")] = inventory.get(e.get("concern_id"), 0) + 1

    recent_desc = " / ".join(
        f"{e['episode_id']}:{concern_by_id.get(e.get('concern_id'), {}).get('label') or '（関心ごとなし）'}"
        f"[{domains.get(e.get('domain') or '', {}).get('label', '?')}"
        f"{'・ワイルドカード' if e.get('slot_type') == 'wildcard' else ''}]"
        for e in recent
    )
    print(f"次の回: {next_id}")
    print(f"直近{len(recent)}話: {recent_desc}")
    print(f"この回で使える枠: 健康系 あと{max(health_left, 0)}話 / ワイルドカード あと{max(wildcard_left, 0)}話"
          f"（連続{window}話のうち健康系{rules['max_health_per_window']}話まで・ワイルドカード{rules['wildcard_per_window']}話まで）")
    if wildcard_left > 0:
        print("  → この回をワイルドカード（旧在庫・制作者の直感から意外性で選ぶ回）にすることもできます")

    def status(c: dict) -> tuple:
        """(選べるか, 理由, 前回からの話数)"""
        last = last_covered.get(c["id"])
        gap = next_num - episode_number(last) if last else None
        if last and gap <= rules["min_gap_same_concern"]:
            return False, f"{last}で扱ったばかり（{rules['min_gap_same_concern']}話空ける）", gap
        if domains[c["domain"]]["is_health"] and health_left <= 0:
            return False, "健康系の枠が埋まっている", gap
        return True, "", gap

    rows = []
    for c in concerns:
        ok, reason, gap = status(c)
        rows.append((c, ok, reason, gap))

    eligible = [r for r in rows if r[1]]
    # 当事者の広さが大きい順、前回から間が空いている順（未扱いを最優先）
    eligible.sort(key=lambda r: (r[0].get("breadth_rank", 0), r[3] if r[3] is not None else 10_000), reverse=True)

    print(f"\n=== 提案（上位{min(args.top, len(eligible))}件、選べる関心ごと全{len(eligible)}件中） ===")
    for c, _, _, gap in eligible[: args.top]:
        last = last_covered.get(c["id"])
        print(f"\n■ {c['label']}（{c['id']}） — {domains[c['domain']]['label']}")
        print(f"  当事者の広さ: {c.get('breadth_rank')}／5 — {(c.get('breadth') or {}).get('summary', '')}")
        print(f"  問いの例: {' / '.join(c.get('questions', []))}")
        print(f"  前回: {last + f'（{gap}話前）' if last else 'まだ扱っていない'} / 新在庫: {inventory.get(c['id'], 0)}件")

    if args.all:
        print("\n=== 全関心ごとの状態 ===")
        for c, ok, reason, gap in rows:
            last = last_covered.get(c["id"]) or "-"
            mark = "○" if ok else "×"
            print(f"  {mark} {c['label'][:18]:<18} {domains[c['domain']]['label']:<6} 広さ{c.get('breadth_rank')} "
                  f"前回{last:<6} 在庫{inventory.get(c['id'], 0):>3}件 {reason}")


if __name__ == "__main__":
    main()
