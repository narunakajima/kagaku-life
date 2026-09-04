"""
kl_paper_hypecheck.py — くらしを変える科学 STAGE3誇張表現検出スクリプト

stage2_screened.json（kl_paper_screen.pyの出力）のうち overall が pass/flag の候補を
Gemini（Google Searchグラウンディング付き）に1件ずつ渡し、アドバーサリアル役（懐疑的
レビュアー）として、論文本文の実際の主張と二次報道・プレスリリースの煽り表現との
ギャップを検証させる（CLAUDE.md STAGE3）。「〜の可能性がある」等のヘッジ表現が
二次情報で断定表現に変わっていないかを確認する。

Opusは使わない。Geminiのみで完結する（STAGE2と同方針）。

使い方:
  python3 kl_paper_hypecheck.py                        # STAGE2通過分すべてを検証
  python3 kl_paper_hypecheck.py --category aging_care   # 特定カテゴリのみ
  python3 kl_paper_hypecheck.py --limit 3               # 各カテゴリ先頭N件のみ（動作確認用）

出力: stage3_hypecheck.json（カテゴリ別: ok/caution/high_riskの内訳・各論文の検証結果）
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from google import genai
from google.genai import types

BASE_DIR = Path(__file__).parent
INPUT_PATH = BASE_DIR / "stage2_screened.json"
OUTPUT_PATH = BASE_DIR / "stage3_hypecheck.json"

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "models/gemini-flash-latest"
CALL_DELAY_SEC = 1.5
REQUEST_TIMEOUT_MS = 60_000  # 2026-08追加: タイムアウト未設定で1件が3時間以上ハングした事故があったため（kl_paper_screen.py参照）

PROMPT_TEMPLATE = """あなたはアドバーサリアル役（懐疑的レビュアー）です。以下の論文について、
実際に検索して二次報道・プレスリリース・SNSでの紹介記事を確認し、論文本文が実際に
主張している内容と、外部でどう紹介されているかのギャップを検証してください。

タイトル: {title}
掲載誌: {venue}
発表年: {year}
DOI: {doi}
アブストラクト: {abstract}

確認すること:
- 「〜の可能性がある」「〜傾向が見られた」「予備的な結果として」といった論文側の
  ヘッジ表現が、二次報道やプレスリリースでは断定的な表現（「〜できる」「〜が証明された」）
  に変わっていないか
- 二次報道が、論文が扱っていないスコープ（例: 特定条件下の実験結果を一般化した紹介）
  にまで話を広げていないか
- そもそも二次報道・プレスリリースが見つかるか（見つからない場合、外部の誇張はまだ
  存在しないが、動画化する際に自分たちが同様の誇張をしないよう注意すべき点を代わりに指摘する）

