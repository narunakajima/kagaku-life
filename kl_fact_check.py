"""
kl_fact_check.py — くらしを変える科学 台本ファクトチェックスクリプト

STAGE3（kl_paper_hypecheck.py）は論文選定段階で「論文本体 vs 二次報道」を検証するが、
台本執筆後に「実際に書いたナレーション vs 論文本体」が食い違っていないかは
これまで人間の目視チェック（kl_confirmation_doc.pyのチェックリスト）任せだった。
本スクリプトはそこをGemini（Google Searchグラウンディング付き）で自動化する。

episodes/kl{NNN}.json の reference_index 付きシーン（finding/data）を参照論文ごとに
まとめ、Geminiに実際に論文を検索・確認させたうえで、以下を照合する:
- 数値（成功率・人数・統計的有意差等）が論文本文の記載と一致しているか
- 所属機関名が出典の記載と一致しているか
- ヘッジ表現（研究段階である旨・限界の記載）が省略されていないか
- 論文が扱っていないスコープにまで話を広げていないか（誇張の混入）

「査読」「プレプリント」語のナレーション内混入チェックは検索不要の単純な
文字列チェックのため、Gemini呼び出しとは別にPythonで直接行う。

2026-09-29追加: 健康の話題の語り方のチェック（検索なし、エピソード全体で1回）。
YouTubeは2026年7月、AIの語り手が専門家を装って健康・医療の助言をする内容を
収益化の対象外にした（YouTubeヘルプ「不自然なコンテンツ」）。一方、特定の医学研究の
結果を紹介・議論すること自体は医療に関する誤情報ポリシーの例外として明記されている。
そこで台本が「研究結果の紹介」にとどまり、①視聴者への健康上の助言（「〜しましょう」
「〜すれば治る」、薬・サプリの勧め等）、②語り手が医師・専門家を名乗る、
③研究段階の結果を確立した治療法のように語る、のいずれにもなっていないかを確認する
（ネタ選定パイプライン作り直し、PIPELINE_REDESIGN.md §9）。

Opusは使わない。Geminiのみで完結する（STAGE2/STAGE3と同方針）。

使い方:
  python3 kl_fact_check.py --episode kl001

出力: ~/Desktop/kagaku-life/fact_check_result.json
（Desktopは常に最新1エピソード分の確認用。エピソードIDのサブフォルダは作らない）
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

from google import genai
from google.genai import types

sys.stdout.reconfigure(line_buffering=True)

BASE_DIR = Path(__file__).parent
DESKTOP_DIR = Path.home() / "Desktop" / "kagaku-life"

API_KEY = os.environ.get("GEMINI_API_KEY_KL") or os.environ.get("GEMINI_API_KEY", "")
MODEL = "models/gemini-flash-latest"
CALL_DELAY_SEC = 1.5
REQUEST_TIMEOUT_MS = 60_000

JARGON_WORDS = ["査読", "プレプリント"]

PROMPT_TEMPLATE = """あなたは懐疑的なファクトチェック担当者です。以下の論文について実際に検索・
確認し、番組のナレーション原稿がその論文の内容と食い違っていないかを検証してください。

【論文】
タイトル: {title}
著者: {authors}
掲載誌: {venue}
発表年: {year}
DOI/URL: {doi_url}
所属機関（ナレーションでの表記）: {institution}

【この論文について書かれたナレーション原稿（複数シーンをまとめて表示）】
{narration_block}

確認すること:
- ナレーション内の具体的な数値（成功率・人数・統計的有意差の有無等）が、論文本文の
  実際の記載と一致しているか
- 所属機関名がナレーションの表記と一致しているか
- 論文側のヘッジ表現（「予備的な結果」「限定的な条件下」等）や研究段階であることが、
  ナレーションで断定的な表現に変わっていないか
- ナレーションが、論文が実際には扱っていない範囲にまで話を広げていないか（誇張）

出力は次のJSON形式のみで、他のテキスト・Markdown装飾は一切含めないこと:
{{"numbers_match": true|false, "institution_match": true|false, "hedging_preserved": true|false,
"scope_exaggerated": true|false, "issues": ["具体的な問題点", ...], "overall": "ok|caution|high_risk",
"reasoning": "..."}}
"""


HEALTH_TONE_PROMPT = """あなたはYouTubeのポリシーに詳しい台本チェック担当です。以下は、学術研究を一般向けに
紹介する日本語チャンネルの台本（ナレーション全文・タイトル・概要欄）です。語り手の声はAIで
合成しています。登場する主人公は架空の生活者です。

