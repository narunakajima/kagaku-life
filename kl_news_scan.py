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

使い方（collect → score → tag → enrich → buzz → list）:
  python3 kl_news_scan.py collect [--days 21]
  python3 kl_news_scan.py score [--top 15]      # 検索つき、1件ずつ課金
  python3 kl_news_scan.py tag                   # ジャンル未付与に5ジャンル（テキストのみ）
  python3 kl_news_scan.py enrich                # ゲート通過分に検索語・見出しの語・発表の種類・系列（テキストのみ）
  python3 kl_news_scan.py buzz [--max 50]       # Google ニュース RSS で注目度を実測（1候補1回、2秒以上の間隔）
  python3 kl_news_scan.py list [--top 10] [--by-genre] [--check-urls]
  python3 kl_news_scan.py check-urls [--id ID ...]   # 一次資料のURL（ソフト404も）を確認
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
    for t in (tag, "{http://www.w3.org/2005/Atom}" + tag):
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


def fetch_feed(feed: dict, since: datetime) -> list:
    raw = urllib.request.urlopen(urllib.request.Request(feed["url"], headers=UA), timeout=20).read()
    root = ET.fromstring(raw)
    items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
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
    return out


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


def cmd_collect(days: int):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    feeds = json.loads(SOURCES_JSON.read_text(encoding="utf-8"))["feeds"]
    pool = []
    for f in feeds:
        try:
            got = fetch_feed(f, since)
            pool += got
            print(f"  {f['name']}: {len(got)}件")
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️ {f['name']}: 取得失敗 {e}")
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

    # 話題の絞り込み（タイトルと要約だけで、番組で扱える分野かをまとめて判定する。検索なし）
    client, types = _gemini()
    keep = []
    for i in range(0, len(uniq), 60):
        batch = uniq[i:i + 60]
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
    print(f"\n収集 {len(uniq)}件 → 番組で扱える分野 {len(keep)}件（{POOL_JSON.name}）")


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
"hype_gap": 0, "debate": 0, "wonder": 0, "life_relevance": 0, "concern_id": null, "entry_question": "",
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


def cmd_score(top: int):
    pool = json.loads(POOL_JSON.read_text(encoding="utf-8"))["items"]
    cands = load_candidates()
    known = {c["id"] for c in cands["items"]}
    todo = [p for p in pool if p["id"] not in known]
    # 新しい順に、最大 top 件だけ採点する（検索つきの呼び出しは1件ずつ課金されるため）
    todo.sort(key=lambda p: p.get("published", ""), reverse=True)
    todo = todo[:top]
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
    if freshness_score(c.get("announced_on") or c.get("published", "")) < GATE_MIN_FRESHNESS:
        r.append(f"鮮度<{GATE_MIN_FRESHNESS}")
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


def check_primary_url(url: str, timeout: int = 15) -> dict:
    """一次資料のURLを開いて確かめる（標準ライブラリのみ。取得したHTMLは <title> を読むだけで実行しない）。
    ok: True=開ける / False=404・ソフト404 / None=判断できない（403・429等。ボット拒否の可能性があり人が確認）"""
    try:
        resp = urllib.request.urlopen(urllib.request.Request(url, headers=BROWSER_UA), timeout=timeout)
        raw = resp.read(400_000)
        html = _decode(raw, resp.headers.get("Content-Type", ""))
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        title = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
        if title and SOFT404_TITLE.search(title):
            return {"url": url, "ok": False, "status": f"ソフト404（HTTP {resp.status}、title「{title[:40]}」）"}
        return {"url": url, "ok": True, "status": f"HTTP {resp.status}" + (f"「{title[:30]}」" if title else "")}
    except urllib.error.HTTPError as e:
        if e.code in (404, 410):
            return {"url": url, "ok": False, "status": f"HTTP {e.code}"}
        return {"url": url, "ok": None, "status": f"HTTP {e.code}（ボット拒否の可能性。ブラウザで確認）"}
    except Exception as e:  # noqa: BLE001
        return {"url": url, "ok": None, "status": f"取得失敗（{type(e).__name__}: {str(e)[:60]}）"}


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


