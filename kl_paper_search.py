"""
kl_paper_search.py — くらしを変える科学 STAGE1論文検索スクリプト

Semantic Scholar Graph API（bulk search）を使い、query_vocabulary.json のカテゴリ別
クエリでSTAGE1（一次収集）を実行する。実際の総ヒット件数（total）を必ずログに残し、
CLAUDE.md STAGE1の自動プレフィルタ（鮮度・publicationTypes除外・重複排除）を適用したうえで、
機械的フィルタを通過した全件を stage1_pool.json に出力する。

2026-08〜: プレプリント（arXiv等）は自動除外しない。信頼性の判断（著者所属機関・
技術的厳密さ等）はSTAGE2（kl_paper_screen.py）のGeminiに委ねる方針に変更した
（CLAUDE.md STAGE2参照）。各候補には is_preprint フラグを付けて出力する。

2026-08〜: 被引用数×新しさによるスコアでの足切り（旧: 各カテゴリ上位8件）も廃止した。
発表直後で被引用数がまだ積み上がっていない最先端論文がこのスコアで不当に低く
評価され、STAGE2のGeminiが判断する前に機械的に取りこぼされるのを防ぐため
（CLAUDE.md STAGE1参照）。`--top-n` で明示的に上限を指定した場合のみ足切りする。

使い方:
  python3 kl_paper_search.py                        # 全カテゴリ実行
  python3 kl_paper_search.py --category aging_care   # 特定カテゴリのみ
  python3 kl_paper_search.py --years 3               # 鮮度基準（年数）を上書き
  python3 kl_paper_search.py --top-n 8               # カテゴリごとの上限件数（省略時は無制限。全件STAGE2へ）
  python3 kl_paper_search.py --dry-run               # API呼び出しをせず生成クエリのみ表示

出力先: stage1_pool.json（カテゴリ別: 実ヒット件数ログ・採用候補・除外理由の内訳）
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
VOCAB_PATH = BASE_DIR / "query_vocabulary.json"
OUTPUT_PATH = BASE_DIR / "stage1_pool.json"
TOPICS_QUEUE_PATH = BASE_DIR / "topics_queue.json"
SHORTLIST_PATH = BASE_DIR / "topics_shortlist.json"

API_URL = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"
FIELDS = "title,abstract,year,venue,publicationTypes,citationCount,externalIds,authors"
EXCLUDE_TYPES = {"Review", "Editorial", "LettersAndComments"}
# venueがこれらに一致する場合はプレプリントサーバ経由。2026-08〜プレプリントは
# 自動除外しない（CLAUDE.md STAGE2改訂）が、is_preprintフラグを付けてSTAGE2の
# Gemini審査（著者所属・技術的厳密さでの信頼性判断）に必ず回すための目印にする。
PREPRINT_VENUES = {
    "arxiv.org",
    "arxiv",
    "biorxiv",
    "medrxiv",
    "ssrn",
    "ssrn electronic journal",
    "social science research network",
    "preprints.org",
    "techrxiv",
    "researchsquare",
    "research square",
    "authorea",
    "authorea preprints",
}
RATE_LIMIT_SEC = 1.1  # APIキー無しの制限(1 req/s)に余裕を持たせる
PAGE_LIMIT = 100  # 1ページあたりの取得件数
MAX_PAGES = 5  # 1クエリあたりの最大ページ数（500件。無制限にすると広すぎるクエリで暴走しうるため上限を設ける）


def expand_to_ss_queries(vocab_query: str) -> list:
    """query_vocabulary.jsonの ' AND '/' OR '/括弧記法を、Semantic Scholar bulk search
    が実際に受け付ける構文（"フレーズ" + 必須語）に変換する。

    1階層の括弧内ORは、括弧を展開して複数のクエリ文字列に分岐させる
    （例: '(A OR B) AND C' → ['A + C', 'B + C']）。ORをその場でトークン結合するより
    複雑なネストを避けられ、誤ったクエリを組み立てるリスクが小さい。
    """
    # 括弧内のORを展開（1階層のみ対応。今のvocabularyはこれで足りる）
    paren_match = re.search(r"\(([^()]+)\)", vocab_query)
    if paren_match:
        branches = [b.strip() for b in paren_match.group(1).split(" OR ")]
        variants = []
        for branch in branches:
            replaced = vocab_query[: paren_match.start()] + branch + vocab_query[paren_match.end() :]
            variants.extend(expand_to_ss_queries(replaced))
        return variants

    # AND連結を " + " に変換。残ったORは（今のvocabularyでは括弧の外に出ない前提だが）
    # 念のため同様に分岐させる
    if " OR " in vocab_query:
        branches = [b.strip() for b in vocab_query.split(" OR ")]
        variants = []
        for branch in branches:
            variants.extend(expand_to_ss_queries(branch))
        return variants

    parts = [p.strip() for p in vocab_query.split(" AND ")]
    return [" + ".join(parts)]


RETRYABLE_CODES = {429, 500, 502, 503, 504}  # Semantic Scholarの公開API（無認証）は
# レート制限だけでなく一時的な500系エラーも比較的頻発するため両方リトライ対象にする
# （2026-09-04追加、pagination実装時の動作確認中に実際に500を複数回観測）。


def http_get_json(url: str, retries: int = 4) -> dict:
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={"User-Agent": "kagaku-life-pipeline/0.1"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in RETRYABLE_CODES and attempt < retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"    HTTP {e.code} — {wait}秒待って再試行", file=sys.stderr)
                time.sleep(wait)
                continue
            raise RuntimeError(f"HTTP {e.code}: {url}") from e
    raise RuntimeError(f"検索失敗（{retries}回リトライ後）: {url}")


def search_bulk(ss_query: str, year_from: int, year_to: int, token: str = None) -> dict:
    params = {
        "query": ss_query,
        "year": f"{year_from}-{year_to}",
        "fields": FIELDS,
        "limit": PAGE_LIMIT,
    }
    if token:
        params["token"] = token
    url = API_URL + "?" + urllib.parse.urlencode(params)
    return http_get_json(url)


def search_bulk_all_pages(ss_query: str, year_from: int, year_to: int) -> tuple:
    """bulk searchのtokenページネーションを辿り、最大MAX_PAGES件ぶんの結果を集める。
    総ヒット件数（total）は常にAPIの真の値をそのまま返すため、ログでは
    「取得件数 < total」でもそれが仕様（MAX_PAGES到達）なのか1ページで
    取り切れたのかが分かるようにする（2026-09-04追加、Fable 5.1監査の指摘:
    以前はtokenを一切辿らず常に先頭ページ（最大100件）のみ取得していた）。
    """
    all_papers = []
    total = 0
    token = None
    for page in range(MAX_PAGES):
        if page > 0:
            time.sleep(RATE_LIMIT_SEC)
        result = search_bulk(ss_query, year_from, year_to, token=token)
        total = result.get("total", 0)
        papers = result.get("data") or []
        all_papers.extend(papers)
        token = result.get("token")
        if not token or not papers:
            break
    return total, all_papers


def _norm_doi(doi: str) -> str:
    return (doi or "").strip().lower().removeprefix("https://doi.org/")


def load_seen_paper_ids() -> set:
    """重複排除用に既知のpaperId・DOIを読み込む（2026-08-21改訂）。

    2つのソースを見る:
    - topics_queue.json: 採用済みエピソードの references[].doi
      （このファイルの各エントリはSTAGE1のpaperIdを持たず、doiのみを保持する
      実際のフォーマットのため、semantic_scholar_idフィールドを見ていた旧実装は
      機能していなかった）
    - topics_shortlist.json: 過去のSTAGE4上位候補（採用・未採用問わず）の
      paperId・doi。未採用（status: "available"）の候補も、検索条件を変えない
      限りSTAGE1で毎回同じ論文が再浮上してしまうため、重複排除に含める
      （STAGE2以降の再スクリーニングという無駄なコストを避ける）。

    戻り値はpaperIdとDOI（正規化済み）を区別せず同じsetに入れる
    （呼び出し側でpaperId・doi両方を同じsetに対してチェックする）。
    """
    seen = set()

    if TOPICS_QUEUE_PATH.exists():
        try:
            data = json.loads(TOPICS_QUEUE_PATH.read_text())
            for entry in data.get("queue", []):
                for ref in entry.get("references", []):
                    doi = _norm_doi(ref.get("doi"))
                    if doi:
                        seen.add(doi)
        except json.JSONDecodeError:
            pass

    if SHORTLIST_PATH.exists():
        try:
            data = json.loads(SHORTLIST_PATH.read_text())
            for entry in data.get("shortlist", []):
                pid = entry.get("paperId")
                if pid:
                    seen.add(pid)
                doi = _norm_doi(entry.get("doi"))
                if doi:
                    seen.add(doi)
        except json.JSONDecodeError:
            pass

    return seen


def score_paper(paper: dict) -> float:
    """引用数×新しさの複合スコア。被引用数はlog的に効かせ、直近の論文が
    まだ引用を積めていないだけで不利になりすぎないよう新しさ側にも加点する。"""
    citation_count = paper.get("citationCount") or 0
    year = paper.get("year") or 0
    current_year = datetime.now().year
    recency = max(0, 3 - (current_year - year)) if year else 0
    import math

    return math.log1p(citation_count) + recency * 1.5


def is_preprint(paper: dict) -> bool:
    venue = (paper.get("venue") or "").strip().lower()
    return venue in PREPRINT_VENUES


def passes_stage1_prefilter(paper: dict) -> tuple:
    """CLAUDE.md STAGE1の自動プレフィルタ。(合格可否, 除外理由) を返す。
    2026-08〜: プレプリントは自動除外しない（信頼性判断はSTAGE2のGeminiに委ねる）。
    レビュー/エディトリアル等の独自データを持たない論文と、venue情報が全くない
    （出典として提示すらできない）ものだけを機械的に弾く。"""
    types = paper.get("publicationTypes") or []
    if any(t in EXCLUDE_TYPES for t in types):
        return False, f"publicationTypesにReview/Editorial等を含む: {types}"
    venue = (paper.get("venue") or "").strip()
    if not venue:
        return False, "venue情報なし（出典として提示できない）"
    return True, None


def run_category(name: str, cat: dict, year_from: int, year_to: int, top_n: int, seen_ids: set, dry_run: bool) -> dict:
    print(f"\n=== カテゴリ: {cat['label']} ({name}) ===")
    all_candidates = {}
    query_log = []

    for vocab_query in cat["queries"]:
        ss_queries = expand_to_ss_queries(vocab_query)
        for ss_query in ss_queries:
            if dry_run:
                print(f"  [dry-run] {ss_query}")
                query_log.append({"vocab_query": vocab_query, "ss_query": ss_query, "total": None})
                continue

            time.sleep(RATE_LIMIT_SEC)
            try:
                total, papers = search_bulk_all_pages(ss_query, year_from, year_to)
            except RuntimeError as e:
                print(f"  ⚠️ クエリ失敗: {ss_query} ({e})", file=sys.stderr)
                query_log.append({"vocab_query": vocab_query, "ss_query": ss_query, "total": None, "error": str(e)})
                continue

            note = "" if len(papers) >= total else f"（MAX_PAGES={MAX_PAGES}到達で打ち切り）"
            print(f"  '{ss_query}' → 総ヒット件数 {total}件（取得 {len(papers)}件）{note}")
            query_log.append({"vocab_query": vocab_query, "ss_query": ss_query, "total": total, "fetched": len(papers)})

            for paper in papers:
                pid = paper.get("paperId")
                if not pid or pid in all_candidates:
                    continue
                all_candidates[pid] = paper

    if dry_run:
        return {"label": cat["label"], "dry_run": True, "queries": query_log}

    excluded_review = 0
    excluded_no_venue = 0
    excluded_dup = 0
    preprint_count = 0
    passing = []
    for pid, paper in all_candidates.items():
        doi = _norm_doi((paper.get("externalIds") or {}).get("DOI"))
        if pid in seen_ids or (doi and doi in seen_ids):
            excluded_dup += 1
            continue
        ok, reason = passes_stage1_prefilter(paper)
        if not ok:
            if "Review/Editorial" in (reason or ""):
                excluded_review += 1
            else:
                excluded_no_venue += 1
            continue
        if is_preprint(paper):
            preprint_count += 1
        passing.append(paper)

    # スコア（被引用数×新しさ）は参考の並び順にのみ使い、足切りには使わない。
    # STAGE1時点では発表直後で被引用数がほぼ0の論文が同点になりやすく、
    # このスコアで機械的に上位N件へ絞ると「変革ポテンシャルの高い最先端論文」を
    # STAGE2のGeminiが判断する前に取りこぼすリスクがあるため（2026-08確認）。
    passing.sort(key=score_paper, reverse=True)
    top = passing[:top_n] if top_n else passing

    print(
        f"  カテゴリ集計: 収集{len(all_candidates)}件 → "
        f"重複排除-{excluded_dup} → レビュー等除外-{excluded_review} → "
        f"venue不明除外-{excluded_no_venue} → "
        f"通過{len(passing)}件（うちプレプリント{preprint_count}件） → STAGE2へ{len(top)}件を送付"
    )

    return {
        "label": cat["label"],
        "queries": query_log,
        "raw_collected": len(all_candidates),
        "excluded_duplicate": excluded_dup,
        "excluded_review_type": excluded_review,
        "excluded_no_venue": excluded_no_venue,
        "passed_stage1": len(passing),
        "preprint_count": preprint_count,
        "candidates": [
            {
                "paperId": p.get("paperId"),
                "title": p.get("title"),
                "year": p.get("year"),
                "venue": p.get("venue"),
                "publicationTypes": p.get("publicationTypes"),
                "citationCount": p.get("citationCount"),
                "doi": (p.get("externalIds") or {}).get("DOI"),
                "authors": [a.get("name") for a in (p.get("authors") or [])][:5],
                "abstract": p.get("abstract"),
                "score": round(score_paper(p), 3),
                "is_preprint": is_preprint(p),
            }
            for p in top
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="STAGE1論文検索（Semantic Scholar Graph API）")
    parser.add_argument("--category", help="特定カテゴリのみ実行（query_vocabulary.jsonのキー）")
    parser.add_argument("--years", type=int, default=3, help="鮮度基準（年数、デフォルト3）")
    parser.add_argument("--top-n", type=int, default=0, help="カテゴリごとの上限件数（0=無制限、デフォルト。STAGE1のスコアで足切りせず全件STAGE2へ送る）")
    parser.add_argument("--dry-run", action="store_true", help="API呼び出しをせず生成クエリのみ表示")
    args = parser.parse_args()

    vocab = json.loads(VOCAB_PATH.read_text())
    categories = vocab["categories"]
    if args.category:
        if args.category not in categories:
            print(f"未知のカテゴリ: {args.category}（候補: {', '.join(categories)}）", file=sys.stderr)
            sys.exit(1)
        categories = {args.category: categories[args.category]}

    current_year = datetime.now().year
    year_from = current_year - args.years
    year_to = current_year

    seen_ids = load_seen_paper_ids()
    if seen_ids:
        print(f"topics_queue.json既出paperIdを{len(seen_ids)}件読み込み、重複排除に使用します")

    results = {}
    for name, cat in categories.items():
        results[name] = run_category(name, cat, year_from, year_to, args.top_n, seen_ids, args.dry_run)

    if args.dry_run:
        print("\n[dry-run] API呼び出しは行っていません。stage1_pool.jsonへの書き込みもスキップします。")
        return

    output = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "year_range": f"{year_from}-{year_to}",
        "top_n_per_category": args.top_n,
        "categories": results,
    }
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"\n✅ STAGE1完了。{OUTPUT_PATH} に保存しました。")


if __name__ == "__main__":
    main()
