"""
kl_paper_interest_score.py — くらしを変える科学 STAGE4「面白いか」一次判定スクリプト

stage3_hypecheck.json（kl_paper_hypecheck.pyの出力）のうち overall が high_risk でない
候補をGeminiに渡し、CLAUDE.md STAGE4の4観点（生活実感との直結度・数字のインパクト・
「使い捨ての生活者」ペルソナへの落とし込みやすさ・サブジャンル分散）で判定させる。
検索は不要な創作寄りの判断のためGoogle Searchグラウンディングは使わない。
Opusは使わない（STAGE2/3と同方針）。

具体的な主人公プロフィール（名前・年齢・職業）とフック文の叩き台まで生成し、
STAGE5（人間の最終ゴーサイン）にそのまま渡せる形にする。

使い方:
  python3 kl_paper_interest_score.py                        # STAGE3通過分すべてを判定
  python3 kl_paper_interest_score.py --category aging_care   # 特定カテゴリのみ
  python3 kl_paper_interest_score.py --limit 3               # 各カテゴリ先頭N件のみ（動作確認用）
  python3 kl_paper_interest_score.py --top 5                 # 全体上位N件をSTAGE5候補として出力（デフォルト5）

出力: stage4_ranked.json（全カテゴリ横断でスコア順に並べた候補・上位N件のSTAGE5候補リスト）
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
INPUT_PATH = BASE_DIR / "stage3_hypecheck.json"
OUTPUT_PATH = BASE_DIR / "stage4_ranked.json"

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "models/gemini-3.6-flash"
CALL_DELAY_SEC = 1.0

PROMPT_TEMPLATE = """あなたは日本語YouTubeチャンネル「くらしを変える科学」の企画担当です。
AI・ロボティクス分野の学術論文を一般視聴者向けに解説し、「その研究が生活をどう変えるか」を
描くチャンネルです。以下の論文が第1話（またはそれに続く候補）としてどれくらい「面白いか」を
判定してください。

タイトル: {title}
掲載誌: {venue}
発表年: {year}
アブストラクト: {abstract}
STAGE3での注意点（動画化時に踏まえるべきヘッジ・限界）: {hedging_notes}

以下4つの観点で1〜5点評価してください（5が最高）:
1. life_relevance_score: 生活実感との直結度（視聴者が「自分ごと」として想像できるか）
2. surprise_score: 数字のインパクト（意外性のある定量的結果があるか）
3. persona_fit_score: 「使い捨ての生活者」ペルソナ（1エピソード限りの具体的な生活者を主人公にする
   演出）に、具体的な生活シーンとして落とし込みやすいか

さらに、実際にこの論文を扱うとしたら:
- example_protagonist: 主人公にふさわしい生活者プロフィール（name, age, job）。
  テーマに応じて対象読者層と重なる人物像を選ぶこと（例: 介護ロボットの回なら高齢の親を持つ世代）
- hook_idea: 冒頭3〜5秒のフック文の叩き台（日本語、生活実感に直結する問いかけ）

