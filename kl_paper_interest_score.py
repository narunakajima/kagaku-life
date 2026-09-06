"""
kl_paper_interest_score.py — くらしを変える科学 STAGE4「面白いか」一次判定スクリプト

stage3_hypecheck.json（kl_paper_hypecheck.pyの出力）のうち overall が high_risk でない
候補をGeminiに渡し、CLAUDE.md STAGE4の観点（変革ポテンシャル・野心度／生活実感との
直結度／数字のインパクト／「使い捨ての生活者」ペルソナへの落とし込みやすさ）で判定させる。
Opusは使わない（STAGE2/3と同方針）。

2026-08〜: 「変革ポテンシャル・野心度」を追加し、最も重く重み付けする（CLAUDE.md
STAGE4参照）。kl001実制作で「査読済み・安全だが地味」な研究に寄り、企画書の核心
（信頼できる研究が暮らしを劇的に変える面白さ）を欠く結果になったための改訂。

2026-08-28改訂: クエリ語彙強化後もtransformation_scoreが「既に市販製品で実現している
体験」に満点をつける問題が発覚した（例: home_robotの"Robi Butler"＝スマホ遠隔操作の
家事ロボットにtransformation_score=5満点。だがスマホからの遠隔操作自体はロボット
掃除機で既に一般的）。原因はプロンプトが「実現したら暮らしがどれだけ変わるか」を
単発で聞くだけで、「現在の市販品と比べて何が新しいか」の比較基準がなかったこと
（STAGE2/3の「論文の主張 vs 二次報道の誇張」チェックとは別の盲点で、「論文の主張 vs
市場の現実」は誰も見ていなかった）。対処として、transformation_scoreの判定に限り
採点前にGoogle検索で類似の市販製品・サービスの有無を確認させる指示を追加し、
このスコアの判定のみGoogle Searchグラウンディングを有効化した（STAGE2/3と同じ
`types.Tool(google_search=types.GoogleSearch())`）。あわせて採点根拠を人間が
検証できるよう`transformation_comparison`フィールド（何と比較して何が新しいと
判断したか）を出力に追加した。

具体的な主人公プロフィール（名前・年齢・職業）とフック文の叩き台まで生成し、
STAGE5（人間の最終ゴーサイン）にそのまま渡せる形にする。

2026-08〜: このスコアリング自体は主観的・創作寄りの判断で、Geminiに単発プロンプトで
228件処理させるより人間・Claudeの文脈判断の方が精度が高い可能性がある。ただし
全件を人間が見るのは非現実的なため、一次選抜（大量処理・低コスト）はGeminiに
任せつつ、STAGE5でClaudeが確認する範囲を上位5件→上位20件に広げることで、
Geminiのスコアだけを鵜呑みにしない設計にした（kl001選定時、上位5件だけでは
カテゴリの偏りに気づきにくかった反省を踏まえる）。

2026-09-06改訂（根本的な指標見直し）: kl015選定時、STAGE4上位候補が軒並み
「既視感がある」「同じ課題を解決する製品が既にある」とユーザーから指摘された。
原因を調査した結果2点判明した:
(1) 2026-08-28のtransformation_score市場比較チェックは「新規にSTAGE1〜4を
    実行したとき」にしか効かず、STAGE0が「カテゴリ在庫3件以上ならSTAGE1〜4を
    丸ごとスキップ」する設計のため、在庫が潤沢なカテゴリほど市場比較なしの
    古いスコアが上位に残り続けていた（`topics_shortlist.json`は一度スコアが
    ついたら再採点されない）。
(2) 従来の4指標（transformation/life_relevance/surprise/persona_fit）は
    いずれも「規模」「自分ごと度」「数字の意外性」「演出しやすさ」という
    理性的な尺度であり、CLAUDE.mdが掲げる番組の核心＝「技術のすごさではなく
    それが主人公にもたらす小さな幸せ」という**感情の質**を直接測る指標が
    存在しなかった。技術的に野心的でも、想像した瞬間に「まあ助かるね」で
    終わる技術（不安解消・問題解決止まり）が高得点になりやすい構造だった。
(1)への対処は`kl_shortlist_rescore.py`（在庫の再採点）と`STAGE4_VERSION`に
よるバージョン管理で行う。(2)への対処として`wonder_score`
（ワクワク感・幸せな未来度）を新設し、最重要指標として最も重く重み付けした
（ユーザー判断、2026-09-06）。抽象的な技術説明のままでは感情は評価しづらい
ため、採点前に必ず`future_scene_sketch`（impactシーン相当の具体的な一場面）を
書かせてから、その情景を採点させる2段階方式にした。あわせて過去の公開
エピソード一覧をプロンプトに渡し、「同じ話の型」の重複がないかも
`deja_vu_note`として判定させる（paperId単位の重複排除では検出できない、
別論文だが問題設定・技術タイプが酷似しているケースへの対処。CLAUDE.md
STAGE4参照）。

使い方:
  python3 kl_paper_interest_score.py                        # STAGE3通過分すべてを判定
  python3 kl_paper_interest_score.py --category aging_care   # 特定カテゴリのみ
  python3 kl_paper_interest_score.py --limit 3               # 各カテゴリ先頭N件のみ（動作確認用）
  python3 kl_paper_interest_score.py --top 20                # 全体上位N件をSTAGE5候補として出力（デフォルト20）

出力: stage4_ranked.json（全カテゴリ横断でスコア順に並べた候補・上位N件のSTAGE5候補リスト）

このファイルの score_paper() / overall_score() / build_past_episodes_context() /
STAGE4_VERSION は `kl_shortlist_rescore.py`（在庫の再採点）からもそのまま
import して使う。プロンプト・重み付けの二重管理を避けるため、採点ロジックの
変更は必ずこのファイル側で行うこと。
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
TOPICS_QUEUE_PATH = BASE_DIR / "topics_queue.json"

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "models/gemini-flash-latest"
CALL_DELAY_SEC = 1.0
REQUEST_TIMEOUT_MS = 60_000  # 2026-08追加: タイムアウト未設定で1件が3時間以上ハングした事故があったため（kl_paper_screen.py参照）

# プロンプト・採点基準（重み含む）を変更するたびに更新する。topics_shortlist.jsonの
# 各エントリにはこの値が`stage4_version`として刻印され、STAGE0の在庫チェック時に
# 現行バージョンと異なるエントリを「再採点が必要な古いスコア」として検出するのに使う
# （2026-09-06導入。それまでは一度スコアがついた在庫が永久に再採点されない問題があった）。
STAGE4_VERSION = "2026-09-06-wonder"

PROMPT_TEMPLATE = """あなたは日本語YouTubeチャンネル「くらしを変える科学」の企画担当です。
AI・ロボティクス分野の学術論文を一般視聴者向けに解説し、「その研究が生活をどう変えるか」を
描くチャンネルです。以下の論文が次エピソード候補としてどれくらい「面白いか」を判定してください。

