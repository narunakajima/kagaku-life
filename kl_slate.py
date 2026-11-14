#!/usr/bin/env python3
"""週次スレート（制作3本＋次点2本）の記録と表示（2026-11-15、指示 2026-11-15-004）。

週次下書き（月曜、`kl_news_scan.py slack --weekly`）から、ユーザーが選んだ「制作3本＋次点2本」を weekly_slate.json に残す。
次点は差し替え用: 選択後のURL再確認で落ちた・制作日までに鮮度期限（21日）を過ぎた・制作に入って素材不足と分かった、のときに入れ替える。
URL再確認は選択後にこの5件だけ行う（kl-new ケースCの手順4。ここでは行わない）。

使い方:
  python3 kl_slate.py add --main ID ID ID --backup ID ID [--week YYYY-MM-DD]   # スレートを記録（同じ週は上書き）。本命が3本に満たない週は少なくてよい
  python3 kl_slate.py show [--json]       # 未制作分を鮮度期限の近い順に表示（kl-new STEP 1 の入口）。尽きていれば終了コード2
  python3 kl_slate.py swap --out ID --reason 理由 [--in ID]   # 本命を外し、次点（--in 省略時は先頭の次点）を本命に繰り上げる
  python3 kl_slate.py drop --id ID --reason 理由               # 次点などを外す（繰り上げなし）

制作済みかどうかは news_candidates.json の status（used / rejected）で判定する（kl-new が制作時に付ける）。
スレートが無い・尽きた場合の kl-new は、従来のケースC（その場で収集）にフォールバックする。
戻し方: スレートを使わないなら weekly_slate.json を空（{"slates": []}）にするか、このツールを呼ばない。
"""
import argparse
import json
import sys
from datetime import date, datetime, timedelta

import kl_news_scan as ns

MAIN_N, BACKUP_N = 3, 2


def _load() -> dict:
    if ns.SLATE_JSON.exists():
        return json.loads(ns.SLATE_JSON.read_text(encoding="utf-8"))
    return {"_comment": "週次スレート（kl_slate.py が書く）。entries[].role: main（制作）/ backup（次点）/ dropped（外した）", "slates": []}


def _save(d: dict):
    ns.SLATE_JSON.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _deadline(c: dict) -> str:
    """鮮度期限の日付（話題の初出＋21日。ゲートの freshness_score 3 以上と同じ）。"""
    try:
        base = datetime.fromisoformat(ns.fresh_date(c)[:10]).date()
        return (base + timedelta(days=ns.FRESH_DEADLINE_DAYS)).isoformat()
    except Exception:  # noqa: BLE001
        return ""


def _by_id(items: list) -> dict:
    return {c["id"]: c for c in items}


def _entry(c: dict, role: str) -> dict:
    return {"id": c["id"], "title": c.get("title", ""), "role": role, "genre": c.get("genre"),
            "series": bool(ns.series_candidate_info(c)), "freshness_deadline": _deadline(c),
            "selected_on": date.today().isoformat()}


def cmd_add(main_ids, backup_ids, week):
    items = ns.load_candidates()["items"]
    idx = _by_id(items)
    ids = list(main_ids) + list(backup_ids)
    missing = [i for i in ids if i not in idx]
    if missing:
        sys.exit(f"候補が見つかりません: {missing}")
    if len(set(ids)) != len(ids):
        sys.exit("同じ候補が重複しています")
    if len(main_ids) > MAIN_N or len(backup_ids) > BACKUP_N:
        sys.exit(f"制作は最大{MAIN_N}本、次点は最大{BACKUP_N}本です")
    n_series = sum(1 for i in main_ids if ns.series_candidate_info(idx[i]))
    if n_series > 1:      # 指示004 項目8: シリーズ優先枠は「週の3本中1本まで」
        sys.exit(f"シリーズ候補（定点観測）が制作{n_series}本です。週の3本中1本までにしてください")
    week = week or _monday(date.today()).isoformat()
    d = _load()
    entries = [_entry(idx[i], "main") for i in main_ids] + [_entry(idx[i], "backup") for i in backup_ids]
    d["slates"] = [s for s in d["slates"] if s.get("week_of") != week] + [
        {"week_of": week, "recorded_on": date.today().isoformat(), "entries": entries, "swaps": []}]
    d["slates"].sort(key=lambda s: s["week_of"])
    _save(d)
    print(f"週次スレート（{week}）を記録: 制作{len(main_ids)}本＋次点{len(backup_ids)}本")
    if len(main_ids) < MAIN_N:
        print(f"  ※ 制作が{len(main_ids)}本（{MAIN_N}本に満たない弱い週。無理に埋めない）")
    for e in entries:
        print(f"  [{e['role']}] {e['id']} 鮮度期限 {e['freshness_deadline']} {e['title'][:50]}")


def _remaining(deadline: str) -> int:
    try:
        return (datetime.fromisoformat(deadline).date() - date.today()).days
    except Exception:  # noqa: BLE001
        return 999


