"""
kl_news_scan.py — ニュース起点のネタ選定（2026-10-04〜）

なるさんの判断（2026-10-04）: 「視聴者の関心ごと → それに答える論文を探す」方式では、見つかる論文が
1年〜数年前のものになりがちで、AI分野の進み方から見ると古めかしく「どこかで聞いた話」になる。
そこで **ニュースを入口に、一次資料で答え合わせ** する方式を加えた（論文起点の方式も残す）。

  1. collect: news_sources.json のRSSから、直近 N 日（既定21日）の発表を集める
     ＋ Gemini（Google検索つき）に、同じ期間に日本語圏でも話題になったAI・ロボット・科学の発表を挙げさせる
  2. score:   候補ごとに Gemini（Google検索つき）で **一次資料**（発表元の論文・公式ブログ・技術レポート・
              プレスリリース・デモの条件）を探させ、鮮度・話題性・検証可能性・誇張度・議論を呼ぶか・
              驚き・暮らしとの関わりを採点する。一次資料が見つからない候補（噂・リーク・出典不明）は採用不可
  3. 結果は news_candidates.json（gitで追跡）に貯める。/kl-new STEP1 ケースC で上位を提示する

報道記事は「何が発表されたか」を知る手がかりにだけ使い、台本の根拠は必ず一次資料に置く
（記事の文章をなぞらない。権利面と内容の厚みの両方のため）。

2026-10-11（P0・P1、旬×注目度の見直し）: 話題性 buzz_jp は Gemini の推定で実質3点に偏り、新しいだけで
地味な話題が上位に出ていた。そこで
  - P0（ゲート）: 使用済み・却下済みと同じ一次資料の候補、企業の顧客導入事例（宣伝）を除外し、
    一次資料のソフト404（HTTP 200 で中身が「404」）を check-urls で検出する
  - P1（実測）: Google ニュース RSS で「この発表そのもの」を報じた日本語の独立媒体の数を数え、
    buzz_measured（1〜5）にする。並び順は core = 鮮度 × buzz_measured（同点は 誇張＋議論＋暮らし）
  - list は「本命／ニッチ／速報（再計測待ち）」の3枠で出す（Gemini の推定 buzz_jp_est は予備）

2026-10-15（NEWS_REDESIGN_2026-10-15.md の1週目）:
  - verify: 採点の直後に一次資料URLの実在を確かめる（HTTP・ソフト404、DOIは doi.org のハンドルAPI）。
    primary_verified が False（全URLが404）の候補はゲートで落とし、None（403等で判断不能）は「要確認」で残す
  - topic_age: 鮮度を「系列の最初の日付」（同じ系列の候補・news_pool.json の記事・buzz_evidence の最古）から数える
  - 答え合わせ候補: 製品発表・日本語10媒体以上・初出から2日以上は、本命・ベスト3ではなく別の枠に出す（2日未満は再評価待ち）
  - yt: 朝に手で数えた日本語の解説動画の本数を記録する

使い方（collect → score → verify → tag → enrich → buzz → list）:
  python3 kl_news_scan.py collect [--days 21]   # RSS＋Googleニュースのキーワード検索（gnews_queries）＋Gemini検索、重複排除
  python3 kl_news_scan.py score [--top 15]      # 検索つき、1件ずつ課金
  python3 kl_news_scan.py verify [--id ID ...] [--all] [--max 60]   # 一次資料URLの実在確認（無料。HTTPだけ）
  python3 kl_news_scan.py tag                   # ジャンル未付与に5ジャンル（テキストのみ）
  python3 kl_news_scan.py enrich                # ゲート通過分に検索語・見出しの語・発表の種類・系列（テキストのみ）
  python3 kl_news_scan.py buzz [--max 50]       # Google ニュース RSS で注目度を実測（1候補1回、2秒以上の間隔）
  python3 kl_news_scan.py list [--top 10] [--by-genre] [--check-urls]
  python3 kl_news_scan.py check-urls [--id ID ...]   # ベスト3・本命・答え合わせ候補（または指定）の一次資料URLを確認し直す
  python3 kl_news_scan.py yt --id ID --count N [--query 検索語]   # 日本語の解説動画の本数を記録（手入力）
"""

import argparse
import email.utils
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

BASE_DIR = Path(__file__).parent
SOURCES_JSON = BASE_DIR / "news_sources.json"
POOL_JSON = BASE_DIR / "news_pool.json"            # collect の結果（作業ファイル、.gitignore）
CANDIDATES_JSON = BASE_DIR / "news_candidates.json"  # score の結果（gitで追跡）
CONCERNS_JSON = BASE_DIR / "viewer_concerns.json"
QUEUE_JSON = BASE_DIR / "topics_queue.json"
GENRES_JSON = BASE_DIR / "genres.json"            # 2026-10-06: 5ジャンル（再生リスト・提案の分類）

API_KEY = os.environ.get("GEMINI_API_KEY_KL") or os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-flash-latest"
UA = {"User-Agent": "Mozilla/5.0 (kagaku-life news scan)"}

# 一次資料が確認できない候補は採用しない（追記メモ §3）。検証可能性がこの点以下なら除外する
MIN_VERIFIABILITY = 3
SCAN_VERSION = "2026-10-11-buzz-measured"

# ベスト3・本命枠に入れる条件（2026-10-11、P0）。一覧そのものの足切りは MIN_VERIFIABILITY のまま
GATE_MIN_VERIFIABILITY = 4
GATE_MIN_LIFE = 4            # 暮らし（life_relevance）と仕事・ビジネス（work_relevance）の高い方が3以下なら本命に入れない（2026-10-12）
GATE_MIN_FRESHNESS = 3       # freshness_score で3以上＝発表から21日以内

# 互換用の加重和（overall_score）。list の並び順の主役は core（= 鮮度 × 実測の注目度）で、こちらは参考表示のみ。
# buzz は buzz_measured（実測）があればそれ、無ければ buzz_jp_est（推定。旧データは buzz_jp）を使う
WEIGHTS = {
    "freshness": 0.25,       # 発表からの日数（コードで計算）。最重視（2026-10-11、なるさんの指示: 旬の話題）
    "buzz": 0.25,            # 日本語圏での注目度（実測優先）。最重視（同: 注目度の高い話題）
    "hype_gap": 0.10,        # 見出しと中身の差（大きいほどツッコミの材料）
    "debate": 0.10,          # 議論を呼ぶか・二人の判定が割れそうか
    "wonder": 0.10,          # 驚き・ワクワク（温かい感動だけでなく知的な驚きも）
    "life_relevance": 0.10,  # 暮らしにどう関わるか（viewer_concerns.json を参照）
    "verifiability": 0.10,   # 一次資料で答え合わせできるか
}

TOPIC_FILTER = (
    "AI, robotics, automation, or a science/technology/medical research result that could change "
    "everyday life within years (health, food, work, home, mobility, aging, pets, environment)"
)


def _text(el, tag):
    for t in (tag, "{http://www.w3.org/2005/Atom}" + tag, "{http://purl.org/rss/1.0/}" + tag):
        x = el.find(t)
        if x is not None:
            return (x.text or x.get("href") or "").strip()
    return ""


def _parse_date(s: str):
    if not s:
        return None
    try:
        return email.utils.parsedate_to_datetime(s).astimezone(timezone.utc)
    except Exception:  # noqa: BLE001
        pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:  # noqa: BLE001
        return None


RSS1_NS = "{http://purl.org/rss/1.0/}"


def _get(url: str, timeout: int = 20) -> bytes:
    """RSSの取得。既定のUAで403/406ならブラウザ風UAで1回だけ取り直す（取得物はパースするだけ）。
    頼んでいないのに gzip で返すサーバーがある（Google DeepMind、2026-10-11に発覚。以前から0件だった）ので展開する。"""
    try:
        raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()
    except urllib.error.HTTPError as e:
        if e.code not in (403, 406):
            raise
        raw = urllib.request.urlopen(urllib.request.Request(url, headers=BROWSER_UA), timeout=timeout).read()
    if raw[:2] == b"\x1f\x8b":
        import gzip
        raw = gzip.decompress(raw)
    return raw


def fetch_feed(feed: dict, since: datetime) -> list:
    """1つのRSS/Atomを取得して、since 以降の記事を返す。
    feed["max_items"] があれば、新しい順にその件数までにする（2026-10-11、件数の多いフィードが候補を占めないように）。"""
    raw = _get(feed["url"])
    root = ET.fromstring(raw)
    items = (root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
             or root.findall(f".//{RSS1_NS}item"))
    out = []
    for it in items:
        title = _text(it, "title")
        link = _text(it, "link")
        if not link:
            le = it.find("{http://www.w3.org/2005/Atom}link")
            link = le.get("href") if le is not None else ""
        date = _parse_date(_text(it, "pubDate") or _text(it, "published") or _text(it, "updated")
                           or _text(it, "{http://purl.org/dc/elements/1.1/}date"))
        if date is None or date < since:
            continue
        desc = re.sub(r"<[^>]+>", " ", _text(it, "description") or _text(it, "summary"))
        out.append({"title": title, "url": link, "published": date.date().isoformat(),
                    "source": feed["name"], "source_kind": feed["kind"],
                    "summary": re.sub(r"\s+", " ", desc).strip()[:400]})
    if feed.get("max_items"):
        out = sorted(out, key=lambda x: x["published"], reverse=True)[: int(feed["max_items"])]
    return out


# ============================================================
# Google ニュースのキーワード検索フィード（kind: gnews、2026-10-11）
# ジャンルごとの検索語で、日本語の報道を拾う。報道は手がかり（二次情報）で、一次資料は score が探す
# ============================================================

GNEWS_COLLECT_WINDOW = 7       # 日。検索語に when:7d を付ける
GNEWS_COLLECT_MAX_REQ = 15     # 1回の collect で Google ニュースに送る上限


def collect_gnews(queries: list, since: datetime, per_query: int) -> list:
    """news_sources.json の gnews_queries（[{"genre": "...", "q": "..."}]）を順に1回ずつ取得する。
    リクエスト間隔は GNEWS_INTERVAL（2秒以上）。失敗（429・同意画面・0件）は警告して次へ進む。"""
    out = []
    for n, gq in enumerate(queries[:GNEWS_COLLECT_MAX_REQ]):
        if n:
            time.sleep(GNEWS_INTERVAL)
        q = gq.get("q", "").strip()
        try:
            items = fetch_gnews(q, window_days=GNEWS_COLLECT_WINDOW)
        except GNewsError as e:
            print(f"  ⚠️ Googleニュース「{q}」: 取得失敗 {e}")
            continue
        got = []
        for it in sorted(items, key=lambda x: x["date"], reverse=True):
            if not it["date"] or it["date"] < since.date().isoformat():
                continue
            outlet = it["outlet"] or it["host"]
            got.append({"title": it["title"], "url": "", "gnews_link": it.get("link", ""),
                        "published": it["date"],
                        "source": f"Googleニュース（{q}）／{outlet}", "source_kind": "media",
                        "outlet": outlet, "outlet_host": it.get("host", ""), "genre_hint": gq.get("genre", ""),
                        "summary": f"{it['title']}（{outlet}）"})
            if len(got) >= per_query:
                break
        print(f"  Googleニュース「{q}」({gq.get('genre', '')}): {len(got)}件（取得 {len(items)}件）")
        out += got
    if len(queries) > GNEWS_COLLECT_MAX_REQ:
        print(f"  ⚠️ gnews_queries が{len(queries)}件あるため、先頭の{GNEWS_COLLECT_MAX_REQ}件だけ取得しました")
    return out


# ============================================================
# 同じ発表の重複排除（2026-10-11）。見出しの語（英語は単語、日本語は2文字ずつ）の Jaccard 類似度でまとめる
# ============================================================

DEDUP_JACCARD = 0.5
_EN_STOP = {"the", "and", "for", "with", "from", "that", "this", "into", "how", "new", "its", "are", "can",
            "will", "has", "have", "was", "were", "you", "your", "our", "about", "after", "more", "than",
            "what", "why", "who", "when", "study", "research", "researchers", "scientists", "finds", "shows"}
KIND_PRIORITY = {"official": 0, "journal": 1, "press": 2, "search": 3, "media": 4}


def _title_tokens(title: str) -> set:
    s = re.sub(r"[【\[](画像|動画|写真)[】\]]", " ", _nfkc(title))
    s = re.sub(r"[「」『』【】（）()\[\]<>《》、。・,.:;!?！？\"'“”‘’…―—–\-|/]", " ", s)
    toks = {w for w in re.findall(r"[a-z0-9][a-z0-9+.%]*", s) if len(w) >= 3 and w not in _EN_STOP}
    for run in re.findall(r"[^\x00-\x7f\s]+", s):
        if len(run) == 1:
            toks.add(run)
        toks |= {run[i:i + 2] for i in range(len(run) - 1)}
    return toks


