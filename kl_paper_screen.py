"""
kl_paper_screen.py — くらしを変える科学 STAGE2信頼性チェックスクリプト

stage1_pool.json（kl_paper_search.pyの出力）の候補をGemini（Google Search
グラウンディング付き）に1件ずつ渡し、懐疑的な査読担当者として
掲載誌の信頼度・サンプルサイズの妥当性・再現性・資金源/利益相反を確認させる
（CLAUDE.md STAGE2）。判定は pass / flag / exclude の3段階。

2026-08〜: 「査読済みのみ」ルールを撤回したため、プレプリント（is_preprint: true）は
掲載誌の査読体制だけでなく、著者所属機関の実績・技術的検証の厳密さで信頼性を
判断する（CLAUDE.md STAGE2参照）。

2026-08〜: コスト削減のため、明らかに信頼できる出版社・学会（REPUTABLE_VENUE_KEYWORDS）
に一致する非プレプリント論文はGemini呼び出しをスキップして自動passする。
一致しないもの（未知の誌・すべてのプレプリント）だけを個別にGeminiへ回す。
許可リスト外を自動excludeにはしない（プレプリント全体を機械的に締め出すと
査読済み限定ルールの復活になり、STAGE2改訂の意図を無効化するため）。

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
VENUE_ALLOWLIST_PATH = BASE_DIR / "reputable_venues.json"

import os

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "models/gemini-flash-latest"
CALL_DELAY_SEC = 1.5
REQUEST_TIMEOUT_MS = 60_000  # 2026-08追加: タイムアウト未設定で1件が3時間以上ハングした事故があったため

# 明らかに信頼できる出版社・学会の許可リスト（venue文字列への部分一致、大小無視）。
# 該当する場合はGemini呼び出しをスキップして自動passする（コスト削減）。
# reputable_venues.json から読み込む（kl_venue_allowlist_update.pyが
# stage2_screened.jsonの実績から追加候補を提案・追記する）。
# 2026-08確定: 「許可リスト外は切り捨て」にはしない——プレプリントサーバー自体は
# 当然このリストに入らないため、それをやると査読済み限定ルールの復活になり
# STAGE2改訂の意図（著者機関・技術的厳密さでの個別判断）を無効化してしまう。
# リスト外・プレプリントは全てGeminiに個別レビューさせる（切り捨てない）。
REPUTABLE_VENUE_KEYWORDS = json.loads(VENUE_ALLOWLIST_PATH.read_text())["keywords"]


def is_reputable_venue(venue: str) -> bool:
    v = (venue or "").lower()
    return any(kw in v for kw in REPUTABLE_VENUE_KEYWORDS)

PROMPT_TEMPLATE = """あなたは懐疑的な査読担当者です。以下の論文候補について、
必要なら検索して信頼性を確認してください。

タイトル: {title}
掲載誌: {venue}
プレプリントか: {preprint_label}
発表年: {year}
被引用数: {citation_count}
著者: {authors}
アブストラクト: {abstract}

判断基準:
- 【査読済みの場合】掲載誌が実在し、まともな査読体制を持つか（IEEE/ACM/Nature/Science/
  JMIR/PLOS等の認知された出版社・学会か、逆に量産型・実効的な査読が機能していない
  疑いのある会議/誌でないか）
- 【プレプリントの場合、査読済みと同列の必須条件にはしない。代わりに以下で信頼性を判断する】
  - 著者の所属機関（DeepMind / Stanford / MIT / CMU / Berkeley / NUS等の主要大学・研究所、
    Figure AI / 1X / Boston Dynamics等の実績あるロボティクス企業の研究部門など、実績ある
    機関に所属しているか。無名の個人・実績不明の機関のみの場合は信頼性を下げて判断する）
  - 技術的検証の厳密さ（定量的なベンチマーク・比較評価が示されているか、単なる宣伝や
    コンセプト提案に留まらないか）
  - 著者・研究室の過去実績（同分野で既発表の実績があるか検索で確認できるか）
  - 動画化する場合は「査読前の研究」であることを必ず明示する前提で判断してよい
    （査読前であること自体は除外理由にしない）
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
        preprint_label="プレプリント（査読前）" if paper.get("is_preprint") else "査読済み想定",
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
    auto_passed = 0
    for paper in candidates:
        if not paper.get("is_preprint") and is_reputable_venue(paper.get("venue")):
            verdict = {
                "venue_assessment": "reputable",
                "venue_note": "許可リストに一致したため自動pass（Gemini呼び出しなし）",
                "sample_size_note": "",
                "replication_note": "",
                "funding_coi_note": "",
                "overall": "pass",
                "reasoning": "既知の信頼できる出版社・学会のためGeminiレビューを省略した。",
            }
            auto_passed += 1
            mark = "✅"
            print(f"  {mark} [pass/auto] {paper.get('title')[:70]} — {paper.get('venue')}")
        else:
            time.sleep(CALL_DELAY_SEC)
            verdict = screen_paper(client, paper)
            overall = verdict.get("overall", "flag")
            if overall not in counts:
                overall = "flag"
            verdict["overall"] = overall
            mark = {"pass": "✅", "flag": "⚠️", "exclude": "❌"}[overall]
            print(f"  {mark} [{overall}] {paper.get('title')[:70]} — {verdict.get('venue_assessment')}")

        counts[verdict["overall"]] += 1
        results.append({**paper, "stage2": verdict})

    print(
        f"  カテゴリ集計: pass={counts['pass']}（うち許可リスト自動pass{auto_passed}）"
        f" flag={counts['flag']} exclude={counts['exclude']}"
    )

    return {
        "label": label,
        "counts": counts,
        "auto_passed": auto_passed,
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

    sys.stdout.reconfigure(line_buffering=True)  # ファイルにリダイレクトしても進捗が都度見えるように

    pool = json.loads(INPUT_PATH.read_text())
    categories = pool["categories"]
    if args.category:
        if args.category not in categories:
            print(f"未知のカテゴリ: {args.category}（候補: {', '.join(categories)}）", file=sys.stderr)
            sys.exit(1)
        categories = {args.category: categories[args.category]}

    client = genai.Client(api_key=API_KEY, http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))

    def write_checkpoint(results: dict, done: bool) -> dict:
        total_counts = {"pass": 0, "flag": 0, "exclude": 0}
        total_auto_passed = 0
        for cat_result in results.values():
            for k in total_counts:
                total_counts[k] += cat_result["counts"][k]
            total_auto_passed += cat_result["auto_passed"]
        output = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "source": str(INPUT_PATH.name),
            "complete": done,
            "total_counts": total_counts,
            "total_auto_passed": total_auto_passed,
            "categories": results,
        }
        OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2))
        return total_counts | {"auto_passed": total_auto_passed}

    results = {}
    for name, cat in categories.items():
        results[name] = run_category(client, name, cat, args.limit)
        # カテゴリ完了ごとに書き出す（2026-08追加: 1件のハングで全進捗を失った事故を受けて）
        totals = write_checkpoint(results, done=False)
        print(f"  [チェックポイント保存済み] 累計 pass={totals['pass']} flag={totals['flag']} exclude={totals['exclude']}")

    totals = write_checkpoint(results, done=True)
    print(
        f"\n✅ STAGE2完了。pass={totals['pass']}（うち許可リスト自動pass{totals['auto_passed']}） "
        f"flag={totals['flag']} exclude={totals['exclude']}。{OUTPUT_PATH} に保存しました。"
    )


if __name__ == "__main__":
    main()