出力は次のJSON形式のみで、他のテキスト・Markdown装飾は一切含めないこと:
{{"life_relevance_score": 1-5, "surprise_score": 1-5, "persona_fit_score": 1-5, "example_protagonist": {{"name": "...", "age": 0, "job": "..."}}, "hook_idea": "...", "reasoning": "..."}}
"""


def strip_code_fence(text: str) -> str:
    text = text.strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    return m.group(1) if m else text


def score_paper(client: genai.Client, paper: dict, retries: int = 3) -> dict:
    prompt = PROMPT_TEMPLATE.format(
        title=paper.get("title") or "(不明)",
        venue=paper.get("venue") or "(不明)",
        year=paper.get("year") or "(不明)",
        abstract=(paper.get("abstract") or "(アブストラクトなし)")[:2000],
        hedging_notes=(paper.get("stage3") or {}).get("hedging_notes") or "(特になし)",
    )
    for attempt in range(retries):
        try:
            resp = client.models.generate_content(model=MODEL, contents=prompt)
            raw = strip_code_fence(resp.text or "")
            return json.loads(raw)
        except json.JSONDecodeError:
            return {
                "life_relevance_score": 1,
                "surprise_score": 1,
                "persona_fit_score": 1,
                "example_protagonist": {},
                "hook_idea": "",
                "reasoning": f"Geminiの応答をJSONとして解析できなかった。生の応答: {raw[:300]}",
            }
        except Exception as e:  # noqa: BLE001
            if attempt < retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"    ⚠️ Gemini呼び出し失敗、{wait}秒待って再試行: {e}", file=sys.stderr)
                time.sleep(wait)
                continue
            return {
                "life_relevance_score": 1,
                "surprise_score": 1,
                "persona_fit_score": 1,
                "example_protagonist": {},
                "hook_idea": "",
                "reasoning": f"Gemini呼び出しが{retries}回とも失敗: {e}",
            }


def overall_score(v: dict) -> float:
    return (
        v.get("life_relevance_score", 0) * 0.4
        + v.get("surprise_score", 0) * 0.35
        + v.get("persona_fit_score", 0) * 0.25
    )


def run_category(client: genai.Client, name: str, cat: dict, limit: int) -> list:
    label = cat["label"]
    eligible = [p for p in cat["papers"] if p.get("stage3", {}).get("overall") != "high_risk"]
    excluded = len(cat["papers"]) - len(eligible)
    targets = eligible[:limit] if limit else eligible
    print(f"\n=== カテゴリ: {label} ({name}) — {len(targets)}件を判定（STAGE3 high_risk除外{excluded}件）===")

    scored = []
    for paper in targets:
        time.sleep(CALL_DELAY_SEC)
        verdict = score_paper(client, paper)
        score = round(overall_score(verdict), 2)
        print(f"  [{score}] {paper.get('title')[:70]}")
        scored.append({**paper, "category": name, "category_label": label, "stage4": verdict, "overall_score": score})

    return scored


def main():
    parser = argparse.ArgumentParser(description="STAGE4「面白いか」一次判定（Gemini）")
    parser.add_argument("--category", help="特定カテゴリのみ実行（stage3_hypecheck.jsonのキー）")
    parser.add_argument("--limit", type=int, default=0, help="カテゴリごとに先頭N件のみ処理（0=全件）")
    parser.add_argument("--top", type=int, default=5, help="全体上位N件をSTAGE5候補として出力（デフォルト5）")
    args = parser.parse_args()

    if not API_KEY:
        print("❌ GEMINI_API_KEY が設定されていません", file=sys.stderr)
        sys.exit(1)

    if not INPUT_PATH.exists():
        print(f"❌ {INPUT_PATH} がありません。先に kl_paper_hypecheck.py を実行してください", file=sys.stderr)
        sys.exit(1)

    checked = json.loads(INPUT_PATH.read_text())
    categories = checked["categories"]
    if args.category:
        if args.category not in categories:
            print(f"未知のカテゴリ: {args.category}（候補: {', '.join(categories)}）", file=sys.stderr)
            sys.exit(1)
        categories = {args.category: categories[args.category]}

    client = genai.Client(api_key=API_KEY)

    all_scored = []
    for name, cat in categories.items():
        all_scored.extend(run_category(client, name, cat, args.limit))

    all_scored.sort(key=lambda p: p["overall_score"], reverse=True)
    top_n = all_scored[: args.top]

    print(f"\n=== STAGE4 全体ランキング 上位{len(top_n)}件（STAGE5候補） ===")
    for i, p in enumerate(top_n, 1):
        print(f"  {i}. [{p['overall_score']}] {p['category_label']} — {p['title'][:60]}")
        print(f"     フック案: {p['stage4'].get('hook_idea', '')}")

    output = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(INPUT_PATH.name),
        "total_scored": len(all_scored),
        "stage5_candidates": top_n,
        "all_scored": all_scored,
    }
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"\n✅ STAGE4完了。{len(all_scored)}件を判定し、上位{len(top_n)}件をSTAGE5候補として{OUTPUT_PATH}に保存しました。")


if __name__ == "__main__":
    main()