def dedup_similar(items: list, known_ids: set) -> tuple:
    """見出しが似た記事（同じ発表）を1件にまとめる。代表は news_candidates.json に既にある id を優先
    （既存の重複判定を崩さないため）、次に一次資料に近い kind（official > journal > press > search > media）。
    代表には sources（まとめた記事のフィード名・媒体名、代表を含む）と dup_ids を残す。戻り値は (まとめた後, まとめた組)。"""
    toks = [_title_tokens(it["title"]) for it in items]
    nums = [set(re.findall(r"\d+(?:\.\d+)?", _nfkc(it["title"]))) for it in items]
    parent = list(range(len(items)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for i in range(len(items)):
        if len(toks[i]) < 4:
            continue
        for j in range(i + 1, len(items)):
            if len(toks[j]) < 4:
                continue
            if (nums[i] - nums[j]) and (nums[j] - nums[i]):
                continue            # 互いに相手に無い数字がある（日付・版・数値の違う別の記事。例: NHK の「10月8日の動き」と「10月9日の動き」）
            inter = len(toks[i] & toks[j])
            if inter and inter / len(toks[i] | toks[j]) >= DEDUP_JACCARD:
                parent[find(j)] = find(i)
    groups = {}
    for i in range(len(items)):
        groups.setdefault(find(i), []).append(items[i])
    out, merged = [], []
    for members in groups.values():
        rep = min(members, key=lambda m: (m["id"] not in known_ids, KIND_PRIORITY.get(m.get("source_kind"), 9),
                                          bool(m.get("gnews_link")), m.get("published", "")))
        names = []
        for m in members:
            nm = m.get("outlet") or m.get("source", "")
            if nm and nm not in names:
                names.append(nm)
        rep["sources"] = names
        if len(members) > 1:
            rep["dup_ids"] = [m["id"] for m in members if m is not rep]
            rep["genre_hint"] = rep.get("genre_hint") or next((m["genre_hint"] for m in members if m.get("genre_hint")), "")
            merged.append(members)
        out.append(rep)
    return out, merged


def prescore_exclusions(it: dict, used: dict) -> str:
    """プールの段階で外す理由（score の課金を避ける）。使用済み・却下済みと同じ一次資料のURL、顧客の導入事例（宣伝）。"""
    u = _norm_url(it.get("url", ""))
    if u and u in used:
        return f"使用済みと同じ資料（{used[u]}）"
    if is_customer_case(it):
        return "顧客の導入事例（宣伝）"
    return ""


def _gemini():
    from google import genai
    from google.genai import types
    return genai.Client(api_key=API_KEY), types


def _json_from(text: str):
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if m:
        text = m.group(1)
    start = min([i for i in (text.find("["), text.find("{")) if i >= 0] or [0])
    return json.loads(text[start:])


def gemini_trending(days: int) -> list:
    """Google検索つきで、直近 days 日に日本語圏でも話題になった発表を挙げさせる（RSSに無い話題の補完）。"""
    client, types = _gemini()
    today = datetime.now().date().isoformat()
    prompt = (
        f"今日は{today}です。過去{days}日以内に発表された、{TOPIC_FILTER} に関する発表・ニュースのうち、"
        "日本語のニュースサイトやSNSでも話題になったもの、またはこれから話題になりそうなものを、Google検索で調べて"
        "最大15件挙げてください。噂・リーク・出典不明のものは除き、発表元（企業・大学・学術誌）が明確なものだけにしてください。"
        "株価や投資の話題は除いてください。\n"
        'JSON配列のみで出力: [{"title": "発表の内容（日本語）", "announced_by": "発表元", '
        '"published": "YYYY-MM-DD", "url": "発表元の一次資料のURL（分かれば）", "summary": "1〜2文"}]'
    )
    resp = client.models.generate_content(
        model=MODEL, contents=prompt,
        config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]))
    items = _json_from(resp.text)
    return [{"title": i.get("title", ""), "url": i.get("url", ""), "published": i.get("published", ""),
             "source": f"Gemini検索（{i.get('announced_by', '')}）", "source_kind": "search",
             "summary": i.get("summary", "")} for i in items]


def _id(item: dict) -> str:
    return hashlib.sha1((item.get("url") or item["title"]).encode("utf-8")).hexdigest()[:10]


def cmd_collect(days: int, sources_path: Path = None, no_gemini: bool = False):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    cfg = json.loads((sources_path or SOURCES_JSON).read_text(encoding="utf-8"))
    feeds = cfg["feeds"]
    pool = []
    for f in feeds:
        try:
            got = fetch_feed(f, since)
            pool += got
            print(f"  {f['name']}: {len(got)}件" + (f"（上限{f['max_items']}）" if f.get("max_items") else ""))
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️ {f['name']}: 取得失敗 {type(e).__name__}: {str(e)[:100]}")
    if cfg.get("gnews_queries"):
        pool += collect_gnews(cfg["gnews_queries"], since, int(cfg.get("gnews_max_per_query", 30)))
    if not no_gemini:
        try:
            trend = gemini_trending(days)
            pool += trend
            print(f"  Gemini検索（日本語圏で話題）: {len(trend)}件")
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️ Gemini検索に失敗: {e}")
    seen, uniq = set(), []
    for it in pool:
        it["id"] = _id(it)
        if it["id"] in seen:
            continue
        seen.add(it["id"])
        uniq.append(it)

    # 同じ発表の重複排除（複数のフィード・検索語・Googleニュースで見出しが似た記事を1件に）
    cands = load_candidates()["items"]
    known = {c["id"] for c in cands}
    n_before = len(uniq)
    uniq, merged = dedup_similar(uniq, known)
    print(f"\n重複排除: {n_before}件 → {len(uniq)}件（{len(merged)}組をまとめた）")
    for g in sorted(merged, key=len, reverse=True)[:8]:
        print(f"  ・{len(g)}件: " + " ｜ ".join(m["title"][:40] for m in g[:3]))

    # score の前に外す（課金を避ける）: 使用済みと同じ資料・顧客の導入事例（宣伝）
    used = used_source_urls(cands)
    dropped = []
    for it in list(uniq):
        why = prescore_exclusions(it, used)
        if why:
            dropped.append((it, why))
            uniq.remove(it)
    if dropped:
        print(f"プールの段階で除外: {len(dropped)}件")
        for it, why in dropped[:10]:
            print(f"  × {it['title'][:60]}（{why}）")

    if no_gemini:
        keep = uniq
        POOL_JSON.write_text(json.dumps({"collected_at": datetime.now().isoformat(timespec="seconds"),
                                         "days": days, "items": keep}, ensure_ascii=False, indent=2),
                             encoding="utf-8")
        print(f"\n収集 {len(uniq)}件（--no-gemini: 分野の絞り込みなし、{POOL_JSON.name}）")
        return

    # 話題の絞り込み（タイトルと要約だけで、番組で扱える分野かをまとめて判定する。検索なし）
    client, types = _gemini()
    keep = []
    n_calls = 0
    for i in range(0, len(uniq), 60):
        batch = uniq[i:i + 60]
        n_calls += 1
        listing = "\n".join(f"{j}. {b['title']} — {b['summary'][:160]}" for j, b in enumerate(batch))
        prompt = (f"次のニュースのうち、{TOPIC_FILTER} に当てはまるものの番号だけを選んでください。"
                  "製品の値下げ・人事・決算・株価・資金調達だけの話題、イベント告知は除きます。\n"
                  f"{listing}\n\nJSON配列（番号のリスト）のみで出力。")
        try:
            idx = _json_from(client.models.generate_content(model=MODEL, contents=prompt).text)
            keep += [batch[k] for k in idx if isinstance(k, int) and 0 <= k < len(batch)]
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️ 絞り込みに失敗（このまとまりは全件残す）: {e}")
            keep += batch
    POOL_JSON.write_text(json.dumps({"collected_at": datetime.now().isoformat(timespec="seconds"),
                                     "days": days, "items": keep}, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    print(f"\n収集 {len(uniq)}件 → 番組で扱える分野 {len(keep)}件（{POOL_JSON.name}。分野の判定 {n_calls}回の呼び出し、検索なし）")


def genres_brief() -> str:
    g = json.loads(GENRES_JSON.read_text(encoding="utf-8"))
    lines = [f"- {k}: {g['genres'][k]['label']} — {g['genres'][k]['definition']}（含める: {g['genres'][k]['include']}／含めない: {g['genres'][k]['exclude']}）"
             for k in g["order"]]
    return "\n".join(lines) + "\n分類の規則: " + g["rules"]["classify"] + "\nhealth: " + g["rules"]["health"]


def freshness_score(published: str) -> int:
    try:
        d = (datetime.now().date() - datetime.fromisoformat(published[:10]).date()).days
    except Exception:  # noqa: BLE001
        return 1
    return 5 if d <= 7 else 4 if d <= 14 else 3 if d <= 21 else 2 if d <= 31 else 1


def past_episodes_brief() -> str:
    try:
        q = json.loads(QUEUE_JSON.read_text(encoding="utf-8")).get("queue", [])
    except Exception:  # noqa: BLE001
        return ""
    return "\n".join(f"- {e.get('episode_id')}: {e.get('title', '')}" for e in q[-20:])


SCORE_PROMPT = """あなたは日本語の科学解説YouTubeチャンネル「幸せな未来のサイエンス」のネタ選定担当です。
番組は、夢語り担当とツッコミ担当の二人が、最新の発表を「一次資料」で確かめ、「本物か、盛っているか、いつ暮らしに来るか」を
「もうすぐ来る／3年はかかる／まだ眉唾」で判定する掛け合い形式です。

【候補のニュース】
タイトル: {title}
発表日（RSS/検索の日付）: {published}
情報源: {source}（{source_kind}）
URL: {url}
要約: {summary}

【この番組の過去の回（似た話の重複を避けるため）】
{past}

【視聴者の関心ごと（暮らしとの関わりを描くときの参照）】
{concerns}

Google検索で調べ、次を出力してください。
1. primary_sources: 一次資料（発表元の論文、企業・研究機関の公式ブログ・技術レポート・プレスリリース、デモの条件を書いた公式ページ）。
   報道記事は一次資料に含めない。各要素は {{"kind": "paper|official_blog|tech_report|press_release|official_page", "url": "...", "what_it_states": "そこに書かれている具体的な数値・条件"}}
2. announced_on: 一次資料での発表日（YYYY-MM-DD）
3. headline_claim: 見出し・報道で言われていること（1文）
4. actual_content: 一次資料に実際に書かれていること（数値・条件・被験者数・試行回数・限界を具体的に、2〜4文）
5. 採点（1〜5）:
   - buzz_jp_est: 現時点（今日まで）の日本語圏での注目度の推定（RSSでの実測が失敗したときの予備）。将来話題になりそうかは含めない。
     数えるのは「この発表（この研究・この製品）そのもの」を扱った日本語の記事だけ。テーマ全般の記事（薬の名前・食品名だけの記事）、
     発表元の自社リリース、PR TIMES等の配信、転載サイトは数えない。
     5 = 全国紙・NHK・Yahoo!ニュースを含む10以上の媒体が報じ、一般の人も名前を聞いたことがある
     4 = 6〜9の媒体が報じた、またはYahoo!ニュースに掲載された
     3 = 3〜5の媒体が報じた（専門メディア中心でもよい）
     2 = 1〜2本だけ
     1 = 見つからない
     迷ったら低い方を付ける。
   - verifiability: 一次資料で答え合わせできるか（一次資料が無い・噂・リーク・出典不明なら1。具体的な数値や条件が一次資料にあれば5）
   - hype_gap: 見出しと実際の中身の差（差が大きいほど高い。ツッコミの材料になる）
   - debate: 議論を呼ぶか・二人の判定が割れそうか
   - wonder: 驚き・ワクワク（温かい感動だけでなく「え、本当に？」という知的な驚きも）
   - life_relevance: 暮らしにどう関わるか（関心ごとのどれかに具体的につながるほど高い）
   - work_relevance: 仕事・ビジネスにどう関わるか（働く人・経営者・個人事業主が今日の仕事や判断で使える、または影響を受けるほど高い。
     開発者・研究者しか使わない専用品は低い）
6. concern_id: いちばん近い関心ごとのid（無ければ null）
7. entry_question: 視聴者側の問い（「〜は本当？」「〜はもう買える？」「〜はいつ来る？」の形。一次資料の範囲を超えない）
8. expected_verdicts: {{"dreamer": "soon|decade|dubious", "skeptic": "soon|decade|dubious"}}
9. tsukkomi_material: ツッコミが突ける具体的な点（1〜2文）
10. investment_related: 株価・投資判断の話が中心なら true
11. deja_vu_note: 過去の回と似ていれば、どの回か
12. genre: 次の5ジャンルのどれか1つ（id）。
{genres}
13. health: 健康系の回として数えるか（true/false）。上の health の規則に従う
14. jp_news_query: Google ニュース（日本語）でこの発表そのものの記事を探すための検索語。固有名詞（製品名・モデル名・研究機関名・企業名）を必ず1つ含む2語以内
    （例: "GPT-6.1 Sol"、"シャープ 介護 AIトレーナー"）。一般名詞だけ（例: "ゲノム編集 ALS"）にしない。日本語の報道で使われる表記にする（英語の製品名は英語のまま）。
15. jp_title_anchor: この発表を扱った日本語記事の見出しに必ず含まれるはずの語を1〜3個の配列で（どれか1つを含めば関連とみなす。例: ["GPT-6.1"]、["クレアチン"]、["介護向けAIトレーナー", "シャープ"]）。
    テーマ全般の語（"超加工食品" だけ等）は避け、この研究・製品に固有の語を入れる。
16. announcement_type: research | product_release | customer_case | policy | event | other（企業による顧客の導入事例・成功談は customer_case）

JSONオブジェクトのみで出力（他の文章は書かない）:
{{"primary_sources": [], "announced_on": "", "headline_claim": "", "actual_content": "", "buzz_jp_est": 0, "verifiability": 0,
"hype_gap": 0, "debate": 0, "wonder": 0, "life_relevance": 0, "work_relevance": 0, "concern_id": null, "entry_question": "",
"expected_verdicts": {{}}, "tsukkomi_material": "", "investment_related": false, "deja_vu_note": "", "genre": "", "health": false,
"jp_news_query": "", "jp_title_anchor": [], "announcement_type": ""}}
"""


def score_item(client, types, item: dict, past: str, concerns: str) -> dict:
    prompt = SCORE_PROMPT.format(title=item["title"], published=item.get("published", ""),
                                 source=item.get("source", ""), source_kind=item.get("source_kind", ""),
                                 url=item.get("url", ""), summary=item.get("summary", ""),
                                 past=past or "（なし）", concerns=concerns, genres=genres_brief())
    for attempt in range(3):
        try:
            resp = client.models.generate_content(
                model=MODEL, contents=prompt,
                config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]))
            return _json_from(resp.text)
        except Exception as e:  # noqa: BLE001
            if attempt == 2:
                return {"_error": str(e)}
            time.sleep(2 ** (attempt + 1))


def stake(c: dict) -> int:
    """視聴者との関わり＝暮らし（life_relevance）と仕事・ビジネス（work_relevance）の高い方。ゲートと core に使う。"""
    return max(_clamp5(c.get("life_relevance")), _clamp5(c.get("work_relevance")))


def _clamp5(v) -> int:
    try:
        return max(0, min(5, int(round(float(v or 0)))))
    except (TypeError, ValueError):
        return 0


def buzz_value(c: dict):
    """注目度の値と出どころ。実測（buzz_measured）があればそれ、無ければ推定（buzz_jp_est、旧データは buzz_jp）。"""
    if c.get("buzz_measured") is not None:
        return _clamp5(c["buzz_measured"]), "実測"
    est = c.get("buzz_jp_est", c.get("buzz_jp"))
    return _clamp5(est), "推定"


def overall(v: dict, published: str) -> float:
    s = dict(v)
    s["freshness"] = freshness_score(v.get("announced_on") or published)
    s["buzz"] = buzz_value(v)[0]
    total = 0.0
    for k, w in WEIGHTS.items():
        try:
            total += max(0, min(5, int(round(float(s.get(k, 0)))))) * w
        except (TypeError, ValueError):
            pass
    return round(total, 2), s["freshness"]


