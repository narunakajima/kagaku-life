"""
kl_paper_screen.py — くらしを変える科学 STAGE2信頼性チェックスクリプト

stage1_pool.json（kl_paper_search.pyの出力）の候補をGemini（Google Search
グラウンディング付き）に1件ずつ渡し、懐疑的な査読担当者として
掲載誌の信頼度・サンプルサイズの妥当性・再現性・資金源/利益相反を確認させる
（CLAUDE.md STAGE2）。判定は pass / flag / exclude の3段階。

Opusは使わない（コスト・利用枠の都合。2026-08確定）。Geminiのみで完結する。

使い方:
  python3 kl_paper_screen.py                        # stage1_pool.json全件をスクリーニング
  python3 kl_paper_screen.py --category aging_care   # 特定カテゴリのみ
  python3 kl_paper_screen.py --limit 3               # 各カテゴリ上位N件のみ（動作確認用）

出力: stage2_screened.json（カテゴリ別: pass/flag/exclude件数・各論文の判定理由）
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from google import genai
from google.genai import types

BASE_DIR = Path(__file__).parent
INPUT_PATH = BASE_DIR / "stage1_pool.json"
OUTPUT_PATH = BASE_DIR / "stage2_screened.json"

import os

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "models/gemini-3.6-flash"
CALL_DELAY_SEC = 1.5

PROMPT_TEMPLATE = """あなたは懐疑的な査読担当者です。以下の論文候補について、
必要なら検索して掲載誌の実在性・査読体制の信頼度、サンプルサイズの妥当性、
既に他の独立した研究で類似結果が追試されているか、資金源・利益相反の懸念が
ないかを確認してください。

タイトル: {title}
掲載誌: {venue}
発表年: {year}
被引用数: {citation_count}
著者: {authors}
アブストラクト: {abstract}

判断基準:
- 掲載誌が実在し、まともな査読体制を持つか（IEEE/ACM/Nature/Science/JMIR/PLOS等の
  認知された出版社・学会か、逆に量産型・実効的な査読が機能していない疑いのある
  会議/誌でないか）
- アブストラクトからサンプルサイズ（参加者数・実験規模）が読み取れるか、
  極端に小さい場合はその旨
- 単発研究か、既知の先行研究で類似結果が追試されているように見えるか
- 企業自主資金研究など利益相反の懸念がアブストラクトから読み取れるか

出力は次のJSON形式のみで、他のテキスト・Markdown装飾は一切含めないこと:
{{"venue_assessment": "reputable|unknown|low_quality", "venue_note": "...", "sample_size_note": "...", "replication_note": "...", "funding_coi_note": "...", "overall": "pass|flag|exclude", "reasoning": "..."}}
"""


def strip_code_fence(text: str) -> str:
    text = text.strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    return m.group(1) if m else text


def screen_paper(client: genai.Client, paper: dict, retries: int = 3) -> dict:
    prompt = PROMPT_TEMPLATE.format(
        title=paper.get("title") or "(不明)",
        venue=paper.get("venue") or "(不明)",
        year=paper.get("year") or "(不明)",
        citation_count=paper.get("citationCount", 0),
        authors=", ".join(paper.get("authors") or []) or "(不明)",
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
            return {
                "venue_assessment": "unknown",
                "venue_note": "Geminiの応答をJSONとして解析できなかった",
                "sample_size_note": "",
                "replication_note": "",
                "funding_coi_note": "",
                "overall": "flag",
                "reasoning": f"パース失敗。生の応答: {raw[:300]}",
            }
        except Exception as e:  # noqa: BLE001 — API側の一時エラーはリトライして吸収する
            if attempt < retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"    ⚠️ Gemini呼び出し失敗、{wait}秒待って再試行: {e}", file=sys.stderr)
                time.sleep(wait)
                continue
            return {
                "venue_assessment": "unknown",
                "venue_note": "",
                "sample_size_note": "",
                "replication_note": "",
                "funding_coi_note": "",
                "overall": "flag",
                "reasoning": f"Gemini呼び出しが{retries}回とも失敗: {e}",
            }


def run_category(client: genai.Client, name: str, cat: dict, limit: int) -> dict:
    label = cat["label"]
    candidates = cat["candidates"][:limit] if limit else cat["candidates"]
    print(f"\n=== カテゴリ: {label} ({name}) — {len(candidates)}件をスクリーニング ===")

    results = []
    counts = {"pass": 0, "flag": 0, "exclude": 0}
    for paper in candidates:
        time.sleep(CALL_DELAY_SEC)
        verdict = screen_paper(client, paper)
        overall = verdict.get("overall", "flag")
        if overall not in counts:
            overall = "flag"
        counts[overall] += 1
        mark = {"pass": "✅", "flag": "⚠️", "exclude": "❌"}[overall]
        print(f"  {mark} [{overall}] {paper.get('title')[:70]} — {verdict.get('venue_assessment')}")
        results.append({**paper, "stage2": verdict})

    print(
        f"  カテゴリ集計: pass={counts['pass']} flag={counts['flag']} "
        f"exclude={counts['exclude']}"
    )

    return {
        "label": label,
        "counts": counts,
        "papers": results,
    }


def main():
    parser = argparse.ArgumentParser(description="STAGE2信頼性チェック（Gemini + Google Search）")
    parser.add_argument("--category", help="特定カテゴリのみ実行（stage1_pool.jsonのキー）")
    parser.add_argument("--limit", type=int, default=0, help="カテゴリごとに先頭N件のみ処理（0=全件）")
    args = parser.parse_args()

    if not API_KEY:
        print("❌ GEMINI_API_KEY が設定されていません", file=sys.stderr)
        sys.exit(1)

    if not INPUT_PATH.exists():
        print(f"❌ {INPUT_PATH} がありません。先に kl_paper_search.py を実行してください", file=sys.stderr)
        sys.exit(1)

    pool = json.loads(INPUT_PATH.read_text())
    categories = pool["categories"]
    if args.category:
        if args.category not in categories:
            print(f"未知のカテゴリ: {args.category}（候補: {', '.join(categories)}）", file=sys.stderr)
            sys.exit(1)
        categories = {args.category: categories[args.category]}

    client = genai.Client(api_key=API_KEY)

    results = {}
    total_counts = {"pass": 0, "flag": 0, "exclude": 0}
    for name, cat in categories.items():
        cat_result = run_category(client, name, cat, args.limit)
        results[name] = cat_result
        for k in total_counts:
            total_counts[k] += cat_result["counts"][k]

    output = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(INPUT_PATH.name),
        "total_counts": total_counts,
        "categories": results,
    }
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(
        f"\n✅ STAGE2完了。pass={total_counts['pass']} flag={total_counts['flag']} "
        f"exclude={total_counts['exclude']}。{OUTPUT_PATH} に保存しました。"
    )


if __name__ == "__main__":
    main()
