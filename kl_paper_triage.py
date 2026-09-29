"""
kl_paper_triage.py — くらしを変える科学 STAGE1.5 関心ごとへの関連度トリアージ

stage1_pool.json（kl_paper_search.pyの出力）の候補を、タイトルとアブストラクト冒頭だけで
Geminiにまとめて判定させ、「その関心ごとを持つ一般の人への答えになりそうか」の上位だけを
STAGE2以降へ送る（2026-09-29追加、ネタ選定パイプライン作り直し。PIPELINE_REDESIGN.md参照）。

なぜ必要か: 関心ごと起点の検索は、旧カテゴリ（ロボティクス中心の狭い検索語）より
ヒット件数が桁違いに多い（実測: 睡眠で2,664件がSTAGE1を通過）。STAGE3・STAGE4は
1件ごとにGoogle検索付きでGeminiを呼ぶため、そのままでは時間もコストも見合わない。

旧方針「STAGE1のスコアで足切りしない」（CLAUDE.md STAGE1）との関係: 旧方針が禁じたのは
被引用数×新しさという「関心ごとと無関係な指標」での足切り（発表直後の最先端論文が
不当に落ちるため）。ここでの判定は「関心ごとへの答えになっているか（relevance）」と
「未来を変える新しさ（novelty）」の2軸（各1〜5、合計で並べる）で、被引用数は使わない。
発表年は同点のときの並び順にだけ使う。
2026-09-29改訂: 当初は関連度の1軸だけで判定していたが、睡眠で試すと上位が「乳酸菌・
クルミ・機能性パジャマで睡眠改善」のような市販食品・サプリ・生活習慣の小規模な効果検証で
埋まった（医師チャンネルの「今日からできる健康法」の側で、KLの「未来を変える新しい科学」
ではない）。しかも満点が87件並び、そこから発表年だけで40件を選ぶ粗い選別になっていた。
そのため新しさを独立した軸にし、市販品・既存習慣の小規模検証は新しさ2点以下とした。

1回のGemini呼び出しで BATCH_SIZE 件をまとめて判定する（Google検索なし）ため、
2,000件超でも数十回の呼び出しで済む。1回の呼び出しに数十秒かかるため、
PARALLEL_CALLS 本を並列に実行する（直列だと睡眠の2,664件で45分以上かかった）。

使い方:
  python3 kl_paper_triage.py --concern sleep            # 上位40件を残す（デフォルト）
  python3 kl_paper_triage.py --concern sleep --keep 60  # 残す件数を変える

stage1_pool.json を上書きする（残した候補に `triage` フィールドを付け、判定の内訳を
`triage_summary` に記録する）。
"""

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from google import genai
from google.genai import types

BASE_DIR = Path(__file__).parent
POOL_PATH = BASE_DIR / "stage1_pool.json"
CONCERNS_PATH = BASE_DIR / "viewer_concerns.json"

API_KEY = os.environ.get("GEMINI_API_KEY_KL") or os.environ.get("GEMINI_API_KEY", "")
MODEL = "models/gemini-flash-latest"
BATCH_SIZE = 40
ABSTRACT_CHARS = 350
PARALLEL_CALLS = 6
REQUEST_TIMEOUT_MS = 120_000

PROMPT_TEMPLATE = """あなたは日本語YouTubeチャンネル「幸せな未来のサイエンス」の企画担当です。
このチャンネルは、視聴者が日頃抱えている関心ごと・悩みに対して、最新の学術研究が
どんな答えを出しつつあるか、そしてそれが10年後の暮らしをどう変えうるかを一般向けに紹介します。
「今日からできる健康法」を紹介する番組ではありません。

今回の関心ごと: {label}
視聴者の問いの例: {questions}

以下の論文候補（タイトルとアブストラクト冒頭）を1件ずつ、次の2つの観点で1〜5点で判定してください。

【relevance: 関心ごとへの答えになっているか】
5: この関心ごとを持つ一般の人（特定の患者群や専門家ではなく、ふつうの視聴者やその家族）に
   直接かかわる答えを出している
3: 関係はあるが、対象がかなり限られる（特定の病気の患者・特定の職業など）
1: 関心ごととほぼ無関係（手法の検証、評価尺度の開発、看護手順、調査の記述統計など）
動物実験・細胞実験だけの研究は最大3点。

【novelty: 未来を変える新しさ】
5: これまでになかった仕組みの発見、新しい技術・治療・方法（研究段階でもよい）、
   大規模なデータで常識を覆す結果。「そんなことができるのか」「そうだったのか」と思える
4: 新しいアプローチの有望な初期結果
3: 既存の方法の改良・組み合わせ
2: 市販の食品・サプリ・機能性素材・既存の生活習慣（運動・音・寝具・アロマなど）の小規模な
   効果検証、既存の治療法どうしの比較
1: 新しさがほぼない
被引用数や掲載誌の格は判定に使わないでください。

論文候補:
{papers}

出力は次のJSON配列のみで、他のテキスト・Markdown装飾は一切含めないこと。
各要素は候補番号 i、relevance、novelty、判定理由 reason（日本語20字以内）:
[{{"i": 0, "relevance": 4, "novelty": 3, "reason": "..."}}, ...]
"""


def strip_code_fence(text: str) -> str:
    text = text.strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    return m.group(1) if m else text