def load_candidates() -> dict:
    if CANDIDATES_JSON.exists():
        return json.loads(CANDIDATES_JSON.read_text(encoding="utf-8"))
    return {"_comment": "kl_news_scan.py score の結果。status: available / used / rejected（却下は rejected_reason を残す）",
            "items": []}


# score の対象選び（2026-10-11、なるさんの方針「旬と注目度を最重視」）:
# ジャンルごとに分け、採点済みの本命候補（available かつゲート通過）が少ないジャンルから1件ずつ順に選ぶ。
# ジャンル内は 報じた媒体の数（sources＋dup_ids）→ 新しい順 → kind（公式・学術誌・プレス > 報道 > 娯楽寄りの報道）
GENRE_ORDER = ("humanoid", "life_tech", "food_health", "medical", "ai")
UNKNOWN_GENRE = "不明"
GENRE_RULES = [   # 見出しの簡易分類（genre_hint が無いときだけ使う。上から順に最初に当たったもの）
    ("humanoid", r"ヒューマノイド|人型ロボ|humanoid|optimus|unitree|二足歩行"),
    ("medical", r"がん|癌|cancer|ips細胞|治療|therap|患者|patient|新薬|薬剤|治療薬|drug|疾患|disease|alzheimer|認知症|遺伝子治療|gene therapy|clinical|治験|tumor|再生医療|stem cell"
                r"|眼科|眼の|網膜|視力|retina|\beyes?\b|感染症|infection|ウイルス|virus|(?<!頭)脳|\bbrains?\b|神経|neuro"),
    ("food_health", r"食事|食べ|食品|diet|food|腸内|gut|睡眠|sleep|運動|exercise|栄養|nutri|肥満|obes|健康|血糖|blood sugar|メンタル|mental health"
                    r"|関節|膝|knee|arthritis|肝臓|\bliver|脂肪|\bfat|サプリ|supplement|オリーブ|olive|コーヒー|coffee"),
    ("life_tech", r"ロボット|robot|電池|battery|電気自動車|\bev\b|自動運転|autonomous|self-driving|ドローン|drone|家電|住宅|防災|地震|太陽光|solar|エネルギー|energy|充電|charging"),
    ("ai", r"\bai\b|ai[^a-z]|生成ai|llm|gpt|openai|gemini|claude|chatgpt|deepmind|機械学習|machine learning|language model|エージェント|agent"),
]
ENTERTAINMENT_SOURCES = ("GIGAZINE", "ナゾロジー")


def pool_genre(p: dict) -> str:
    """見出し・要約の簡易分類で決まればそれ、決まらないときだけ genre_hint（Googleニュースの検索語のジャンル）。
    検索語には別の話題も引っかかるため（例: 「がん 新しい治療 研究」で拾った「AI『思考』過程は信用できず」）、見出しを優先する。"""
    t = _nfkc(p.get("title", "") + " " + (p.get("summary") or "")[:120])
    for g, rx in GENRE_RULES:
        if re.search(rx, t):
            return g
    if p.get("genre_hint") in GENRE_ORDER:
        return p["genre_hint"]
    return UNKNOWN_GENRE


def outlet_count(p: dict) -> int:
    """報じた独立した媒体の数（重複排除でまとめた sources から数える。最低1）。
    buzz と同じく、転載・まとめ（Yahoo!ニュース・ライブドア・BigGo 等、AGGREGATOR_NAMES）と PR配信は数えない。
    同じ媒体の別の版（【画像】版・「ITmedia」と「ITmedia NEWS」のような表記ゆれ）は1つと数える。dup_ids の数は使わない
    （同じ媒体の【画像】版も dup_ids に入るため）。"""
    names = []
    for n in p.get("sources") or []:
        low = _nfkc(n)
        if not low or any(_nfkc(a) in low for a in AGGREGATOR_NAMES + PR_WIRE_NAMES):
            continue
        if any(low.startswith(x) or x.startswith(low) for x in names):
            continue
        names.append(low)
    return max(len(names), 1)


def _is_entertainment(p: dict) -> bool:
    return any(p.get("source", "").startswith(n) or p.get("outlet") == n for n in ENTERTAINMENT_SOURCES)


# 日本語フィード（news_sources.json の feeds のうち日本語の媒体）。Googleニュース由来は見出しが日本語なら日本語媒体とみなす
JP_FEEDS = ("ITmedia AI+", "ITmedia NEWS", "NHK 科学・文化", "GIGAZINE", "ナゾロジー", "JST サイエンスポータル")
HANGUL = re.compile(r"[가-힣]")
FOREIGN_OUTLET_NAMES = ("vietnam.vn",)   # 見出しを日本語に訳して載せる外国の媒体（Googleニュースに出てくる）


def jp_outlet_count(p: dict) -> int:
    """この記事を報じた独立した日本語の媒体の数（2026-10-11、日本での注目度の先行指標）。
    見出しが日本語で、日本語フィード由来か Googleニュース由来のものだけ。転載・まとめ・PR配信、同じ媒体の別版、
    外国の媒体（韓国語の媒体名・FOREIGN_OUTLET_NAMES・外国のドメイン）、Gemini検索の補完は数えない。
    重複排除は見出しの語で似たものをまとめるので、日本語の見出しの代表のまとまりは日本語の記事どうし。"""
    if p.get("source_kind") == "search":
        return 0
    if not (KANA.search(p.get("title", "")) or KANJI.search(p.get("title", ""))):
        return 0
    if not (p.get("gnews_link") or p.get("outlet") or p.get("source") in JP_FEEDS):
        return 0
    if _host_in(p.get("outlet_host", ""), FOREIGN_HOSTS) or (p.get("outlet_host") or "").endswith(FOREIGN_TLDS):
        return 0
    names = []
    for n in p.get("sources") or [p.get("outlet") or p.get("source", "")]:
        low = _nfkc(n)
        if not low or HANGUL.search(n) or any(f in low for f in FOREIGN_OUTLET_NAMES):
            continue
        if any(_nfkc(a) in low for a in AGGREGATOR_NAMES + PR_WIRE_NAMES):
            continue
        if any(low.startswith(x) or x.startswith(low) for x in names):
            continue
        names.append(low)
    return len(names)


def scoring_priority(p: dict) -> tuple:
    """ジャンル内の並び（小さいほど先）。区分: 0=日本語の媒体が報じている（多いほど先）、1=公式・プレス・学術誌、2=その他の報道。
    各区分の中で娯楽寄り（GIGAZINE・ナゾロジー）は最後、残りは新しい順。"""
    jp = jp_outlet_count(p)
    tier = 0 if jp >= 1 else 1 if p.get("source_kind") in ("official", "press", "journal") else 2
    return (tier, _is_entertainment(p), -jp, _neg_date(p.get("published", "")))


def select_for_scoring(todo: list, cands: list, top: int, verbose: bool = True) -> list:
    used = used_source_urls(cands)
    have = {g: 0 for g in GENRE_ORDER}
    for c in cands:
        if c.get("status") == "available" and c.get("genre") in have and not gate_reasons(c, used):
            have[c["genre"]] += 1
    # 「不明」は巡回に入れず、ジャンルの候補で top に満たないときだけ空き枠を埋める
    order = sorted(GENRE_ORDER, key=lambda g: (have[g], GENRE_ORDER.index(g)))
    groups = {g: [] for g in order + [UNKNOWN_GENRE]}
    for p in todo:
        groups[pool_genre(p)].append(p)
    for g in groups:
        groups[g].sort(key=scoring_priority)
    picked, idx = [], {g: 0 for g in order}
    while len(picked) < top and any(idx[g] < len(groups[g]) for g in order):
        for g in order:
            if len(picked) >= top:
                break
            if idx[g] < len(groups[g]):
                picked.append((g, groups[g][idx[g]]))
                idx[g] += 1
    for p in groups[UNKNOWN_GENRE][: max(0, top - len(picked))]:
        picked.append((UNKNOWN_GENRE, p))
    if verbose:
        print("採点済みの本命候補（available・ゲート通過）の数: " + "、".join(f"{g} {have[g]}" for g in GENRE_ORDER))
        print("回す順: " + " → ".join(order) + f"（{UNKNOWN_GENRE}は空き枠だけ）")
        print("未採点の候補（ジャンル別）: " + "、".join(f"{g} {len(groups[g])}" for g in order + [UNKNOWN_GENRE]))
        cnt = {}
        for g, _ in picked:
            cnt[g] = cnt.get(g, 0) + 1
        print(f"選んだ {len(picked)}件: " + "、".join(f"{g} {n}" for g, n in cnt.items()))
        for n, (g, p) in enumerate(picked, 1):
            print(f"  {n:2d}. [{g}] {p.get('published', '')} 日本語媒体{jp_outlet_count(p)} {p.get('source_kind', '')}"
                  f" ｜ {p['title'][:60]} ｜ {p.get('source', '')[:40]}")
    return [p for _, p in picked]


def _neg_date(d: str) -> int:
    try:
        return -datetime.fromisoformat(d[:10]).toordinal()
    except Exception:  # noqa: BLE001
        return 0


SCORE_MAX_AGE_DAYS = 21       # ゲートの鮮度（freshness_score 3以上＝21日以内）と同じ


def _pool_age(p: dict):
    try:
        return (datetime.now().date() - datetime.fromisoformat((p.get("published") or "")[:10]).date()).days
    except Exception:  # noqa: BLE001
        return None


