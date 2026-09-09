"""
kl_shortlist_rescore.py — topics_shortlist.json の在庫を最新のSTAGE4ロジックで再採点する

2026-09-06追加、同日Fable監査を経て全面改修。背景: STAGE0の在庫チェックは「カテゴリに
`available`が3件以上あればSTAGE1〜4を丸ごとスキップし、既存の在庫をそのまま使う」設計に
なっている。この設計は検索コストの節約には有効だが、`topics_shortlist.json`の各エントリは
一度スコアがついたら二度と再採点されないため、`kl_paper_interest_score.py`側の採点ロジック
（プロンプト・重み付け）を後から改善しても、既に在庫にある古いエントリには一切反映されない
問題があった。kl015選定時、在庫上位のほとんどが2026-08-28の市場比較チェック導入前の
スコアのまま放置されていたことが判明し（新旧世代のスコア混在、平均で約1.5点の系統差）、
「既視感がある」「同じ課題を解決する製品が既にある」という指摘の直接原因になった。

このスクリプトは`topics_shortlist.json`の`status: "available"`エントリのうち
`stage4_version`が`kl_paper_interest_score.STAGE4_VERSION`と異なる（＝古いロジックで
採点された、または一度も採点情報が無い）ものを対象に、同じ採点ロジック
（score_paper/overall_score/build_past_episodes_context、すべて
kl_paper_interest_score.pyからimportして再利用——プロンプト・重み付けの二重管理を
避けるため）で再採点し、topics_shortlist.json を直接上書きする。

2026-09-06 Fable監査での指摘を反映した改修点:
- abstractはSemantic Scholarの単一論文エンドポイントを1件ずつ叩くのではなく、
  batchエンドポイント（`POST /graph/v1/paper/batch`、最大500件/回）で一括取得する。
  無認証APIは全ユーザー共有のレート制限プールのため、1件ずつのfetchはクライアント側の
  スリープ間隔をいくら調整しても429を避けられない。335件でも1〜数リクエストで済む
  batch方式なら429の議論自体が発生しない。
- abstract取得に失敗した場合、**stage4_versionを刻印せずスキップする**（次回再試行
  対象として残す）。以前は404・429等どんな失敗でも空文字列のabstractで採点を続行し、
  その壊れたスコアに「最新版で採点済み」の刻印をしてしまうバグがあった
  （needs_rescore()はバージョンのみで要否判定するため、一度刻印されると永久に
  再採点されなくなる）。ただし論文が本当にSemantic Scholarから削除・統合された
  （404）場合はタイトルのみ＋Google検索グラウンディングで採点を続行し、
  `abstract_unavailable: true`を記録したうえでバージョンは更新する（このケースは
  何度再試行しても解決しないため、永久に保留にする方が害が大きい）。
- Gemini呼び出しが全滅した場合のフォールバック（`kl_paper_interest_score.py`の
  `score_paper()`が返す`_fallback: True`）も同様にstage4_versionを更新しない。
- カテゴリ単位でのアトミック書き込み（tmp+os.replace）に変更し、書き込み中の
  中断でJSONファイルが壊れることを防ぐ。
- 旧スコアを`score_history`に残し、再採点前後の変化を後から監査できるようにする。
- `--check`モードを追加。再採点が必要なエントリ数を出力し、1件でもあれば
  非ゼロで終了する。`/kl-new` STAGE0がSTAGE2提示前にこれを実行し、新旧スコアの
  混在したまま候補提示を進めることを防ぐゲートとして使う。

2026-09-09追加（Fable監査）: 既視感判定の鮮度切れ検出。
- STAGE4の既視感（deja_vu_note/deja_vu_level）は採点時点の公開・企画済み
  エピソード一覧に対してしか判定されない。その後エピソードが増えても
  STAGE4_VERSIONは変わらないため、在庫のdeja_vu判定は古いまま上位に残る。
  実際に在庫全件が2026-09-06に再採点された直後にkl015（義手の触覚再建）が
  公開されたが、在庫上位の触覚再建論文群（「250 Tactile Edges...」等）の
  deja_vu_noteはkl009にしか触れておらず、kl015との重複が一切反映されていなかった。
- 各エントリに採点時の最新エピソードIDを`deja_vu_context_upto`として刻印し、
  `--check`は「バージョンが古い件数」に加え「既視感判定がその後のエピソードを
  見ていない件数」も出力する（後者は警告のみで非ゼロ終了の条件にはしない——
  エピソードが1本増えるたびに在庫全件をGeminiで再採点するのはコストが
  見合わないため。全件再判定したい場合は`--stale-deja-vu`を明示する）。

使い方:
  python3 kl_shortlist_rescore.py --check                # 再採点が必要な件数を確認するだけ（非ゼロ終了=要再採点）
  python3 kl_shortlist_rescore.py                         # 全カテゴリ、古いバージョンのみ再採点
  python3 kl_shortlist_rescore.py --category aging_care   # 特定カテゴリのみ
  python3 kl_shortlist_rescore.py --limit 5               # カテゴリごと先頭N件のみ（動作確認用）
  python3 kl_shortlist_rescore.py --force                 # 既に最新バージョンのエントリも含め全件再採点
  python3 kl_shortlist_rescore.py --stale-deja-vu         # 既視感判定が最新エピソードを見ていないエントリも対象に含める

対象は必ず status: "available" のみ（"used"/"rejected" は対象外）。
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date

from google import genai
from google.genai import types

from kl_paper_interest_score import (
    BASE_DIR,
    STAGE4_VERSION,
    build_past_episodes_context,
    latest_known_episode_id,
    overall_score,
    score_paper,
)

SHORTLIST_PATH = BASE_DIR / "topics_shortlist.json"
SS_BATCH_URL = "https://api.semanticscholar.org/graph/v1/paper/batch"
SS_BATCH_FIELDS = "paperId,abstract"
SS_BATCH_SIZE = 500  # Semantic Scholar batch endpointの1リクエストあたり上限
RATE_LIMIT_SEC = 1.1
RETRYABLE_CODES = {429, 500, 502, 503, 504}

API_KEY = os.environ.get("GEMINI_API_KEY_KL") or os.environ.get("GEMINI_API_KEY", "")


# チャンク全体のリクエスト自体が失敗した（429等、一時的な混雑）ことを示す番兵値。
# Noneとの違い: Noneは「APIが正常応答したうえでそのIDが見つからなかった」
# （論文がSemantic Scholarから削除・統合された等、恒久的）ことを示す。
# 2026-09-06追加: 当初はこの2つを区別しておらず、一時的な429でも「確認したが
# 存在しない」と同じ扱いにして採点・バージョン刻印を進めてしまい、一時的な
# 混雑のせいでabstractなしの低品質スコアが「最新版」として永久に固定される
# 事故が実際に発生した（home_robotの29件chunkが429で3回とも失敗）。
CHUNK_REQUEST_FAILED = object()


def fetch_abstracts_batch(paper_ids: list, retries: int = 6) -> dict:
    """Semantic Scholarのbatchエンドポイントで複数論文のabstractを一括取得する
    （2026-09-06改修）。無認証APIの共有レート制限プールは1件ずつのfetchでは
    回避できないが、batchなら335件でも数リクエストで済み429を根本的に回避できる。

    戻り値: {paperId: abstract | None | CHUNK_REQUEST_FAILED}
    - 文字列: 正常取得
    - None: APIが正常応答し、そのIDが見つからなかった（恒久的な不在）
    - CHUNK_REQUEST_FAILED: リクエスト自体がリトライ上限まで失敗した（一時的、
      呼び出し側はこのIDを今回スキップし次回に再試行すべき）
    """
    result = {}
    for i in range(0, len(paper_ids), SS_BATCH_SIZE):
        chunk = paper_ids[i : i + SS_BATCH_SIZE]
        url = f"{SS_BATCH_URL}?fields={SS_BATCH_FIELDS}"
        body = json.dumps({"ids": chunk}).encode("utf-8")
        for attempt in range(retries):
            req = urllib.request.Request(
                url,
                data=body,
                method="POST",
                headers={"User-Agent": "kagaku-life-pipeline/0.1", "Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                for pid, entry in zip(chunk, data):
                    # batchエンドポイントは見つからないIDに対しnullを返す仕様
                    result[pid] = (entry or {}).get("abstract")
                break
            except urllib.error.HTTPError as e:
                if e.code in RETRYABLE_CODES and attempt < retries - 1:
                    wait = min(2 ** (attempt + 1), 60)
                    print(f"    HTTP {e.code} — {wait}秒待って再試行（{len(chunk)}件のchunk、{attempt + 1}/{retries}回目）", file=sys.stderr)
                    time.sleep(wait)
                    continue
                print(f"    ⚠️ batch取得失敗（HTTP {e.code}、{retries}回試行）: {len(chunk)}件のchunkは今回スキップ（次回再試行対象）", file=sys.stderr)
                for pid in chunk:
                    result.setdefault(pid, CHUNK_REQUEST_FAILED)
                break
            except Exception as e:  # noqa: BLE001
                if attempt < retries - 1:
                    wait = min(2 ** (attempt + 1), 60)
                    time.sleep(wait)
                    continue
                print(f"    ⚠️ batch取得失敗（{retries}回試行）: {len(chunk)}件のchunk — {e}", file=sys.stderr)
                for pid in chunk:
                    result.setdefault(pid, CHUNK_REQUEST_FAILED)
                break
        if i + SS_BATCH_SIZE < len(paper_ids):
            time.sleep(RATE_LIMIT_SEC)
    return result


def is_deja_vu_stale(entry: dict, latest_episode: str) -> bool:
    """既視感判定が、その後に増えたエピソードを見ていないか（2026-09-09追加）。
    `deja_vu_context_upto`が無い（刻印導入前に採点された）エントリも古いとみなす。"""
    if not latest_episode:
        return False
    return (entry.get("deja_vu_context_upto") or "") < latest_episode


def needs_rescore(entry: dict, force: bool, stale_deja_vu: bool = False, latest_episode: str = "") -> bool:
    if entry.get("status") != "available":
        return False
    if force:
        return True
    if entry.get("stage4_version") != STAGE4_VERSION:
        return True
    if stale_deja_vu and is_deja_vu_stale(entry, latest_episode):
        return True
    return False


def atomic_write(path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    os.replace(tmp, path)


def main():
    parser = argparse.ArgumentParser(description="topics_shortlist.jsonの在庫を最新STAGE4ロジックで再採点する")
    parser.add_argument("--category", help="特定カテゴリのみ再採点")
    parser.add_argument("--limit", type=int, default=0, help="カテゴリごと先頭N件のみ（0=全件、動作確認用）")
    parser.add_argument("--force", action="store_true", help="既に最新バージョンのエントリも含め全件再採点する")
    parser.add_argument("--dry-run", action="store_true", help="対象件数の確認のみ、API呼び出しをしない")
    parser.add_argument(
        "--check",
        action="store_true",
        help="再採点が必要な件数を確認して終了する（1件でもあれば非ゼロ終了。/kl-new STAGE0のゲート用）",
    )
    parser.add_argument(
        "--stale-deja-vu",
        action="store_true",
        help="既視感判定が最新エピソードを見ていない（deja_vu_context_uptoが古い）エントリも再採点対象に含める",
    )
    args = parser.parse_args()

    if not SHORTLIST_PATH.exists():
        print(f"❌ {SHORTLIST_PATH} がありません", file=sys.stderr)
        sys.exit(1)

    sys.stdout.reconfigure(line_buffering=True)

    data = json.loads(SHORTLIST_PATH.read_text())
    entries = data["shortlist"]
    latest_episode = latest_known_episode_id()

    targets_by_cat: dict = {}
    stale_by_cat: dict = {}
    for e in entries:
        if args.category and e.get("category") != args.category:
            continue
        if needs_rescore(e, args.force, args.stale_deja_vu, latest_episode):
            targets_by_cat.setdefault(e.get("category", "unknown"), []).append(e)
        if e.get("status") == "available" and is_deja_vu_stale(e, latest_episode):
            stale_by_cat.setdefault(e.get("category", "unknown"), []).append(e)

    total = sum(len(v) for v in targets_by_cat.values())
    stale_total = sum(len(v) for v in stale_by_cat.values())

    if args.check:
        print(f"再採点が必要なエントリ: 全{total}件（バージョン: {STAGE4_VERSION}）")
        for cat, lst in targets_by_cat.items():
            print(f"  {cat}: {len(lst)}件")
        if stale_total:
            print(
                f"⚠️ 既視感判定が最新エピソード（{latest_episode}）を見ていないエントリ: 全{stale_total}件"
                "（警告のみ。上位候補の提示時はdeja_vu_noteが最新の公開回を反映していない前提で読むこと。"
                "再判定するには --stale-deja-vu を付けて再採点する）"
            )
            for cat, lst in stale_by_cat.items():
                print(f"  {cat}: {len(lst)}件")
        sys.exit(1 if total > 0 else 0)

    print(f"=== 再採点対象: 全{total}件（バージョン: {STAGE4_VERSION}、既視感コンテキスト: 〜{latest_episode or '（なし）'}） ===")
    for cat, lst in targets_by_cat.items():
        print(f"  {cat}: {len(lst)}件")
    if stale_total and not args.stale_deja_vu:
        print(f"  （参考: 既視感判定が{latest_episode}を見ていないエントリが別途{stale_total}件。--stale-deja-vu で対象に含められる）")

    if args.dry_run:
        print("\n--dry-run のためAPI呼び出しは行いません")
        return

    if total == 0:
        print("再採点対象はありません")
        return

    if not API_KEY:
        print("❌ GEMINI_API_KEY が設定されていません", file=sys.stderr)
        sys.exit(1)

    client = genai.Client(api_key=API_KEY, http_options=types.HttpOptions(timeout=60_000))
    past_episodes = build_past_episodes_context()
    today = date.today().isoformat()

    rescored_count = 0
    skipped_count = 0
    for cat, lst in targets_by_cat.items():
        targets = lst[: args.limit] if args.limit else lst
        print(f"\n=== カテゴリ: {cat} — {len(targets)}件を再採点 ===")

        print(f"  abstractを一括取得中（batch API、{len(targets)}件）...")
        abstracts = fetch_abstracts_batch([e["paperId"] for e in targets])

        for entry in targets:
            abstract = abstracts.get(entry["paperId"])

            if abstract is CHUNK_REQUEST_FAILED:
                # 2026-09-06: リクエスト自体が一時的に失敗した（429等）場合は
                # 今回スキップし、次回の再採点対象として残す（stage4_versionを
                # 更新しない）。これを「確認したが存在しない」と混同すると、
                # 一時的な混雑のせいでabstractなしの低品質スコアが「最新版」として
                # 永久に固定されてしまう（実際に発生した事故）。
                skipped_count += 1
                print(f"  [SKIP: abstract取得が一時的に失敗、次回再試行] {entry.get('title', '')[:60]}")
                continue

            abstract_unavailable = abstract is None
            if abstract_unavailable:
                # 2026-09-06: APIが正常応答したうえで論文が見つからなかった
                # （Semantic Scholarから削除・統合された等、恒久的な不在）場合は、
                # タイトルのみ＋Google検索グラウンディングで採点を続行する。
                # 何度再試行しても解決しないため、バージョンは更新して先に進める。
                abstract = ""

            paper = {
                "title": entry.get("title"),
                "venue": entry.get("venue"),
                "is_preprint": entry.get("is_preprint"),
                "year": entry.get("year"),
                "abstract": abstract,
                "stage3": {},  # 当時のhedging_notesは再現不可。STEP4/5が最終安全網
            }

            time.sleep(1.0)  # Gemini呼び出し間隔
            verdict = score_paper(client, paper, past_episodes)

            if verdict.get("_fallback"):
                # 2026-09-06: Gemini呼び出しが全滅した場合、stage4_versionを更新せず
                # 旧スコアをそのまま残す（次回の再採点対象として残り続ける）。
                skipped_count += 1
                print(f"  [SKIP: Gemini失敗] {entry.get('title', '')[:60]}")
                continue

            score = round(overall_score(verdict), 2)
            old_score = entry.get("overall_score")

            entry.setdefault("score_history", []).append({
                "version": entry.get("stage4_version"),
                "score": old_score,
                "rescored_at": today,
            })

            entry["overall_score"] = score
            entry["score_breakdown"] = {
                "wonder_score": verdict.get("wonder_score", 0),
                "transformation_score": verdict.get("transformation_score", 0),
                "life_relevance_score": verdict.get("life_relevance_score", 0),
                "surprise_score": verdict.get("surprise_score", 0),
                "persona_fit_score": verdict.get("persona_fit_score", 0),
            }
            entry["market_status"] = verdict.get("market_status", "")
            entry["novel_delta"] = verdict.get("novel_delta", "")
            entry["behavioral_familiarity"] = verdict.get("behavioral_familiarity", "")
            entry["behavioral_familiarity_note"] = verdict.get("behavioral_familiarity_note", "")
            entry["demonstrated_capability"] = verdict.get("demonstrated_capability", "")
            entry["future_scene_sketch"] = verdict.get("future_scene_sketch", "")
            entry["deja_vu_note"] = verdict.get("deja_vu_note", "")
            entry["deja_vu_level"] = verdict.get("deja_vu_level", "")
            entry["deja_vu_context_upto"] = latest_episode
            if abstract_unavailable:
                entry["abstract_unavailable"] = True
            if verdict.get("hook_idea"):
                entry["hook_idea"] = verdict["hook_idea"]
            if verdict.get("example_protagonist"):
                entry["example_protagonist"] = verdict["example_protagonist"]
            entry["stage4_version"] = STAGE4_VERSION
            entry["rescored_at"] = today

            rescored_count += 1
            tags = []
            if abstract_unavailable:
                tags.append("abstract取得不可")
            if entry["behavioral_familiarity"] == "familiar":
                tags.append("振る舞い既知")
            if entry["deja_vu_level"] in ("strong", "partial"):
                tags.append(f"既視感{entry['deja_vu_level']}: {entry['deja_vu_note'][:30]}")
            elif entry["deja_vu_note"]:
                tags.append(f"既視感: {entry['deja_vu_note'][:30]}")
            tag_str = f" ⚠️{' / '.join(tags)}" if tags else ""
            print(f"  [{old_score} → {score}]{tag_str} {entry.get('title', '')[:55]}")

        # カテゴリ完了ごとにアトミック書き出す（Gemini呼び出しのハングで
        # 全進捗を失わないため。tmp+os.replaceで書き込み中断による破損も防ぐ）。
        atomic_write(SHORTLIST_PATH, data)
        print(f"  [保存済み] 累計 再採点{rescored_count}件 / スキップ{skipped_count}件 / 全{total}件")

    data["last_updated"] = today
    atomic_write(SHORTLIST_PATH, data)
    print(f"\n✅ 完了。再採点{rescored_count}件、Gemini失敗でスキップ{skipped_count}件（次回再試行対象）。")


if __name__ == "__main__":
    main()