出力は次のJSON形式のみで、他のテキスト・Markdown装飾は一切含めないこと:
{{"secondary_coverage_found": true|false, "coverage_summary": "...", "exaggeration_gap": "none|minor|significant", "hedging_notes": "...", "overall": "ok|caution|high_risk", "reasoning": "..."}}
"""


def strip_code_fence(text: str) -> str:
    text = text.strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    return m.group(1) if m else text


def check_paper(client: genai.Client, paper: dict, retries: int = 3) -> dict:
    prompt = PROMPT_TEMPLATE.format(
        title=paper.get("title") or "(不明)",
        venue=paper.get("venue") or "(不明)",
        year=paper.get("year") or "(不明)",
        doi=paper.get("doi") or "(不明)",
        abstract=(paper.get("abstract") or "(アブストラクトなし)")[:2000],
    )
    for attempt in range(retries):
        try:
            resp = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                ),
            )
            raw = strip_code_fence(resp.text or "")
            return json.loads(raw)
        except json.JSONDecodeError:
            # 2026-09-04修正: 以前は1回目の解析失敗で即座にフォールバック（caution扱い）
            # していたが、一過性の応答不良でも即座に候補が沈んでしまうため、
            # 下のExceptionと同様にリトライしてから諦めるようにする。
            if attempt < retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"    ⚠️ JSON解析失敗、{wait}秒待って再試行: raw={raw[:200]}", file=sys.stderr)
                time.sleep(wait)
                continue
            return {
                "secondary_coverage_found": False,
                "coverage_summary": "",
                "exaggeration_gap": "minor",
                "hedging_notes": "",
                "overall": "caution",
                "reasoning": f"Geminiの応答をJSONとして解析できなかった（{retries}回試行）。生の応答: {raw[:300]}",
            }
        except Exception as e:  # noqa: BLE001 — API側の一時エラーはリトライして吸収する
            if attempt < retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"    ⚠️ Gemini呼び出し失敗、{wait}秒待って再試行: {e}", file=sys.stderr)
                time.sleep(wait)
                continue
            return {
                "secondary_coverage_found": False,
                "coverage_summary": "",
                "exaggeration_gap": "minor",
                "hedging_notes": "",
                "overall": "caution",
                "reasoning": f"Gemini呼び出しが{retries}回とも失敗: {e}",
            }


def run_category(client: genai.Client, name: str, cat: dict, limit: int) -> dict:
    label = cat["label"]
    eligible = [p for p in cat["papers"] if p.get("stage2", {}).get("overall") in ("pass", "flag")]
    excluded_at_stage2 = len(cat["papers"]) - len(eligible)
    targets = eligible[:limit] if limit else eligible
    print(
        f"\n=== カテゴリ: {label} ({name}) — "
        f"STAGE2通過{len(eligible)}件中{len(targets)}件を検証（STAGE2除外済み{excluded_at_stage2}件はスキップ）==="
    )

    results = []
    counts = {"ok": 0, "caution": 0, "high_risk": 0}
    for paper in targets:
        time.sleep(CALL_DELAY_SEC)
        verdict = check_paper(client, paper)
        overall = verdict.get("overall", "caution")
        if overall not in counts:
            overall = "caution"
        counts[overall] += 1
        mark = {"ok": "✅", "caution": "⚠️", "high_risk": "❌"}[overall]
        coverage = "報道あり" if verdict.get("secondary_coverage_found") else "報道なし"
        print(f"  {mark} [{overall}/{coverage}] {paper.get('title')[:70]}")
        results.append({**paper, "stage3": verdict})

    print(f"  カテゴリ集計: ok={counts['ok']} caution={counts['caution']} high_risk={counts['high_risk']}")

    return {
        "label": label,
        "counts": counts,
        "papers": results,
    }


def main():
    parser = argparse.ArgumentParser(description="STAGE3誇張表現検出（Gemini + Google Search）")
    parser.add_argument("--category", help="特定カテゴリのみ実行（stage2_screened.jsonのキー）")
    parser.add_argument("--limit", type=int, default=0, help="カテゴリごとに先頭N件のみ処理（0=全件）")
    args = parser.parse_args()

    if not API_KEY:
        print("❌ GEMINI_API_KEY が設定されていません", file=sys.stderr)
        sys.exit(1)

    if not INPUT_PATH.exists():
        print(f"❌ {INPUT_PATH} がありません。先に kl_paper_screen.py を実行してください", file=sys.stderr)
        sys.exit(1)

    sys.stdout.reconfigure(line_buffering=True)  # ファイルにリダイレクトしても進捗が都度見えるように

    screened = json.loads(INPUT_PATH.read_text())
    categories = screened["categories"]
    if args.category:
        if args.category not in categories:
            print(f"未知のカテゴリ: {args.category}（候補: {', '.join(categories)}）", file=sys.stderr)
            sys.exit(1)
        categories = {args.category: categories[args.category]}

    client = genai.Client(api_key=API_KEY, http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))

    def write_checkpoint(results: dict, done: bool) -> dict:
        total_counts = {"ok": 0, "caution": 0, "high_risk": 0}
        for cat_result in results.values():
            for k in total_counts:
                total_counts[k] += cat_result["counts"][k]
        output = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "source": str(INPUT_PATH.name),
            "complete": done,
            "total_counts": total_counts,
            "categories": results,
        }
        OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2))
        return total_counts

    results = {}
    for name, cat in categories.items():
        results[name] = run_category(client, name, cat, args.limit)
        totals = write_checkpoint(results, done=False)
        print(f"  [チェックポイント保存済み] 累計 ok={totals['ok']} caution={totals['caution']} high_risk={totals['high_risk']}")

    total_counts = write_checkpoint(results, done=True)
    print(
        f"\n✅ STAGE3完了。ok={total_counts['ok']} caution={total_counts['caution']} "
        f"high_risk={total_counts['high_risk']}。{OUTPUT_PATH} に保存しました。"
    )


if __name__ == "__main__":
    main()