def cmd_score(top: int, dry_run: bool = False):
    pool = json.loads(POOL_JSON.read_text(encoding="utf-8"))["items"]
    cands = load_candidates()
    known = {c["id"] for c in cands["items"]}
    todo = [p for p in pool if p["id"] not in known and not (set(p.get("dup_ids") or []) & known)]
    # 鮮度の簡易ゲート（2026-10-11）: 記事の日付から SCORE_MAX_AGE_DAYS 日を超えたものは採点しない（ゲートで落ちるため）。
    # 日付の無いもの（Gemini検索で日付が取れなかった等）は残す
    stale = [p for p in todo if _pool_age(p) is not None and _pool_age(p) > SCORE_MAX_AGE_DAYS]
    if stale:
        print(f"  発表から{SCORE_MAX_AGE_DAYS}日を超えた {len(stale)}件は採点しません")
    todo = [p for p in todo if p not in stale]
    # ジャンルを順に回して最大 top 件だけ採点する（検索つきの呼び出しは1件ずつ課金されるため）。2026-10-11:
    # 以前は新しい順だけで、その日の ScienceDaily・GIGAZINE などで埋まっていた
    todo = select_for_scoring(todo, cands["items"], top)
    if dry_run:
        print("\n--dry-run: 採点せずに終了します")
        return
    concerns = json.loads(CONCERNS_JSON.read_text(encoding="utf-8"))["concerns"]
    concerns_txt = "\n".join(f"- {c['id']}: {c['label']}" for c in concerns)
    client, types = _gemini()
    past = past_episodes_brief()
    for p in todo:
        v = score_item(client, types, p, past, concerns_txt)
        if "_error" in v:
            print(f"  ⚠️ 採点失敗: {p['title'][:60]} ({v['_error'][:80]})")
            continue
        if "buzz_jp_est" not in v and "buzz_jp" in v:   # 旧キーで返ってきたときの互換
            v["buzz_jp_est"] = v.pop("buzz_jp")
        score, fresh = overall(v, p.get("published", ""))
        excluded = []
        if int(v.get("verifiability") or 0) < MIN_VERIFIABILITY or not v.get("primary_sources"):
            excluded.append("一次資料で確認できない")
        if v.get("investment_related"):
            excluded.append("投資・株価が中心")
        entry = dict(p, **v, freshness=fresh, overall_score=score, scan_version=SCAN_VERSION,
                     status="excluded" if excluded else "available", excluded_reason="・".join(excluded),
                     scored_at=datetime.now().date().isoformat())
        cands["items"].append(entry)
        mark = "×" if excluded else " "
        print(f" {mark}[{score:.2f}] {p['title'][:70]}")
        print(f"       問い: {v.get('entry_question', '')}  鮮度{fresh} 検証{v.get('verifiability')} "
              f"誇張{v.get('hype_gap')} 議論{v.get('debate')} 話題(推定){v.get('buzz_jp_est', v.get('buzz_jp'))}"
              + (f"  除外: {entry['excluded_reason']}" if excluded else ""))
        time.sleep(1.0)
    CANDIDATES_JSON.write_text(json.dumps(cands, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{len(todo)}件を採点して {CANDIDATES_JSON.name} に追記しました")


def cmd_tag():
    """採点済みでジャンルが未付与の候補に、5ジャンルと health を付ける（検索なし・テキストのみの1回の呼び出し）。"""
    cands = load_candidates()
    todo = [c for c in cands["items"] if not c.get("genre")]
    if not todo:
        print("ジャンル未付与の候補はありません")
        return
    client, types = _gemini()
    rows = "\n".join(f"{i}. {c['title']} / {c.get('entry_question', '')} / {(c.get('actual_content') or c.get('summary') or '')[:160]}"
                     for i, c in enumerate(todo))
    prompt = (f"科学解説番組のニュース候補を5ジャンルに分類してください。\n{genres_brief()}\n\n候補:\n{rows}\n\n"
              'JSON配列のみ出力: [{"i": 0, "genre": "id", "health": false}, ...]（全候補分）')
    resp = client.models.generate_content(model=MODEL, contents=prompt)
    out = _json_from(resp.text)
    valid = set(json.loads(GENRES_JSON.read_text(encoding="utf-8"))["order"])
    n = 0
    for r in out:
        c = todo[int(r["i"])]
        if r.get("genre") in valid:
            c["genre"], c["health"] = r["genre"], bool(r.get("health"))
            n += 1
    CANDIDATES_JSON.write_text(json.dumps(cands, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{n}/{len(todo)}件にジャンルを付けました")


def _save_candidates(cands: dict):
    # 旧データの buzz_jp は消さずに buzz_jp_est として写す（2026-10-11、P2の移行。全件の再採点はしない）
    for c in cands["items"]:
        if "buzz_jp_est" not in c and "buzz_jp" in c:
            c["buzz_jp_est"] = c["buzz_jp"]
    CANDIDATES_JSON.write_text(json.dumps(cands, ensure_ascii=False, indent=2), encoding="utf-8")


# ============================================================
# P0: ベスト3・本命枠のゲート（2026-10-11、費用ゼロ）
# ============================================================

def _host(u: str) -> str:
    try:
        h = urllib.parse.urlsplit(u if "://" in (u or "") else "http://" + (u or "")).hostname or ""
    except ValueError:
        return ""
    return h.lower()[4:] if h.lower().startswith("www.") else h.lower()


def _norm_url(u: str) -> str:
    """一次資料URLの比較用の正規化。スキーム・www.・末尾のスラッシュ・クエリ・#以降の違いを無視する。
    パス先頭の言語コード（/ja-JP/ 等）も落とす（kl034 は openai.com/ja-JP/index/... を参照していた）。"""
    u = (u or "").strip()
    if not u:
        return ""
    try:
        sp = urllib.parse.urlsplit(u if "://" in u else "http://" + u)
    except ValueError:
        return u.lower()
    path = re.sub(r"^/[a-z]{2}-[a-z]{2}(?=/|$)", "", sp.path.lower()).rstrip("/")
    return _host(u) + path


def used_source_urls(cands: list) -> dict:
    """使用済み・却下済みの一次資料URL（正規化）→ どこで使ったか。
    topics_queue.json の各回の references[].url と、news_candidates.json の used / rejected の primary_sources。"""
    out = {}
    try:
        for e in json.loads(QUEUE_JSON.read_text(encoding="utf-8")).get("queue", []):
            for r in e.get("references", []) or []:
                if r.get("url"):
                    out.setdefault(_norm_url(r["url"]), e.get("episode_id", "既出の回"))
    except Exception:  # noqa: BLE001
        pass
    for c in cands:
        if c.get("status") in ("used", "rejected"):
            label = c.get("used_in") or ("却下済み" if c["status"] == "rejected" else "使用済み")
            for s in c.get("primary_sources", []) or []:
                if s.get("url"):
                    out.setdefault(_norm_url(s["url"]), f"{label}: {c['title'][:30]}")
    out.pop("", None)
    return out


# 企業による顧客の導入事例（宣伝）の簡易判定。announcement_type が無い既存候補だけに使う（2026-10-11）。
# 規則: 情報源（一次資料・候補のURL）が企業ブログのホストで、かつ見出しが導入事例の形のもの。
#   - "X cuts ... with ..."（Asana・Sophos）
#   - "turns days of work into minutes" のような "turns ... into ..."（Oracle、Pollo AI）
#   - "... with ChatGPT / OpenAI / Codex"（Oracle、Chatham、The Den）
#   - "How 〈固有名詞〉 uses / is / turns ..."（Albertsons。"How workers are ..." のような一般名詞は除く）
#   - "frees up ..."（The Den）
# 研究発表・新製品（"Introducing ..."）はこの形にならないので巻き込まない。
CORPORATE_BLOG_HOSTS = ("openai.com", "anthropic.com", "blog.google", "deepmind.google", "microsoft.com",
                        "nvidia.com", "aws.amazon.com", "about.fb.com", "meta.com")
CUSTOMER_CASE_TITLE = [
    re.compile(r"\bcuts\b.+\bwith\b", re.I),
    re.compile(r"\bturns\b.+\binto\b", re.I),
    re.compile(r"\bwith (ChatGPT|OpenAI|Codex|Claude|Gemini)\b", re.I),
    re.compile(r"^How [A-Z][\w&.'-]*( [A-Z][\w&.'-]*)* (uses|is|are|turns|built|scales|cuts)\b"),
    re.compile(r"\bfrees up\b", re.I),
]
ANNOUNCEMENT_TYPES = ("research", "product_release", "customer_case", "policy", "event", "other")


def is_customer_case(c: dict) -> bool:
    if c.get("announcement_type"):
        return c["announcement_type"] == "customer_case"
    hosts = {_host(c.get("url", ""))} | {_host(s.get("url", "")) for s in c.get("primary_sources", []) or []}
    corporate = any(h == b or h.endswith("." + b) for h in hosts if h for b in CORPORATE_BLOG_HOSTS)
    return corporate and any(p.search(c.get("title", "")) for p in CUSTOMER_CASE_TITLE)


def age_days(c: dict) -> int:
    try:
        return (datetime.now().date() - datetime.fromisoformat((c.get("announced_on") or c.get("published") or "")[:10]).date()).days
    except Exception:  # noqa: BLE001
        return 999


def gate_reasons(c: dict, used: dict) -> list:
    """ベスト3・本命枠（と buzz の実測対象）に入れない理由。空ならゲート通過。"""
    r = []
    if _clamp5(c.get("verifiability")) < GATE_MIN_VERIFIABILITY:
        r.append(f"検証<{GATE_MIN_VERIFIABILITY}")
    if freshness_score(fresh_date(c)) < GATE_MIN_FRESHNESS:
        r.append(f"鮮度<{GATE_MIN_FRESHNESS}")
    if c.get("primary_verified") is False:     # 2026-10-15: 一次資料のURLが全部404・ソフト404（verify）。None（要確認）は通す
        r.append("一次資料URLが実在しない（" + (c.get("primary_verified_note") or "全URLが404・ソフト404") + "）")
    if stake(c) < GATE_MIN_LIFE:
        r.append(f"暮らし・仕事<{GATE_MIN_LIFE}")
    hit = [used[u] for u in (_norm_url(s.get("url", "")) for s in c.get("primary_sources", []) or []) if u in used]
    if hit:
        r.append(f"使用済みと同じ一次資料（{hit[0]}）")
    if is_customer_case(c):
        r.append("宣伝（顧客の導入事例）")
    return r


# 一次資料のURL確認。HTTPコードだけでなく、<title> に「404」「ページが見つかりません」等が無いかも見る
# （CiRA の .../241009-110000.html は HTTP 200 で中身が「エラー 404」だった）
SOFT404_TITLE = re.compile(
    r"\b404\b|not\s*found|ページが見つかりません|ページが存在しません|お探しのページ(は|が)|^\s*(エラー|error)\s*$"
    r"|ページを表示できません|削除された可能性", re.I)
URL_CHECK_INTERVAL = 2.0     # 秒。一次資料の確認は2秒以上あける
BROWSER_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
              "Accept-Language": "ja,en-US;q=0.8,en;q=0.6"}


def _decode(raw: bytes, content_type: str) -> str:
    m = re.search(r"charset=([\w-]+)", content_type or "", re.I) or \
        re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", raw[:4000], re.I)
    enc = m.group(1) if m else "utf-8"
    enc = enc.decode("ascii", "ignore") if isinstance(enc, bytes) else enc
    try:
        return raw.decode(enc, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def check_primary_url(url: str, timeout: int = 15, anchors: list = None) -> dict:
    """一次資料のURLを開いて確かめる（標準ライブラリのみ。取得したHTMLは <title> と本文の先頭を文字列として読むだけで実行しない）。
    ok: True=開ける / False=404・ソフト404 / None=判断できない（403・429等。ボット拒否の可能性があり人が確認）
    anchors（候補の固有の語）を渡すと、<title>＋本文の先頭にどれかが含まれるかを anchor_hit に入れる（参考表示。判定には使わない）"""
    try:
        resp = urllib.request.urlopen(urllib.request.Request(url, headers=BROWSER_UA), timeout=timeout)
        raw = resp.read(400_000)
        html = _decode(raw, resp.headers.get("Content-Type", ""))
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        title = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
        if title and SOFT404_TITLE.search(title):
            return {"url": url, "ok": False, "status": f"ソフト404（HTTP {resp.status}、title「{title[:40]}」）"}
        out = {"url": url, "ok": True, "status": f"HTTP {resp.status}" + (f"「{title[:30]}」" if title else ""),
               "page_title": title[:120]}
        final = resp.geturl() or url
        if final != url and urllib.parse.urlsplit(final).path in ("", "/") and urllib.parse.urlsplit(url).path not in ("", "/"):
            out["redirected_to_top"] = True      # 記事のURLがトップページに転送された（記事が無い可能性）
            out["status"] += f"（トップページへ転送: {final[:60]}）"
        if anchors:
            body = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html[:200_000], flags=re.I | re.S)
            head = _nfkc(title + " " + re.sub(r"<[^>]+>", " ", body)[:30_000])
            out["anchor_hit"] = any(a in head for a in anchors)
        return out
    except urllib.error.HTTPError as e:
        if e.code in (404, 410):
            return {"url": url, "ok": False, "status": f"HTTP {e.code}"}
        return {"url": url, "ok": None, "status": f"HTTP {e.code}（ボット拒否の可能性。ブラウザで確認）", "http": e.code}
    except Exception as e:  # noqa: BLE001
        return {"url": url, "ok": None, "status": f"取得失敗（{type(e).__name__}: {str(e)[:60]}）", "transient": True}


# ============================================================
# verify: 一次資料の実在確認（2026-10-15、NEWS_REDESIGN_2026-10-15.md §3.5 の第1段階）
# score の直後に、primary_sources のURLを開いて確かめる（Gemini不要・無料）。
# primary_verified: True＝1件でも開けた（HTTP 200・ソフト404でない、DOIはハンドルAPIで実在）／
#                   False＝全URLが404・ソフト404（またはURLが無い）→ ゲートで落とす（削除はしない）／
#                   None＝403・429・タイムアウト等で判断できない（要確認。ベスト3には残すが目立たせる）
# ============================================================

DOI_HANDLE_API = "https://doi.org/api/handles/"
DOI_IN_URL = re.compile(r"(10\.\d{4,9}/[^\s?#&]+)", re.I)
VERIFY_MAX_URLS = 4              # 1候補あたり確かめるURLの上限
VERIFY_SAME_HOST_INTERVAL = 5.0  # 秒。同じホストへの連続アクセスはこれ以上あける（doi.org など）
VERIFY_RETRY_WAIT = 5.0          # 秒。タイムアウト・429・5xx のときだけ1回だけ取り直す
VERIFY_DEFAULT_MAX = 60          # verify の既定の上限（候補の数）
PRIMARY_LABEL = {True: "確認済み", False: "実在しない", None: "要確認"}


def extract_doi(url: str) -> str:
    """URLからDOIを取り出す（doi.org/10.xxx、出版社の /doi/10.xxx/... など）。無ければ空。"""
    try:
        sp = urllib.parse.urlsplit(url or "")
    except ValueError:
        return ""
    path = urllib.parse.unquote(sp.path or "")
    if _host(url) in ("doi.org", "dx.doi.org"):
        m = DOI_IN_URL.search(path)
        return m.group(1).rstrip("/.") if m else ""
    m = re.search(r"/doi/(?:abs/|full/|pdf/|epdf/|epub/)?(10\.\d{4,9}/[^\s?#&]+)", path, re.I)
    return m.group(1).rstrip("/.") if m else ""


def check_doi(doi: str, timeout: int = 15) -> dict:
    """doi.org のハンドルAPI（無料・認証なし。出版社に行かないのでボット拒否を受けない）でDOIの実在を確かめる。
    HTTP 200 で responseCode 1 → 実在。responseCode 100（HTTP 404）→ 実在しない。"""
    api = DOI_HANDLE_API + urllib.parse.quote(doi, safe="/")
    try:
        body = urllib.request.urlopen(urllib.request.Request(api, headers=UA), timeout=timeout).read(200_000)
        code = None
    except urllib.error.HTTPError as e:
        code = e.code
        try:
            body = e.read(200_000)
        except Exception:  # noqa: BLE001
            body = b""
    except Exception as e:  # noqa: BLE001
        return {"ok": None, "status": f"DOI確認の取得失敗（{type(e).__name__}）", "transient": True}
    try:
        rc = json.loads(body.decode("utf-8", "replace")).get("responseCode")
    except Exception:  # noqa: BLE001
        rc = None
    if rc == 1:
        return {"ok": True, "status": f"DOI実在（ハンドルAPI、{doi}）"}
    if rc == 100 or code == 404:
        return {"ok": False, "status": f"DOIが存在しない（ハンドルAPI、{doi}）"}
    return {"ok": None, "status": f"DOI確認で判断できない（HTTP {code}、responseCode {rc}）",
            "transient": code is not None and (code == 429 or code >= 500)}


def _verify_anchors(c: dict) -> list:
    """ページに含まれるかを見る固有の語（参考表示用）。jp_title_anchor のうち組織名・略語だけでないもの。"""
    a = c.get("jp_title_anchor") or []
    a = [a] if isinstance(a, str) else a
    return [x for x in (_nfkc(v) for v in a if v and v.strip()) if x not in GENERIC_ANCHORS]


def verify_one_url(url: str, anchors: list) -> dict:
    """1つのURLを確かめる。doi.org はハンドルAPIだけ。出版社のURLで判断できない（403等）ときは、URL中のDOIをハンドルAPIで確かめる。"""
    doi = extract_doi(url)
    if doi and _host(url) in ("doi.org", "dx.doi.org"):
        r = dict(check_doi(doi), url=url, method="doi_handle")
        return r
    r = dict(check_primary_url(url, anchors=anchors), method="http")
    if r["ok"] is None and doi:
        d = check_doi(doi)
        if d["ok"] is not None:
            r = dict(r, ok=d["ok"], status=f"{r['status']} → {d['status']}", method="http+doi_handle")
    return r


class _HostPacer:
    """全体で URL_CHECK_INTERVAL、同じホストには VERIFY_SAME_HOST_INTERVAL 以上の間隔をあける。"""

    def __init__(self):
        self.last_any = 0.0
        self.last_host = {}

    def wait(self, url: str):
        h = "doi.org" if extract_doi(url) else _host(url)
        now = time.monotonic()
        need = max(self.last_any + URL_CHECK_INTERVAL, self.last_host.get(h, 0.0) + VERIFY_SAME_HOST_INTERVAL) - now
        if self.last_any and need > 0:
            time.sleep(need)
        self.last_any = self.last_host[h] = time.monotonic()


def effective_ok(x: dict):
    """URL1件の判定。開けても、トップページへの転送か、候補の固有の語がページに無いときは「要確認」（別のページの可能性）。
    固有の語は jp_title_anchor（日本語の見出し向けの語）なので、英語のページでは当たらないことがある。そのときも要確認に倒す
    （ゲートで落とすのは全URLが404のときだけなので、要確認が増えても候補は消えない）。"""
    if x.get("ok") and (x.get("redirected_to_top") or x.get("anchor_hit") is False):
        return None
    return x.get("ok")


def primary_verdict(results: list):
    """URLごとの判定（effective_ok）から primary_verified を決める。1件でも True → True、全部 False（またはURLなし）→ False、
    それ以外 → None（403・429・開けたが固有の語が無い など）。"""
    oks = [effective_ok(x) for x in results]
    if True in oks:
        return True
    if not oks or all(o is False for o in oks):
        return False
    return None


def verify_candidate(c: dict, pacer: "_HostPacer") -> list:
    """候補の一次資料URLを確かめて、primary_verified 等を c に書く（url_ok・url_status など既存の欄も同じ結果で更新する）。"""
    anchors = _verify_anchors(c)
    res = []
    for s in (c.get("primary_sources") or [])[:VERIFY_MAX_URLS]:
        url = (s.get("url") or "").strip()
        if not url:
            continue
        pacer.wait(url)
        r = verify_one_url(url, anchors)
        if r["ok"] is None and (r.get("transient") or r.get("http") == 429 or (r.get("http") or 0) >= 500):
            time.sleep(VERIFY_RETRY_WAIT)
            pacer.wait(url)
            r2 = verify_one_url(url, anchors)
            r = dict(r2, status=r2["status"] + "（再試行）")
        r.pop("transient", None)
        r.pop("http", None)
        r["kind"] = s.get("kind", "")
        res.append(r)
    now = datetime.now().isoformat(timespec="seconds")
    c["primary_verified"] = primary_verdict(res)
    c["primary_check"] = res
    c["primary_verified_at"] = now
    if not res:
        c["primary_verified_note"] = "一次資料のURLが無い"
    else:
        c.pop("primary_verified_note", None)
        # 既存の欄（check-urls・旧 list --check-urls の表示用）。url_ok は「1件でもNGなら False」のまま
        oks = [x["ok"] for x in res]
        c["url_check"] = [{"url": x["url"], "ok": x["ok"], "status": x["status"]} for x in res]
        c["url_ok"] = False if False in oks else (True if all(oks) else None)
        c["url_status"] = " ／ ".join(f"{_host(x['url'])}: {x['status']}" for x in res)
        c["url_checked_at"] = now
    return res


def _primary_line(c: dict) -> str:
    if "primary_verified" not in c:
        return "一次資料の実在: 未確認（verify 未実行）"
    pv = c["primary_verified"]
    parts = []
    for x in c.get("primary_check") or []:
        hit = {True: "・固有語あり", False: "・固有語なし（別ページの可能性）"}.get(x.get("anchor_hit"), "")
        parts.append(f"{_host(x['url'])}: {x['status']}{hit}")
    body = " ／ ".join(parts) or c.get("primary_verified_note", "")
    return f"一次資料の実在: {PRIMARY_LABEL[pv]}{'（ブラウザで開いて確かめる）' if pv is None else ''} — {body}" \
           f"（{(c.get('primary_verified_at') or '')[:16]}確認）"


# ============================================================
# topic_age（話題の年齢、2026-10-15、NEWS_REDESIGN_2026-10-15.md §3.3）
# 系列の最初の日付＝同じ系列の候補の発表日・記事の日付／news_pool.json の同じ系列の記事／buzz_evidence のうち最も古いもの。
# 鮮度（freshness）はこの日から数える（以前は announced_on＝最新の出来事の発表日から）。
# プール・buzz_evidence の記事を同じ系列とみなすのは、見出しが候補の固有の語（jp_title_anchor のうち組織名・略語だけでないもの）を
# **すべて**含むか、候補の見出しと語の Jaccard 類似度が DEDUP_JACCARD 以上のときだけ（「安川電機」だけを含む別の記事を拾わないため）。
# プールは毎晩作り直され21日より前の記事が消えるので、プール由来の最古の記事は候補に残しておき、次回以降も使う。
# ============================================================

def _topic_anchors(c: dict) -> list:
    a = _verify_anchors(c)
    return [x for x in a if not any(x != y and x in y for y in a)]   # 「gemini 4」と「gemini 4 argon」は長い方だけ


def _valid_day(d: str):
    try:
        day = datetime.fromisoformat((d or "")[:10]).date()
    except Exception:  # noqa: BLE001
        return None
    if day > datetime.now().date() + timedelta(days=1):   # 未来の日付（誤り）は使わない。古い日付はそのまま使う（古い論文の再報道を新しく見せないため）
        return None
    return day


def _load_pool_items() -> list:
    try:
        return json.loads(POOL_JSON.read_text(encoding="utf-8")).get("items", [])
    except Exception:  # noqa: BLE001
        return []


def _distinct_numbers(a: str, b: str) -> bool:
    """互いに相手に無い数字がある（版・日付の違う別の発表。dedup_similar と同じ考え方）"""
    na, nb = set(re.findall(r"\d+(?:\.\d+)?", _nfkc(a))), set(re.findall(r"\d+(?:\.\d+)?", _nfkc(b)))
    return bool((na - nb) and (nb - na))


def topic_groups(cands: list) -> dict:
    """話題の初出を数えるための系列（id → 系列のキー）。表示用の assign_series（発表元のホスト＋見出しの語の部分一致）より厳しくする:
    明示の series が同じ／一方の固有の語（_topic_anchors）が**すべて**他方の見出しに含まれる／見出しの語の Jaccard が DEDUP_JACCARD 以上
    （互いに相手に無い数字があればまとめない）。assign_series を全候補に使うと、組織名や「人型ロボット」のような語で
    別の発表がつながり、7月の記事まで同じ系列になった（2026-10-15の実データで確認）。"""
    parent = {c["id"]: c["id"] for c in cands}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    info = [(c, _nfkc(c.get("title", "")), _topic_anchors(c), _title_tokens(c.get("title", ""))) for c in cands]
    for i, (a, ta, aa, ka) in enumerate(info):
        for b, tb, ab, kb in info[i + 1:]:
            if _distinct_numbers(a.get("title", ""), b.get("title", "")):
                same = bool(a.get("series")) and a.get("series") == b.get("series")
            else:
                same = (bool(a.get("series")) and a.get("series") == b.get("series")) \
                    or (aa and all(x in tb for x in aa)) or (ab and all(x in ta for x in ab)) \
                    or (len(ka) >= 4 and len(kb) >= 4 and len(ka & kb) / len(ka | kb) >= DEDUP_JACCARD) \
                    or b["id"] in (a.get("dup_ids") or []) or a["id"] in (b.get("dup_ids") or [])
            if same:
                parent[find(a["id"])] = find(b["id"])
    by_id = {c["id"]: c for c in cands}
    return {c["id"]: (by_id[find(c["id"])].get("series") or find(c["id"])) for c in cands}


def refresh_topic_ages(cands: list, pool: list = None):
    """各候補に topic_first_date（系列の最初の日付）・topic_first_source（その根拠）・topic_series を付ける（メモリ上。保存は呼び出し側）。"""
    if pool is None:
        pool = _load_pool_items()
    pool_tok = [(p, _nfkc(p.get("title", "")), _title_tokens(p.get("title", ""))) for p in pool]
    ser = topic_groups(cands)
    groups = {}
    for c in cands:
        groups.setdefault(ser[c["id"]], []).append(c)
    for key, members in groups.items():
        ev = []   # (date, source の説明)
        ids = set()
        for m in members:
            ids.add(m["id"])
            ids.update(m.get("dup_ids") or [])
            for fld in ("announced_on", "published"):
                d = _valid_day(m.get(fld))
                if d:
                    ev.append((d, f"候補 {m['id']} の{fld}（{m['title'][:30]}）"))
        anchor_sets = [a for a in (_topic_anchors(m) for m in members) if a]
        mtoks = [t for t in (_title_tokens(m.get("title", "")) for m in members) if len(t) >= 4]

        def same_topic(title_n, toks):
            if any(all(a in title_n for a in aset) for aset in anchor_sets):
                return True
            return len(toks) >= 4 and any(len(toks & t) / len(toks | t) >= DEDUP_JACCARD for t in mtoks)

        for m in members:
            for e in m.get("buzz_evidence") or []:
                d = _valid_day(e.get("date"))
                if d and same_topic(_nfkc(e.get("title", "")), _title_tokens(e.get("title", ""))):
                    ev.append((d, f"日本語記事（{e.get('outlet', '')}「{e.get('title', '')[:30]}」）"))
            kept = m.get("topic_pool_first")      # 以前のプールで見つけた最古の記事（プールから消えても使う）
            if kept and _valid_day(kept.get("date")):
                ev.append((_valid_day(kept["date"]), f"プールの記事（{kept.get('title', '')[:40]}）"))
        pool_hits = []
        for p, tn, tk in pool_tok:
            d = _valid_day(p.get("published"))
            if not d:
                continue
            if p.get("id") in ids or set(p.get("dup_ids") or []) & ids or same_topic(tn, tk):
                pool_hits.append((d, p))
        if pool_hits:
            d, p = min(pool_hits, key=lambda x: x[0])
            ev.append((d, f"プールの記事（{p.get('title', '')[:40]}）"))
            pf = {"date": d.isoformat(), "title": p.get("title", "")[:120], "id": p.get("id", ""),
                  "source": (p.get("source") or "")[:60]}
        else:
            pf = None
        if not ev:
            continue
        first_d, first_src = min(ev, key=lambda x: x[0])
        for m in members:
            m["topic_first_date"] = first_d.isoformat()
            m["topic_first_source"] = first_src
            m["topic_series"] = key
            m["freshness_basis"] = "topic_first_date"
            if pf and (not m.get("topic_pool_first") or pf["date"] < m["topic_pool_first"].get("date", "9999")):
                m["topic_pool_first"] = pf


def fresh_date(c: dict) -> str:
    """鮮度を数える日。topic_first_date（話題の初出）があればそれ、無ければ従来どおり announced_on → published。"""
    return c.get("topic_first_date") or c.get("announced_on") or c.get("published", "")


def topic_age_days(c: dict) -> int:
    try:
        return (datetime.now().date() - datetime.fromisoformat(fresh_date(c)[:10]).date()).days
    except Exception:  # noqa: BLE001
        return 999


def _topic_line(c: dict) -> str:
    ann = (c.get("announced_on") or c.get("published") or "")[:10]
    if not c.get("topic_first_date"):
        return f"話題の初出: 未計算（鮮度は発表日 {ann} から）"
    first = c["topic_first_date"]
    same = "＝発表日" if first == ann else f"、一次資料の発表日 {ann}"
    return f"話題の初出: {first}（{topic_age_days(c)}日前{same}。根拠: {c.get('topic_first_source', '')}）。鮮度は初出から数える"


def _yt_line(c: dict) -> str:
    if c.get("yt_competitors") is None:
        return "競合（日本語の解説動画）: 未記録"
    q = f"、検索語 {c['yt_competitors_query']!r}" if c.get("yt_competitors_query") else ""
    return f"競合（日本語の解説動画）: {c['yt_competitors']}本（{(c.get('yt_competitors_checked_at') or '')[:16]}記録{q}）"


# ============================================================
# P1: Google ニュース RSS による注目度の実測（buzz）
# ============================================================

GNEWS_URL = "https://news.google.com/rss/search?"
GNEWS_WINDOW_DAYS = 14         # 1候補1回、14日窓で取得し、7日窓は手元の日付で絞る（別取得すると件数が逆転することがあった）
GNEWS_INTERVAL = 2.5           # 秒。リクエスト間隔は2秒以上
GNEWS_MAX_PER_RUN = 50         # 1回の実行で取得する上限

# 実測の換算（ユニークな日本語の独立媒体の数 n → buzz_measured）。
# 2026-10-11の24件の実測から決めた暫定値、2〜3回運用後に見直す。
BUZZ_TIERS = ((10, 5), (6, 4), (3, 3), (1, 2), (0, 1))   # n 以上 → 点
BUZZ_YAHOO_BONUS_MIN_OUTLETS = 2                          # Yahoo!ニュース掲載 かつ n がこれ以上なら +1（上限5）

# 数えない記事の媒体（ホストの末尾一致、または <source> の名前の部分一致）
PR_WIRE_HOSTS = ("prtimes.jp", "atpress.ne.jp", "value-press.com", "dreamnews.jp", "newscast.jp",
                 "kyodonewsprwire.jp", "jcnnews.jp", "prwire.jp", "prnewswire.com", "businesswire.com")
PR_WIRE_NAMES = ("PR TIMES", "@Press", "＠Press", "ValuePress", "Dream News", "PRワイヤー", "PR Newswire", "Business Wire")
AGGREGATOR_HOSTS = ("news.yahoo.co.jp", "yahoo.co.jp", "livedoor.com", "livedoor.jp", "docomo.ne.jp",
                    "infoseek.co.jp", "auone.jp", "nicovideo.jp", "biggo.jp", "biggo.com", "goo.ne.jp",
                    "biglobe.ne.jp", "msn.com", "excite.co.jp", "smartnews.com", "newspicks.com", "gunosy.com")
AGGREGATOR_NAMES = ("Yahoo", "ライブドア", "livedoor", "dメニュー", "docomo", "インフォシーク", "Infoseek", "auone",
                    "au Webポータル", "ニコニコ", "BigGo", "goo", "BIGLOBE", "MSN", "エキサイト", "SmartNews", "NewsPicks", "グノシー")
SKIP_HOSTS = ("youtube.com", "youtu.be", "x.com", "twitter.com", "facebook.com", "note.com")
FOREIGN_TLDS = (".kr", ".vn", ".cn", ".tw", ".hk")
FOREIGN_HOSTS = ("chosun.com", "joongang.co.kr", "vietnam.vn", "chinadaily.com.cn")
GENERIC_SOURCE_HOSTS = ("doi.org", "youtube.com", "youtu.be", "github.com", "arxiv.org", "x.com", "twitter.com",
                        "prnewswire.com", "businesswire.com", "huggingface.co")
# 見出しの語のうち、組織名だけ・略語だけの語は単独では関連の判定に使わない（他の語があるときだけ）。
# enrich の指示で避けさせているが、守られないことがあるためコード側でも外す
GENERIC_ANCHORS = {"mit", "google", "nvidia", "aws", "openai", "microsoft", "meta", "apple", "amazon", "ai",
                   "als", "ucla", "ucsf", "cira"}
KANA = re.compile(r"[぀-ヿ]")
KANJI = re.compile(r"[一-鿿]")


class GNewsError(Exception):
    pass


def _host_in(h: str, hosts) -> bool:
    return any(h == x or h.endswith("." + x) for x in hosts if h)


def _nfkc(s: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKC", s or "").lower()


def fetch_gnews(query: str, timeout: int = 20, window_days: int = None) -> list:
    """Google ニュース RSS（日本語）を1回取得する。取得物はXMLとしてパースするだけ。
    失敗（HTTPエラー・同意画面・XMLでない・0件）は GNewsError。window_days は collect 用（既定は buzz の14日窓）。"""
    url = GNEWS_URL + urllib.parse.urlencode({"q": f"{query} when:{window_days or GNEWS_WINDOW_DAYS}d",
                                              "hl": "ja", "gl": "JP", "ceid": "JP:ja"})
    try:
        raw = urllib.request.urlopen(urllib.request.Request(url, headers=BROWSER_UA), timeout=timeout).read()
    except urllib.error.HTTPError as e:
        raise GNewsError(f"HTTP {e.code}") from e
    except Exception as e:  # noqa: BLE001
        raise GNewsError(f"{type(e).__name__}: {str(e)[:60]}") from e
    if b"<rss" not in raw[:2000]:
        raise GNewsError("RSSではない応答（同意画面・ブロックの可能性）")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        raise GNewsError(f"XMLのパース失敗: {e}") from e
    items = []
    for it in root.findall(".//item"):
        src = it.find("source")
        name = ((src.text if src is not None else "") or "").strip()
        title = (it.findtext("title") or "").strip()
        if name and title.endswith(" - " + name):     # 見出しの末尾の「 - 媒体名」を落とす
            title = title[: -len(" - " + name)].strip()
        d = _parse_date(it.findtext("pubDate") or "")
        items.append({"title": title, "outlet": name, "link": (it.findtext("link") or "").strip(),
                      "host": _host((src.get("url") if src is not None else "") or ""),
                      "date": d.date().isoformat() if d else ""})
    if not items:
        raise GNewsError("0件（検索語が合っていない可能性）")
    return items


def count_buzz(items: list, anchors: list, issuer_hosts: set) -> dict:
    """関連する記事（見出しが anchors のどれかを含む）から、日本語の独立媒体の数 n と換算値を出す。"""
    anc = [_nfkc(a) for a in anchors if a and a.strip()]
    if any(a not in GENERIC_ANCHORS for a in anc):
        anc = [a for a in anc if a not in GENERIC_ANCHORS]
    now = datetime.now(timezone.utc).date()
    since14 = now - timedelta(days=GNEWS_WINDOW_DAYS)
    since7 = now - timedelta(days=7)
    yahoo, counted = False, []
    for it in items:
        t = _nfkc(it["title"])
        if not anc or not any(a in t for a in anc):
            continue
        if it["date"] and it["date"] < since14.isoformat():
            continue
        h, name = it["host"], it["outlet"]
        if _host_in(h, AGGREGATOR_HOSTS) or any(n.lower() in name.lower() for n in AGGREGATOR_NAMES):
            if "yahoo" in h or "Yahoo" in name:
                yahoo = True        # 転載だが「Yahoo!に載ったか」は別に記録する
            continue
        if _host_in(h, PR_WIRE_HOSTS) or any(n.lower() in name.lower() for n in PR_WIRE_NAMES):
            continue
        if _host_in(h, SKIP_HOSTS) or _host_in(h, FOREIGN_HOSTS) or h.endswith(FOREIGN_TLDS):
            continue
        if any(h == x or h.endswith("." + x) or x.endswith("." + h) for x in issuer_hosts if h):
            continue                # 発表元自身のドメイン
        if not (KANA.search(it["title"]) or (KANJI.search(it["title"]) and h.endswith(".jp"))):
            continue                # 日本語の見出しでない（漢字だけの見出しは .jp の媒体に限る。中国語の見出しを除くため）
        counted.append(it)
    outlets = {}
    for it in sorted(counted, key=lambda x: x["date"], reverse=True):
        outlets.setdefault(it["outlet"] or it["host"], it)
    n = len(outlets)
    m = next(score for lo, score in BUZZ_TIERS if n >= lo)
    if yahoo and n >= BUZZ_YAHOO_BONUS_MIN_OUTLETS:
        m = min(5, m + 1)
    c14 = len(counted)
    c7 = sum(1 for it in counted if it["date"] >= since7.isoformat())
    evidence = [{"title": it["title"][:80], "outlet": it["outlet"] or it["host"], "date": it["date"]}
                for it in list(outlets.values())[:3]]
    return {"buzz_measured": m, "buzz_outlets": n, "yahoo": yahoo, "buzz_evidence": evidence,
            "buzz_trend": round(c7 / c14, 2) if c14 else None, "buzz_articles_14d": c14}


def issuer_hosts(c: dict) -> set:
    hs = {_host(s.get("url", "")) for s in c.get("primary_sources", []) or []}
    return {h for h in hs if h and not _host_in(h, GENERIC_SOURCE_HOSTS)}


def _two_words(q: str) -> str:
    """検索語は2語まで（Google ニュースは語が増えるほど0件になりやすい。2026-10-11の実測で3語以上の検索語の大半が0件）。"""
    return " ".join((q or "").split()[:2])


def _fallback_query(c: dict, used_q: str) -> str:
    """0件だったときの検索語の予備: 見出しの語のうち最も固有なもの（組織名・略語だけの語を除いた最長の語）。"""
    anc = c.get("jp_title_anchor") or []
    anc = [anc] if isinstance(anc, str) else anc
    cand = sorted((a for a in anc if a and _nfkc(a) not in GENERIC_ANCHORS), key=len, reverse=True)
    return cand[0] if cand and cand[0] != used_q else ""


def measure_buzz(c: dict, query: str = None) -> dict:
    """1候補1回の取得が基本。0件のときだけ、見出しの語で1回だけ取り直す（その間も GNEWS_INTERVAL をあける）。"""
    q = _two_words(query or c["jp_news_query"])
    try:
        items = fetch_gnews(q)
    except GNewsError as e:
        fb = "" if query else _fallback_query(c, q)
        if "0件" not in str(e) or not fb:
            raise
        time.sleep(GNEWS_INTERVAL)
        q = fb
        items = fetch_gnews(q)
    anchors = c.get("jp_title_anchor") or []
    if isinstance(anchors, str):
        anchors = [anchors]
    r = count_buzz(items, anchors, issuer_hosts(c))
    r["buzz_raw_items"], r["buzz_query"] = len(items), q
    return r


# ============================================================
# 同じ発表の系列（series）。明示の series が同じか、発表元のホストが重なり見出しの語が重なる候補を1つにまとめる
# ============================================================

def assign_series(cands: list) -> dict:
    parent = {c["id"]: c["id"] for c in cands}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def anchors(c):
        a = c.get("jp_title_anchor") or []
        return [_nfkc(x) for x in ([a] if isinstance(a, str) else a) if x and x.strip()]

    for i, a in enumerate(cands):
        for b in cands[i + 1:]:
            sa, sb = a.get("series") or "", b.get("series") or ""
            # 明示の series が同じか、一方が他方の前置き（gpt-6 と gpt-6-1-sol）なら同じ系列
            same = bool(sa and sb) and (sa == sb or sa.startswith(sb + "-") or sb.startswith(sa + "-"))
            if not same and issuer_hosts(a) & issuer_hosts(b):
                same = any(x in y or y in x for x in anchors(a) for y in anchors(b))
            if same:
                parent[find(a["id"])] = find(b["id"])
    by_id = {c["id"]: c for c in cands}
    return {c["id"]: (by_id[find(c["id"])].get("series") or find(c["id"])) for c in cands}


# ============================================================
# enrich: ゲート通過分に検索語・見出しの語・発表の種類・系列を付ける（検索なし・テキストのみ）
# ============================================================

ENRICH_BATCH = 25


def _gate_pool(cands: list) -> list:
    used = used_source_urls(cands)
    return [c for c in cands if c.get("status") == "available" and not gate_reasons(c, used)]


def backfill_work(cands: list, force: bool = False):
    """ゲート以外を通過した候補のうち work_relevance が無いものに、仕事・ビジネスへの関わり（1〜5）を付ける（テキストのみ）。"""
    used = used_source_urls(cands)
    todo = [c for c in cands if c.get("status") == "available" and (force or c.get("work_relevance") is None)
            and not [x for x in gate_reasons(c, used) if not x.startswith("暮らし")]]
    if not todo:
        return
    client, types = _gemini()
    for k in range(0, len(todo), ENRICH_BATCH):
        batch = todo[k:k + ENRICH_BATCH]
        rows = "\n".join(
            f"{i}. タイトル: {c['title']} / 見出し: {c.get('headline_claim', '')} / "
            f"中身: {(c.get('actual_content') or c.get('summary') or '')[:300]}" for i, c in enumerate(batch))
        prompt = (
            "日本の一般視聴者向けの科学ニュース解説番組のネタ候補です。各候補について work_relevance（1〜5）を付けてください。\n"
            "仕事・ビジネスにどう関わるか。働く人・経営者・個人事業主が今日の仕事や判断で使える、または自分の仕事・業界が影響を受けるほど高い。"
            "開発者・研究者・特定の専門職しか使わない専用品や、基礎研究で仕事への影響が見えないものは低い。"
            "言語対応や提供地域は無関係。迷ったら低い方を付ける。\n\n"
            f"候補:\n{rows}\n\n"
            'JSON配列のみ出力: [{"i": 0, "work_relevance": 0}, ...]（全候補分）')
        try:
            out = _json_from(client.models.generate_content(model=MODEL, contents=prompt).text)
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️ work_relevance の付与に失敗（{k}〜{k + len(batch) - 1}件目）: {e}")
            continue
        for r in out:
            try:
                batch[int(r["i"])]["work_relevance"] = _clamp5(r["work_relevance"])
            except (KeyError, ValueError, IndexError, TypeError):
                continue
    print(f"work_relevance を {len(todo)}件に付与しました")


def cmd_enrich(force: bool):
    cands = load_candidates()
    refresh_topic_ages(cands["items"])
    backfill_work(cands["items"], force)
    _save_candidates(cands)
    pool = _gate_pool(cands["items"])
    todo = [c for c in pool if force or not c.get("jp_news_query")]
    if not todo:
        print("付与が必要な候補はありません（ゲート通過分はすべて jp_news_query あり）")
        return
    client, types = _gemini()
    n = 0
    for k in range(0, len(todo), ENRICH_BATCH):
        batch = todo[k:k + ENRICH_BATCH]
        rows = "\n".join(
            f"{i}. タイトル: {c['title']} / 発表元: {', '.join(sorted(issuer_hosts(c))) or c.get('source', '')} / "
            f"見出し: {c.get('headline_claim', '')} / 中身: {(c.get('actual_content') or c.get('summary') or '')[:200]}"
            for i, c in enumerate(batch))
        prompt = (
            "日本語の科学ニュース解説番組のネタ候補です。各候補について、次の4つを付けてください。\n"
            "- jp_news_query: Google ニュース（日本語）でこの発表そのものの記事を探すための検索語。固有名詞（製品名・モデル名・"
            "研究機関名・企業名）を必ず1つ含む2語以内（3語以上は0件になりやすいので必ず2語まで。例: \"GPT-6.1 Sol\"、\"シャープ 介護 AIトレーナー\"）。一般名詞だけ"
            "（例: \"ゲノム編集 ALS\"）にしない。日本語の報道で使われる表記にする（英語の製品名は英語のまま）。\n"
            "- jp_title_anchor: この発表を扱った日本語記事の見出しに必ず含まれるはずの語を1〜3個の配列で（どれか1つを含めば関連と"
            "みなす。例: [\"GPT-6.1\"]、[\"クレアチン\"]、[\"介護向けAIトレーナー\", \"シャープ\"]）。テーマ全般の語（\"超加工食品\" だけ等）"
            "は避け、この研究・製品に固有の語を入れる。研究機関・大企業の名前だけ（\"MIT\"、\"Google\"、\"NVIDIA\" 等）や、"
            "病名・物質名の略語だけ（\"ALS\" 等）を単独の語にしない（その組織・テーマの別の記事まで拾うため）。"
            "検索語にも見出しの語にも、情報源のニュースサイト名（ScienceDaily 等）は入れない。\n"
            "- announcement_type: research | product_release | customer_case | policy | event | other"
            "（企業による顧客の導入事例・成功談は customer_case）\n"
            "- series: 同じ発表の系列を表す短い英小文字のキー（例: gpt-6、atlas-hand、dyna-2）。同じ製品・研究の別記事は同じキーにする。\n\n"
            f"候補:\n{rows}\n\n"
            'JSON配列のみ出力: [{"i": 0, "jp_news_query": "", "jp_title_anchor": [], "announcement_type": "", "series": ""}, ...]（全候補分）')
        try:
            out = _json_from(client.models.generate_content(model=MODEL, contents=prompt).text)
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️ 付与に失敗（{k}〜{k + len(batch) - 1}件目）: {e}")
            continue
        for r in out:
            try:
                c = batch[int(r["i"])]
            except (KeyError, ValueError, IndexError, TypeError):
                continue
            q = (r.get("jp_news_query") or "").strip()
            anc = r.get("jp_title_anchor") or []
            anc = [anc] if isinstance(anc, str) else [a.strip() for a in anc if isinstance(a, str) and a.strip()][:3]
            if not q or not anc:
                continue
            c["jp_news_query"], c["jp_title_anchor"] = q, anc
            if r.get("announcement_type") in ANNOUNCEMENT_TYPES:
                c["announcement_type"] = r["announcement_type"]
            ser = re.sub(r"[^a-z0-9-]", "", (r.get("series") or "").lower())
            if ser:
                c["series"] = ser
            c["enriched_version"] = SCAN_VERSION
            n += 1
            print(f"  {c['id']} [{c.get('announcement_type', '?'):15s}] {q!r} {anc} series={c.get('series', '')}  {c['title'][:40]}")
    _save_candidates(cands)
    print(f"\n{n}/{len(todo)}件に検索語・見出しの語・発表の種類を付けました（{CANDIDATES_JSON.name}）")


# ============================================================
# buzz: 注目度の実測
# ============================================================

def cmd_buzz(max_n: int, force: bool, remeasure_hours: float, ids: list, dry_run: bool):
    cands = load_candidates()
    refresh_topic_ages(cands["items"])
    if ids:
        pool = [c for c in cands["items"] if c["id"] in ids]
    else:
        pool = _gate_pool(cands["items"])
    now = datetime.now()

    def recent(c):
        try:
            return (now - datetime.fromisoformat(c["buzz_measured_at"])).total_seconds() < remeasure_hours * 3600
        except Exception:  # noqa: BLE001
            return False

    no_q = [c for c in pool if not c.get("jp_news_query")]
    todo = [c for c in pool if c.get("jp_news_query") and (force or ids or not recent(c))]
    todo.sort(key=lambda c: (-freshness_score(fresh_date(c)), -buzz_value(c)[0]))
    todo = todo[:min(max_n, GNEWS_MAX_PER_RUN)]
    if no_q:
        print(f"  ※ jp_news_query が無い {len(no_q)}件は測れません（先に enrich）")
    print(f"実測 {len(todo)}件（Google ニュース RSS、{GNEWS_INTERVAL}秒間隔）")
    ok = fail = 0
    for k, c in enumerate(todo):
        if k:
            time.sleep(GNEWS_INTERVAL)
        try:
            r = measure_buzz(c)
        except GNewsError as e:
            fail += 1
            c["buzz_error"], c["buzz_error_at"] = str(e), now.isoformat(timespec="seconds")
            print(f"  ⚠️ {c['id']} 実測失敗（{e}）→ 推定 {buzz_value(c)[0]} で代用  {c['title'][:40]}")
            continue
        ok += 1
        c.update(r, buzz_measured_at=datetime.now().isoformat(timespec="seconds"))
        c.pop("buzz_error", None)
        c.pop("buzz_error_at", None)
        print(f"  {c['id']} 実測{r['buzz_measured']}（{r['buzz_outlets']}媒体{'・Yahoo!あり' if r['yahoo'] else ''}、"
              f"関連{r['buzz_articles_14d']}/取得{r['buzz_raw_items']}件）{r['buzz_query']!r}  {c['title'][:40]}")
    if dry_run:
        print(f"\n（--dry-run のため保存しません）成功{ok}・失敗{fail}")
        return
    _save_candidates(cands)
    print(f"\n成功{ok}・失敗{fail}件。{CANDIDATES_JSON.name} に保存しました")


# ============================================================
# list: 本命／ニッチ／速報 の3枠
# ============================================================

BREAKING_HOURS = 72
BREAKING_TYPES = ("research", "product_release")
NICHE_MIN_FRESHNESS = 4
NICHE_MIN_HYPE_DEBATE = 7

# 答え合わせ候補（L2候補、2026-10-15、NEWS_REDESIGN_2026-10-15.md §3.2・§4.1 決定4=(a)）:
# 大手の製品発表は、日本語の報道が当日〜翌日に出そろう。発表の時点で速報にはせず、数日たってから
# 「発表の盛り vs 使った人の声・第三者の検証」で扱う。条件を満たす候補は本命・ベスト3に入れない。
#   製品発表 かつ 日本語の独立媒体が L2_MIN_JP_OUTLETS 以上 かつ 話題の初出から L2_MIN_TOPIC_AGE_DAYS 日以上 → 「答え合わせ候補」
#   同じ条件で初出から L2_MIN_TOPIC_AGE_DAYS 日未満 → 「再評価待ち」（ベスト3に入れない）
# 並びの式（core）は変えない（表示の枠を分けるだけ）。段階の数字は暫定
L2_TYPES = ("product_release",)
L2_MIN_JP_OUTLETS = 10
L2_MIN_TOPIC_AGE_DAYS = 2
L2_LANE = "答え合わせ候補"
L2_WAIT_LANE = "再評価待ち"
L2_HEADING = "答え合わせ候補（発表から数日。使った人の声・第三者の検証を探す価値あり）"


def is_l2_type(c: dict) -> bool:
    return c.get("announcement_type") in L2_TYPES and (c.get("buzz_outlets") or 0) >= L2_MIN_JP_OUTLETS


def tie_break(c: dict) -> int:
    return sum(_clamp5(c.get(k)) for k in ("hype_gap", "debate", "life_relevance"))


def classify(cands: list) -> list:
    """available な候補に、鮮度・core・枠（lane）・ゲートの理由・系列を付けて返す。
    話題の初出（topic_first_date）はメモリ上で計算し直す（保存は呼び出し側。verify・buzz・check-urls が保存する）。"""
    refresh_topic_ages(cands)
    used = used_source_urls(cands)
    rows = []
    for c in cands:
        if c.get("status") != "available":
            continue
        fresh = freshness_score(fresh_date(c))
        gate = gate_reasons(c, used)
        bm = c.get("buzz_measured")
        if gate:
            lane = "除外"
        elif bm is None:
            lane = "未計測"
        elif is_l2_type(c):
            lane = L2_LANE if topic_age_days(c) >= L2_MIN_TOPIC_AGE_DAYS else L2_WAIT_LANE
        elif bm >= 3:
            lane = "本命"
        elif topic_age_days(c) * 24 <= BREAKING_HOURS and c.get("announcement_type") in BREAKING_TYPES:
            lane = "速報"
        elif fresh >= NICHE_MIN_FRESHNESS and _clamp5(c.get("hype_gap")) + _clamp5(c.get("debate")) >= NICHE_MIN_HYPE_DEBATE:
            lane = "ニッチ"
        else:
            lane = "注目度低"
        rows.append({"c": c, "fresh": fresh, "gate": gate, "lane": lane,
                     "core": fresh * bm * stake(c) if bm is not None else None,
                     "core_est": fresh * buzz_value(c)[0] * stake(c), "tb": tie_break(c),
                     "old": overall(c, c.get("published", ""))[0]})
    ser = assign_series([r["c"] for r in rows if not r["gate"]])
    for r in rows:
        r["series"] = ser.get(r["c"]["id"], r["c"]["id"])
    return rows


def _sorted_core(rows: list) -> list:
    # core → 誇張+議論+暮らし → 媒体数（同点が多いので最後に実測の媒体数で並べる）
    return sorted(rows, key=lambda r: (r["core"] if r["core"] is not None else -1, r["tb"],
                                       r["c"].get("buzz_outlets") or 0), reverse=True)


def collapse_series(rows: list) -> list:
    """同じ系列は先頭の1件にまとめ、残りを r['same_series'] に入れる（並び順は保つ）。"""
    head, out = {}, []
    for r in rows:
        if r["series"] in head:
            head[r["series"]]["same_series"].append(r)
        else:
            r = dict(r, same_series=[])
            head[r["series"]] = r
            out.append(r)
    return out


def best3(rows: list):
    """ベスト3の機械的な下書き: 本命枠から core の順に、ジャンルと系列が重ならないように選ぶ。
    足りなければ満たないまま返し、ニッチ枠の先頭を別に添える。"""
    picks, genres, series = [], set(), set()
    for r in _sorted_core([r for r in rows if r["lane"] == "本命"]):
        if r["c"].get("genre") in genres or r["series"] in series:
            continue
        picks.append(r)
        genres.add(r["c"].get("genre"))
        series.add(r["series"])
        if len(picks) == 3:
            break
    niche = _sorted_core([r for r in rows if r["lane"] == "ニッチ"])
    return picks, (niche[0] if niche and len(picks) < 3 else None)


def _buzz_line(c: dict) -> str:
    if c.get("buzz_measured") is not None:
        t = c.get("buzz_trend")
        return (f"注目度: 実測{c['buzz_measured']}（{c.get('buzz_outlets', 0)}媒体"
                f"{'・Yahoo!あり' if c.get('yahoo') else '・Yahoo!なし'}"
                + (f"、勢い{t:.2f}" if t is not None else "")
                + f"、{(c.get('buzz_measured_at') or '')[:16]}計測、検索語 {c.get('buzz_query', '')!r}）")
    msg = f"注目度: 推定{buzz_value(c)[0]}（未計測"
    if c.get("buzz_error"):
        msg += f"。実測失敗: {c['buzz_error']}"
    return msg + "）"


def _print_candidate(r: dict, short: bool = False):
    c = r["c"]
    core = f"core {r['core']:3d}＝鮮度{r['fresh']}×注目{c['buzz_measured']}×関わり{stake(c)}" if r["core"] is not None \
        else f"core —（鮮度{r['fresh']}、推定なら{r['core_est']}）"
    warn = "  ⚠️一次資料 要確認" if c.get("primary_verified", "未") is None else \
        ("  ⚠️一次資料 未確認" if "primary_verified" not in c else "")
    print(f"[{core}｜誇張+議論+暮らし {r['tb']}｜旧加重和 {r['old']:.2f}] {c['title'][:76]}"
          f"（{c.get('announced_on') or c.get('published')}、{c.get('genre', '?')}）" + ("  ※健康系" if c.get("health") else "")
          + warn)
    print(f"   {_topic_line(c)}")
    print(f"   {_buzz_line(c)}")
    for e in c.get("buzz_evidence") or []:
        print(f"     - {e['title']}（{e['outlet']}、{e['date']}）")
    print(f"   {_primary_line(c)}")
    if c.get("yt_competitors") is not None or not short:
        print(f"   {_yt_line(c)}")
    if r.get("same_series"):
        print(f"   同じ系列の候補 他{len(r['same_series'])}件: " + " ／ ".join(x['c']['title'][:40] for x in r["same_series"]))
    if short:
        return
    print(f"   問い: {c.get('entry_question')}")
    print(f"   見出し: {c.get('headline_claim')}")
    print(f"   実際: {c.get('actual_content')}")
    print(f"   ツッコミ: {c.get('tsukkomi_material')}  予想判定: {c.get('expected_verdicts')}")
    print(f"   一次資料: " + ", ".join(s.get('url', '') for s in c.get('primary_sources', [])))
    if c.get("deja_vu_note"):
        print(f"   既視感: {c['deja_vu_note']}")


def _print_exclusions(rows: list):
    ex = [r for r in rows if r["gate"]]
    from collections import Counter
    cnt = Counter(g.split("（")[0] for r in ex for g in r["gate"])
    print(f"ゲート（検証≥{GATE_MIN_VERIFIABILITY}・鮮度≥{GATE_MIN_FRESHNESS}（話題の初出から）・使用済み/宣伝でない・"
          f"一次資料URLが実在しないでない）で外した候補: {len(ex)}件 "
          + "／".join(f"{k} {v}" for k, v in cnt.items()))
    for r in ex:
        named = [g for g in r["gate"] if g.startswith(("使用済み", "宣伝", "一次資料"))]
        if named:
            print(f"   × {r['c']['title'][:60]} — {'・'.join(named)}")


def run_url_checks(targets: list, cands: dict) -> dict:
    """一次資料のURLを確かめて候補に保存する（verify と check-urls の共通部分。1候補あたり最大 VERIFY_MAX_URLS、
    全体で2秒以上・同じホストには5秒以上の間隔）。primary_verified と、既存の url_ok・url_status の両方を更新する。"""
    pacer = _HostPacer()
    tally = {True: 0, False: 0, None: 0}
    for c in targets:
        verify_candidate(c, pacer)
        pv = c["primary_verified"]
        tally[pv] += 1
        mark = {True: "OK", False: "NG", None: "要確認"}[pv]
        print(f"  [{mark}] {c['id']} {c['title'][:50]} — {c.get('url_status') or c.get('primary_verified_note', '')}")
    _save_candidates(cands)
    return tally


def cmd_verify(ids: list, all_: bool, max_n: int):
    """score の直後に、一次資料のURLの実在を確かめる（2026-10-15）。既定は「未確認」で、一次資料以外のゲートを通る候補だけ。
    --all は確認済みも確かめ直す。--id は指定の候補だけ（ゲートに関係なく）。話題の初出（topic_first_date）もここで計算して保存する。"""
    cands = load_candidates()
    refresh_topic_ages(cands["items"])
    if ids:
        targets = [c for c in cands["items"] if c["id"] in ids]
        why = "指定のID"
    else:
        used = used_source_urls(cands["items"])
        pool = [c for c in cands["items"] if c.get("status") == "available"
                and not [g for g in gate_reasons(c, used) if not g.startswith("一次資料")]]
        targets = pool if all_ else [c for c in pool if "primary_verified" not in c]
        targets.sort(key=lambda c: (-freshness_score(fresh_date(c)), -buzz_value(c)[0]))
        why = "一次資料以外のゲートを通る候補" + ("（確認済みも含む）" if all_ else "のうち未確認")
        if len(targets) > max_n:
            print(f"  対象が{len(targets)}件あるため、新しい順に{max_n}件だけ確かめます（残りは次回）")
            targets = targets[:max_n]
    n_url = sum(min(len([s for s in c.get("primary_sources") or [] if s.get("url")]), VERIFY_MAX_URLS) for c in targets)
    print(f"一次資料の実在確認: {len(targets)}件・URL {n_url}件（{why}。間隔{URL_CHECK_INTERVAL}秒、同じホストは{VERIFY_SAME_HOST_INTERVAL}秒）")
    if not targets:
        _save_candidates(cands)
        return
    t = run_url_checks(targets, cands)
    print(f"\n確認済み {t[True]}・実在しない {t[False]}（ゲートで除外）・要確認 {t[None]}（{CANDIDATES_JSON.name} に保存）")


def cmd_yt(ids: list, count, query: str):
    """朝の YouTube 確認（ケースC）で数えた、日本語の解説動画の本数を記録する（手入力、2026-10-15）。YouTube API は使わない。"""
    if not ids or count is None:
        sys.exit("yt: --id ID と --count N（日本語の解説動画の本数。分からなければ記録しない）を指定してください")
    if count < 0:
        sys.exit("yt: --count は0以上")
    cands = load_candidates()
    hit = [c for c in cands["items"] if c["id"] in ids]
    if not hit:
        sys.exit(f"yt: 候補が見つかりません: {ids}")
    now = datetime.now().isoformat(timespec="seconds")
    for c in hit:
        c["yt_competitors"], c["yt_competitors_checked_at"] = int(count), now
        if query:
            c["yt_competitors_query"] = query
        print(f"  {c['id']} 競合 {count}本を記録  {c['title'][:50]}")
    _save_candidates(cands)


def cmd_check_urls(ids: list, top: int):
    cands = load_candidates()
    if ids:
        targets = [c for c in cands["items"] if c["id"] in ids]
    else:
        rows = classify(cands["items"])
        picks, _ = best3(rows)
        honmei = collapse_series(_sorted_core([r for r in rows if r["lane"] == "本命"]))[:top]
        l2 = collapse_series(_sorted_core([r for r in rows if r["lane"] == L2_LANE]))[:3]
        seen, targets = set(), []
        for r in picks + honmei + l2:
            if r["c"]["id"] not in seen:
                seen.add(r["c"]["id"])
                targets.append(r["c"])
    print(f"一次資料のURLを確認: {len(targets)}件（" + ("指定のID" if ids else "ベスト3・本命枠・答え合わせ候補") + "）")
    run_url_checks(targets, cands)


def cmd_list(top: int, check_urls: bool):
    if check_urls:
        cmd_check_urls([], top)
        print()
    rows = classify(load_candidates()["items"])
    _print_exclusions(rows)

    picks, niche_extra = best3(rows)
    print(f"\n==== ベスト3の下書き（本命枠から core の順、ジャンルと系列が重ならないように）: {len(picks)}件 ====")
    if len(picks) < 3:
        print(f"   ※ 本命枠の条件を満たす候補が{len(picks)}件しかない（3件に満たないまま出す）")
    for r in picks:
        _print_candidate(r, short=True)
    unv = [r for r in picks if r["c"].get("primary_verified", "未") is None or "primary_verified" not in r["c"]]
    if unv:
        print(f"   ⚠️ 一次資料が「要確認」または未確認の候補が{len(unv)}件: ブラウザか WebFetch で開いて確かめてから提示する")
    if niche_extra:
        print("   ＋ ニッチ枠から入れるならこの1件（注目度は低い）:")
        _print_candidate(niche_extra, short=True)

    honmei = collapse_series(_sorted_core([r for r in rows if r["lane"] == "本命"]))
    print(f"\n==== 本命（ゲート通過・実測の注目度≥3、core の順）: {len(honmei)}系列 ====")
    for r in honmei[:top]:
        _print_candidate(r)
    l2 = collapse_series(_sorted_core([r for r in rows if r["lane"] == L2_LANE]))
    print(f"\n==== {L2_HEADING}: {len(l2)}系列 ====")
    print(f"   条件: 製品発表・日本語の独立媒体{L2_MIN_JP_OUTLETS}以上・話題の初出から{L2_MIN_TOPIC_AGE_DAYS}日以上。"
          "本命・ベスト3には入れない（発表の紹介ではなく、発表の盛り vs 使った人の声・第三者の検証で扱う）")
    for r in l2[:top]:
        _print_candidate(r)
    wait = collapse_series(_sorted_core([r for r in rows if r["lane"] == L2_WAIT_LANE]))
    if wait:
        print(f"\n==== {L2_WAIT_LANE}（大手の製品発表、初出から{L2_MIN_TOPIC_AGE_DAYS}日未満。速報にせず、"
              f"{L2_MIN_TOPIC_AGE_DAYS}日後に答え合わせ候補として見直す）: {len(wait)}系列 ====")
        for r in wait[:top]:
            _print_candidate(r, short=True)
    niche = collapse_series(_sorted_core([r for r in rows if r["lane"] == "ニッチ"]))
    print(f"\n==== ニッチ（鮮度≥{NICHE_MIN_FRESHNESS}・実測1〜2・誇張+議論≥{NICHE_MIN_HYPE_DEBATE}。注目度は低い）: {len(niche)}件 ====")
    for r in niche[:top]:
        _print_candidate(r)
    brk = collapse_series(sorted([r for r in rows if r["lane"] == "速報"], key=lambda r: r["tb"], reverse=True))
    print(f"\n==== 速報（発表から{BREAKING_HOURS}時間以内・実測<3。加点なし、48時間後に測り直す）: {len(brk)}件 ====")
    for r in brk[:top]:
        _print_candidate(r, short=True)
        print(f"   → 48時間後に `buzz --id {r['c']['id']}` で測り直す")
    un = sorted([r for r in rows if r["lane"] == "未計測"], key=lambda r: r["core_est"], reverse=True)
    if un:
        print(f"\n==== 未計測（ゲート通過、本命枠には入れない。enrich → buzz で測る）: {len(un)}件 ====")
        for r in un[:top]:
            print(f"   [推定 core {r['core_est']}] {r['c']['title'][:70]}  {_buzz_line(r['c'])}")
    low = [r for r in rows if r["lane"] == "注目度低"]
    print(f"\n（ゲート通過だが注目度が低くニッチ・速報の条件も満たさない候補: {len(low)}件）")


def cmd_slack(note_path: str):
    """夜間実行用: ベスト3の下書きをスマホで読める Slack の Block Kit にして標準出力へ JSON で出す（2026-10-14）。"""
    g = json.loads(GENRES_JSON.read_text(encoding="utf-8"))
    gen = {k: v for k, v in g["genres"]} if isinstance(g["genres"], list) else dict(g["genres"])
    vname = {"soon": "もうすぐ", "decade": "3年", "dubious": "眉唾"}
    rows = classify(load_candidates()["items"])
    picks, niche = best3(rows)
    nums = "①②③"

    def esc(t):
        return (t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def clip(t, n):
        t = esc(t or "")
        return t if len(t) <= n else t[:n - 1] + "…"

    def day(c):
        d = (c.get("announced_on") or c.get("published") or "")[:10]
        return f"{int(d[5:7])}/{int(d[8:10])}発表" if len(d) >= 10 else ""

    def first(c):
        f = c.get("topic_first_date") or ""
        d = (c.get("announced_on") or c.get("published") or "")[:10]
        return f"初出{int(f[5:7])}/{int(f[8:10])}" if len(f) >= 10 and f != d else ""

    def card(i, r):
        c = r["c"]
        gi = gen.get(c.get("genre"), {})
        title = esc(c["title"])
        title = title if len(title) <= 60 else title[:59] + "…"
        buzz = (f"注目{c['buzz_measured']}（{c.get('buzz_outlets', 0)}媒体"
                f"{'・Yahoo!' if c.get('yahoo') else ''}）") if c.get("buzz_measured") is not None else "注目 未計測"
        meta = " ・ ".join(x for x in [f"{gi.get('icon', '')}{gi.get('label', c.get('genre', '?'))}", day(c), first(c), buzz,
                                       "健康系" if c.get("health") else ""] if x)
        if "primary_verified" in c:     # 2026-10-15: verify の結果（1件でも開ければ確認済み）
            pv = c["primary_verified"]
            mark, label = {True: ("✅", "確認済み"), False: ("❌", "実在しない"), None: ("⚠️", "要確認")}[pv]
            ok_src = [x["url"] for x in c.get("primary_check") or [] if x.get("ok")]
            src = ok_src[0] if ok_src else (c.get("primary_sources") or [{}])[0].get("url", "")
        else:
            mark = {True: "✅", False: "❌", None: "⚠️"}[c.get("url_ok")] if c.get("url_status") else "⚠️"
            label = {True: "OK", False: "リンク切れ", None: "要確認"}[c.get("url_ok")] if c.get("url_status") else "未確認"
            src = (c.get("primary_sources") or [{}])[0].get("url", "")
        link = f"<{src}|一次資料 {label}>" if src else f"一次資料 {label}"
        ev = c.get("expected_verdicts") or {}
        verdict = (f"大輔 {vname.get(ev.get('dreamer'), '?')} ／ 沙織 {vname.get(ev.get('skeptic'), '?')}") if ev else ""
        lines = [f"*{nums[i]} {title}*", meta, f"💬 {esc(c.get('entry_question'))}",
                 f"🔎 ツッコミ: {clip(c.get('tsukkomi_material'), 90)}"]
        if verdict:
            lines.append(f"⚖️ 予想判定: {verdict}")
        if c.get("deja_vu_note"):
            lines.append(f"⚠️ 既視感: {clip(c['deja_vu_note'], 80)}")
        lines.append(f"{mark} {link}")
        return {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)[:2900]}}

    blocks = [{"type": "header", "text": {"type": "plain_text", "text": f"KL ネタ ベスト3の下書き　{datetime.now().strftime('%-m/%-d')}"}}]
    note = Path(note_path) if note_path else None
    if note and note.exists():
        keep = [ln.strip() for ln in note.read_text(encoding="utf-8").splitlines()
                if ln.startswith(("ジャンルの間隔", "この回で使える枠", "次の回"))]
        if keep:
            blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": esc("\n".join(keep))[:1900]}]})
    if not picks:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "今夜は本命なし（実測の注目度3以上でゲートを通った候補がありません）。"}})
    for i, r in enumerate(picks):
        blocks.append({"type": "divider"})
        blocks.append(card(i, r))
    if len(picks) < 3 and picks:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": f"本命が{len(picks)}件のみ（3件に満たないまま出しています）"}]})
    if niche:
        blocks.append({"type": "divider"})
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": "ニッチ（注目度は低い）: " + esc(niche["c"]["title"][:60])}]})
    l2 = collapse_series(_sorted_core([r for r in rows if r["lane"] == L2_LANE]))[:3]
    if l2:
        blocks.append({"type": "divider"})
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": (
            f"*{L2_HEADING}*\n" + "\n".join(
                f"・{esc(r['c']['title'][:40])}（{first(r['c']) or day(r['c'])}、{r['c'].get('buzz_outlets', 0)}媒体"
                + ("、⚠️一次資料 要確認" if r["c"].get("primary_verified", "未") is None else "") + "）" for r in l2))[:2900]}]})
    wait = [r for r in rows if r["lane"] == L2_WAIT_LANE][:3]
    if wait:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": f"再評価待ち（大手の製品発表、{L2_MIN_TOPIC_AGE_DAYS}日後に答え合わせ候補へ）: "
                                                       + " ／ ".join(esc(r["c"]["title"][:28]) for r in wait)}]})
    n_false = sum(1 for r in rows if r["c"].get("primary_verified") is False)
    if n_false:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": f"一次資料URLが実在しない（全URLが404）ため除外: {n_false}件"}]})
    brk = [r for r in rows if r["lane"] == "速報"][:3]
    if brk:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": "速報（48時間後に再計測）: " + " ／ ".join(esc(r["c"]["title"][:28]) for r in brk)}]})
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": "朝の /kl-new で仕上げます（既視感・競合動画・一次資料の確認）"}]})
    print(json.dumps({"text": "KL ネタ ベスト3の下書き", "blocks": blocks}, ensure_ascii=False))


