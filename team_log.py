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
  python3 team_log.py action add --agent sc-writer --text "やること" --metric "狙う指標" --judge "判定の方法と時期"
  python3 team_log.py action list [--agent sc-writer] [--all]
  python3 team_log.py action close --id SC2611-01 --status effective --evidence "根拠"
  python3 team_log.py applied --agent sc-writer --episode ep120 --ids SC2611-01 [--skipped SC2611-02 --reason "..."]
  python3 team_log.py sync-notebooks   # 実施中の改善アクションを各担当のノートに書き出す
  python3 team_log.py due              # 前月の月次評価が済んでいなければ知らせる（何もなければ何も出さない）
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
ACTIONS = TEAM_DIR / "actions.jsonl"
NOTEBOOKS = TEAM_DIR / "notebooks"
EVALUATIONS = TEAM_DIR / "evaluations"
ACTION_START = "<!-- actions:start（team_log.py sync-notebooks が書く。手で直さない） -->"
ACTION_END = "<!-- actions:end -->"
TEAM_START = "2026-10"  # 担当者制を始めた月。これより前の月の評価は催促しない
ACTION_CLOSED = ("effective", "no_effect", "dropped")
ACTION_STATUS_JA = {"open": "実施中", "effective": "効果あり", "no_effect": "効果なし", "dropped": "取り下げ"}
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
        elif kind == "applied":
            s.setdefault("applied", []).append({"episode": r.get("episode"), "ids": r.get("ids", []),
                                                "skipped": r.get("skipped", []), "reason": r.get("reason", "")})
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
    return {"month": month, "agents": stats, "previous_scores": last_scores, "actions": action_report()}


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
    print("\n## 改善アクションの実施状況（全期間。効果の判定は、適用した回の測定窓がそろってから）")
    report = summary["actions"]
    if not report:
        print("- なし")
    for a in report:
        eps = ", ".join(a["applied_episodes"]) or "まだ無し"
        print(f"- {a['id']}（{ACTION_STATUS_JA.get(a['status'], a['status'])}）{label(a['agent'], roster)}: {a['text']}")
        print(f"  狙う指標: {a['metric']} ／ 判定: {a['judge']}")
        print(f"  適用した回: {eps} ／ 機会 {a['opportunities']} 回中 {len(a['applied_episodes'])} 回適用"
              + (f" ／ 見送り: {'、'.join(a['skipped'])}" if a["skipped"] else ""))
        if a.get("evidence"):
            print(f"  判定の根拠: {a['evidence']}")
    gaps = [label(n, roster) for n, s in summary["agents"].items() if s["calls_auto"] > s["records"]]
    if gaps:
        print("\n注意: 自動の呼び出し数より手動の記録が少ない担当があります（記録漏れの可能性）: " + ", ".join(gaps))


def action_report() -> list:
    """改善アクションごとに、適用した回・見送った回・機会（作成後にその担当が作業した回）を数える。"""
    work = read_jsonl(WORK_LOG)
    out = []
    for a in read_jsonl(ACTIONS):
        since = a.get("created", "")
        applied, skipped, chances = [], [], set()
        for r in work:
            if r.get("agent") != a["agent"] or str(r.get("ts", "")) < since:
                continue
            if r.get("kind") == "work" and r.get("episode"):
                chances.add(r["episode"])
            elif r.get("kind") == "applied":
                if a["id"] in r.get("ids", []):
                    applied.append(r.get("episode", ""))
                if a["id"] in r.get("skipped", []):
                    skipped.append(f"{r.get('episode', '')}（{r.get('reason', '')}）")
        out.append({**a, "applied_episodes": sorted(set(applied)), "skipped": skipped,
                    "opportunities": len(chances | set(applied))})
    return out


def next_action_id(agent_id: str, month: str) -> str:
    prefix = agent_id.split("-")[0].upper() + month[2:4] + month[5:7]
    n = sum(1 for a in read_jsonl(ACTIONS) if a.get("id", "").startswith(prefix + "-")) + 1
    return f"{prefix}-{n:02d}"


def cmd_action(args) -> None:
    roster = load_roster()
    rows = read_jsonl(ACTIONS)
    if args.action_cmd == "add":
        agent = resolve_agent(args.agent, roster)
        month = args.month or datetime.now(JST).strftime("%Y-%m")
        open_count = sum(1 for a in rows if a["agent"] == agent and a.get("status") == "open")
        if open_count >= 2 and not args.force:
            print(f"エラー: {label(agent, roster)} の実施中の改善アクションがすでに {open_count} 件あります。"
                  "効果を見分けるため、1人2件までにする（先に close するか、--force）。", file=sys.stderr)
            sys.exit(1)
        row = {"id": next_action_id(agent, month), "agent": agent, "month": month, "text": args.text,
               "metric": args.metric, "judge": args.judge, "status": "open", "created": now_jst()}
        append_jsonl(ACTIONS, row)
        print(f"改善アクションを登録しました: {row['id']} {label(agent, roster)}")
    elif args.action_cmd == "close":
        hit = [a for a in rows if a.get("id") == args.id]
        if not hit:
            print(f"エラー: 改善アクション {args.id} がありません", file=sys.stderr)
            sys.exit(1)
        for a in hit:
            a.update({"status": args.status, "evidence": args.evidence, "closed": now_jst()})
        ACTIONS.write_text("".join(json.dumps(a, ensure_ascii=False) + "\n" for a in rows), encoding="utf-8")
        print(f"改善アクション {args.id} を「{ACTION_STATUS_JA[args.status]}」で閉じました")
    else:
        agent = resolve_agent(args.agent, roster) if args.agent else None
        for a in action_report():
            if (agent and a["agent"] != agent) or (not args.all and a["status"] != "open"):
                continue
            print(f"- {a['id']}（{ACTION_STATUS_JA.get(a['status'], a['status'])}）{label(a['agent'], roster)}: {a['text']}"
                  f" ／ 適用 {len(a['applied_episodes'])}/{a['opportunities']}")