このチャンネルは「研究結果を紹介する」番組であり、視聴者に健康上の助言をする番組ではありません。
次のいずれかに当たる箇所がないか確認してください。
1. 視聴者への健康・医療上の助言や指示（例:「〜しましょう」「〜を試してみてください」
   「〜すれば治ります」、薬・サプリ・治療法を勧める、用量を示す）。主人公が自分の体験として
   語る独白や、研究内容の説明は助言に当たらない
2. 語り手が医師・専門家・研究者本人を名乗る、またはそう装う
3. 研究段階の結果（動物実験・小規模試験・承認前の治療など）を、すでに確立した治療法や
   誰にでも効く方法のように語っている

【タイトル】{title}
【概要欄】{description}
【ナレーション】
{narrations}

出力は次のJSON形式のみで、他のテキスト・Markdown装飾は一切含めないこと。該当がなければ issues は空配列:
{{"issues": [{{"where": "S05 など場所", "type": "advice|expert_claim|overclaim", "text": "該当箇所の引用", "fix": "直し方の案"}}],
"overall": "ok|caution|high_risk", "reasoning": "..."}}
"""


def strip_code_fence(text: str) -> str:
    text = text.strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    return m.group(1) if m else text


def check_reference(client: genai.Client, ref: dict, narrations: list, retries: int = 3) -> dict:
    narration_block = "\n\n".join(f"- {n}" for n in narrations)
    prompt = PROMPT_TEMPLATE.format(
        title=ref.get("title") or "(不明)",
        authors=", ".join(ref.get("authors", [])) or "(不明)",
        venue=ref.get("venue") or "(不明)",
        year=ref.get("year") or "(不明)",
        doi_url=ref.get("doi") or ref.get("url") or "(不明)",
        institution=ref.get("institution") or "(不明)",
        narration_block=narration_block,
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
            # していたが、一過性の応答不良でも即座にファクトチェックが不確定のまま
            # 終わってしまうため、下のExceptionと同様にリトライしてから諦めるようにする。
            if attempt < retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"    ⚠️ JSON解析失敗、{wait}秒待って再試行: raw={raw[:200]}", file=sys.stderr)
                time.sleep(wait)
                continue
            return {
                "numbers_match": None, "institution_match": None, "hedging_preserved": None,
                "scope_exaggerated": None, "issues": [], "overall": "caution",
                "reasoning": f"Geminiの応答をJSONとして解析できなかった（{retries}回試行）。生の応答: {raw[:300]}",
            }
        except Exception as e:  # noqa: BLE001
            if attempt < retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"    ⚠️ Gemini呼び出し失敗、{wait}秒待って再試行: {e}", file=sys.stderr)
                time.sleep(wait)
                continue
            return {
                "numbers_match": None, "institution_match": None, "hedging_preserved": None,
                "scope_exaggerated": None, "issues": [], "overall": "caution",
                "reasoning": f"Gemini呼び出しが{retries}回とも失敗: {e}",
            }


def check_jargon(scenes: list) -> list:
    """「査読」「プレプリント」語のナレーション内混入を単純な文字列チェックで検出する。"""
    hits = []
    for s in scenes:
        for word in JARGON_WORDS:
            if word in s.get("narration", ""):
                hits.append(f"S{s['scene_id']:02d}: 「{word}」がナレーションに含まれています")
    return hits


def check_health_tone(client: genai.Client, ep: dict, retries: int = 3) -> dict:
    """健康の話題の語り方（助言・専門家の名乗り・言い過ぎ）をエピソード全体で1回チェックする。"""
    lines = [f"S{s['scene_id']:02d}（{s.get('type')}）: {s.get('narration', '')}" for s in ep.get("scenes", [])]
    for sh in ep.get("shorts", []):
        for i, sc in enumerate(sh.get("scenes", []), start=1):
            lines.append(f"Shorts{sh.get('shorts_id')} S{i:02d}: {sc.get('narration', '')}")
    prompt = HEALTH_TONE_PROMPT.format(
        title=ep.get("youtube_title") or ep.get("episode_title") or "",
        description=(ep.get("youtube_description") or "")[:1500],
        narrations="\n".join(lines),
    )
    for attempt in range(retries):
        try:
            resp = client.models.generate_content(model=MODEL, contents=prompt)
            return json.loads(strip_code_fence(resp.text or ""))
        except Exception as e:  # noqa: BLE001
            if attempt < retries - 1:
                time.sleep(2 ** (attempt + 1))
                continue
            return {"issues": [], "overall": "caution", "reasoning": f"チェックに失敗（{retries}回試行）: {e}"}


def run(episode_id: str):
    if not API_KEY:
        print("❌ GEMINI_API_KEY が設定されていません", file=sys.stderr)
        sys.exit(1)

    ep_path = BASE_DIR / "episodes" / f"{episode_id}.json"
    if not ep_path.exists():
        print(f"❌ {ep_path} がありません", file=sys.stderr)
        sys.exit(1)
    ep = json.loads(ep_path.read_text())

    references = ep.get("references", [])
    scenes = ep["scenes"]

    # reference_index ごとにナレーションをまとめる
    by_ref = {}
    for s in scenes:
        idx = s.get("reference_index")
        lines = s.get("lines") or []
        # 2026-10-06: 掛け合い形式では、1シーンに複数の資料の事実が混じることがある（kl034で、同じシーンに
        # ヘルプセンターと発表ブログの内容があり、行ごとの reference_index を無視して誤指摘が出た）。
        # 行ごとの reference_index があれば、行単位でその資料に振り分ける。無い行はシーンの値を使う。
        if any(l.get("reference_index") is not None for l in lines):
            for l in lines:
                li = l.get("reference_index", idx)
                if li is None:
                    continue
                by_ref.setdefault(li, []).append(l["text"])
            continue
        if idx is None:
            continue
        by_ref.setdefault(idx, []).append(s["narration"])

    client = genai.Client(api_key=API_KEY, http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))

    results = []
    counts = {"ok": 0, "caution": 0, "high_risk": 0}
    for idx, narrations in sorted(by_ref.items()):
        if idx >= len(references):
            continue
        ref = references[idx]
        print(f"検証中: [{idx}] {ref.get('title', '')[:50]}... ", end="", flush=True)
        time.sleep(CALL_DELAY_SEC)
        verdict = check_reference(client, ref, narrations)
        verdict["reference_index"] = idx
        verdict["title"] = ref.get("title")
        results.append(verdict)
        overall = verdict.get("overall", "caution")
        counts[overall] = counts.get(overall, 0) + 1
        icon = {"ok": "✅", "caution": "⚠️", "high_risk": "❌"}.get(overall, "❓")
        print(f"{icon} {overall}")
        if verdict.get("issues"):
            for issue in verdict["issues"]:
                print(f"    - {issue}")

    jargon_hits = check_jargon(scenes)
    if jargon_hits:
        print(f"\n⚠️ 専門用語混入チェック: {len(jargon_hits)}件")
        for h in jargon_hits:
            print(f"  - {h}")
    else:
        print("\n✓ 「査読」「プレプリント」語の混入なし")

    print("\n健康の話題の語り方をチェック中（助言・専門家の名乗り・言い過ぎ）... ", end="", flush=True)
    time.sleep(CALL_DELAY_SEC)
    health_tone = check_health_tone(client, ep)
    tone_overall = health_tone.get("overall", "caution")
    print({"ok": "✅", "caution": "⚠️", "high_risk": "❌"}.get(tone_overall, "❓"), tone_overall)
    for issue in health_tone.get("issues", []):
        print(f"    - [{issue.get('where')}/{issue.get('type')}] {issue.get('text')} → {issue.get('fix')}")

    print(f"\n=== 結果: ok={counts.get('ok', 0)} caution={counts.get('caution', 0)} "
          f"high_risk={counts.get('high_risk', 0)} / 健康の語り方: {tone_overall} ===")

    DESKTOP_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DESKTOP_DIR / "fact_check_result.json"
    out_path.write_text(
        json.dumps({"counts": counts, "results": results, "jargon_hits": jargon_hits, "health_tone": health_tone},
                   ensure_ascii=False, indent=2)
    )
    print(f"\n結果を保存しました: {out_path}")


def main():
    parser = argparse.ArgumentParser(description="くらしを変える科学 台本ファクトチェック")
    parser.add_argument("--episode", required=True, help="エピソードID（例: kl001）")
    args = parser.parse_args()
    run(args.episode)


if __name__ == "__main__":
    main()