LANE_ORDER = {"本命": 0, L2_LANE: 1, "速報": 2, L2_WAIT_LANE: 3, "ニッチ": 4, "注目度低": 5, "未計測": 6}


def cmd_list_by_genre(per: int):
    """5ジャンルごとに、本命枠と同じゲート・同じ並び（core）で上位 per 件を出す。薄いときは薄いと表示する。"""
    g = json.loads(GENRES_JSON.read_text(encoding="utf-8"))
    rows = [r for r in classify(load_candidates()["items"]) if not r["gate"]]
    for key in g["order"]:
        mine = [r for r in rows if r["c"].get("genre") == key]
        mine = collapse_series(sorted(mine, key=lambda r: (-LANE_ORDER[r["lane"]], r["core"] if r["core"] is not None else -1, r["tb"],
                                                             r["c"].get("buzz_outlets") or 0),
                                      reverse=True))
        nh = sum(1 for r in mine if r["lane"] == "本命")
        nl2 = sum(1 for r in mine if r["lane"] == L2_LANE)
        print(f"\n==== {g['genres'][key]['label']}（{key}）— ゲート通過{len(mine)}系列（うち本命{nh}"
              + (f"、{L2_LANE}{nl2}" if nl2 else "") + "） ====")
        if not mine:
            print("   （ゲートを通る候補なし。collect/score を増やす必要あり）")
        elif nh == 0:
            print("   （本命枠の候補なし。以下は注目度が低いか未計測）")
        for r in mine[:per]:
            print(f"  〈{r['lane']}〉", end="")
            _print_candidate(r)