def fetch_gnews(query: str, timeout: int = 20) -> list:
    """Google ニュース RSS（日本語）を1回取得する。取得物はXMLとしてパースするだけ。
    失敗（HTTPエラー・同意画面・XMLでない・0件）は GNewsError。"""
    url = GNEWS_URL + urllib.parse.urlencode({"q": f"{query} when:{GNEWS_WINDOW_DAYS}d",
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
        items.append({"title": title, "outlet": name,
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


def cmd_enrich(force: bool):
    cands = load_candidates()
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
    todo.sort(key=lambda c: (-freshness_score(c.get("announced_on") or c.get("published", "")), -buzz_value(c)[0]))
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


def tie_break(c: dict) -> int:
    return sum(_clamp5(c.get(k)) for k in ("hype_gap", "debate", "life_relevance"))


def classify(cands: list) -> list:
    """available な候補に、鮮度・core・枠（lane）・ゲートの理由・系列を付けて返す（データは書き換えない）。"""
    used = used_source_urls(cands)
    rows = []
    for c in cands:
        if c.get("status") != "available":
            continue
        fresh = freshness_score(c.get("announced_on") or c.get("published", ""))
        gate = gate_reasons(c, used)
        bm = c.get("buzz_measured")
        if gate:
            lane = "除外"
        elif bm is None:
            lane = "未計測"
        elif bm >= 3:
            lane = "本命"
        elif age_days(c) * 24 <= BREAKING_HOURS and c.get("announcement_type") in BREAKING_TYPES:
            lane = "速報"
        elif fresh >= NICHE_MIN_FRESHNESS and _clamp5(c.get("hype_gap")) + _clamp5(c.get("debate")) >= NICHE_MIN_HYPE_DEBATE:
            lane = "ニッチ"
        else:
            lane = "注目度低"
        rows.append({"c": c, "fresh": fresh, "gate": gate, "lane": lane,
                     "core": fresh * bm if bm is not None else None,
                     "core_est": fresh * buzz_value(c)[0], "tb": tie_break(c),
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
    core = f"core {r['core']:2d}＝鮮度{r['fresh']}×注目{c['buzz_measured']}" if r["core"] is not None \
        else f"core —（鮮度{r['fresh']}、推定なら{r['core_est']}）"
    print(f"[{core}｜誇張+議論+暮らし {r['tb']}｜旧加重和 {r['old']:.2f}] {c['title'][:76]}"
          f"（{c.get('announced_on') or c.get('published')}、{c.get('genre', '?')}）" + ("  ※健康系" if c.get("health") else ""))
    print(f"   {_buzz_line(c)}")
    for e in c.get("buzz_evidence") or []:
        print(f"     - {e['title']}（{e['outlet']}、{e['date']}）")
    if c.get("url_status"):
        mark = {True: "OK", False: "NG", None: "要確認"}[c.get("url_ok")]
        print(f"   一次資料URL: {mark} — {c['url_status']}（{(c.get('url_checked_at') or '')[:10]}確認）")
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
    print(f"ゲート（検証≥{GATE_MIN_VERIFIABILITY}・鮮度≥{GATE_MIN_FRESHNESS}・使用済み/宣伝でない）で外した候補: {len(ex)}件 "
          + "／".join(f"{k} {v}" for k, v in cnt.items()))
    for r in ex:
        named = [g for g in r["gate"] if g.startswith(("使用済み", "宣伝"))]
        if named:
            print(f"   × {r['c']['title'][:60]} — {'・'.join(named)}")


def run_url_checks(targets: list, cands: dict):
    """一次資料のURLを確かめて候補に保存する（1候補あたり最大3つ、2秒以上の間隔）。"""
    first = True
    for c in targets:
        res = []
        for s in (c.get("primary_sources") or [])[:3]:
            if not s.get("url"):
                continue
            if not first:
                time.sleep(URL_CHECK_INTERVAL)
            first = False
            res.append(check_primary_url(s["url"]))
        if not res:
            continue
        oks = [x["ok"] for x in res]
        c["url_check"] = res
        c["url_ok"] = False if False in oks else (True if all(oks) else None)
        c["url_status"] = " ／ ".join(f"{_host(x['url'])}: {x['status']}" for x in res)
        c["url_checked_at"] = datetime.now().isoformat(timespec="seconds")
        print(f"  [{ {True: 'OK', False: 'NG', None: '要確認'}[c['url_ok']] }] {c['title'][:50]} — {c['url_status']}")
    _save_candidates(cands)


def cmd_check_urls(ids: list, top: int):
    cands = load_candidates()
    if ids:
        targets = [c for c in cands["items"] if c["id"] in ids]
    else:
        rows = classify(cands["items"])
        picks, _ = best3(rows)
        honmei = collapse_series(_sorted_core([r for r in rows if r["lane"] == "本命"]))[:top]
        seen, targets = set(), []
        for r in picks + honmei:
            if r["c"]["id"] not in seen:
                seen.add(r["c"]["id"])
                targets.append(r["c"])
    print(f"一次資料のURLを確認: {len(targets)}件（" + ("指定のID" if ids else "ベスト3・本命枠") + "）")
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
    if niche_extra:
        print("   ＋ ニッチ枠から入れるならこの1件（注目度は低い）:")
        _print_candidate(niche_extra, short=True)

    honmei = collapse_series(_sorted_core([r for r in rows if r["lane"] == "本命"]))
    print(f"\n==== 本命（ゲート通過・実測の注目度≥3、core の順）: {len(honmei)}系列 ====")
    for r in honmei[:top]:
        _print_candidate(r)
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


LANE_ORDER = {"本命": 0, "速報": 1, "ニッチ": 2, "注目度低": 3, "未計測": 4}


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
        print(f"\n==== {g['genres'][key]['label']}（{key}）— ゲート通過{len(mine)}系列（うち本命{nh}） ====")
        if not mine:
            print("   （ゲートを通る候補なし。collect/score を増やす必要あり）")
        elif nh == 0:
            print("   （本命枠の候補なし。以下は注目度が低いか未計測）")
        for r in mine[:per]:
            print(f"  〈{r['lane']}〉", end="")
            _print_candidate(r)


def main():
    ap = argparse.ArgumentParser(description="ニュース起点のネタ選定（collect → score → tag → enrich → buzz → list）")
    ap.add_argument("command", choices=["collect", "score", "list", "tag", "enrich", "buzz", "check-urls"])
    ap.add_argument("--days", type=int, default=21)
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--by-genre", action="store_true", help="list: 5ジャンルごとに上位を出す（--top はジャンルあたりの件数）")
    ap.add_argument("--check-urls", action="store_true", help="list: ベスト3・本命枠の一次資料URLを確認してから出す（ソフト404も検出）")
    ap.add_argument("--max", type=int, default=GNEWS_MAX_PER_RUN, help=f"buzz: 1回で測る上限（最大{GNEWS_MAX_PER_RUN}）")
    ap.add_argument("--id", nargs="*", default=[], help="buzz / check-urls: 対象の候補ID（指定するとゲートに関係なく測る・確かめる）")
    ap.add_argument("--force", action="store_true", help="enrich: 付与済みも付け直す / buzz: 最近測った候補も測り直す")
    ap.add_argument("--remeasure-hours", type=float, default=24, help="buzz: これより最近に測った候補は飛ばす（既定24時間）")
    ap.add_argument("--dry-run", action="store_true", help="buzz: 測るが保存しない")
    args = ap.parse_args()
    if args.command == "collect":
        cmd_collect(args.days)
    elif args.command == "score":
        cmd_score(args.top)
    elif args.command == "tag":
        cmd_tag()
    elif args.command == "enrich":
        cmd_enrich(args.force)
    elif args.command == "buzz":
        cmd_buzz(args.max, args.force, args.remeasure_hours, args.id, args.dry_run)
    elif args.command == "check-urls":
        cmd_check_urls(args.id, args.top)
    elif args.by_genre:
        cmd_list_by_genre(args.top)
    else:
        cmd_list(args.top, args.check_urls)


if __name__ == "__main__":
    main()
