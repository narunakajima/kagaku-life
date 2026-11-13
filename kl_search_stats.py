"""検索つきGemini呼び出しの記録と、JSON読み取り失敗時の整形し直し（2026-11-13 指示004、削減プラン項目C）。

JSON の読み取りに失敗しても、検索つきで呼び直さない（検索が成功した後で、形式の失敗のためにもう1回分課金されるのを避ける）。
1回目の応答テキストを、検索なしの呼び出しで JSON に整形し直す。整形し直しても読めなければ、呼び出し側が従来どおり失敗として扱う。

記録: search_usage_log.json（gitで追跡）。形式:
  {"events": [{"at": ISO秒, "kind": "score_item|check_reference|prior_art", "queries": 検索クエリ数,
               "json_failed": bool, "reformat": "none|ok|failed"}, ...],
   "totals": {kind: {"calls": n, "queries": n, "json_failed": n, "reformat_ok": n, "reformat_failed": n}}}
events は新しい 3000 件だけ残す。totals は累計。集計: python3 kl_search_stats.py
"""
import json
from datetime import datetime
from pathlib import Path

LOG = Path(__file__).resolve().parent / "search_usage_log.json"
KEEP_EVENTS = 3000


def count_queries(resp) -> int:
    """応答の grounding_metadata.web_search_queries の数。取れなければ 0。"""
    try:
        n = 0
        for cand in (getattr(resp, "candidates", None) or []):
            gmeta = getattr(cand, "grounding_metadata", None)
            n += len(getattr(gmeta, "web_search_queries", None) or [])
        return n
    except Exception:  # noqa: BLE001
        return 0


def record(kind: str, queries: int, json_failed: bool, reformat: str = "none"):
    """記録の失敗で本処理を止めない。"""
    try:
        log = {"events": [], "totals": {}}
        if LOG.exists():
            try:
                log = json.loads(LOG.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                pass
        log.setdefault("events", []).append({"at": datetime.now().isoformat(timespec="seconds"), "kind": kind,
                                              "queries": queries, "json_failed": json_failed, "reformat": reformat})
        log["events"] = log["events"][-KEEP_EVENTS:]
        t = log.setdefault("totals", {}).setdefault(kind, {"calls": 0, "queries": 0, "json_failed": 0,
                                                            "reformat_ok": 0, "reformat_failed": 0})
        t["calls"] += 1
        t["queries"] += queries
        t["json_failed"] += int(json_failed)
        t["reformat_ok"] += int(reformat == "ok")
        t["reformat_failed"] += int(reformat == "failed")
        LOG.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def parse_with_reformat(client, model: str, resp, parse, kind: str):
    """検索つき応答 resp を parse(text) で読む。失敗したら、その応答テキストを検索なしで JSON に整形し直して読む。
    整形し直しても読めなければ例外を送出する（検索つきの再呼び出しはしない。整形は1回だけ）。"""
    q = count_queries(resp)
    text = getattr(resp, "text", None) or ""
    try:
        out = parse(text)
    except Exception:  # noqa: BLE001
        if not text.strip():          # 元の応答が空なら整形のしようがない（呼び出しも省く）
            record(kind, q, True, "failed")
            raise ValueError("empty response")
        prompt = ("次のテキストは、JSON だけを出力するよう頼んだ応答です。含まれる内容を変えずに、正しい JSON だけに整形して"
                  "出力してください（説明・コードフェンスは不要）。\n\n" + text[:12000])
        try:
            out = parse(client.models.generate_content(model=model, contents=prompt).text)
            if not out:               # {} / [] は成功扱いにしない
                raise ValueError("empty JSON after reformat")
        except Exception:
            record(kind, q, True, "failed")
            raise
        record(kind, q, True, "ok")
        return out
    record(kind, q, False, "none")
    return out


if __name__ == "__main__":
    if not LOG.exists():
        print("記録なし")
    else:
        for k, t in json.loads(LOG.read_text(encoding="utf-8")).get("totals", {}).items():
            c = max(t["calls"], 1)
            print(f"{k}: 呼び出し{t['calls']} / 検索クエリ計{t['queries']}（平均{t['queries']/c:.2f}）/ "
                  f"JSON失敗{t['json_failed']}（整形で回復{t['reformat_ok']}・失敗{t['reformat_failed']}）")