タイトル: {title}
掲載誌: {venue}
プレプリントか: {preprint_label}
発表年: {year}
アブストラクト: {abstract}
STAGE3での注意点（動画化時に踏まえるべきヘッジ・限界）: {hedging_notes}

このチャンネルが最も大切にしているのは、技術そのもののすごさではなく、それが実現した
未来が主人公の暮らしにもたらす「小さいけれど確かな幸せ」です。以下の手順で評価してください。

【ステップ0】**採点前に必ずGoogle検索で「現在すでに市販・実用化されている類似の
消費者向け製品・サービス」（スマート家電、ロボット掃除機、既存のAIエージェント
サービス等）を確認すること。** そのうえで以下2つを出力する:
- `market_status`: 次のいずれか1つ — `"existing_product"`（市場に既にほぼ同じ体験の
  製品・サービスがある）／`"incremental"`（既存製品はあるが明確な改善がある）／
  `"novel"`（今の市場には存在しない体験）
- `novel_delta`: 「今の市場で既に実現していること」と切り分けたうえで、**本当に
  新しい部分だけ**を日本語1文で明記する（`market_status`が`existing_product`の
  場合は「新しい部分はほぼない」等、正直に書くこと。ここで新しさを誇張しない）
- `demonstrated_capability`: アブストラクトに実際に書かれている、この研究が
  現時点で実証した内容（サンプル数・実験環境等の条件込み）を日本語1文で要約する。
  この先のステップで空想を広げすぎないための基準line。

【ステップ1】この技術が実際に実現した場合、主人公がある日常のワンシーンでそれを
体験している様子を1〜2文で具体的に描写してください（`future_scene_sketch`）。
番組の`impact`シーンに相当するもので、「誰が」「いつ」「何をしていて」「何を感じるか」が
伝わる具体的な情景にすること（抽象的な機能説明にしない）。**この情景は`novel_delta`
（今の市場にはない、本当に新しい部分）が主役になるように描くこと。市場に既にある
体験の部分（`market_status`が`existing_product`ならほぼ全体）を幸せそうに描いても、
それは既存製品でも得られる幸せであり評価の対象にならない。**

