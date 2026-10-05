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

使い方:
  python3 kl_news_scan.py collect [--days 21]
  python3 kl_news_scan.py score [--top 15]
  python3 kl_news_scan.py list [--top 10]
"""

import argparse
import email.utils
import hashlib
import json
import os
import re
import sys
import time
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
SCAN_VERSION = "2026-10-06-genres"

# 採点の重み（追記メモ §4）。検証可能性は足切り（MIN_VERIFIABILITY）にも使う
WEIGHTS = {
    "freshness": 0.15,       # 発表からの日数（コードで計算）
    "buzz_jp": 0.15,         # 日本語圏で話題か、今後なりそうか
    "hype_gap": 0.15,        # 見出しと中身の差（大きいほどツッコミの材料）
    "debate": 0.15,          # 議論を呼ぶか・二人の判定が割れそうか
    "wonder": 0.15,          # 驚き・ワクワク（温かい感動だけでなく知的な驚きも）
    "life_relevance": 0.15,  # 暮らしにどう関わるか（viewer_concerns.json を参照）
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
   - buzz_jp: 日本語圏でも話題になっているか、今後なりそうか
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

JSONオブジェクトのみで出力（他の文章は書かない）:
{{"primary_sources": [], "announced_on": "", "headline_claim": "", "actual_content": "", "buzz_jp": 0, "verifiability": 0,
"hype_gap": 0, "debate": 0, "wonder": 0, "life_relevance": 0, "concern_id": null, "entry_question": "",
"expected_verdicts": {{}}, "tsukkomi_material": "", "investment_related": false, "deja_vu_note": "", "genre": "", "health": false}}
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


def overall(v: dict, published: str) -> float:
    s = dict(v)
    s["freshness"] = freshness_score(v.get("announced_on") or published)
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
              f"誇張{v.get('hype_gap')} 議論{v.get('debate')} 話題{v.get('buzz_jp')}"
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


def _print_candidate(c: dict):
    print(f"[{c['overall_score']:.2f}] {c['title'][:80]}（{c.get('announced_on') or c.get('published')}）"
          + ("  ※健康系" if c.get("health") else ""))
    print(f"   問い: {c.get('entry_question')}")
    print(f"   見出し: {c.get('headline_claim')}")
    print(f"   実際: {c.get('actual_content')}")
    print(f"   ツッコミ: {c.get('tsukkomi_material')}  予想判定: {c.get('expected_verdicts')}")
    print(f"   一次資料: " + ", ".join(s.get('url', '') for s in c.get('primary_sources', [])))
    if c.get("deja_vu_note"):
        print(f"   既視感: {c['deja_vu_note']}")


def cmd_list_by_genre(per: int):
    """5ジャンルごとに上位 per 件を出す。ジャンルが薄いときは薄いと表示する（無理に埋めない）。"""
    g = json.loads(GENRES_JSON.read_text(encoding="utf-8"))
    cands = load_candidates()["items"]
    avail = [c for c in cands if c.get("status") == "available"]
    for c in avail:
        c["overall_score"], c["freshness"] = overall(c, c.get("published", ""))
    for key in g["order"]:
        mine = sorted((c for c in avail if c.get("genre") == key), key=lambda c: c["overall_score"], reverse=True)
        print(f"\n==== {g['genres'][key]['label']}（{key}）— 採点済み{len(mine)}件 ====")
        if not mine:
            print("   （採点済みの候補なし。collect/score を増やす必要あり）")
        for c in mine[:per]:
            _print_candidate(c)


def cmd_list(top: int):
    cands = load_candidates()["items"]
    avail = [c for c in cands if c.get("status") == "available"]
    # 鮮度は表示時点で計算し直す（日が経つほど下がる）
    for c in avail:
        c["overall_score"], c["freshness"] = overall(c, c.get("published", ""))
    avail.sort(key=lambda c: c["overall_score"], reverse=True)
    for c in avail[:top]:
        _print_candidate(c)


def main():
    ap = argparse.ArgumentParser(description="ニュース起点のネタ選定")
    ap.add_argument("command", choices=["collect", "score", "list", "tag"])
    ap.add_argument("--days", type=int, default=21)
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--by-genre", action="store_true", help="list: 5ジャンルごとに上位を出す（--top はジャンルあたりの件数）")
    args = ap.parse_args()
    if args.command == "collect":
        cmd_collect(args.days)
    elif args.command == "score":
        cmd_score(args.top)
    elif args.command == "tag":
        cmd_tag()
    elif args.by_genre:
        cmd_list_by_genre(args.top)
    else:
        cmd_list(args.top)


if __name__ == "__main__":
    main()