def cmd_applied(args) -> None:
    roster = load_roster()
    agent = resolve_agent(args.agent, roster)
    known = {a["id"] for a in read_jsonl(ACTIONS)}
    ids = [x for x in args.ids.split(",") if x] if args.ids else []
    skipped = [x for x in args.skipped.split(",") if x] if args.skipped else []
    unknown = [x for x in ids + skipped if x not in known]
    if unknown:
        print(f"エラー: 登録されていない改善アクション: {', '.join(unknown)}（`action list` で確認）", file=sys.stderr)
        sys.exit(1)
    append_jsonl(WORK_LOG, {"ts": now_jst(), "kind": "applied", "agent": agent, "episode": args.episode,
                            "ids": ids, "skipped": skipped, "reason": args.reason})
    print(f"記録しました: {label(agent, roster)} {args.episode} 適用 {'、'.join(ids) or 'なし'} 見送り {'、'.join(skipped) or 'なし'}")


def cmd_sync_notebooks(_args) -> None:
    roster = load_roster()
    report = action_report()
    for agent in roster:
        path = NOTEBOOKS / f"{agent}.md"
        if not path.exists():
            continue
        mine = [a for a in report if a["agent"] == agent and a["status"] == "open"]
        lines = ["## 改善アクション（実施中。作業で必ず使い、報告で適用したIDを書く）", "", ACTION_START]
        if not mine:
            lines.append("（いまはありません）")
        for a in mine:
            lines.append(f"- **{a['id']}**: {a['text']}")
            lines.append(f"  - 狙う指標: {a['metric']} ／ 判定: {a['judge']} ／ これまでの適用: {len(a['applied_episodes'])} 回")
        lines.append(ACTION_END)
        block = "\n".join(lines)
        text = path.read_text(encoding="utf-8")
        if ACTION_START in text and ACTION_END in text:
            head = text[:text.index(ACTION_START)]
            head = head[:head.rfind("## 改善アクション")] if "## 改善アクション" in head else head
            text = head.rstrip("\n") + "\n\n" + block + text[text.index(ACTION_END) + len(ACTION_END):]
        else:
            anchor = "## 管理担当からのフィードバック"
            i = text.find(anchor)
            text = (text[:i] + block + "\n\n" + text[i:]) if i >= 0 else (text.rstrip("\n") + "\n\n" + block + "\n")
        path.write_text(text, encoding="utf-8")
    print("ノートの改善アクションを更新しました")


def cmd_due(_args) -> None:
    """前月の月次評価が無ければ一言だけ知らせる（制作コマンドの STEP 0 で呼ぶ）。"""
    first = datetime.now(JST).replace(day=1)
    prev = (first - timedelta(days=1)).strftime("%Y-%m")
    if prev >= TEAM_START and not (EVALUATIONS / f"{prev}.md").exists():
        print(f"お知らせ: {prev} の月次評価（アナリティクス → 担当の評価 → フィードバック）がまだです。"
              "制作の後でよいので、月次のアナリティクスのコマンドを実行してください。")


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

    ac = sub.add_parser("action", help="改善アクション（管理担当が出し、担当が実行し、効果を判定する）")
    acs = ac.add_subparsers(dest="action_cmd", required=True)
    aa = acs.add_parser("add")
    aa.add_argument("--agent", required=True)
    aa.add_argument("--text", required=True, help="次の作業でそのまま実行できる、具体的なやること")
    aa.add_argument("--metric", required=True, help="狙う指標（例: 非登録者の維持率）")
    aa.add_argument("--judge", required=True, help="判定の方法と時期（例: 適用した3回の14日窓を、同月の他の回と比べる。12月の評価で）")
    aa.add_argument("--month", help="出した月 YYYY-MM（省略時は今月）")
    aa.add_argument("--force", action="store_true")
    acl = acs.add_parser("close")
    acl.add_argument("--id", required=True)
    acl.add_argument("--status", required=True, choices=ACTION_CLOSED)
    acl.add_argument("--evidence", required=True)
    al = acs.add_parser("list")
    al.add_argument("--agent")
    al.add_argument("--all", action="store_true")
    ac.set_defaults(func=cmd_action)

    ap = sub.add_parser("applied", help="担当が作業で改善アクションを適用した・見送ったことを記録する")
    ap.add_argument("--agent", required=True)
    ap.add_argument("--episode", required=True)
    ap.add_argument("--ids", default="", help="適用したID（カンマ区切り）")
    ap.add_argument("--skipped", default="", help="見送ったID（カンマ区切り）")
    ap.add_argument("--reason", default="", help="見送った理由")
    ap.set_defaults(func=cmd_applied)

    sn = sub.add_parser("sync-notebooks", help="実施中の改善アクションをノートに書き出す")
    sn.set_defaults(func=cmd_sync_notebooks)

    du = sub.add_parser("due", help="前月の月次評価が済んでいなければ知らせる")
    du.set_defaults(func=cmd_due)

    h = sub.add_parser("hook", help="SubagentStop フック用")
    h.set_defaults(func=cmd_hook)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