【ステップ2】過去に企画・公開したエピソードの一覧を下記に示します（`[却下]`と
付いているものは、過去に候補として検討したが「既視感がある」「面白みに欠ける」等の
理由で不採用と判断された論文で、その判断理由も併記されている）。問題設定・技術の
タイプ・描く未来の情景がこれらと酷似していないか確認してください。酷似している場合は
`deja_vu_note`にその旨と該当エピソード（または却下履歴）を明記し、下記の採点
（特にwonder_score・transformation_score）を厳しめにつけること。別の論文であっても
「着るロボットで歩行を助ける」「非接触センサーで転倒を検知する」のように話の型が
同じなら既視感の対象とする。似た前例がなければ`deja_vu_note`は空文字列でよい。

過去の公開・企画済み・却下済みエピソード一覧:
{past_episodes}

【ステップ3】以下5つの観点で1〜5点評価してください（5が最高）:
1. wonder_score【最重要指標】: ステップ1で描いた情景（＝`novel_delta`の情景）を
   読んだとき、視聴者が心から「幸せな未来だ、こうなったらいいな」とワクワクし
   温かい気持ちになれるか。`market_status`が`existing_product`の場合、新しい
   部分がほぼ無いということなので、この点は必ず2点以下にすること。
   「技術的に野心的か」と「幸せそうに見えるか」は別物である点にも注意すること
   （数値的なインパクトが大きくても、不安の解消・問題の除去に留まり
   『まあ助かるね』で終わる情景は低い点にする）。ステップ2で酷似した前例が
   あると判定した場合、新鮮な驚き・幸福感が薄れるためこの点を下げること。
2. transformation_score: 変革ポテンシャル・野心度。`novel_delta`が本当に広く
   実現した場合、暮らしをどれだけ劇的に変えるか。`market_status`が
   `existing_product`の場合はこの点も2点以下にすること。「すでに確立された
   地味な改善」や「既存製品の焼き直し」には低い点を、既存製品との違いが明確で
   「まだ実現していないが実現すれば劇的」なものには高い点をつける。査読済みか
   未査読かはこのスコアに影響させない（査読状況の信頼性判断はSTAGE2で既に
   完了している前提）
3. life_relevance_score: 生活実感との直結度（視聴者が「自分ごと」として想像できるか）
4. surprise_score: 数字のインパクト（意外性のある定量的結果があるか）
5. persona_fit_score: 「使い捨ての生活者」ペルソナ（1エピソード限りの具体的な生活者を主人公にする
   演出）に、具体的な生活シーンとして落とし込みやすいか

さらに、実際にこの論文を扱うとしたら:
- example_protagonist: 主人公にふさわしい生活者プロフィール（name, age, job）。
  テーマに応じて対象読者層と重なる人物像を選ぶこと（例: 介護ロボットの回なら高齢の親を持つ世代）
- hook_idea: 冒頭3〜5秒のフック文の叩き台（日本語、生活実感に直結する問いかけ）