def format_papers(batch: list) -> str:
    lines = []
    for i, p in enumerate(batch):
        abstract = (p.get("abstract") or "").replace("\n", " ")[:ABSTRACT_CHARS]
        lines.append(f"[{i}] {p.get('title')}（{p.get('year')}）\n    {abstract}")
    return "\n".join(lines)


def triage_batch(client: genai.Client, concern: dict, batch: list, retries: int = 3) -> dict:
    """{バッチ内の番号: (relevance, novelty, reason)} を返す。失敗時は空dict（呼び出し側で0点扱い）。"""
    prompt = PROMPT_TEMPLATE.format(
        label=concern["label"],
        questions=" / ".join(concern.get("questions", [])),
        papers=format_papers(batch),
    )
    for attempt in range(retries):
        try:
            resp = client.models.generate_content(model=MODEL, contents=prompt)
            items = json.loads(strip_code_fence(resp.text or ""))
            result = {}
            for item in items:
                try:
                    i = int(item.get("i"))
                    relevance = max(1, min(5, int(item.get("relevance"))))
                    novelty = max(1, min(5, int(item.get("novelty"))))
                except (TypeError, ValueError):
                    continue
                if 0 <= i < len(batch):
                    result[i] = (relevance, novelty, str(item.get("reason") or ""))
            return result
        except Exception as e:  # noqa: BLE001
            if attempt < retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"    ⚠️ 判定失敗、{wait}秒待って再試行: {e}", file=sys.stderr)
                time.sleep(wait)
                continue
            print(f"    ⚠️ 判定失敗（{retries}回試行）。このバッチ{len(batch)}件は0点扱い: {e}", file=sys.stderr)
            return {}


def main():
    parser = argparse.ArgumentParser(description="STAGE1.5 関心ごとへの関連度トリアージ（Gemini、まとめて判定）")
    parser.add_argument("--concern", required=True, help="stage1_pool.jsonの関心ごと（viewer_concerns.jsonのid）")
    parser.add_argument("--keep", type=int, default=40, help="STAGE2へ送る件数（デフォルト40）")
    args = parser.parse_args()

    if not API_KEY:
        print("❌ GEMINI_API_KEY が設定されていません", file=sys.stderr)
        sys.exit(1)
    if not POOL_PATH.exists():
        print(f"❌ {POOL_PATH} がありません。先に kl_paper_search.py を実行してください", file=sys.stderr)
        sys.exit(1)

    sys.stdout.reconfigure(line_buffering=True)

    pool = json.loads(POOL_PATH.read_text())
    entry = pool.get("concerns", {}).get(args.concern)
    if entry is None:
        print(f"❌ stage1_pool.jsonに関心ごと {args.concern} がありません", file=sys.stderr)
        sys.exit(1)
    concern = {c["id"]: c for c in json.loads(CONCERNS_PATH.read_text())["concerns"]}[args.concern]

    candidates = entry["candidates"]
    print(f"=== トリアージ: {concern['label']}（{len(candidates)}件、{BATCH_SIZE}件ずつ判定） ===")

    client = genai.Client(api_key=API_KEY, http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))
    batches = [candidates[i : i + BATCH_SIZE] for i in range(0, len(candidates), BATCH_SIZE)]
    failed_batches = 0
    done = 0
    with ThreadPoolExecutor(max_workers=PARALLEL_CALLS) as executor:
        futures = {executor.submit(triage_batch, client, concern, batch): batch for batch in batches}
        for future in as_completed(futures):
            batch = futures[future]
            verdicts = future.result()
            if not verdicts:
                failed_batches += 1
            for i, p in enumerate(batch):
                relevance, novelty, reason = verdicts.get(i, (0, 0, "判定失敗"))
                p["triage"] = {"score": relevance + novelty, "relevance": relevance, "novelty": novelty, "reason": reason}
            done += len(batch)
            print(f"  {done}/{len(candidates)}件 判定済み")

    ranked = sorted(candidates, key=lambda p: (p["triage"]["score"], p.get("year") or 0), reverse=True)
    kept = ranked[: args.keep]

    distribution = {str(s): sum(1 for p in candidates if p["triage"]["score"] == s) for s in range(0, 11)}
    entry["triage_summary"] = {
        "triaged_at": datetime.now().isoformat(timespec="seconds"),
        "input": len(candidates),
        "kept": len(kept),
        "score_distribution": distribution,
        "failed_batches": failed_batches,
        "min_kept_score": kept[-1]["triage"]["score"] if kept else None,
    }
    entry["candidates"] = kept
    POOL_PATH.write_text(json.dumps(pool, ensure_ascii=False, indent=2))

    print(f"\n合計点（関連度＋新しさ、2〜10）の分布: " + " / ".join(f"{s}点={n}件" for s, n in sorted(distribution.items(), reverse=True) if n))
    print(f"上位{len(kept)}件を残しました（最低点 {entry['triage_summary']['min_kept_score']}）。")
    for p in kept[:20]:
        t = p["triage"]
        print(f"  [{t['score']}={t['relevance']}+{t['novelty']}] {p['title'][:65]} — {t['reason']}")
    if failed_batches:
        print(f"⚠️ 判定に失敗したバッチが{failed_batches}個あります（その候補は0点扱い）。必要なら再実行してください。")
    print(f"\n✅ stage1_pool.jsonを更新しました。次は kl_paper_screen.py --concern {args.concern}")


if __name__ == "__main__":
    main()
