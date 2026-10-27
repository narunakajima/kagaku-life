#!/usr/bin/env python3
"""担当者制（チーム）の作業記録・月次集計・評価の記録。

samurai-chronicles / kagaku-life / lamp-whisper の3リポジトリで同じファイルを使う（中身をそろえること）。
名簿の正本は .claude/agents/*.md の frontmatter（name・model・description）。
運用ルールは team/TEAM.md。

使い方:
  python3 team_log.py add --agent sc-writer --episode ep120 --step 2A --result ok [--retries 0] [--note "..."]
  python3 team_log.py feedback --agent sc-art-director --episode ep120 --source user --severity major --text "指摘の原文"
  python3 team_log.py summary --month 2026-11 [--json]
  python3 team_log.py score --month 2026-11 --agent sc-writer --outcome 3 --quality 4 --improvement 3 --overall B --summary "..."
  python3 team_log.py scores [--agent sc-writer]
  python3 team_log.py roster
  python3 team_log.py hook        # SubagentStop フック用（標準入力の JSON を読む。失敗しても何も出さず終了コード0）
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AGENTS_DIR = ROOT / ".claude" / "agents"
TEAM_DIR = ROOT / "team"
WORK_LOG = TEAM_DIR / "work_log.jsonl"
SCORECARDS = TEAM_DIR / "scorecards.jsonl"
JST = timezone(timedelta(hours=9))

RESULTS = ("ok", "retry", "fail", "escalated")
SOURCES = ("user", "qa", "viewer", "manager")
SEVERITIES = ("major", "minor")
GRADES = ("S", "A", "B", "C", "D")


def now_jst() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def load_roster() -> dict:
    """.claude/agents/*.md の frontmatter から名簿を作る。"""
    roster = {}
    for path in sorted(AGENTS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---", text, re.S)
        if not m:
            continue
        meta = {}
        for line in m.group(1).splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                meta[key.strip()] = val.strip()
        name = meta.get("name")
        if name:
            parts = [meta.get("team", ""), meta.get("role", ""), meta.get("display_name", "")]
            roster[name] = {"model": meta.get("model", "?"), "display_name": meta.get("display_name", ""),
                            "full_name": " ".join(x for x in parts if x), "description": meta.get("description", "")}
    return roster


def read_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def resolve_agent(name: str, roster: dict) -> str:
    """呼び出し名（sc-writer）・名前（クレア）・呼び方（SCチーム 脚本担当 クレア）のどれでも受け付け、呼び出し名を返す。"""
    if name in roster:
        return name
    for agent_id, info in roster.items():
        if name and name in (info["display_name"], info["full_name"]):
            return agent_id
    require_agent(name, roster)
    return name


def label(agent_id: str, roster: dict) -> str:
    nm = roster.get(agent_id, {}).get("full_name")
    return f"{nm}（{agent_id}）" if nm else agent_id


def require_agent(name: str, roster: dict) -> None:
    if name not in roster:
        print(f"エラー: 担当者 '{name}' は名簿（.claude/agents/）にいません。登録済み: {', '.join(roster) or 'なし'}",
              file=sys.stderr)
        sys.exit(1)


def cmd_add(args) -> None:
    roster = load_roster()
    args.agent = resolve_agent(args.agent, roster)
    append_jsonl(WORK_LOG, {
        "ts": now_jst(), "kind": "work", "agent": args.agent, "episode": args.episode,
        "step": args.step, "result": args.result, "retries": args.retries, "note": args.note,
    })
    print(f"記録しました: {args.agent} {args.episode} {args.step} {args.result}")


def cmd_feedback(args) -> None:
    roster = load_roster()
    args.agent = resolve_agent(args.agent, roster)
    append_jsonl(WORK_LOG, {
        "ts": now_jst(), "kind": "feedback", "agent": args.agent, "episode": args.episode,
        "source": args.source, "severity": args.severity, "text": args.text,
    })
    print(f"記録しました: {args.agent} {args.episode} 指摘（{args.source}/{args.severity}）")


def cmd_hook(_args) -> None:
    """SubagentStop フック。名簿にいる担当者の呼び出しだけを自動で記録する。何があっても止めない。"""
    try:
        data = json.loads(sys.stdin.read() or "{}")
        agent = data.get("agent_type") or data.get("subagent_type") or ""
        if agent and agent in load_roster():
            append_jsonl(WORK_LOG, {"ts": now_jst(), "kind": "call", "agent": agent,
                                    "session": data.get("session_id", "")})
    except Exception:
        pass
    sys.exit(0)


def month_rows(month: str) -> list:
    return [r for r in read_jsonl(WORK_LOG) if str(r.get("ts", "")).startswith(month)]


def build_summary(month: str) -> dict:
    roster = load_roster()
    stats = {name: {"model": info["model"], "display_name": info["display_name"], "calls_auto": 0, "records": 0, "ok": 0, "retry": 0, "fail": 0,
                    "escalated": 0, "retries": 0, "episodes": set(), "feedback_major": 0, "feedback_minor": 0,
                    "feedback": []}
             for name, info in roster.items()}
    for r in month_rows(month):
        s = stats.get(r.get("agent"))
        if s is None:
            continue
        kind = r.get("kind")
        if kind == "call":
            s["calls_auto"] += 1
        elif kind == "work":
            s["records"] += 1
            if r.get("result") in RESULTS:
                s[r["result"]] += 1
            s["retries"] += int(r.get("retries") or 0)
            if r.get("episode"):
                s["episodes"].add(r["episode"])
        elif kind == "feedback":
            s["feedback_" + ("major" if r.get("severity") == "major" else "minor")] += 1
            s["feedback"].append({"episode": r.get("episode"), "source": r.get("source"),
                                  "severity": r.get("severity"), "text": r.get("text")})
            if r.get("episode"):
                s["episodes"].add(r["episode"])
    for s in stats.values():
        s["episodes"] = sorted(s["episodes"])
        s["first_pass_rate"] = round(s["ok"] / s["records"], 2) if s["records"] else None
    prev = [r for r in read_jsonl(SCORECARDS) if r.get("month", "") < month]
    last_scores = {}
    for r in sorted(prev, key=lambda x: x.get("month", "")):
        last_scores[r.get("agent")] = r
    return {"month": month, "agents": stats, "previous_scores": last_scores}


def cmd_summary(args) -> None:
    roster = load_roster()
    summary = build_summary(args.month)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    print(f"# チーム作業の集計 {args.month}\n")
    print("| 担当 | モデル | 呼び出し(自動) | 記録 | 一発OK | 再試行 | 失敗 | 引き継ぎ | 一発OK率 | 指摘(重/軽) | 担当回 |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for name, s in summary["agents"].items():
        rate = "-" if s["first_pass_rate"] is None else f"{s['first_pass_rate']:.0%}"
        eps = ", ".join(s["episodes"]) or "-"
        print(f"| {label(name, roster)} | {s['model']} | {s['calls_auto']} | {s['records']} | {s['ok']} | {s['retry']} | "
              f"{s['fail']} | {s['escalated']} | {rate} | {s['feedback_major']}/{s['feedback_minor']} | {eps} |")
    print("\n## 指摘の原文")
    any_fb = False
    for name, s in summary["agents"].items():
        for fb in s["feedback"]:
            any_fb = True
            print(f"- {label(name, roster)} {fb['episode']}（{fb['source']}/{fb['severity']}）: {fb['text']}")
    if not any_fb:
        print("- なし")
    print("\n## 前回の評価")
    if summary["previous_scores"]:
        for name, r in summary["previous_scores"].items():
            print(f"- {label(name, roster)}（{r.get('month')}）: 総合 {r.get('overall')} — {r.get('summary', '')}")
    else:
        print("- なし（初回）")
    gaps = [label(n, roster) for n, s in summary["agents"].items() if s["calls_auto"] > s["records"]]
    if gaps:
        print("\n注意: 自動の呼び出し数より手動の記録が少ない担当があります（記録漏れの可能性）: " + ", ".join(gaps))


def cmd_score(args) -> None:
    roster = load_roster()
    args.agent = resolve_agent(args.agent, roster)
    if not re.fullmatch(r"\d{4}-\d{2}", args.month):
        print("エラー: --month は YYYY-MM", file=sys.stderr)
        sys.exit(1)
    rows = [r for r in read_jsonl(SCORECARDS) if not (r.get("month") == args.month and r.get("agent") == args.agent)]
    rows.append({"month": args.month, "agent": args.agent, "outcome": args.outcome, "quality": args.quality,
                 "improvement": args.improvement, "overall": args.overall, "summary": args.summary,
                 "recorded_at": now_jst()})
    SCORECARDS.parent.mkdir(parents=True, exist_ok=True)
    SCORECARDS.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(f"評価を記録しました: {args.month} {args.agent} 総合 {args.overall}")


def cmd_scores(args) -> None:
    roster = load_roster()
    rows = sorted(read_jsonl(SCORECARDS), key=lambda r: (r.get("agent", ""), r.get("month", "")))
    if args.agent:
        agent = resolve_agent(args.agent, roster)
        rows = [r for r in rows if r.get("agent") == agent]
    if not rows:
        print("評価の記録はまだありません。")
        return
    print("| 月 | 担当 | 成果 | 品質 | 改善 | 総合 | 要約 |")
    print("|---|---|---|---|---|---|---|")
    def show(v):
        return "-" if v is None else v

    for r in rows:
        print(f"| {r.get('month')} | {label(r.get('agent'), roster)} | {show(r.get('outcome'))} | {show(r.get('quality'))} | "
              f"{show(r.get('improvement'))} | {r.get('overall')} | {r.get('summary', '')} |")


def cmd_roster(_args) -> None:
    roster = load_roster()
    if not roster:
        print("名簿が空です（.claude/agents/*.md がありません）。")
        return
    for name, info in roster.items():
        desc = info["description"].removeprefix(info["full_name"] + "。")
        print(f"- {label(name, roster)}・{info['model']}: {desc}")


def score_value(text: str):
    if text in ("-", "na"):
        return None
    v = int(text)
    if not 1 <= v <= 5:
        raise argparse.ArgumentTypeError("1〜5、または判定不能なら -")
    return v


def main() -> None:
    p = argparse.ArgumentParser(description="担当者制（チーム）の作業記録・集計")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="担当者の作業結果を記録する")
    a.add_argument("--agent", required=True)
    a.add_argument("--episode", required=True)
    a.add_argument("--step", required=True)
    a.add_argument("--result", required=True, choices=RESULTS)
    a.add_argument("--retries", type=int, default=0)
    a.add_argument("--note", default="")
    a.set_defaults(func=cmd_add)

    f = sub.add_parser("feedback", help="担当者の成果物への指摘を記録する")
    f.add_argument("--agent", required=True)
    f.add_argument("--episode", required=True)
    f.add_argument("--source", required=True, choices=SOURCES)
    f.add_argument("--severity", required=True, choices=SEVERITIES)
    f.add_argument("--text", required=True)
    f.set_defaults(func=cmd_feedback)

    s = sub.add_parser("summary", help="月ごとの集計")
    s.add_argument("--month", default=datetime.now(JST).strftime("%Y-%m"))
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_summary)

    sc = sub.add_parser("score", help="管理担当の月次評価を記録する")
    sc.add_argument("--month", required=True)
    sc.add_argument("--agent", required=True)
    sc.add_argument("--outcome", required=True, type=score_value)
    sc.add_argument("--quality", required=True, type=score_value)
    sc.add_argument("--improvement", required=True, type=score_value)
    sc.add_argument("--overall", required=True, choices=GRADES)
    sc.add_argument("--summary", required=True)
    sc.set_defaults(func=cmd_score)

    ss = sub.add_parser("scores", help="評価の履歴")
    ss.add_argument("--agent")
    ss.set_defaults(func=cmd_scores)

    r = sub.add_parser("roster", help="名簿")
    r.set_defaults(func=cmd_roster)

    h = sub.add_parser("hook", help="SubagentStop フック用")
    h.set_defaults(func=cmd_hook)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