出力は次のJSON形式のみで、他のテキスト・Markdown装飾は一切含めないこと:
{{"market_status": "existing_product|incremental|novel", "novel_delta": "...", "demonstrated_capability": "...", "future_scene_sketch": "...", "deja_vu_note": "...", "wonder_score": 1-5, "transformation_score": 1-5, "life_relevance_score": 1-5, "surprise_score": 1-5, "persona_fit_score": 1-5, "example_protagonist": {{"name": "...", "age": 0, "job": "..."}}, "hook_idea": "...", "reasoning": "..."}}
"""

FALLBACK_VERDICT_TEMPLATE = {
    "market_status": "",
    "novel_delta": "",
    "demonstrated_capability": "",
    "future_scene_sketch": "",
    "deja_vu_note": "",
    "wonder_score": 1,
    "transformation_score": 1,
    "life_relevance_score": 1,
    "surprise_score": 1,
    "persona_fit_score": 1,
    "example_protagonist": {},
    "hook_idea": "",
    # 2026-09-06追加: このフラグが立った採点結果（JSON解析失敗・Gemini呼び出し全滅）を
    # 呼び出し側（run_category/kl_shortlist_rescore.py）が検知し、stage4_versionを
    # 刻印せず古いスコアを保持できるようにする。以前はこのフラグが無く、失敗時の
    # 全項目1点のフォールバックがそのまま「最新版で採点済み」として在庫を
    # 恒久的に破壊するバグがあった。
    "_fallback": True,
}


def strip_code_fence(text: str) -> str:
    text = text.strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    return m.group(1) if m else text


def build_past_episodes_context(
    queue_path: Path = TOPICS_QUEUE_PATH,
    shortlist_path: Path = None,
) -> str:
    """topics_queue.json（公開・企画済み）と topics_shortlist.json（却下済み）の
    一覧を、既視感チェック用のコンテキスト文字列に整形する（paperId単位の重複
    排除では検出できない『話の型』の重複をGeminiに判定させるため、2026-09-06追加）。

    2026-09-06改訂（Fable監査で指摘）: 当初はtopics_queue.json（公開・企画済み
    14話）のみを渡していたが、これでは「候補として検討したが既視感・面白み
    不足で却下したテーマ」（例: 転倒検知レーダー）が一切コンテキストに
    含まれず、同じテーマが翌回もdeja_vu判定なしで再浮上する欠陥があった。
    status: "rejected"のshortlistエントリも却下理由付きで含めるようにした。
    """
    if shortlist_path is None:
        shortlist_path = BASE_DIR / "topics_shortlist.json"

    lines = []

    if queue_path.exists():
        try:
            data = json.loads(queue_path.read_text())
            for e in data.get("queue", []):
                title = e.get("title") or ""
                hook = e.get("hook_idea") or ""
                cat_label = e.get("category_label") or e.get("category") or ""
                lines.append(f"- {e.get('episode_id', '?')} [{cat_label}] {title}（フック: {hook}）")
        except json.JSONDecodeError:
            pass

    if shortlist_path.exists():
        try:
            data = json.loads(shortlist_path.read_text())
            for e in data.get("shortlist", []):
                if e.get("status") != "rejected":
                    continue
                title = e.get("title") or ""
                cat_label = e.get("category_label") or e.get("category") or ""
                reason = e.get("rejected_reason") or "（理由未記録）"
                lines.append(f"- [却下] [{cat_label}] {title}（却下理由: {reason}）")
        except json.JSONDecodeError:
            pass

    return "\n".join(lines) if lines else "（まだ公開・企画済み・却下済みエピソードなし）"


def score_paper(client: genai.Client, paper: dict, past_episodes: str, retries: int = 3) -> dict:
    prompt = PROMPT_TEMPLATE.format(
        title=paper.get("title") or "(不明)",
        venue=paper.get("venue") or "(不明)",
        preprint_label="プレプリント（査読前）" if paper.get("is_preprint") else "査読済み想定",
        year=paper.get("year") or "(不明)",
        abstract=(paper.get("abstract") or "(アブストラクトなし)")[:2000],
        hedging_notes=(paper.get("stage3") or {}).get("hedging_notes") or "(特になし)",
        past_episodes=past_episodes,
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
            # 2026-09-04修正: 以前は1回目の解析失敗で即座にフォールバック（全スコア1）
            # していたが、一過性の応答不良でも即座に候補が沈んでしまうため、
            # 下のExceptionと同様にリトライしてから諦めるようにする。
            if attempt < retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"    ⚠️ JSON解析失敗、{wait}秒待って再試行: raw={raw[:200]}", file=sys.stderr)
                time.sleep(wait)
                continue
            return {
                **FALLBACK_VERDICT_TEMPLATE,
                "reasoning": f"Geminiの応答をJSONとして解析できなかった（{retries}回試行）。生の応答: {raw[:300]}",
            }
        except Exception as e:  # noqa: BLE001
            if attempt < retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"    ⚠️ Gemini呼び出し失敗、{wait}秒待って再試行: {e}", file=sys.stderr)
                time.sleep(wait)
                continue
            return {
                **FALLBACK_VERDICT_TEMPLATE,
                "reasoning": f"Gemini呼び出しが{retries}回とも失敗: {e}",
            }


# market_statusが"existing_product"（市場に既にほぼ同じ体験がある）と判定された
# 場合の、wonder_score/transformation_scoreの上限（2026-09-06追加）。プロンプト側の
# 指示（ステップ3参照）だけに頼ると、Geminiが指示を読み飛ばした場合に「市販品と
# 同等だが情景の作文が魅力的」という候補がそのまま高得点になってしまう
# （Fable監査で指摘されたcriticalな回帰リスク）。コード側でも機械的に上限をかけ、
# 二重の安全策にする。
EXISTING_PRODUCT_SCORE_CAP = 2


def overall_score(v: dict) -> float:
    wonder = v.get("wonder_score", 0)
    transformation = v.get("transformation_score", 0)
    if v.get("market_status") == "existing_product":
        wonder = min(wonder, EXISTING_PRODUCT_SCORE_CAP)
        transformation = min(transformation, EXISTING_PRODUCT_SCORE_CAP)
    return (
        wonder * 0.45
        + transformation * 0.25
        + v.get("life_relevance_score", 0) * 0.15
        + v.get("surprise_score", 0) * 0.10
        + v.get("persona_fit_score", 0) * 0.05
    )


def run_category(client: genai.Client, name: str, cat: dict, limit: int, past_episodes: str) -> list:
    label = cat["label"]
    eligible = [p for p in cat["papers"] if p.get("stage3", {}).get("overall") != "high_risk"]
    excluded = len(cat["papers"]) - len(eligible)
    targets = eligible[:limit] if limit else eligible
    print(f"\n=== カテゴリ: {label} ({name}) — {len(targets)}件を判定（STAGE3 high_risk除外{excluded}件）===")

    scored = []
    for paper in targets:
        time.sleep(CALL_DELAY_SEC)
        verdict = score_paper(client, paper, past_episodes)
        score = round(overall_score(verdict), 2)
        fallback_tag = " [FALLBACK]" if verdict.get("_fallback") else ""
        print(f"  [{score}]{fallback_tag} {paper.get('title')[:70]}")
        entry = {
            **paper,
            "category": name,
            "category_label": label,
            "stage4": verdict,
            "overall_score": score,
        }
        # 2026-09-06追加: フォールバック（JSON解析失敗・Gemini呼び出し全滅）の
        # 結果にはstage4_versionを刻印しない。刻印してしまうと「最新版で採点
        # 済み」と誤認され、全項目1点の壊れたスコアが二度と再採点されなくなる
        # （kl_shortlist_rescore.pyのneeds_rescore()はバージョンのみで判定するため）。
        if not verdict.get("_fallback"):
            entry["stage4_version"] = STAGE4_VERSION
        scored.append(entry)

    return scored


def main():
    parser = argparse.ArgumentParser(description="STAGE4「面白いか」一次判定（Gemini）")
    parser.add_argument("--category", help="特定カテゴリのみ実行（stage3_hypecheck.jsonのキー）")
    parser.add_argument("--limit", type=int, default=0, help="カテゴリごとに先頭N件のみ処理（0=全件）")
    parser.add_argument("--top", type=int, default=20, help="全体上位N件をSTAGE5候補として出力（デフォルト20）")
    args = parser.parse_args()

    if not API_KEY:
        print("❌ GEMINI_API_KEY が設定されていません", file=sys.stderr)
        sys.exit(1)

    if not INPUT_PATH.exists():
        print(f"❌ {INPUT_PATH} がありません。先に kl_paper_hypecheck.py を実行してください", file=sys.stderr)
        sys.exit(1)

    sys.stdout.reconfigure(line_buffering=True)  # ファイルにリダイレクトしても進捗が都度見えるように

    checked = json.loads(INPUT_PATH.read_text())
    categories = checked["categories"]
    if args.category:
        if args.category not in categories:
            print(f"未知のカテゴリ: {args.category}（候補: {', '.join(categories)}）", file=sys.stderr)
            sys.exit(1)
        categories = {args.category: categories[args.category]}

    client = genai.Client(api_key=API_KEY, http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))
    past_episodes = build_past_episodes_context()

    all_scored = []
    for name, cat in categories.items():
        all_scored.extend(run_category(client, name, cat, args.limit, past_episodes))
        # カテゴリ完了ごとに書き出す（2026-08追加: 1件のハングで全進捗を失った事故を受けて）
        OUTPUT_PATH.write_text(json.dumps(
            {"generated_at": datetime.now().isoformat(timespec="seconds"), "complete": False, "all_scored": all_scored},
            ensure_ascii=False, indent=2,
        ))
        print(f"  [チェックポイント保存済み] 累計{len(all_scored)}件")

    all_scored.sort(key=lambda p: p["overall_score"], reverse=True)
    top_n = all_scored[: args.top]

    print(f"\n=== STAGE4 全体ランキング 上位{len(top_n)}件（STAGE5候補） ===")
    for i, p in enumerate(top_n, 1):
        print(f"  {i}. [{p['overall_score']}] {p['category_label']} — {p['title'][:60]}")
        print(f"     フック案: {p['stage4'].get('hook_idea', '')}")

    output = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(INPUT_PATH.name),
        "complete": True,
        "total_scored": len(all_scored),
        "stage5_candidates": top_n,
        "all_scored": all_scored,
    }
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"\n✅ STAGE4完了。{len(all_scored)}件を判定し、上位{len(top_n)}件をSTAGE5候補として{OUTPUT_PATH}に保存しました。")


if __name__ == "__main__":
    main()