def main():
    ap = argparse.ArgumentParser(description="ニュース起点のネタ選定（collect → score → tag → enrich → buzz → list）")
    ap.add_argument("command", choices=["collect", "score", "verify", "list", "tag", "enrich", "buzz", "check-urls", "slack", "yt"])
    ap.add_argument("--days", type=int, default=21)
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--by-genre", action="store_true", help="list: 5ジャンルごとに上位を出す（--top はジャンルあたりの件数）")
    ap.add_argument("--check-urls", action="store_true", help="list: ベスト3・本命枠の一次資料URLを確認してから出す（ソフト404も検出）")
    ap.add_argument("--max", type=int, default=None,
                    help=f"buzz: 1回で測る上限（既定・最大{GNEWS_MAX_PER_RUN}） / verify: 確かめる候補の上限（既定{VERIFY_DEFAULT_MAX}）")
    ap.add_argument("--id", nargs="*", default=[],
                    help="buzz / check-urls / verify / yt: 対象の候補ID（指定するとゲートに関係なく測る・確かめる）")
    ap.add_argument("--all", action="store_true", help="verify: 確認済みの候補も確かめ直す（既定は未確認だけ）")
    ap.add_argument("--count", type=int, default=None, help="yt: 日本語の解説動画の本数（手で数えた値）")
    ap.add_argument("--query", default="", help="yt: YouTube で検索した語（任意、記録用）")
    ap.add_argument("--force", action="store_true", help="enrich: 付与済みも付け直す / buzz: 最近測った候補も測り直す")
    ap.add_argument("--remeasure-hours", type=float, default=24, help="buzz: これより最近に測った候補は飛ばす（既定24時間）")
    ap.add_argument("--dry-run", action="store_true", help="buzz: 測るが保存しない / score: 採点する候補を表示するだけ（課金なし）")
    ap.add_argument("--sources", type=Path, default=None, help="collect: news_sources.json の代わりに使う設定（試験用）")
    ap.add_argument("--no-gemini", action="store_true", help="collect: Gemini（話題の補完・分野の絞り込み）を呼ばない（試験用）")
    ap.add_argument("--note", default="", help="slack: ジャンルの間隔などを拾うテキスト（kl_concern_select.py の出力）")
    args = ap.parse_args()
    if args.command == "slack":
        cmd_slack(args.note)
    elif args.command == "collect":
        cmd_collect(args.days, args.sources, args.no_gemini)
    elif args.command == "score":
        cmd_score(args.top, args.dry_run)
    elif args.command == "tag":
        cmd_tag()
    elif args.command == "enrich":
        cmd_enrich(args.force)
    elif args.command == "buzz":
        cmd_buzz(args.max or GNEWS_MAX_PER_RUN, args.force, args.remeasure_hours, args.id, args.dry_run)
    elif args.command == "verify":
        cmd_verify(args.id, args.all, args.max or VERIFY_DEFAULT_MAX)
    elif args.command == "yt":
        cmd_yt(args.id, args.count, args.query)
    elif args.command == "check-urls":
        cmd_check_urls(args.id, args.top)
    elif args.by_genre:
        cmd_list_by_genre(args.top)
    else:
        cmd_list(args.top, args.check_urls)


if __name__ == "__main__":
    main()