def cmd_show(as_json):
    d = _load()
    if not d["slates"]:
        print("スレートなし（ケースCのその場収集にフォールバック）")
        sys.exit(2)
    s = d["slates"][-1]
    items = ns.load_candidates()["items"]
    idx = _by_id(items)
    rows = []
    for e in s["entries"]:
        c = idx.get(e["id"])
        status = (c or {}).get("status", "?")
        done = status in ("used", "rejected")
        rem = _remaining(e["freshness_deadline"])
        rows.append(dict(e, status=status, done=done, remaining_days=rem, expired=rem < 0))
    todo_main = sorted([r for r in rows if r["role"] == "main" and not r["done"]], key=lambda r: r["remaining_days"])
    todo_back = sorted([r for r in rows if r["role"] == "backup" and not r["done"]], key=lambda r: r["remaining_days"])
    if as_json:
        print(json.dumps({"week_of": s["week_of"], "main": todo_main, "backup": todo_back}, ensure_ascii=False, indent=2))
    else:
        if s["week_of"] != _monday(date.today()).isoformat():
            print(f"  （注: このスレートは {s['week_of']} 週のもの。今週の分が未記録なら、週次下書きから選び直す。期限が残る未制作分は使える）")
        print(f"週次スレート（{s['week_of']}週）— 未制作の本命 {len(todo_main)}本・次点 {len(todo_back)}本（鮮度期限の近い順）")
        for r in todo_main:
            tag = "【期限切れ→差し替え】" if r["expired"] else ""
            print(f"  本命 {r['id']} あと{r['remaining_days']}日（期限 {r['freshness_deadline']}）{tag} {r['title'][:50]}"
                  + ("  📌シリーズ" if r["series"] else ""))
        for r in todo_back:
            tag = "【期限切れ】" if r["expired"] else ""
            print(f"  次点 {r['id']} あと{r['remaining_days']}日（期限 {r['freshness_deadline']}）{tag} {r['title'][:50]}")
        done = [r for r in rows if r["done"]]
        if done:
            print("  制作済み・却下済み: " + "、".join(f"{r['id']}({r['status']})" for r in done))
        expired = [r for r in todo_main if r["expired"]]
        if expired:
            print(f"  ⚠️ 本命{len(expired)}本が鮮度期限切れ。次点があれば swap で入れ替える")
    live = [r for r in todo_main if not r["expired"]]
    if not live:
        print("本命が尽きています（次点に繰り上げるか、ケースCのその場収集にフォールバック）")
        sys.exit(2)


def cmd_swap(out_id, in_id, reason):
    d = _load()
    if not d["slates"]:
        sys.exit("スレートがありません")
    s = d["slates"][-1]
    ent = {e["id"]: e for e in s["entries"]}
    if out_id not in ent or ent[out_id]["role"] != "main":
        sys.exit(f"{out_id} は本命ではありません")
    if in_id is None:
        backs = sorted([e for e in s["entries"] if e["role"] == "backup" and _remaining(e["freshness_deadline"]) >= 0],
                       key=lambda e: _remaining(e["freshness_deadline"]))
        if not backs:
            sys.exit("繰り上げられる次点がありません（ケースCのその場収集にフォールバック）")
        in_id = backs[0]["id"]
    if in_id not in ent or ent[in_id]["role"] != "backup":
        sys.exit(f"{in_id} は次点ではありません")
    if ent[in_id].get("series") and not ent[out_id].get("series") and sum(
            1 for e in s["entries"] if e["role"] == "main" and e.get("series")) >= 1:
        sys.exit(f"{in_id} はシリーズ候補で、制作に既にシリーズ候補があります（週の3本中1本まで）。別の次点を --in で指定してください")
    ent[out_id]["role"], ent[out_id]["drop_reason"] = "dropped", reason
    ent[in_id]["role"] = "main"
    s["swaps"].append({"date": date.today().isoformat(), "out": out_id, "in": in_id, "reason": reason})
    _save(d)
    print(f"差し替え: {out_id} を外し（{reason}）、次点 {in_id} を本命に繰り上げました")


def cmd_drop(cid, reason):
    d = _load()
    if not d["slates"]:
        sys.exit("スレートがありません")
    for e in d["slates"][-1]["entries"]:
        if e["id"] == cid:
            e["role"], e["drop_reason"] = "dropped", reason
            _save(d)
            print(f"{cid} をスレートから外しました（{reason}）")
            return
    sys.exit(f"{cid} はスレートにありません")


def main():
    ap = argparse.ArgumentParser(description="週次スレート（制作3本＋次点2本）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--main", nargs="*", default=[])
    a.add_argument("--backup", nargs="*", default=[])
    a.add_argument("--week", default=None)
    s = sub.add_parser("show")
    s.add_argument("--json", action="store_true")
    w = sub.add_parser("swap")
    w.add_argument("--out", required=True)
    w.add_argument("--in", dest="in_id", default=None)
    w.add_argument("--reason", required=True)
    r = sub.add_parser("drop")
    r.add_argument("--id", required=True)
    r.add_argument("--reason", required=True)
    args = ap.parse_args()
    if args.cmd == "add":
        cmd_add(args.main, args.backup, args.week)
    elif args.cmd == "show":
        cmd_show(args.json)
    elif args.cmd == "swap":
        cmd_swap(args.out, args.in_id, args.reason)
    else:
        cmd_drop(args.id, args.reason)


if __name__ == "__main__":
    main()
