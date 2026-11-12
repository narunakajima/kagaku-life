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

2026-10-25（想定する視聴者に合わせた並び、なるさんの指示）: core を 鮮度 × 実測の注目度 × 視聴者（audience_fit）にした。
  audience_fit は「AIや新しい技術に興味がある50〜60代（経営者・自営業・商売人が多い）」が見たいと思い、自分の暮らし・店・会社に
  引きつけて考えられるか（1〜5、AUDIENCE_FIT_RUBRIC）。score で付け、それ以前の候補には enrich がテキストのみで付ける。
  無い候補は暮らし・仕事の高い方で代用する。健康系は4までに丸める（健康が中心の番組にしないため）。同点の並びも 誇張＋議論＋視聴者。
  ゲート（暮らし・仕事≧4）は変えていない

2026-10-26（構成 v4「実現ラウンド」、なるさんの指示。DIALOGUE_REDESIGN_2026-10-26.md）: 実現への手応え（promise、1〜5、PROMISE_RUBRIC）と
  hope_material（一次資料で確かめられる前向きな事実）を採点に足した。同点の並びを 手応え＋議論＋視聴者 にし（誇張を外した）、
  加重和の hype_gap を 0.10 → 0.05 に下げた。promise が3未満（誇張・宣伝が中心）の候補はベスト3に入れない（一覧・ニッチ枠には残る）。
  同日、ベスト3に「視聴者との合い方3以上・健康系1件まで」の条件も足した

2026-11-07（面白さで並べる、なるさんの決定。Muse の提案「ネタ選定の改善」）: 旬（鮮度）と実測の注目度は「入る条件」に下げ
  （本命＝鮮度3以上・実測3以上のゲートはそのまま）、条件を通った候補の中は **面白さ＝驚き（wonder）＋視聴者（audience_fit）＋
  見せられるか（tangible）**（3〜15）で並べる。core（鮮度×注目×視聴者）は面白さが同点のときの並びに回した。wonder は採点の目安を
  WONDER_RUBRIC に書き直し、視聴者が何に驚くかの1行（surprise_line）を足した。1行で言い切れない（空の）候補はベスト3に入れない。
  既存の候補は enrich が付け直す（interest_version）

2026-10-15（NEWS_REDESIGN_2026-10-15.md の1週目）:
  - verify: 採点の直後に一次資料URLの実在を確かめる（HTTP・ソフト404、DOIは doi.org のハンドルAPI）。
    primary_verified が False（全URLが404）の候補はゲートで落とし、None（403等で判断不能）は「要確認」で残す
  - topic_age: 鮮度を「系列の最初の日付」（同じ系列の候補・news_pool.json の記事・buzz_evidence の最古）から数える
  - 答え合わせ候補: 製品発表・日本語10媒体以上・初出から2日以上は、本命とは別の枠に出す（2日未満は再評価待ち）
  - ベスト3は混成（同日の追加）: 本命の上位を優先し、空きを答え合わせ候補で埋める（〈本命〉〈答え合わせ〉）。
    3件に満たないときだけ同じジャンルを2件まで許し、一次資料が「要確認」の候補は最後の補欠
  - buzz の履歴（同日の追加）: 測り直しても上書きせず buzz_history に残し、同じ検索語の直近3回（7日以内）の最大を採用
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
import math
import os
import kl_gemini_model as gm
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
# 2026-11-09: "gemini-flash-latest" は Actions（nightly-news #27）で 404（models/gemini-flash-latest is not found for API version v1）
# になり、採点・付与が全件失敗した。-latest のエイリアスは使わず、安定版のモデルIDを固定する
# gemini-2.5-flash は「新規キーでは使えない」404 になったため（2026-11-09 実測）、ListModels にある gemini-3.8-flash にした
MODEL = gm.primary()
STALL_FILE = BASE_DIR / "nightly_stall.txt"   # 採点停止の記録（Actions が Slack に「止まっています」を送る。コミットしない）
UA = {"User-Agent": "Mozilla/5.0 (kagaku-life news scan)"}

# 一次資料が確認できない候補は採用しない（追記メモ §3）。検証可能性がこの点以下なら除外する
MIN_VERIFIABILITY = 3
SCAN_VERSION = "2026-11-07-interest"
INTEREST_VERSION = "2026-11-07"   # wonder（新しい目安）と surprise_line を付けた版。違えば enrich が付け直す

# 想定する視聴者（2026-10-25、CLAUDE.md「想定する視聴者」）。audience_fit（1〜5）の採点に使い、
# core の「関わり」は audience_fit で数える（無い候補は従来の暮らし・仕事の高い方）
AUDIENCE = (
    "50〜60代で、AIや新しい技術に興味がある人。経営者・自営業・商売をしている人が多く、会社勤めの人・退職した人もいる。"
    "統計・論文・プログラミングの専門知識はない。健康の話題ばかりの番組は望んでいない")
AUDIENCE_FIT_RUBRIC = (
    "audience_fit: 上の視聴者が見出しを見て「見たい」と思い、自分の暮らし・店・会社に引きつけて考えられるか。\n"
    "     5 = 自分の店・会社・暮らしで使えるか、お金を払う価値があるかをすぐ考えたくなる（例: 小さな会社でも使えるAIの新機能、人手不足を補う機械）\n"
    "     4 = 強く興味を引く（AI・ロボットの大きな進歩で、自分や業界・取引先への影響が想像できる）\n"
    "     3 = 興味は持つが、自分ごとにはなりにくい\n"
    "     2 = 若い世代・特定の趣味向け（ゲーム、SNSの流行、若者のガジェット）や、開発者・研究者向けの道具\n"
    "     1 = 専門家しか関心を持たない\n"
    "     迷ったら低い方を付ける。")
HEALTH_FIT_MAX = 4   # 健康系（health: true）の audience_fit の上限。健康が中心の番組にしないため（コードで丸める）
# 実現への手応え（2026-10-26、構成 v4。DIALOGUE_REDESIGN_2026-10-26.md）。番組の問いを「本当か？」から
# 「どこまで来た？ どうすれば使える？」に変えたため、誇張（hype_gap）の加点を下げ、本物の進歩かを採点する
PROMISE_RUBRIC = (
    "promise: 実現への手応え。一次資料で確かめられる本物の進歩があり、上の視聴者が「こう使える」と使い道を思い描けるか。\n"
    "     5 = 本物の進歩が一次資料の数字・実物で確かめられ、使い道がすぐ描ける（もう使える、または試せる）\n"
    "     4 = 本物の進歩で、条件つきでも使い道が描ける\n"
    "     3 = 進歩はあるが、使い道はまだぼんやりしている\n"
    "     2 = 中身が薄い（見出しの盛りが話題の中心、既存品の組み合わせ・言い換え）\n"
    "     1 = 宣伝・誇張だけで、確かめられる進歩がない\n"
    "     迷ったら低い方を付ける。")
# 登録につながる要素（2026-11-04、他チャンネル調査 docs/channel_research_2026-11-04.md、なるさんが採用）。
# 伸びている小〜中規模の日本語チャンネルは、人型ロボなど「物」を、値段・買える時期・どこで動いているかと組み合わせ、
# 同じ問いを連番で続けている（推定）。当チャンネルで登録が出たShorts 4本のうち3本もロボット
TANGIBLE_RUBRIC = (
    "tangible: 手で触れる物として見せられるか。実物の映像・写真があり、一目で「何か」が分かるか。\n"
    "     5 = 人型ロボット・機械・装置・治療の実物など、映像で一目で分かる物が主役\n"
    "     4 = 物が主役だが、映像が限られる（試作機、図面が中心）\n"
    "     3 = 物と抽象が半々（物を使うソフト、物を含む研究）\n"
    "     2 = ソフト・サービスが中心で、画面の見せ方が限られる\n"
    "     1 = 性能の数字・予測・方針など抽象的な話で、見せる物がない\n"
    "     迷ったら低い方を付ける。")
DECISION_NUMBER_RUBRIC = (
    "decision_number: 経営者・商売人が「うちで使えるか、いくらか」を考えるための判断の数字が、一次資料で言えるか。\n"
    "     5 = 値段（本体・月額）と、買える・予約できる・導入できる時期や条件が、一次資料に書かれている\n"
    "     4 = 値段か時期のどちらか、または導入先・台数・稼働している現場が書かれている\n"
    "     3 = 条件つきの目安はあるが、値段・時期は書かれていない\n"
    "     2 = 数字はあるが、使う側の判断には関係しない（性能指標だけ）\n"
    "     1 = 判断に使える数字が無い\n"
    "     迷ったら低い方を付ける。")
SERIES_FIT_RUBRIC = (
    "series_fit: ヒューマノイド（人型ロボット）の定点観測シリーズ「いつ・いくらで・どこで店や家に来る？」の続きになるか。\n"
    "     5 = 人型ロボの発表で、前回から動いた値段・予約・出荷・導入先・稼働中の現場が一次資料にある\n"
    "     4 = 人型ロボの発表で、シリーズの物差し（どこまで来た？ いつ・いくらで？）に当てはめられる\n"
    "     3 = 人型でないロボット・機械の発表で、同じ物差しで比べられる\n"
    "     2 = ロボットだが、物差しには当てはめにくい（研究の途中経過、要素技術）\n"
    "     1 = ロボットと関係がない\n"
    "     迷ったら低い方を付ける。")

# 驚き（2026-11-07、目安を書き直した）。面白さ（wonder＋audience_fit＋tangible）としてベスト3の並び順の主役に使う
WONDER_RUBRIC = (
    "wonder: 上の視聴者が「え、本当に？」「そこまで来たの？」と驚くか（一次資料の範囲で言える驚きだけ。見出しの盛りは数えない）。\n"
    "     5 = 常識が覆る・予想と逆の結果、または桁違いの数字（例: 人がやると思っていた仕事を機械が丸一日こなした、値段が1/10になった）\n"
    "     4 = 「もうそこまで？」と思う進み方（身近な店・家・仕事で、予想より早く実物が動いている）\n"
    "     3 = 順当な進歩（前の版より良くなった、予想どおりの発表）\n"
    "     2 = 業界の人には意味があるが、一般の人は驚かない（性能の数字の小さな更新、提携・人事）\n"
    "     1 = 驚く点がない\n"
    "     既に主要なAIサービス・OS・アプリで一般の人が普通に使えている機能は、新発表でも2以下（先行事例チェックでも上限2を掛ける）。\n"
    "     迷ったら低い方を付ける。")
SURPRISE_LINE_RULE = (
    "surprise_line: 上の視聴者のうち「誰が、何に驚くか」を1行（40字以内）で。形は「〇〇の人が、〜に驚く」"
    "（例: 「コンビニの店主が、ロボが夜中も含め24時間店を回したことに驚く」）。一次資料に書かれていることだけで言い切れなければ空にする。"
    "「誰が」は特定の業界・職種・立場に狭めない（経営者だけ・エンジニアだけが驚く話は向かない）")

# ベスト3・本命枠に入れる条件（2026-10-11、P0）。一覧そのものの足切りは MIN_VERIFIABILITY のまま
GATE_MIN_VERIFIABILITY = 4
GATE_MIN_LIFE = 4            # 暮らし（life_relevance）と仕事・ビジネス（work_relevance）の高い方が3以下なら本命に入れない（2026-10-12）
GATE_MIN_FRESHNESS = 3       # freshness_score で3以上＝発表から21日以内

# 互換用の加重和（overall_score）。list の並び順の主役は面白さ（interest、2026-11-07〜。その次が core）で、こちらは参考表示のみ。
# buzz は buzz_measured（実測）があればそれ、無ければ buzz_jp_est（推定。旧データは buzz_jp）を使う
WEIGHTS = {
    "freshness": 0.25,       # 発表からの日数（コードで計算）。最重視（2026-10-11、なるさんの指示: 旬の話題）
    "buzz": 0.25,            # 日本語圏での注目度（実測優先）。最重視（同: 注目度の高い話題）
    "hype_gap": 0.05,        # 見出しと中身の差（2026-10-26 に 0.10 から下げた。誇張の大きさは番組の価値ではない）
    "promise": 0.05,         # 実現への手応え（2026-10-26 追加、PROMISE_RUBRIC）
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
GNEWS_COLLECT_MAX_REQ = 30     # 1回の collect で Google ニュースに送る上限（2026-11-10: 15→30。シリーズのウォッチ対象を狙う検索語を足したため）


def collect_gnews(queries: list, since: datetime, per_query: int, series_per_query: int = None) -> list:
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
        # 2026-11-10: series 付きの検索語（ウォッチ対象×節目の語）は取り込み上限を小さくし、ノイズでプールを埋めない
        cap = (series_per_query or per_query) if gq.get("series") else per_query
        for it in sorted(items, key=lambda x: x["date"], reverse=True):
            if not it["date"] or it["date"] < since.date().isoformat():
                continue
            outlet = it["outlet"] or it["host"]
            row = {"title": it["title"], "url": "", "gnews_link": it.get("link", ""),
                   "published": it["date"],
                   "source": f"Googleニュース（{q}）／{outlet}", "source_kind": "media",
                   "outlet": outlet, "outlet_host": it.get("host", ""), "genre_hint": gq.get("genre", ""),
                   "summary": f"{it['title']}（{outlet}）"}
            if gq.get("series"):
                row["series_query"] = gq["series"]
            got.append(row)
            if len(got) >= cap:
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


# NHK の政治ニュースの除外（2026-11-10、指示 2026-11-10-016。ソース×ジャンルの判定）。
#   対象の「ソース」= NHK（フィード名・Googleニュースの媒体名・URL が NHK）。他の媒体の政治ニュースはここでは扱わない。
#   「ジャンル」= 見出し・要約の語による簡易判定（政治）。強い語（首相・大統領・外相・与野党・国会・首脳会談・選挙・戦争・和平 等）に
#   当たれば常に除外。弱い語（政府・規制・省庁 等）は、科学・技術の語（AI・ロボット・研究・実験・開発 等）が無いときだけ除外。
#   NHK の科学・技術系（研究成果・技術・医療・製品）は残る。収集（prescore_exclusions）・採点キュー（cmd_score）・
#   既存の採点済み候補（gate_reasons）の3か所で同じ判定を使う。
NHK_POLITICS_STRONG = re.compile(
    r"首相|大統領|外相|官房長官|副総理|総理|閣僚|大臣|与党|野党|自民|維新|立憲|公明|国民民主|共産党|参政党|れいわ|国会|参院|衆院|"
    r"議員|議運|内閣|政権|首脳|外交|会談|選挙|解散|法案|予算案|安保|防衛|自衛隊|軍事侵攻|侵攻|停戦|和平|戦闘|ミサイル|ウクライナ|(?<![ァ-ヶー])イラン|イスラエル|ロシア|北朝鮮|"
    r"制裁|関税|サミット|G7|G20|APEC|ASEAN|外相会合|COP\d+|国連|大使|領事|首相動静|知事|市長|"
    r"農相|法相|財務相|経産相|文科相|国交相|厚労相|環境相|総務相|防衛相|デジタル相|議会|議席|議長|県議|都議|市議|党|与野|検査院|財務省|財政審|"
    r"トランプ|習近平|プーチン|ゼレンスキー|ネタニヤフ|高市|石破|茂木|木原|フーシ派|(?<![ァ-ヶー])ハマス|(?<![ァ-ヶー])ガザ|"
    r"(?<![ァ-ヶー])テロ|銃乱射|クーデター", re.I)
NHK_POLITICS_WEAK = re.compile(r"政府|規制|省|庁|国交|法改正|支持率|世論調査|審議|税|補助金|与野党", re.I)
NHK_SCITECH = re.compile(
    r"AI|人工知能|ロボット|研究|実験|開発|技術|発見|ウイルス|治療|治験|新薬|医療|がん|iPS|細胞|遺伝子|量子|半導体|"
    r"宇宙|衛星|ロケット|電池|自動運転|ドローン|センサー|解明|成功|論文|大学|科学|搭載", re.I)


def is_nhk(it: dict) -> bool:
    """NHK の記事か（フィード名・Googleニュースの媒体名・URL のどれかが NHK）。"""
    s = " ".join([it.get("source") or "", it.get("outlet") or "", it.get("outlet_host") or "", it.get("url") or ""] + list(it.get("sources") or []))
    return bool(re.search(r"NHK|nhk\.or\.jp|news\.web\.nhk", s, re.I))


def nhk_politics_reason(it: dict) -> str:
    """NHK の政治ニュースなら除外の理由（語）、そうでなければ空。見出し・要約・（採点済みなら）問いと実際の内容で判定する。"""
    if not is_nhk(it):
        return ""
    t = _nfkc((it.get("title") or "") + " " + (it.get("summary") or "")[:120])
    m = NHK_POLITICS_STRONG.search(t)
    if m:
        return f"NHKの政治ニュース（語: {m.group(0)}）"
    m = NHK_POLITICS_WEAK.search(t)
    if m and not NHK_SCITECH.search(t):
        return f"NHKの政治ニュース（語: {m.group(0)}、科学・技術の語なし）"
    return ""


def prescore_exclusions(it: dict, used: dict) -> str:
    """プールの段階で外す理由（score の課金を避ける）。使用済み・却下済みと同じ一次資料のURL、顧客の導入事例（宣伝）、NHK の政治ニュース。"""
    why = nhk_politics_reason(it)
    if why:
        return why
    u = _norm_url(it.get("url", ""))
    if u and u in used:
        return f"使用済みと同じ資料（{used[u]}）"
    if is_customer_case(it):
        return "顧客の導入事例（宣伝）"
    return ""


def _gemini():
    from google import genai
    from google.genai import types
    return gm.wrap_client(genai.Client(api_key=API_KEY)), types


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
        pool += collect_gnews(cfg["gnews_queries"], since, int(cfg.get("gnews_max_per_query", 30)),
                              int(cfg.get("gnews_series_max_per_query", 12)))
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
番組は、期待担当と確かめ担当の二人が、最新の発表を「一次資料」で確かめ、「どこまで来たか、どうすれば使えるか、いつ暮らしに来るか」を
「もうすぐ来る／3年はかかる／根拠待ち／まだ眉唾」で判定する掛け合い形式です。夢を潰す番組ではなく、資料で確かめて夢を実現に近づける番組です。

【候補のニュース】
タイトル: {title}
発表日（RSS/検索の日付）: {published}
情報源: {source}（{source_kind}）
URL: {url}
要約: {summary}

【この番組の過去の回（似た話の重複を避けるため）】
{past}

【想定する視聴者】
{audience}

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
   - hype_gap: 見出しと実際の中身の差（差が大きいほど高い）
   - {promise_rubric}
   - debate: 議論を呼ぶか・二人の判定が割れそうか
   - {wonder_rubric}
   - life_relevance: 暮らしにどう関わるか（関心ごとのどれかに具体的につながるほど高い）
   - work_relevance: 仕事・ビジネスにどう関わるか（働く人・経営者・個人事業主が今日の仕事や判断で使える、または影響を受けるほど高い。
     開発者・研究者しか使わない専用品は低い）
   - {audience_fit_rubric}
   - {tangible_rubric}
   - {decision_number_rubric}
   - {series_fit_rubric}
6. concern_id: いちばん近い関心ごとのid（無ければ null）
7. entry_question: 視聴者側の問い（「〜は本当？」「〜はもう買える？」「〜はいつ来る？」の形。一次資料の範囲を超えない）
7b. {surprise_line_rule}
8. expected_verdicts: {{"dreamer": "soon|decade|pending|dubious", "skeptic": "soon|decade|pending|dubious"}}
   （soon=もうすぐ来る（もう使えるか1年ほどで）／decade=3年はかかる（お題の主張が3年以内に来そうで、物理・臨床の壁がある）／
    pending=根拠待ち（否定する資料は無いが、支える資料もまだ無い。3年より先の予測を含む）／
    dubious=まだ眉唾（資料が逆を示す・資料の範囲を大きく超える・数字が誇張）。お題の主張そのものに対して付ける）
9. tsukkomi_material: 確かめ担当が突ける具体的な点（1〜2文）
9b. hope_material: 一次資料で確かめられる、前向きに使える事実（数値・条件つき、1〜2文。資料に無ければ空にする）
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
"hype_gap": 0, "promise": 0, "debate": 0, "wonder": 0, "life_relevance": 0, "work_relevance": 0, "audience_fit": 0, "tangible": 0, "decision_number": 0, "series_fit": 0, "concern_id": null, "entry_question": "", "surprise_line": "",
"expected_verdicts": {{}}, "tsukkomi_material": "", "hope_material": "", "investment_related": false, "deja_vu_note": "", "genre": "", "health": false,
"jp_news_query": "", "jp_title_anchor": [], "announcement_type": ""}}
"""


def score_item(client, types, item: dict, past: str, concerns: str) -> dict:
    prompt = SCORE_PROMPT.format(title=item["title"], published=item.get("published", ""),
                                 source=item.get("source", ""), source_kind=item.get("source_kind", ""),
                                 url=item.get("url", ""), summary=item.get("summary", ""),
                                 past=past or "（なし）", concerns=concerns, genres=genres_brief(),
                                 audience=AUDIENCE, audience_fit_rubric=AUDIENCE_FIT_RUBRIC,
                                 promise_rubric=PROMISE_RUBRIC, tangible_rubric=TANGIBLE_RUBRIC,
                                 decision_number_rubric=DECISION_NUMBER_RUBRIC,
                                 series_fit_rubric=SERIES_FIT_RUBRIC, wonder_rubric=WONDER_RUBRIC,
                                 surprise_line_rule=SURPRISE_LINE_RULE)
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


def fit(c: dict) -> int:
    """想定する視聴者との合い方（2026-10-25）。core と同点の並びに使う。audience_fit が無い候補は stake で代用する。
    健康系は HEALTH_FIT_MAX までに丸める。ゲートは従来どおり stake（暮らし・仕事）で判定する。"""
    v = _clamp5(c["audience_fit"]) if c.get("audience_fit") is not None else stake(c)
    return min(v, HEALTH_FIT_MAX) if c.get("health") else v


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
        d = json.loads(CANDIDATES_JSON.read_text(encoding="utf-8"))
        for c in d.get("items", []):
            ensure_buzz_history(c)      # 2026-10-15: 履歴の無い実測済みは、現在の値を履歴の1件目にする（既存の欄は変えない）
        return d
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


SERIES_SCORE_RESERVE = 4        # 採点 top 件のうち、シリーズ候補（ウォッチ対象×節目の語）に先に回す最大枠（15件枠の約1/4。残りは従来のジャンル均等）
SERIES_SCORE_PER_SERIES = 2     # 1シリーズあたりの上限（1つのシリーズが優先枠を独占しない）


def pool_series_info(p: dict):
    """プール記事（未採点）の語マッチによるシリーズ判定。ジャンルは見出しの簡易分類（pool_genre）。series_fit は未付与（足切りしない）。"""
    try:
        return series_candidate_info(dict(p, genre=pool_genre(p), series_fit=None))
    except Exception:  # noqa: BLE001
        return None


def pick_series_priority(todo: list, limit: int = SERIES_SCORE_RESERVE) -> list:
    """採点キューの先頭に回すシリーズ候補（語マッチ。収集段階の判定で、採点ではない）。
    シリーズごとに最大 SERIES_SCORE_PER_SERIES 件、全体で最大 limit 件。並びは scoring_priority（日本語媒体が多い・公式・新しい順）。"""
    per, out = {}, []
    for p in sorted(todo, key=scoring_priority):
        si = pool_series_info(p)
        if not si or per.get(si["series_id"], 0) >= SERIES_SCORE_PER_SERIES:
            continue
        per[si["series_id"]] = per.get(si["series_id"], 0) + 1
        out.append((si, p))
        if len(out) >= limit:
            break
    return out


def select_for_scoring(todo: list, cands: list, top: int, verbose: bool = True) -> list:
    used = used_source_urls(cands)
    # 2026-11-10 (handoff 2026-11-10-015): シリーズ候補を先に採点キューへ。通常枠は top - 優先件数（最低 top - SERIES_SCORE_RESERVE = 11件）が残る
    prio = pick_series_priority(todo)
    prio_ids = {p["id"] for _, p in prio}
    todo = [p for p in todo if p["id"] not in prio_ids]
    top_regular = max(0, top - len(prio))
    if verbose and prio:
        print(f"シリーズ候補を優先: {len(prio)}件（上限{SERIES_SCORE_RESERVE}、1シリーズ{SERIES_SCORE_PER_SERIES}件まで）。通常枠は {top_regular}件")
        for si, p in prio:
            print(f"  ★ [{si['name']}] {p.get('published', '')} {p['title'][:60]} ｜ 対象:{si['target']} 節目:{'・'.join(si['milestones'])}")
    top = top_regular
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
    return [p for _, p in prio] + [p for _, p in picked]


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


def report_stall(msg: str):
    """採点・付与が「対象があるのに0件」のときの可視化（2026-11-09）。緑のまま0件、を起こさない。
    STALL_FILE に追記し、呼び出し側は終了コードを非0にする。"""
    line = f"採点が止まっています: {msg}"
    print(f"\n⚠️ {line}")
    with STALL_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


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
    pol = [p for p in todo if nhk_politics_reason(p)]       # 2026-11-10: NHK の政治ニュースは採点しない（既にプールにあるもの）
    if pol:
        print(f"  NHK の政治ニュース {len(pol)}件は採点しません")
        todo = [p for p in todo if p not in pol]
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
    failed = 0
    for p in todo:
        v = score_item(client, types, p, past, concerns_txt)
        if "_error" in v:
            failed += 1
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
        entry = dict(p, **v, freshness=fresh, overall_score=score, scan_version=SCAN_VERSION, interest_version=INTEREST_VERSION,
                     status="excluded" if excluded else "available", excluded_reason="・".join(excluded),
                     scored_at=datetime.now().date().isoformat(),
                     first_seen_at=datetime.now().isoformat(timespec="seconds"), presented_on=[])
        cands["items"].append(entry)
        mark = "×" if excluded else " "
        print(f" {mark}[{score:.2f}] {p['title'][:70]}")
        print(f"       問い: {v.get('entry_question', '')}  鮮度{fresh} 検証{v.get('verifiability')} "
              f"誇張{v.get('hype_gap')} 議論{v.get('debate')} 話題(推定){v.get('buzz_jp_est', v.get('buzz_jp'))}"
              + (f"  除外: {entry['excluded_reason']}" if excluded else ""))
        time.sleep(1.0)
    CANDIDATES_JSON.write_text(json.dumps(cands, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{len(todo) - failed}/{len(todo)}件を採点して {CANDIDATES_JSON.name} に追記しました")
    if todo and failed == len(todo):
        report_stall(f"score: 対象{len(todo)}件すべて失敗（0件採点）")
        sys.exit(1)


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
                for u in (s.get("url"), s.get("repaired_url")):
                    if u:
                        out.setdefault(_norm_url(u), f"{label}: {c['title'][:30]}")
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
    hit = [used[u] for u in (_norm_url(x) for s in c.get("primary_sources", []) or []
                             for x in (s.get("url", ""), s.get("repaired_url", "")) if x) if u in used]
    if hit:
        r.append(f"使用済みと同じ一次資料（{hit[0]}）")
    if is_customer_case(c):
        r.append("宣伝（顧客の導入事例）")
    if nhk_politics_reason(c):
        r.append("NHKの政治ニュース")
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


class _RedirectRecorder(urllib.request.HTTPRedirectHandler):
    """リダイレクトの経路を記録する（2026-11-12: 国別リダイレクト先の404を見分けるため）。"""

    def __init__(self):
        self.chain = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.chain.append(f"{code} {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def check_primary_url(url: str, timeout: int = 15, anchors: list = None, headers: dict = None) -> dict:
    """一次資料のURLを開いて確かめる（標準ライブラリのみ。取得したHTMLは <title> と本文の先頭を文字列として読むだけで実行しない）。
    ok: True=開ける / False=404・ソフト404 / None=判断できない（403・429等。ボット拒否の可能性があり人が確認）
    anchors（候補の固有の語）を渡すと、<title>＋本文の先頭にどれかが含まれるかを anchor_hit に入れる（参考表示。判定には使わない）
    redirects（経路）と final_url（最終URL）を、転送があったときに結果へ入れる。headers は既定の BROWSER_UA を置き換える"""
    rec = _RedirectRecorder()
    try:
        resp = urllib.request.build_opener(rec).open(urllib.request.Request(url, headers=headers or BROWSER_UA), timeout=timeout)
        raw = resp.read(400_000)
        html = _decode(raw, resp.headers.get("Content-Type", ""))
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        title = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
        final = resp.geturl() or url
        if title and SOFT404_TITLE.search(title):
            return dict({"url": url, "ok": False, "status": f"ソフト404（HTTP {resp.status}、title「{title[:40]}」）"}, **_redir_info(url, final, rec))
        out = {"url": url, "ok": True, "status": f"HTTP {resp.status}" + (f"「{title[:30]}」" if title else ""),
               "page_title": title[:120]}
        out.update(_redir_info(url, final, rec))
        if final != url and urllib.parse.urlsplit(final).path in ("", "/") and urllib.parse.urlsplit(url).path not in ("", "/"):
            out["redirected_to_top"] = True      # 記事のURLがトップページに転送された（記事が無い可能性）
            out["status"] += f"（トップページへ転送: {final[:60]}）"
        if anchors:
            body = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html[:200_000], flags=re.I | re.S)
            head = _nfkc(title + " " + re.sub(r"<[^>]+>", " ", body)[:30_000])
            out["anchor_hit"] = any(a in head for a in anchors)
        return out
    except urllib.error.HTTPError as e:
        info = _redir_info(url, getattr(e, "url", None) or url, rec)
        if e.code in (404, 410):
            st = f"HTTP {e.code}" + (f"（転送先 {info['final_url'][:80]} が{e.code}）" if info.get("final_url") else "")
            return dict({"url": url, "ok": False, "status": st, "http404": e.code}, **info)
        return dict({"url": url, "ok": None, "status": f"HTTP {e.code}（ボット拒否の可能性。ブラウザで確認）", "http": e.code}, **info)
    except Exception as e:  # noqa: BLE001
        return {"url": url, "ok": None, "status": f"取得失敗（{type(e).__name__}: {str(e)[:60]}）", "transient": True}


def _redir_info(url: str, final: str, rec) -> dict:
    """転送があれば final_url と redirects（経路）を返す。無ければ空。"""
    if rec.chain or (final and final != url):
        return {"final_url": final, "redirects": list(rec.chain)}
    return {}


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


RECHECK_404_WAIT = 20.0        # 秒。404のとき、少し時間をおいて取り直す
RECHECK_EN_HEADERS = dict(BROWSER_UA, **{"Accept-Language": "en-US,en;q=0.9",
                                         "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"})
LOCALE_PREFIXES = ("/us/en", "/en-us", "/en")     # 国別リダイレクトで404になるサイト向けの、別地域・別言語の候補
_LOCALE_RE = re.compile(r"^/([a-z]{2}([-_][a-z]{2})?)(/[a-z]{2})?(/|$)", re.I)


def alt_locale_urls(url: str) -> list:
    """元のURLに地域・言語の接頭辞を付けた別のURL（元のURLが既に /jp/ja/ のような接頭辞を持つときは、それを外した形も）。"""
    try:
        sp = urllib.parse.urlsplit(url)
    except ValueError:
        return []
    path = sp.path or "/"
    out = []
    m = _LOCALE_RE.match(path)
    base = path[m.end(0) - (1 if m.group(0).endswith("/") else 0):] if m else path
    if m:
        out.append(urllib.parse.urlunsplit((sp.scheme, sp.netloc, base or "/", sp.query, "")))
    for p in LOCALE_PREFIXES:
        if path.startswith(p + "/"):
            continue
        out.append(urllib.parse.urlunsplit((sp.scheme, sp.netloc, p + base, sp.query, "")))
    seen, res = {url}, []
    for u in out:
        if u not in seen:
            seen.add(u)
            res.append(u)
    return res


def recheck_404(url: str, first: dict, anchors: list, pacer=None, wait: float = None, fetch=None) -> dict:
    """HTTP 404/410 を1回で「実在しない」にしない（2026-11-12）。経路と最終URLを記録し、
    (1) 英語のAccept-Languageで取り直す (2) 少し時間をおいて元のヘッダで取り直す (3) 別の地域・言語のURLを試す。
    どれかで開ければ、その結果を返す（別のURLで開けたときは alt_url を付ける）。全て404のときだけ ok=False のまま返す。
    すべての試行を attempts に残す。fetch は試験用の差し替え。"""
    fetch = fetch or (lambda u, h: check_primary_url(u, anchors=anchors, headers=h))
    wait = RECHECK_404_WAIT if wait is None else wait
    attempts = [{"url": url, "via": "初回", "status": first.get("status", ""), "final_url": first.get("final_url", ""),
                 "redirects": first.get("redirects", []), "at": datetime.now().isoformat(timespec="seconds")}]

    def rec(u, via, r):
        attempts.append({"url": u, "via": via, "status": r.get("status", ""), "final_url": r.get("final_url", ""),
                         "redirects": r.get("redirects", []), "at": datetime.now().isoformat(timespec="seconds")})

    plan = [(url, "英語のAccept-Languageで再試行", RECHECK_EN_HEADERS, 0.0),
            (url, f"{int(wait)}秒おいて再試行", BROWSER_UA, wait)]
    plan += [(u, "別の地域・言語のURL", BROWSER_UA, 0.0) for u in alt_locale_urls(url)[:4]]
    for u, via, hdr, w in plan:
        if w:
            time.sleep(w)
        if pacer:
            pacer.wait(u)
        r = fetch(u, hdr)
        rec(u, via, r)
        if r.get("ok") is not False:        # True（開けた）または None（403等＝判断できない）
            out = dict(r, url=url, attempts=attempts, recheck=via)
            if u != url:
                out["alt_url"] = u
                out["status"] = f"{r.get('status', '')}（元のURLは404。{via}: {u}）"
            else:
                out["status"] = f"{r.get('status', '')}（初回は404、{via}で開けた）"
            return out
    return dict(first, attempts=attempts, status=f"{first.get('status', 'HTTP 404')}（再確認{len(attempts) - 1}回とも404・開けず）")


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
        url = (s.get("repaired_url") or s.get("url") or "").strip()    # repair で修復したURLがあればそちらを確かめる
        if not url:
            continue
        pacer.wait(url)
        r = verify_one_url(url, anchors)
        if r["ok"] is None and (r.get("transient") or r.get("http") == 429 or (r.get("http") or 0) >= 500):
            time.sleep(VERIFY_RETRY_WAIT)
            pacer.wait(url)
            r2 = verify_one_url(url, anchors)
            r = dict(r2, status=r2["status"] + "（再試行）")
        if r.get("ok") is False and r.get("http404"):
            # 2026-11-12: 1回の404で「実在しない」にしない。取り直し・別地域のURLを試し、全部404のときだけ False のまま
            r = dict(recheck_404(url, r, anchors, pacer=pacer), method=r.get("method", "http"))
            if r.get("alt_url") and r.get("ok"):      # 別の地域・言語のURLで開けた → そのURLを一次資料として差し替える
                s["repaired_url"], s["repair_method"] = r["alt_url"], "locale-alt"
                s["repair_from"], s["repaired_at"] = url, datetime.now().isoformat(timespec="seconds")
                r.update(url=r["alt_url"], repaired=True, orig_url=url, repair_method="locale-alt", repair_from=url)
        r.pop("transient", None)
        r.pop("http", None)
        r.pop("http404", None)
        r["kind"] = s.get("kind", "")
        if s.get("repaired_url") and not r.get("repaired"):
            if r.get("ok") and _is_pdf(url) and s.get("repair_pdf_text_checked") is False:
                # PDFの本文は標準ライブラリで読めない（check_primary_url の語の照合は当てにならない）。repair の採用時の照合を引き継ぐ
                r.pop("anchor_hit", None)
                r["status"] += "・PDF（本文の語は未確認。repair の採用時にリンク文の語と発表日で照合）"
            r.update(repaired=True, orig_url=s.get("url", ""), repair_method=s.get("repair_method", ""),
                     repair_from=s.get("repair_from", ""))
        res.append(r)
    now = datetime.now().isoformat(timespec="seconds")
    prev = {"verdict": c.get("primary_verified"), "at": c.get("primary_verified_at"),
            "check": c.get("primary_check")} if "primary_verified" in c else None
    verdict = primary_verdict(res)
    note = None
    if prev:
        verdict, note = reconcile_primary(c, prev, verdict, res, now)
    c["primary_verified"] = verdict
    c["primary_check"] = res
    c["primary_verified_at"] = now
    hist = c.get("primary_history") or []
    hist.append({"at": now, "verdict": verdict, "urls": [_hist_url(x) for x in res]})
    c["primary_history"] = hist[-6:]
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
    if note:
        c["primary_verified_note"] = note
    return res


def _hist_url(x: dict) -> dict:
    return {"url": x.get("url", ""), "status": x.get("status", ""), "final_url": x.get("final_url", ""), "ok": x.get("ok")}


def reconcile_primary(c: dict, prev: dict, verdict, res: list, now: str):
    """前回の確認と今回の確認が食い違ったとき、候補を無言で落とさない（2026-11-12）。
    前回 True（開けた）→ 今回 全URLが404（False）のときは、判定を None（要確認）にして primary_conflict に両方の結果
    （時刻・判定・URLごとの状態・最終URL）を残す。落とすかどうかは編集長・ユーザーが決める。
    今回 True になれば食い違いは解消（primary_conflict を消す）。戻り値は (判定, 注記 or None)。"""
    if verdict is True:
        c.pop("primary_conflict", None)
        return verdict, None
    had_ok = prev["verdict"] is True or bool(c.get("primary_conflict"))
    if not had_ok or verdict is not False:
        return verdict, None
    old = c.get("primary_conflict", {}).get("before") if prev["verdict"] is not True else \
        {"at": prev["at"], "verdict": True, "urls": [_hist_url(x) for x in prev["check"] or []]}
    now_r = {"at": now, "verdict": False, "urls": [_hist_url(x) for x in res]}
    c["primary_conflict"] = {"before": old, "after": now_r,
                             "reason": f"確認が食い違い: {(old or {}).get('at', '')[:16]} は開けた／{now[:16]} は全URLが404（再確認でも）"}
    return None, "確認が食い違い（以前は開けたが、今回の再確認は全URL404）。落とすかは編集長・ユーザーが判断"


def _primary_line(c: dict) -> str:
    if "primary_verified" not in c:
        return "一次資料の実在: 未確認（verify 未実行）"
    pv = c["primary_verified"]
    parts = []
    repaired = False
    for x in c.get("primary_check") or []:
        hit = {True: "・固有語あり", False: "・固有語なし（別ページの可能性）"}.get(x.get("anchor_hit"), "")
        if x.get("repaired"):
            repaired = True
            parts.append(f"{x['url']}: {x['status']}{hit}（URLを自動で修復: {REPAIR_METHOD_LABEL.get(x.get('repair_method'), x.get('repair_method', ''))}、"
                         f"元のURL {x.get('orig_url', '')} は404）")
        else:
            parts.append(f"{_host(x['url'])}: {x['status']}{hit}")
    body = " ／ ".join(parts) or c.get("primary_verified_note", "")
    if pv is False and c.get("repair_tried"):
        body += f"（自動修復も見つからず、{(c.get('repair_tried_at') or '')[:10]}）"
    return f"一次資料の実在: {PRIMARY_LABEL[pv]}{'（ブラウザで開いて確かめる）' if pv is None else ''} — {body}" \
           f"（{(c.get('primary_verified_at') or '')[:16]}確認）" + (f"\n   ⚠️ {REPAIR_CAUTION}" if repaired else "") \
           + ("".join("\n   " + ln for ln in conflict_lines(c)))


def _short_urls(side: dict) -> str:
    return "、".join(f"{_host(u['url'])} {u.get('status', '')}" + (f"→最終URL {u['final_url'][:70]}" if u.get("final_url") else "")
                    for u in (side or {}).get("urls", []))


def conflict_lines(c: dict) -> list:
    """確認が食い違っている候補の説明（両方の結果。時刻・状態・最終URL）。無ければ空。"""
    cf = c.get("primary_conflict")
    if not cf:
        return []
    b, a = cf.get("before") or {}, cf.get("after") or {}
    return [f"🔀 {cf.get('reason', '確認が食い違い')}",
            f"   前: {(b.get('at') or '')[:16]} {PRIMARY_LABEL.get(b.get('verdict'), '?')} — {_short_urls(b)}",
            f"   後: {(a.get('at') or '')[:16]} {PRIMARY_LABEL.get(a.get('verdict'), '?')} — {_short_urls(a)}"]


def primary_gate_dropped(rows: list) -> list:
    """一次資料のゲート（全URLが404）だけが理由で、ベスト3・本命から外れた候補。無言で消さず理由つきで見せる用。"""
    out = []
    for r in rows:
        g = r.get("gate") or []
        if g and all(x.startswith("一次資料") for x in g) and r["c"].get("status") == "available":
            out.append(r)
    return out


def primary_drop_text(c: dict) -> str:
    """ゲート落ちの理由つきの1行（URLごとの状態・転送先・再確認の回数・確認時刻）。"""
    parts = []
    for x in c.get("primary_check") or []:
        extra = f"→最終URL {x['final_url'][:60]}" if x.get("final_url") else ""
        n = len(x.get("attempts") or [])
        parts.append(f"{_host(x['url'])} {x.get('status', '')}{extra}" + (f"（試行{n}回）" if n > 1 else ""))
    return f"{'／'.join(parts) or c.get('primary_verified_note', '')}（{(c.get('primary_verified_at') or '')[:16]}確認）"


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


def count_buzz(items: list, anchors: list, issuer_hosts: set, foreign_n: int = None) -> dict:
    """関連する記事（見出しが anchors のどれかを含む）から、日本語の独立媒体の数 n と換算値を出す。
    foreign_n（海外の独立媒体数）を渡すと、海外分を合成した値にする（combine_foreign）。渡さなければ従来どおり日本だけ。"""
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
    out = {"buzz_measured": m, "buzz_outlets": n, "yahoo": yahoo, "buzz_evidence": evidence,
           "buzz_trend": round(c7 / c14, 2) if c14 else None, "buzz_articles_14d": c14}
    if foreign_n is not None:
        out.update(combine_foreign(n, yahoo, foreign_n))
    return out


# 海外メディアの取り入れ（2026-11-10、handoff 2026-11-10-013。編集長ケビンの設計）:
#   日本の独立媒体 nj に、海外（英語圏）の独立媒体 nf を「半分の重み」で足して段階に換算する。
#     n_合算 = nj + ceil(nf / 2)  → BUZZ_TIERS で段階に換算（海外だけでも nf≥5 で 3、nf≥11 で 4。上限6のため海外だけでは5にならない）
#     Yahoo!加点は従来どおり（Yahoo!掲載 かつ 日本の媒体 nj≥2 のときだけ +1。海外分では付かない）
#     新しい値 = max(従来の日本だけの値, 合算の値)  → 従来より下がることはない（海外は足すだけ）
#   buzz_outlets は日本の媒体数のまま（答え合わせ候補の条件 L2_MIN_JP_OUTLETS の意味を変えない）。
#   海外分で入口（3以上）を越えた候補は buzz_foreign_boost=True。本命に入れるには視聴者への合い方が FOREIGN_BOOST_MIN_FIT 以上
#   （日本の視聴者に無関係な海外バズで本命にならないためのゲート。classify 参照）
FOREIGN_WEIGHT_DIV = 2
FOREIGN_EFF_MAX = 6          # 海外分として足せる上限（媒体数換算）。海外だけでは最大4（日本の媒体が4以上あって初めて5）
FOREIGN_BOOST_MIN_FIT = 4
# 汎用の語（製品群・媒体名・分野名だけの検索語は、無関係な記事まで拾って海外の件数がふくらむ。2026-11-10 の実測で
# 「ChatGPT」69媒体・「AMR」24媒体・「Our Future」34媒体）。この語だけの検索語は海外を測らない
FOREIGN_GENERIC = GENERIC_ANCHORS | {"chatgpt", "gemini", "claude", "llm", "amr", "cnn", "bbc", "robot", "our future",
                                     "xai", "ibm", "samsung", "sony", "tesla", "nature", "science"}


def combine_foreign(nj: int, yahoo: bool, nf: int) -> dict:
    jp_m = next(score for lo, score in BUZZ_TIERS if nj >= lo)
    if yahoo and nj >= BUZZ_YAHOO_BONUS_MIN_OUTLETS:
        jp_m = min(5, jp_m + 1)
    n_all = nj + min(FOREIGN_EFF_MAX, (nf + FOREIGN_WEIGHT_DIV - 1) // FOREIGN_WEIGHT_DIV)
    m = next(score for lo, score in BUZZ_TIERS if n_all >= lo)
    if yahoo and nj >= BUZZ_YAHOO_BONUS_MIN_OUTLETS:
        m = min(5, m + 1)
    m = max(m, jp_m)
    return {"buzz_measured": m, "buzz_jp_measured": jp_m, "buzz_outlets_foreign": nf,
            "buzz_foreign_boost": m >= 3 and jp_m < 3}


def _latin_words(s: str) -> list:
    return [w for w in (s or "").split() if re.search(r"[A-Za-z0-9]", w) and w.isascii()]


def foreign_query(c: dict) -> tuple:
    """海外（英語圏）の検索語と、見出しに全て含まれるべき語。日本語だけの候補は ("", [])（海外は測らない）。
    en_news_query・en_title_anchor があればそれ、無ければ jp_news_query の英数字の語（固有名詞は英語表記のまま使われるため）。"""
    q = c.get("en_news_query") or " ".join(_latin_words(c.get("jp_news_query") or "")[:2])
    anc = c.get("en_title_anchor") or _latin_words(q)
    anc = [a.lower() for a in ([anc] if isinstance(anc, str) else anc) if a]
    if not q or not anc or all(a in FOREIGN_GENERIC for a in anc) or q.lower() in FOREIGN_GENERIC:
        return "", []
    return q, anc


def fetch_gnews_en(query: str, timeout: int = 20) -> list:
    """Google ニュース RSS（英語・米国版）を1回取得する。fetch_gnews の英語版。失敗は GNewsError。"""
    url = GNEWS_URL + urllib.parse.urlencode({"q": f"{query} when:{GNEWS_WINDOW_DAYS}d",
                                              "hl": "en-US", "gl": "US", "ceid": "US:en"})
    try:
        raw = urllib.request.urlopen(urllib.request.Request(url, headers=BROWSER_UA), timeout=timeout).read()
        root = ET.fromstring(raw)
    except Exception as e:  # noqa: BLE001
        raise GNewsError(f"{type(e).__name__}: {str(e)[:60]}") from e
    items = []
    for it in root.findall(".//item"):
        src = it.find("source")
        d = _parse_date(it.findtext("pubDate") or "")
        items.append({"title": (it.findtext("title") or "").strip(), "outlet": ((src.text if src is not None else "") or "").strip(),
                      "host": _host((src.get("url") if src is not None else "") or ""),
                      "date": d.date().isoformat() if d else ""})
    return items


def count_foreign(items: list, anchors: list, issuer: set = frozenset()) -> int:
    """英語圏の独立媒体数。見出しが anchors を全て含み、日本語の見出し・転載・PR配信・発表元自身・SNS を除く。14日窓。"""
    since = (datetime.now(timezone.utc).date() - timedelta(days=GNEWS_WINDOW_DAYS)).isoformat()
    outlets = set()
    for it in items:
        t = _nfkc(it["title"])
        # 語境界で照合（"bee" が been、"neo" が neon、"03" が 2003 に当たらないように。管理担当の指摘）
        if not all(re.search(r"(?<![a-z0-9])" + re.escape(a) + r"(?![a-z0-9])", t) for a in anchors) or KANA.search(it["title"]) or (it["date"] and it["date"] < since):
            continue
        h, name = it["host"], it["outlet"]
        if _host_in(h, AGGREGATOR_HOSTS) or any(n.lower() in name.lower() for n in AGGREGATOR_NAMES):
            continue
        if _host_in(h, PR_WIRE_HOSTS) or any(n.lower() in name.lower() for n in PR_WIRE_NAMES) or _host_in(h, SKIP_HOSTS):
            continue
        if any(h == x or h.endswith("." + x) or x.endswith("." + h) for x in issuer if h):
            continue
        outlets.add(name or h)
    return len(outlets)


# YouTube の「英語では熱いが日本語では薄い」差（2026-11-10、handoff 2026-11-10-016。編集長ケビンの設計）:
#   狙い: 英語の YouTube で広く取り上げられているのに日本語の YouTube ではまだ薄い話題は、日本語チャンネルが先行できる好機。
#   測り方: YouTube Data API v3（キー YOUTUBE_API_KEY_KL。無ければ何もしない＝従来どおり）。1候補につき英語・日本語それぞれ
#     search.list（100ユニット）＋videos.list（1ユニット）。14日窓・視聴数順・最大50件。見出しに候補の固有の語を含む動画だけ数える。
#     数えるもの: 独立したチャンネル数・再生数の合計（1本あたり上限 YT_VIEW_CAP。1本のバイラルで膨らまない）・直近7日の本数。
#     差 = log10((英語の再生数+1)/(日本語の再生数+1))。単なる合算ではなく、英語が広く（チャンネル数）・今（7日以内）・厚く（再生数）、
#     かつ日本語が薄い（チャンネル数・再生数比）ときだけ「差あり」。
#   注目度への入れ方（013 の海外メディアとは別枠）: 海外メディア分（combine_foreign）を先に足し、その後に YouTube の差で +1。
#     ・合算の上限: 最終値 ≤ 日本だけの値 + 2（海外メディアと YouTube の合計の持ち上げ幅）、かつ最大 YT_GAP_CAP(=4)。5 は日本の報道が広がった候補だけ
#     ・差あり、の条件に「英語の独立媒体（ニュース）が3以上」を含める（YouTube の再生数だけの話題＝釣り・内輪を除く。実際のニュースを伴うこと）
#     ・視聴者への合い方（audience_fit）が FOREIGN_BOOST_MIN_FIT(4) 未満の候補では、classify が YouTube 分の加点を外して並べる
#       （日本の視聴者に無関係な話題が、差だけで浮かない）。日本語がゼロでも、日本の視聴者に合わない話題は上がらない
YT_API = "https://www.googleapis.com/youtube/v3/"
YT_WINDOW_DAYS = 14
YT_MAX_RESULTS = 50
YT_VIEW_CAP = 500_000            # 1本あたりの再生数の上限（合計に入れる値）
YT_EN_MIN_CHANNELS = 4           # 英語: 独立したチャンネル数
YT_EN_MIN_VIEWS = 50_000         # 英語: 再生数の合計（上限つき）
YT_EN_MIN_RECENT7 = 2            # 英語: 直近7日の本数（今も広がっている）
YT_JA_MAX_CHANNELS = 2           # 日本語: これ以下なら薄い
YT_GAP_MIN_LOG = 1.3             # 差（log10）。20倍以上
YT_MIN_FOREIGN_MEDIA = 3         # 英語の独立媒体（ニュース）がこれ以上ある候補だけ測る・差ありにする（ニュースを伴うこと）
YT_GAP_CAP = 4
YT_TOTAL_LIFT_MAX = 2            # 海外メディア＋YouTube の合計の持ち上げ幅の上限（日本だけの値に対して）
YT_MAX_PER_RUN = 25              # 1回の buzz で YouTube を測る候補の上限（1候補≒202ユニット、無料枠は1日10,000ユニット）


class YTError(Exception):
    pass


def yt_api_key() -> str:
    return os.environ.get("YOUTUBE_API_KEY_KL", "")


def _yt_get(path: str, params: dict, key: str, timeout: int = 20) -> dict:
    url = YT_API + path + "?" + urllib.parse.urlencode(dict(params, key=key))
    try:
        return json.loads(urllib.request.urlopen(url, timeout=timeout).read())
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode("utf-8", "replace"))["error"].get("status", "")
        except Exception:  # noqa: BLE001
            msg = ""
        raise YTError(f"HTTP {e.code} {msg}") from e
    except Exception as e:  # noqa: BLE001
        raise YTError(f"{type(e).__name__}: {str(e)[:60]}") from e


def fetch_yt_videos(query: str, lang: str, key: str) -> list:
    """YouTube で query の動画を14日窓・視聴数順に最大50件。lang は "en" か "ja"。各: title・channel_id・views・published(YYYY-MM-DD)。
    quota: search.list 100 + videos.list 1。失敗は YTError。"""
    since = (datetime.now(timezone.utc) - timedelta(days=YT_WINDOW_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    region = {"en": "US", "ja": "JP"}[lang]
    s = _yt_get("search", {"part": "id", "q": query, "type": "video", "order": "viewCount", "maxResults": YT_MAX_RESULTS,
                           "publishedAfter": since, "relevanceLanguage": lang, "regionCode": region}, key)
    ids = [i["id"]["videoId"] for i in s.get("items", []) if i.get("id", {}).get("videoId")]
    if not ids:
        return []
    v = _yt_get("videos", {"part": "snippet,statistics", "id": ",".join(ids)}, key)
    out = []
    for it in v.get("items", []):
        sn, st = it.get("snippet", {}), it.get("statistics", {})
        out.append({"title": sn.get("title", ""), "channel_id": sn.get("channelId", ""),
                    "views": int(st.get("viewCount") or 0), "published": (sn.get("publishedAt") or "")[:10]})
    return out


def _word_hit(anchor: str, text: str) -> bool:
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(anchor) + r"(?![a-z0-9])", text))


def count_yt(videos: list, lang: str, en_anchors: list, jp_anchors: list = None) -> dict:
    """候補に関連する動画だけを数える。en: 見出しが en_anchors を全て含み、かな文字を含まない。
    ja: かな・漢字を含む見出しで、jp_anchors（組織名・略語だけの語を除く）のどれかか en_anchors の全てを含む。
    戻り値: videos（本数）・channels（独立したチャンネル数）・views（1本 YT_VIEW_CAP で頭打ちの合計）・recent7（直近7日の本数）。"""
    since7 = (datetime.now(timezone.utc).date() - timedelta(days=7)).isoformat()
    jp = [_nfkc(a) for a in (jp_anchors or []) if a and a.strip()]
    if any(a not in GENERIC_ANCHORS for a in jp):
        jp = [a for a in jp if a not in GENERIC_ANCHORS]
    chans, n, views, recent = set(), 0, 0, 0
    for v in videos:
        t = _nfkc(v["title"])
        en_hit = bool(en_anchors) and all(_word_hit(a, t) for a in en_anchors)
        if lang == "en":
            if not en_hit or KANA.search(v["title"]):
                continue
        else:
            if not (KANA.search(v["title"]) or KANJI.search(v["title"])):
                continue
            if not (en_hit or any(a in t for a in jp)):
                continue
        n += 1
        chans.add(v["channel_id"] or v["title"])
        views += min(int(v["views"]), YT_VIEW_CAP)
        if (v["published"] or "") >= since7:
            recent += 1
    return {"videos": n, "channels": len(chans), "views": views, "recent7": recent}


def yt_gap(en: dict, ja: dict, foreign_media: int) -> dict:
    """英語 YouTube が広く熱く、日本語 YouTube が薄い「差」。戻り値: gap_log（差）・gap（True/False）・why（差なしの理由 or 差ありの根拠）。"""
    g = round(math.log10(en["views"] + 1) - math.log10(ja["views"] + 1), 2)
    why = []
    if foreign_media < YT_MIN_FOREIGN_MEDIA:
        why.append(f"英語の独立媒体{foreign_media}（{YT_MIN_FOREIGN_MEDIA}未満。ニュースを伴わない）")
    if en["channels"] < YT_EN_MIN_CHANNELS:
        why.append(f"英語のチャンネル{en['channels']}（{YT_EN_MIN_CHANNELS}未満。広がっていない）")
    if en["views"] < YT_EN_MIN_VIEWS:
        why.append(f"英語の再生{en['views']}（{YT_EN_MIN_VIEWS}未満）")
    if en["recent7"] < YT_EN_MIN_RECENT7:
        why.append(f"英語の直近7日{en['recent7']}本（{YT_EN_MIN_RECENT7}未満。今は熱くない）")
    if ja["channels"] > YT_JA_MAX_CHANNELS:
        why.append(f"日本語のチャンネル{ja['channels']}（{YT_JA_MAX_CHANNELS}超。もう薄くない）")
    if g < YT_GAP_MIN_LOG:
        why.append(f"差{g}（{YT_GAP_MIN_LOG}未満）")
    return {"gap_log": g, "gap": not why, "why": "・".join(why)}


def apply_yt_gap(r: dict, en: dict, ja: dict, foreign_media: int) -> dict:
    """measure_buzz の結果 r（combine_foreign 済み）に YouTube の差を足す。buzz_yt に測定値、差ありなら buzz_measured を +1（上限つき）。
    別枠: 加点は海外メディア分の後。合計の持ち上げは YT_TOTAL_LIFT_MAX・YT_GAP_CAP まで。"""
    g = yt_gap(en, ja, foreign_media)
    m0 = r["buzz_measured"]
    jp_m = r.get("buzz_jp_measured", m0)
    bonus = 0
    if g["gap"]:
        m1 = min(m0 + 1, YT_GAP_CAP, jp_m + YT_TOTAL_LIFT_MAX)
        bonus = max(0, m1 - m0)
    r["buzz_yt"] = {"en": en, "ja": ja, "gap_log": g["gap_log"], "gap": g["gap"], "why": g["why"], "bonus": bonus,
                    "pre_yt": m0, "jp_m": jp_m}
    r["buzz_measured"] = m0 + bonus
    r["buzz_yt_bonus"] = bonus
    r["buzz_yt_boost"] = bool(bonus) and r["buzz_measured"] >= 3 and m0 < 3
    return r


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


def measure_yt(c: dict, r: dict, yt_budget: list) -> None:
    """YouTube の英日の差を測って r に足す（キーが無い・英語の独立媒体が少ない・上限超過・失敗のときは何もしない）。
    yt_budget は [残り件数]（呼び出し側が回をまたいで共有）。"""
    key = yt_api_key()
    fnm = r.get("buzz_outlets_foreign")
    if not key or yt_budget[0] <= 0 or fnm is None or fnm < YT_MIN_FOREIGN_MEDIA or not r.get("buzz_query_en"):
        return
    eq, eanc = foreign_query(c)
    jq = r.get("buzz_query") or _two_words(c.get("jp_news_query", ""))
    anchors = c.get("jp_title_anchor") or []
    anchors = [anchors] if isinstance(anchors, str) else anchors
    try:
        yt_budget[0] -= 1
        en = count_yt(fetch_yt_videos(eq, "en", key), "en", eanc)
        ja = count_yt(fetch_yt_videos(jq, "ja", key), "ja", eanc, anchors)
    except YTError as e:
        r["buzz_yt_error"] = str(e)
        return
    apply_yt_gap(r, en, ja, fnm)


def measure_buzz(c: dict, query: str = None, yt_budget: list = None) -> dict:
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
    fn, fq = None, ""
    eq, eanc = foreign_query(c)
    if eq:                      # 海外分（英語圏）。取得に失敗しても日本だけで続ける（従来の値）
        time.sleep(GNEWS_INTERVAL)
        try:
            fn, fq = count_foreign(fetch_gnews_en(eq), eanc, issuer_hosts(c)), eq
        except GNewsError:
            fn = None
    r = count_buzz(items, anchors, issuer_hosts(c), foreign_n=fn)
    r["buzz_raw_items"], r["buzz_query"] = len(items), q
    if fn is not None:
        r["buzz_query_en"] = fq
        measure_yt(c, r, yt_budget if yt_budget is not None else [YT_MAX_PER_RUN])
    return r


# 注目度の測定の履歴（2026-10-15、1週目の追加）: 同じ話題でも Google ニュース RSS の取得結果は測るたびにぶれる
# （カチャカEvo が3媒体→2媒体で本命から外れた）。そこで測り直しても上書きせず buzz_history に残し、
# 採用する値は「最新と同じ検索語」の測定のうち、最新から BUZZ_ADOPT_DAYS 日以内・直近 BUZZ_ADOPT_LAST 回の最大にする。
# 採用した測定の根拠（見出し・媒体・日付）・Yahoo!・勢いも同じ測定のものを使う（媒体数と根拠がちぐはぐにならないように）。
# 検索語が違う測定どうしは比べない（別の検索語は拾う記事の集合が違うため）。buzz_measured_at は最新の測定の時刻のまま
# （buzz の測り直しの間隔 --remeasure-hours はこれで判定する。動きは変えない）
BUZZ_ADOPT_LAST = 3
BUZZ_ADOPT_DAYS = 7
BUZZ_HISTORY_MAX = 10        # 履歴に残す件数（古いものから捨てる）
BUZZ_ENTRY_KEYS = ("buzz_measured", "buzz_outlets", "yahoo", "buzz_evidence", "buzz_trend",
                   "buzz_articles_14d", "buzz_raw_items", "buzz_query")


def _buzz_entry(r: dict, at: str, seeded: bool = False) -> dict:
    e = {"at": at, "query": r.get("buzz_query", ""), "measured": r.get("buzz_measured"),
         "outlets": r.get("buzz_outlets", 0), "yahoo": bool(r.get("yahoo")),
         "evidence": r.get("buzz_evidence") or [], "trend": r.get("buzz_trend"),
         "articles_14d": r.get("buzz_articles_14d"), "raw_items": r.get("buzz_raw_items")}
    if r.get("buzz_outlets_foreign") is not None:       # 2026-11-10: 海外分（無ければ欄を足さない＝従来の履歴と同じ形）
        e.update({"jp_measured": r.get("buzz_jp_measured"), "outlets_foreign": r.get("buzz_outlets_foreign"),
                  "foreign_boost": bool(r.get("buzz_foreign_boost")), "query_en": r.get("buzz_query_en", "")})
    if r.get("buzz_yt"):                                # 2026-11-10: YouTube の英日の差（無ければ欄を足さない）
        e.update({"yt": r["buzz_yt"], "yt_boost": bool(r.get("buzz_yt_boost"))})
    if seeded:
        e["seeded"] = True       # 履歴を持つ前の測定（読み込み時に現在の値から作った1件目）
    return e


def ensure_buzz_history(c: dict) -> bool:
    """履歴の無い実測済みの候補に、現在の値を履歴の1件目として持たせる（既存の欄は変えない）。足したら True。"""
    if c.get("buzz_history") or c.get("buzz_measured") is None:
        return False
    c["buzz_history"] = [_buzz_entry(c, c.get("buzz_measured_at") or "", seeded=True)]
    return True


def _at(e: dict):
    try:
        return datetime.fromisoformat(e.get("at") or "")
    except ValueError:
        return None


def buzz_window(hist: list) -> list:
    """採用の比較対象: 最新と同じ検索語、最新から BUZZ_ADOPT_DAYS 日以内、直近 BUZZ_ADOPT_LAST 回（新しい順）。"""
    if not hist:
        return []
    latest = hist[-1]
    lt = _at(latest)
    out = []
    for e in reversed(hist):
        if e.get("query") != latest.get("query"):
            continue
        t = _at(e)
        if lt and t and (lt - t).total_seconds() > BUZZ_ADOPT_DAYS * 86400:
            continue
        out.append(e)
        if len(out) == BUZZ_ADOPT_LAST:
            break
    return out


def adopt_buzz(c: dict) -> dict:
    """履歴から採用する測定を選び、既存の欄（buzz_measured・buzz_outlets・yahoo・buzz_evidence・buzz_trend 等）に書く。
    最大は 実測の段階 → 媒体数 → 関連記事の数 → 新しさ の順で比べる。採用した測定を返す。"""
    win = buzz_window(c.get("buzz_history") or [])
    if not win:
        return {}
    best = max(win, key=lambda e: (e.get("measured") or 0, e.get("outlets") or 0, e.get("articles_14d") or 0, e.get("at") or ""))
    c.update({"buzz_measured": best["measured"], "buzz_outlets": best["outlets"], "yahoo": best["yahoo"],
              "buzz_evidence": best["evidence"], "buzz_trend": best["trend"],
              "buzz_articles_14d": best["articles_14d"], "buzz_raw_items": best["raw_items"], "buzz_query": best["query"]})
    for k in ("buzz_jp_measured", "buzz_outlets_foreign", "buzz_foreign_boost", "buzz_query_en", "buzz_yt", "buzz_yt_bonus", "buzz_yt_boost"):
        c.pop(k, None)
    if best.get("yt"):          # 2026-11-10: YouTube の英日の差（無ければ欄を足さない）
        c.update({"buzz_yt": best["yt"], "buzz_yt_bonus": best["yt"].get("bonus", 0),
                  "buzz_yt_boost": bool(best.get("yt_boost"))})
    if best.get("outlets_foreign") is not None:
        c.update({"buzz_jp_measured": best.get("jp_measured"), "buzz_outlets_foreign": best["outlets_foreign"],
                  "buzz_foreign_boost": bool(best.get("foreign_boost")), "buzz_query_en": best.get("query_en", "")})
    c["buzz_adopted_at"] = best.get("at", "")
    c["buzz_adopted_n"] = len(win)
    return best


def record_buzz(c: dict, r: dict, at: str = None) -> dict:
    """measure_buzz の結果 r を履歴に足し、採用する値を決め直す（上書きしない）。採用した測定を返す。"""
    at = at or datetime.now().isoformat(timespec="seconds")
    ensure_buzz_history(c)
    hist = c.setdefault("buzz_history", [])
    hist.append(_buzz_entry(r, at))
    del hist[:-BUZZ_HISTORY_MAX]
    c["buzz_measured_at"] = at
    return adopt_buzz(c)


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
        return 0, 0
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
    got = sum(1 for c in todo if c.get("work_relevance") is not None)
    print(f"work_relevance を {got}/{len(todo)}件に付与しました")
    return len(todo), got


AUDIENCE_KEYS = ("audience_fit", "promise", "tangible", "decision_number", "series_fit")   # backfill_audience が付ける欄


def backfill_audience(cands: list, force: bool = False):
    """available の候補のうち audience_fit が無いものに、想定する視聴者との合い方（1〜5）を付ける（テキストのみ、2026-10-25）。
    score で付かなかった候補（2026-10-25 より前の採点）もこれで埋まる。"""
    todo = [c for c in cands if c.get("status") == "available"
            and (force or any(c.get(k) is None for k in AUDIENCE_KEYS) or c.get("interest_version") != INTEREST_VERSION)]
    if not todo:
        return 0, 0
    client, types = _gemini()
    n = 0
    for k in range(0, len(todo), ENRICH_BATCH):
        batch = todo[k:k + ENRICH_BATCH]
        rows = "\n".join(
            f"{i}. タイトル: {c['title']} / 見出し: {c.get('headline_claim', '')} / "
            f"中身: {(c.get('actual_content') or c.get('summary') or '')[:300]}" for i, c in enumerate(batch))
        prompt = (
            "日本語の科学ニュース解説YouTube番組のネタ候補です。各候補について "
            "audience_fit・promise・tangible・decision_number・series_fit・wonder（1〜5）と surprise_line を付けてください。\n"
            f"【想定する視聴者】{AUDIENCE}\n"
            f"   - {AUDIENCE_FIT_RUBRIC}\n"
            f"   - {PROMISE_RUBRIC}\n"
            f"   - {TANGIBLE_RUBRIC}\n"
            f"   - {DECISION_NUMBER_RUBRIC}\n"
            f"   - {SERIES_FIT_RUBRIC}\n"
            f"   - {WONDER_RUBRIC}\n"
            f"   - {SURPRISE_LINE_RULE}\n"
            "言語対応や提供地域は無関係。\n\n"
            f"候補:\n{rows}\n\n"
            'JSON配列のみ出力: [{"i": 0, "audience_fit": 0, "promise": 0, "tangible": 0, "decision_number": 0, '
            '"series_fit": 0, "wonder": 0, "surprise_line": ""}, ...]（全候補分）')
        try:
            out = _json_from(client.models.generate_content(model=MODEL, contents=prompt).text)
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️ audience_fit・promise の付与に失敗（{k}〜{k + len(batch) - 1}件目）: {e}")
            continue
        for r in out:
            try:
                c = batch[int(r["i"])]
                if force or c.get("audience_fit") is None:
                    c["audience_fit"] = _clamp5(r["audience_fit"])
                for k in AUDIENCE_KEYS[1:]:   # promise 以降は、返ってきた欄だけ付ける（欠けても audience_fit は残す）
                    if (force or c.get(k) is None) and r.get(k) is not None:
                        c[k] = _clamp5(r[k])
                # 2026-11-07: wonder は新しい目安で付け直し、surprise_line を付ける（interest_version が古い候補）
                if (force or c.get("interest_version") != INTEREST_VERSION) and r.get("wonder") is not None:
                    c["wonder"] = _clamp5(r["wonder"])
                    c["surprise_line"] = (r.get("surprise_line") or "").strip()[:60]
                    c["interest_version"] = INTEREST_VERSION
                n += 1
            except (KeyError, ValueError, IndexError, TypeError):
                continue
    print(f"audience_fit・promise・tangible・decision_number・series_fit・wonder・surprise_line を {n}/{len(todo)}件に付与しました")
    return len(todo), n


SURPRISE_RETRY_MAX = 2   # 入口を通過した候補で驚きの1行が空のとき、付け直す最大回数（通算）


def surprise_retry_targets(cands: list) -> list:
    """入口（ゲート）を通過し、新しい版で付与済みなのに surprise_line が空で、再試行が上限未満の候補。"""
    used = used_source_urls(cands)
    return [c for c in cands if c.get("status") == "available" and c.get("interest_version") == INTEREST_VERSION
            and not (c.get("surprise_line") or "").strip() and not gate_reasons(c, used)
            and len(c.get("surprise_retry") or []) < SURPRISE_RETRY_MAX]


def retry_surprise(cands: list):
    """2026-11-10 (handoff 2026-11-10-015): 入口を通過した候補の驚きの1行が空（付与の失敗かもしれない）なら、
    1候補ずつ、本文を多めに渡して付け直す。基準は変えない（SURPRISE_LINE_RULE のまま。一次資料に書かれていることだけで言い切れなければ
    空のまま）。結果（成功・空・理由）は c['surprise_retry'] に残し、空のままなら surprise_hold_reason に理由を残す
    （下書きに『驚きの1行が付かず保留』と出る）。戻り値: (対象, 付いた数)"""
    todo = surprise_retry_targets(cands)
    if not todo:
        return 0, 0
    client, types = _gemini()
    got = 0
    for c in todo:
        prompt = (
            "日本語の科学ニュース解説YouTube番組のネタ候補です。この候補の surprise_line（驚きの1行）だけを付けてください。\n"
            f"【想定する視聴者】{AUDIENCE}\n   - {SURPRISE_LINE_RULE}\n"
            "言い切れない場合は surprise_line を空にし、reason に空にした理由を30字以内で書く（無理に作らない）。\n\n"
            f"タイトル: {c['title']}\n見出し: {c.get('headline_claim', '')}\n"
            f"中身: {(c.get('actual_content') or c.get('summary') or '')[:900]}\n"
            f"一次資料: {', '.join((s.get('url') or '') for s in (c.get('primary_sources') or [])[:3])}\n\n"
            'JSONオブジェクトのみ出力: {"surprise_line": "", "reason": ""}')
        line, reason = "", "付与の呼び出しに失敗"
        try:
            out = _json_from(client.models.generate_content(model=MODEL, contents=prompt).text)
            if isinstance(out, list) and out:
                out = out[0]
            line = (out.get("surprise_line") or "").strip()[:60]
            reason = (out.get("reason") or "").strip()[:60] or ("" if line else "理由の記載なし")
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️ 驚きの1行の再試行に失敗: {c['title'][:40]} ({str(e)[:80]})")
        c.setdefault("surprise_retry", []).append({"at": datetime.now().isoformat(timespec="seconds"), "ok": bool(line), "reason": reason})
        if line:
            c["surprise_line"] = line
            c.pop("surprise_hold_reason", None)
            got += 1
        else:
            c["surprise_hold_reason"] = reason
        print(f"  {'○' if line else '×'} 驚きの1行 再試行 {len(c['surprise_retry'])}回目: {c['title'][:40]} → {line or '（空）' + reason}")
        time.sleep(1.0)
    print(f"驚きの1行の再試行: {got}/{len(todo)}件に付きました（空のままの候補は理由を記録し、下書きに『保留』と出ます）")
    return len(todo), got


PRIOR_ART_PROMPT = (
    "日本語の科学ニュース解説YouTube番組のネタ候補です。この候補の中心主張（見出しが言っている新しいこと）について、"
    "『既に主要なAIエージェント・AIサービス（ChatGPT・Claude・Gemini・Copilot 等）・OS標準機能（iOS・Android・Windows・macOS）・"
    "パスワードマネージャー・主要なクラウド／家電／ロボットの製品等で、一般ユーザーが普通に使える形で実現済みではないか』をGoogle検索で調べてください。\n"
    "- **先行事例に数えないもの:** この発表そのもの（同じ発表元の同じ製品・同じ機能。例: 発表された新モデルを、その発表元のサービスが提供していること）。"
    "『同じ分野の別のもの』『似た一般的な機能』も数えない。数えるのは、**同じ仕組み・同じ約束（見出しの中心主張）を、別の提供元が既に一般ユーザー向けに出している場合**だけ。\n"
    "- status: realized（実現済み。一般ユーザーが今日使える）／not_realized（調べたが見当たらない）／unsure（判断できない）。"
    "迷ったら unsure（realized にするには、具体的なサービス名と機能名が挙げられること）\n"
    "- evidence: 実現済みの根拠。[{\"service\": \"サービス名\", \"feature\": \"機能名\", \"url\": \"公式ページ（分かれば）\"}] を1〜3件。"
    "realized のときは必須。\n"
    "- reason: 30〜80字で判断の理由\n"
    "- novelty_exception: realized のとき、今回のニュースの新規性が『技術が初めて登場した』ことではなく"
    "『標準化・業界横断の合意・大手の足並み・社会全体に広がる段階に入った』ことにあるなら true。それ以外は false\n"
    "- novelty_line: novelty_exception が true のとき、「何が今回初めてか」を1行（60字以内）。一次資料に書かれていることだけで言い切る。言い切れなければ空\n"
    "- novelty_line_primary: novelty_line が一次資料（発表元の資料）に書かれていて言い切れるなら true、推測・報道の解釈なら false\n")


def prior_art_targets(cands: list, force: bool = False) -> list:
    """入口（ゲート）を通過し、驚き・視聴者の付与が済んでいて、先行事例チェックが今の版でない候補。"""
    used = used_source_urls(cands)
    return [c for c in cands if c.get("status") == "available" and c.get("interest_version") == INTEREST_VERSION
            and not gate_reasons(c, used) and (force or prior_art_state(c) == "unchecked")]


PRIOR_ART_KNOWN_JSON = BASE_DIR / "prior_art_known.json"


def known_prior_art(c: dict, path: Path = None):
    """運営側で既に使えていると確認済みの機能（prior_art_known.json）に、候補が当たるか。当たれば該当の entry、なければ None。
    AIの検索は、運営が日常的に使っている機能（Secure Vault 等）を見落とすため、判定の前に照合する（2026-11-11）。"""
    try:
        entries = json.loads((path or PRIOR_ART_KNOWN_JSON).read_text(encoding="utf-8")).get("entries", [])
    except (OSError, ValueError):
        return None
    text = _nfkc(" ".join(str(c.get(k) or "") for k in ("title", "headline_claim", "actual_content", "summary"))).lower()
    for e in entries:
        groups = e.get("match_all") or []
        if groups and all(any(_nfkc(w).lower() in text for w in g) for g in groups):
            return e
    return None


def backfill_prior_art(cands: list, force: bool = False, only_ids: list = None):
    """2026-11-11（指示2026-11-11-001）: 先行事例チェック。1候補ずつ Google 検索つきで判定し、結果と根拠を c['prior_art'] に残す
    （形式は prior_art_state の上のコメント）。realized のときだけ驚きに上限（PRIOR_ART_WONDER_CAP）がかかる。戻り値: (対象, 付いた数)"""
    todo = [c for c in cands if c["id"] in only_ids] if only_ids else prior_art_targets(cands, force)
    if not todo:
        return 0, 0
    client, types = _gemini()
    got = 0
    for c in todo:
        known = known_prior_art(c)      # 運営が確認済みの既存機能に当たるか（当たれば realized。AIの検索結果より優先）
        known_ev = [{"service": known["service"][:40], "feature": known["feature"][:60], "url": known.get("url", "")}] if known else []
        prompt = (PRIOR_ART_PROMPT
                  + (f"\n【運営が確認済みの先行事例】{known['service']}の「{known['feature']}」。この候補の中心主張が同じ仕組みなら、"
                     "status は realized とし、evidence の先頭にこれを入れる。novelty_exception の判断だけをしてください。\n" if known else "")
                  + f"\nタイトル: {c['title']}\n見出し: {c.get('headline_claim', '')}\n"
                  f"中身: {(c.get('actual_content') or c.get('summary') or '')[:700]}\n発表日: {c.get('announced_on') or c.get('published')}\n"
                  f"一次資料: {', '.join((s.get('url') or '') for s in (c.get('primary_sources') or [])[:3])}\n\n"
                  'JSONオブジェクトのみ出力: {"status": "", "evidence": [], "reason": "", "novelty_exception": false, '
                  '"novelty_line": "", "novelty_line_primary": false}')
        out = {}
        try:
            resp = client.models.generate_content(
                model=MODEL, contents=prompt,
                config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]))
            out = _json_from(resp.text)
            if isinstance(out, list) and out:
                out = out[0]
            if not isinstance(out, dict):
                out = {}
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️ 先行事例チェックの呼び出しに失敗: {c['title'][:40]} ({str(e)[:80]})")
            if not known:
                time.sleep(1.0)
                continue
        st = out.get("status") if out.get("status") in ("realized", "not_realized", "unsure") else "unsure"
        ev = [{"service": str(e.get("service", ""))[:40], "feature": str(e.get("feature", ""))[:60], "url": str(e.get("url", ""))[:200]}
              for e in (out.get("evidence") or []) if isinstance(e, dict)]
        if known:
            st = "realized"
            ev = known_ev      # 運営確認済みの根拠だけを残す（AIが足す根拠は URL・サービス名の誤りが混ざるため）
        ev = ev[:3]
        if st == "realized" and not any(e["service"] and e["feature"] for e in ev):
            st = "unsure"      # 根拠（どのサービスのどの機能か）が挙げられない realized は認めない
        exc = bool(out.get("novelty_exception")) and st == "realized"
        c["prior_art"] = {"version": PRIOR_ART_VERSION, "checked_at": datetime.now().isoformat(timespec="seconds"), "status": st,
                          "evidence": ev, "reason": (str(out.get("reason", "")) or (f"運営確認済みの先行事例に一致（{known['id']}）" if known else ""))[:120],
                          "known_id": known["id"] if known else "", "novelty_exception": exc,
                          "novelty_line": str(out.get("novelty_line", "")).strip()[:80] if exc else "",
                          "novelty_line_primary": bool(out.get("novelty_line_primary")) if exc else False}
        got += 1
        print(f"  {'🔁' if st == 'realized' else '○'} 先行事例 {st}: {c['title'][:44]} → {prior_art_evidence_text(c) if st == 'realized' else ''}")
        time.sleep(1.0)
    print(f"先行事例チェック: {got}/{len(todo)}件")
    return len(todo), got


def cmd_prior_art(ids: list, force: bool, confirm: str = "", by: str = ""):
    """先行事例チェックだけを実行する（--id で候補を指定。指定した候補は、ゲートに関係なく・判定済みでも付け直す）。"""
    cands = load_candidates()
    if ids and confirm:
        # 例外の確認: 一次資料を読んだ人が「何が今回初めてか」の1行を言い切れたときだけ記録する（--by は確認者）
        hit = [c for c in cands["items"] if c["id"] in ids and isinstance(c.get("prior_art"), dict)]
        if not hit or not by:
            sys.exit("prior-art --confirm: 先行事例チェック済みの候補の --id と、確認者 --by（例: kl-planner）が必要です")
        for c in hit:
            pa = c["prior_art"]
            pa.update({"novelty_exception": True, "novelty_line": confirm.strip()[:80], "novelty_line_primary": True,
                       "novelty_confirmed_by": by, "novelty_confirmed_at": datetime.now().isoformat(timespec="seconds")})
            print(f"  例外を確認: {c['title'][:44]} → 今回初めて＝{pa['novelty_line']}（確認者 {by}。状態: {prior_art_state(c)}）")
        _save_candidates(cands)
        return
    if ids:
        hit = [c for c in cands["items"] if c["id"] in ids]
        if not hit:
            sys.exit(f"prior-art: 候補が見つかりません: {ids}")
        for c in hit:
            c.pop("prior_art", None)
        backfill_prior_art(cands["items"], True, only_ids=ids)      # 指定時はゲートに関係なく付ける
    else:
        backfill_prior_art(cands["items"], force)
    _save_candidates(cands)


def cmd_enrich(force: bool):
    cands = load_candidates()
    refresh_topic_ages(cands["items"])
    w_todo, w_got = backfill_work(cands["items"], force) or (0, 0)
    a_todo, a_got = backfill_audience(cands["items"], force) or (0, 0)
    try:      # 付与の失敗の取りこぼし対策（再試行の失敗は他の付与を止めない。停止扱いにもしない）
        retry_surprise(cands["items"])
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️ 驚きの1行の再試行を中断: {e}")
    try:      # 2026-11-11: 先行事例チェック（失敗しても他の付与は止めない。判定できなかった候補は未判定のまま＝従来どおりの扱い）
        backfill_prior_art(cands["items"], force)
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️ 先行事例チェックを中断: {e}")
    _save_candidates(cands)
    stalls = []
    if w_todo and w_got == 0:
        stalls.append(f"enrich(work_relevance): 対象{w_todo}件に0件付与")
    if a_todo and a_got == 0:
        stalls.append(f"enrich(audience_fit・wonder・surprise_line): 対象{a_todo}件に0件付与")
    pool = _gate_pool(cands["items"])
    todo = [c for c in pool if force or not c.get("jp_news_query")]
    if not todo:
        print("付与が必要な候補はありません（ゲート通過分はすべて jp_news_query あり）")
        for m in stalls:
            report_stall(m)
        if stalls:
            sys.exit(1)
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
    if n == 0:
        stalls.append(f"enrich(jp_news_query): 対象{len(todo)}件に0件付与")
    for m in stalls:
        report_stall(m)
    if stalls:
        sys.exit(1)


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
    yt_budget = [YT_MAX_PER_RUN]
    print("  YouTube の英日の差: " + (f"測る（キーあり、上限{YT_MAX_PER_RUN}件。英語の独立媒体{YT_MIN_FOREIGN_MEDIA}以上の候補だけ）"
                                    if yt_api_key() else "測らない（YOUTUBE_API_KEY_KL が未設定）"))
    ok = fail = 0
    for k, c in enumerate(todo):
        if k:
            time.sleep(GNEWS_INTERVAL)
        try:
            r = measure_buzz(c, yt_budget=yt_budget)
        except GNewsError as e:
            fail += 1
            c["buzz_error"], c["buzz_error_at"] = str(e), now.isoformat(timespec="seconds")
            print(f"  ⚠️ {c['id']} 実測失敗（{e}）→ 推定 {buzz_value(c)[0]} で代用  {c['title'][:40]}")
            continue
        ok += 1
        record_buzz(c, r)       # 2026-10-15: 上書きせず履歴に足し、直近の最大を採用する
        c.pop("buzz_error", None)
        c.pop("buzz_error_at", None)
        adopt = (f" → 採用 実測{c['buzz_measured']}（{c['buzz_outlets']}媒体、直近{c.get('buzz_adopted_n', 1)}回の最大）"
                 if c.get("buzz_adopted_at") != c.get("buzz_measured_at") else "")
        print(f"  {c['id']} 実測{r['buzz_measured']}（{r['buzz_outlets']}媒体{'・Yahoo!あり' if r['yahoo'] else ''}、"
              f"関連{r['buzz_articles_14d']}/取得{r['buzz_raw_items']}件）{r['buzz_query']!r}{adopt}  {c['title'][:40]}")
        if r.get("buzz_yt"):
            y = r["buzz_yt"]
            print(f"      YouTube 英{y['en']['channels']}ch/{y['en']['views']}再生・日{y['ja']['channels']}ch/{y['ja']['views']}再生 差{y['gap_log']}"
                  + (f" → 差あり +{y['bonus']}" if y["bonus"] else f"（差なし: {y['why'][:60]}）"))
        elif r.get("buzz_yt_error"):
            print(f"      ⚠️ YouTube の測定に失敗（{r['buzz_yt_error']}）。ニュースだけの値で続行")
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
# 「発表の盛り vs 使った人の声・第三者の検証」で扱う。条件を満たす候補は本命枠に入れない
# （同日の追加で、ベスト3の空きには〈答え合わせ〉として入る。best3 参照）。
#   製品発表 かつ 日本語の独立媒体が L2_MIN_JP_OUTLETS 以上 かつ 話題の初出から L2_MIN_TOPIC_AGE_DAYS 日以上 → 「答え合わせ候補」
#   同じ条件で初出から L2_MIN_TOPIC_AGE_DAYS 日未満 → 「再評価待ち」（ベスト3に入れない。これは変えない）
# 並びの式（core）は変えない（表示の枠を分けるだけ）。段階の数字は暫定
L2_TYPES = ("product_release",)
L2_MIN_JP_OUTLETS = 10
L2_MIN_TOPIC_AGE_DAYS = 2
L2_LANE = "答え合わせ候補"
L2_WAIT_LANE = "再評価待ち"
L2_HEADING = "答え合わせ候補（発表から数日。使った人の声・第三者の検証を探す価値あり）"


def is_l2_type(c: dict) -> bool:
    return c.get("announcement_type") in L2_TYPES and (c.get("buzz_outlets") or 0) >= L2_MIN_JP_OUTLETS


def promise(c: dict) -> int:
    """実現への手応え（2026-10-26）。無い候補（付与前）は3（中立）として扱う。"""
    return _clamp5(c["promise"]) if c.get("promise") is not None else 3


def _neutral3(c: dict, key: str) -> int:
    """tangible・decision_number など、付与前の候補は3（中立）として扱う。"""
    return _clamp5(c[key]) if c.get(key) is not None else 3


def tangible_decision(c: dict) -> int:
    """物として見せられるか＋判断の数字があるか（2〜10、2026-11-04）。同点の並びの先頭に使う。"""
    return _neutral3(c, "tangible") + _neutral3(c, "decision_number")


def tie_break(c: dict) -> int:
    # 2026-10-26: 誇張（hype_gap）を実現への手応え（promise）に替えた（構成 v4。夢を潰しやすいネタを上げない）
    # 2026-11-04: 先頭に「物×判断の数字」（tangible + decision_number）を置いた（他チャンネル調査）。
    # 百の位以上が物×判断の数字、下2桁が 手応え＋議論＋視聴者（最大15）
    return tangible_decision(c) * 100 + promise(c) + _clamp5(c.get("debate")) + fit(c)


def interest(c: dict) -> int:
    """面白さ（2026-11-07、なるさんの決定）＝驚き（wonder）＋視聴者（audience_fit、健康系は4まで）＋見せられるか（tangible）。3〜15。
    ゲート（鮮度・実測の注目度など）を通った候補の中の並び順の主役。付与前の項目は3（中立）"""
    return wonder_eff(c) + fit(c) + _neutral3(c, "tangible")


# ---- 先行事例チェック（既知度チェック）と本命の絶対基準（2026-11-11、handoff 2026-11-11-001、ユーザー決定）----
# 背景: 「AIにパスワードを教えずにログイン」（1Password for Agents）が、Muse では既に日常的に使えているのに驚き8で1位になった。
# 候補データの c["prior_art"] に、中心主張が「既に主要なAIエージェント・AIサービス・OS標準機能・パスワードマネージャー等で、
# 一般ユーザーが普通に使える形で実現済みか」の判定と根拠（どのサービスのどの機能か）を残す。形式:
#   {"version": PRIOR_ART_VERSION, "checked_at": ISO, "status": "realized" | "not_realized" | "unsure",
#    "evidence": [{"service": "サービス名", "feature": "機能名", "url": "任意"}], "reason": "30〜80字",
#    "novelty_exception": bool,         # 新規性が「初登場」でなく「標準化・業界横断の合意・大手の足並み・社会全体へ広がる段階」にあるか
#    "novelty_line": "何が今回初めてか（1行）", "novelty_line_primary": bool}   # 1行が一次資料等で言い切れるか
PRIOR_ART_VERSION = "2026-11-11"
PRIOR_ART_WONDER_CAP = 2          # 実現済みと判定された候補の驚き（wonder）の上限
HONMEI_MIN_WONDER = 4             # ベスト3の1位（本命の筆頭）に置く驚きの下限（3以下は1位に置かない）
WEAK_DAY_LABEL = "本命なし・弱い日"


def prior_art_state(c: dict) -> str:
    """unchecked（未判定・古い版）／clear（実現済みでない）／realized_excluded（実現済み→本命に入れない・驚き上限）／
    realized_exception（実現済みだが、新規性の例外が一次資料等で言い切れている→本命の対象）／
    realized_held（例外を主張するが『何が今回初めてか』の1行が空・言い切れない→ベスト3に入れず保留）。"""
    pa = c.get("prior_art")
    if not isinstance(pa, dict) or pa.get("version") != PRIOR_ART_VERSION:
        return "unchecked"
    if pa.get("status") != "realized":
        return "clear"
    if not pa.get("novelty_exception"):
        return "realized_excluded"
    if ((pa.get("novelty_line") or "").strip() and (pa.get("novelty_confirmed_by") or "").strip()
            and c.get("primary_verified") is True):
        return "realized_exception"      # 例外は、人（企画担当・編集長）が一次資料を読んで1行を確認し（prior-art --confirm）、一次資料URLが実在確認済みのときだけ
    return "realized_held"      # AIが例外を主張しても、確認が付くまでは保留（理由つきで下書きに出す）


def prior_art_ok(c: dict) -> bool:
    """ベスト3に入れてよいか。実現済み（例外なし）と、例外を主張して言い切れない候補は入れない。未判定は通す。"""
    return prior_art_state(c) not in ("realized_excluded", "realized_held")


def prior_art_evidence_text(c: dict, n: int = 2) -> str:
    pa = c.get("prior_art") or {}
    ev = [f"{e.get('service', '?')}の{e.get('feature', '?')}" for e in (pa.get("evidence") or [])[:n]]
    return "、".join(ev) or "根拠の記載なし"


def wonder_eff(c: dict) -> int:
    """採点に使う驚き。実現済み（例外が認められていない）なら PRIOR_ART_WONDER_CAP が上限。付与前は3（中立）。"""
    w = _neutral3(c, "wonder")
    if prior_art_state(c) in ("realized_excluded", "realized_held"):
        w = min(w, PRIOR_ART_WONDER_CAP)
    return w


def honmei_strong(c: dict) -> bool:
    """ベスト3の1位に置ける強さか。驚き（先行事例の上限適用後）が HONMEI_MIN_WONDER 以上。驚きが未付与の候補は判断しない（True）。"""
    return c.get("wonder") is None or wonder_eff(c) >= HONMEI_MIN_WONDER


_NARROW_AUDIENCE = re.compile(r"(経営者|社長|エンジニア|開発者|情シス|IT担当|管理者|担当者|研究者|投資家|医師|薬剤師|弁護士|CISO|CTO)")


def narrow_audience(c: dict) -> bool:
    """驚きの1行の『誰が』が特定の業界・職種・立場に限られていそうか（語の一致による目安。落とさず注記する。最終判断はエマの初見判定）。"""
    line = (c.get("surprise_line") or "").strip()
    head = line.split("が", 1)[0] if "が" in line else ""
    return bool(_NARROW_AUDIENCE.search(head))


def prior_art_lines(c: dict) -> list:
    """list・slack 共通の注記行。"""
    st = prior_art_state(c)
    pa = c.get("prior_art") or {}
    out = []
    if st == "realized_excluded":
        out.append(f"🔁 先行事例あり（実現済み。驚きは上限{PRIOR_ART_WONDER_CAP}・本命に入れない）: {prior_art_evidence_text(c)}")
    elif st == "realized_exception":
        out.append(f"🔁 先行事例あり・例外で本命の対象: 今回初めて＝{(pa.get('novelty_line') or '').strip()}（根拠: {prior_art_evidence_text(c)}）")
    elif st == "realized_held":
        prop = (pa.get("novelty_line") or "").strip()
        out.append(f"🔁 先行事例あり・「何が今回初めてか」が一次資料で確認されておらず保留（先行: {prior_art_evidence_text(c)}"
                   + (f"／AI案の1行: {prop}＝確認待ち。企画担当が一次資料を読み prior-art --confirm で確認すれば本命の対象）" if prop else "／例外の主張なし）"))
    elif st == "unchecked" and c.get("interest_version") == INTEREST_VERSION:
        out.append("🔁 先行事例チェック: 未判定")
    if narrow_audience(c):
        out.append("⚠️ 驚きの1行の「誰が」が特定の職種・立場に狭い可能性（エマの初見判定で確認）")
    return out


def surprise_ok(c: dict) -> bool:
    """驚きの1行が言い切れているか。新しい版で付けたのに空なら False（ベスト3に入れない）。付与前は判断しない（True）。"""
    if c.get("interest_version") != INTEREST_VERSION:
        return True
    return bool((c.get("surprise_line") or "").strip())


def tb_parts(tb: int) -> tuple:
    return tb // 100, tb % 100


BEST3_TANGIBLE_MIN = 4           # ベスト3に「物×判断の数字」の候補を最低1件入れる条件（2026-11-04）
BEST3_DECISION_MIN = 3


def is_tangible_pick(c: dict) -> bool:
    """物として見せられ（tangible≧4）、判断の数字がある（decision_number≧3）。付与前（None）は該当にしない。"""
    return (c.get("tangible") is not None and c.get("decision_number") is not None
            and _clamp5(c["tangible"]) >= BEST3_TANGIBLE_MIN and _clamp5(c["decision_number"]) >= BEST3_DECISION_MIN)


# ============================================================
# 同一ネタの繰り返し対策（2026-11-08、handoff 2026-11-08-001）
#   1. 提示履歴: 下書き（ベスト3）に載った日を presented_on（日付のリスト）に残す。同じ候補は最大 PRESENT_MAX_DAYS 日まで。
#      それだけ提示して選ばれなかった候補は dedupe が status="shelved"（棚上げ。データは消さない）にする
#   2. 重複統合: 同一ストーリー（same_story。直接つながる候補だけ）の候補を dedupe が1件（canonical）に寄せる。他は status="merged"（merged_into）。
#      used / shelved の状態はストーリー単位で効かせる（記事の日付が状態の日以前の兄弟だけ。続報＝その後の日付の記事は新規として残す）
#   3. 新規優先枠: ベスト3の1枠は、初回スキャン（first_seen_at）から NEW_WITHIN_HOURS 時間以内の候補を優先する
# ============================================================
PRESENT_MAX_DAYS = 2             # 同じ候補を下書きに載せる最大の日数
NEW_WITHIN_HOURS = 48            # 新規候補とみなす、初回スキャンからの時間
NEW_MAX_TOPIC_AGE_DAYS = 7       # 採点が遅れて古い話題が「新規」にならないように、話題の初出がこれを超えたものは新規にしない
USED_STORY_GRACE_DAYS = 2        # used の兄弟を吸収する日付の余裕（used には使った日の記録が無いため、初回スキャン日から数える）
STATE_SHELVED, STATE_MERGED = "shelved", "merged"


def _today() -> str:
    return datetime.now().date().isoformat()


def first_seen_dt(c: dict):
    """初回スキャンの日時。first_seen_at が無い（この機能の前の）候補は scored_at の日の 0 時。"""
    for k in ("first_seen_at", "scored_at"):
        v = c.get(k)
        if v:
            try:
                return datetime.fromisoformat(v)
            except ValueError:
                pass
    return None


def is_new_candidate(c: dict) -> bool:
    fs = first_seen_dt(c)
    if fs is None or (datetime.now() - fs).total_seconds() > NEW_WITHIN_HOURS * 3600:
        return False
    return topic_age_days(c) <= NEW_MAX_TOPIC_AGE_DAYS


# ============================================================
# シリーズ候補の優先枠（2026-11-09、handoff 2026-11-09-011、なるさんの指示）
#   『人型ロボ定点観測』（series_watchlist.json の humanoid_watch）のウォッチ対象に、節目イベント（出荷・価格・家庭での使用報告・
#   対応家事の追加・大型更新）が出た候補を、ベスト3の最初の1枠に優先して入れる。
#   入口条件は一切ゆるめない: 優先枠の候補は、旬21日以内・注目度3以上（本命）・視聴者との合い方・手応え・驚きの1行・一次資料確認・
#   提示日数の上限を通った後の並び（order。面白さ順）からだけ選ぶ（best3 の ok から取る）。条件を通らなければ空けたまま。
#   判定は名前と語の一致による機械的な目安（採点とは別）。series_fit が付いていて 3 未満なら対象にしない。
# ============================================================
SERIES_WATCHLIST_JSON = BASE_DIR / "series_watchlist.json"
SERIES_WATCH_ID = "humanoid_watch"
SERIES_TARGET_PATTERNS = {      # ウォッチ対象の名前の表記ゆれ（series_watchlist.json の watch_targets.name の先頭と対応。英字の一般語は大文字小文字を区別）
    # \b は仮名・漢字も単語文字とみなす（「1X社」「NEOが」を逃す）ので、英数字だけで境界を見る
    "1X NEO": r"(?<![A-Za-z0-9])1X(?![A-Za-z0-9])|(?<![A-Za-z0-9])NEO(?![A-Za-z0-9])",
    "Figure": r"(?<![A-Za-z0-9])Figure(?:\s?(?:AI|0\d)(?![A-Za-z0-9])|(?=社|の|が|は|も|、))|(?<![A-Za-z0-9])Helix(?![A-Za-z0-9])|フィギュア(?:AI|ロボ)",
    "Tesla Optimus": r"Optimus|オプティマス",
    "Unitree": r"Unitree|ユニツリー",
}
SERIES_MILESTONE_PATTERNS = {   # 節目イベント5種（series_watchlist.json の milestone_events）
    "出荷・納品開始": r"出荷|納品|納入|配送|お届け|発売|一般販売|\bshipp?ing\b|\bdeliver|\bships\b",
    "価格改定": r"価格|値下げ|値上げ|定価|月額|(?<![\d億兆.,])\d{1,2}万ドル|\bpric(?:e|es|ing)\b|\bMSRP\b|\$\d{1,3},\d{3}(?![\d,.]*\s?(?:[BbMm]illion|bn\b))",
    "家庭での使用報告": r"自宅|家庭で|使ってみ|試してみ|レビュー|体験|\breview|\bin homes?\b|\bhands-on\b|\bat home\b",
    "対応家事の追加": r"家事|洗濯|皿洗い|食洗|掃除|畳む|\bchores?\b|\blaundry\b|\bdishes\b",
    "大型更新": r"アップデート|大型更新|新モデル|新型|次世代|\bupdate\b|\bnew model\b",
}


# 2026-11-09 (handoff 2026-11-09-012): 優先対象は人型ロボに限らず、定点観測シリーズ全般。
#   series_watchlist.json の series のうち、下の SERIES_RULES に照合の語があるものが対象。候補ジャンルは JSON の candidate_genres（無ければ genre）。
#   series_fit（人型ロボ専用の物差し）で足切りするのは humanoid_watch だけ。語の一致による目安で、採点ではない。
SERIES_RULES = {
    "humanoid_watch": {"series_fit_gate": True, "targets": SERIES_TARGET_PATTERNS, "milestones": SERIES_MILESTONE_PATTERNS},
    "ai_scientist_watch": {
        "series_fit_gate": False,
        "targets": {
            "AIによる未解決問題への成果": r"未解決|予想を証明|数理物理|\bconjecture|\bunsolved|open problem|Erd[oő]s",
            "AI実験室・研究自動化": r"AI科学者|AI Scientist|AIサイエンティスト|AI研究者|co-scientist|研究自動化|自律(?:型)?(?:実験|研究|ラボ)|AI実験室|self-driving lab|autonomous lab|AutoDNA|AlphaEvolve|AlphaFold",
            "主要ラボの科学応用発表": r"(?is)(?=.*(?:科学|発見|論文|証明|実験|science|scientific|discover|proof))(?=.*(?:Anthropic|アンソロピック|DeepMind|ディープマインド|OpenAI))",
            "創薬AIの進展": r"AI創薬|創薬AI|AI drug discovery|Isomorphic",
        },
        "milestones": {
            "査読誌への掲載": r"査読|peer.?review|Nature誌|Science誌|学術誌|誌に掲載|論文.{0,10}掲載|published in (?:Nature|Science|Cell)|\bjournal\b",
            "新規性・難度の更新": r"未解決|難問を解|世界初の発見|新発見|予想を証明|を証明した|ブレークスルー|breakthrough|\bproves?\b|\bproved\b|solves? (?:a |an )?(?:long-standing|open|unsolved)",
            "自律実行範囲の拡大": r"研究の自動化|実験の自動化|自律(?:的に|型)?(?:実験|研究)|ロボット実験|closed.loop|autonomous(?:ly)? (?:experiment|research|lab)|self-driving lab",
            "研究者の役割の変化": r"研究者の(?:役割|仕事)|人間の研究者|AIとの?共同研究|AIが共著|AIを共著者|co-scientist|科学者の(?:役割|仕事)|researchers?'? role",
        },
    },
    "autonomy_logistics_watch": {
        "series_fit_gate": False,
        "targets": {
            "ロボタクシー": r"Waymo|ウェイモ|Zoox|Apollo Go|[Rr]obotaxi|ロボタクシー|Cybercab|自動運転タクシー|無人タクシー",
            "自動運転トラック・幹線物流": r"自動運転トラック|自動運転(?:の)?物流|レベル4|Level 4|Aurora Innovation|Kodiak|autonomous truck|self-driving truck|幹線輸送|隊列走行",
            "配送ロボット": r"配送ロボ|デリバリーロボ|delivery robot|Starship|Serve Robotics|Coco Robotics|自動配送",
            "ドローン配送": r"ドローン配送|ドローン宅配|drone delivery|Zipline|Wing(?![A-Za-z])|ドローンポート|ドローン基地",
            "倉庫・店舗の無人化": r"無人店舗|無人コンビニ|無人倉庫|倉庫.{0,6}(?:無人|自動化|ロボット)|Amazon Robotics|Ocado|Just Walk Out",
        },
        "milestones": {
            "運行エリアの拡大": r"(?:運行|営業|サービス|配送|提供)(?:エリア|地域|範囲).{0,8}(?:拡大|拡張|追加|開始)|(?:エリア|都市|地域).{0,6}(?:へ|に)(?:拡大|展開)|\bexpand(?:s|ed|ing)? (?:to|into|its)\b|\blaunch(?:es|ed)? in\b|service area",
            "無人化段階の移行": r"完全無人|ドライバーなし|運転手なし|無人化|安全(?:ドライバー|監視)|監視(?:付き|員)|遠隔監視|レベル4|Level 4|driverless|safety driver|without (?:a )?driver|fully autonomous|unsupervised",
            "日本での実用化・法規制": r"(?:国内|日本).{0,12}(?:実用化|解禁|認可|許可|承認|法改正|規制)|道路交通法|国土交通省|警察庁|特区|レベル4.{0,6}(?:認可|許可|承認)",
            "逆向きの節目（事故・停止）": r"事故|死亡|運休|運行停止|サービス停止|営業停止|リコール|撤退|\bcrash|collision|\brecall|suspend(?:s|ed)? (?:service|operations)|shut ?down|outage|\bkilled",
        },
    },
}


def _series_list() -> list:
    try:
        return [s for s in json.loads(SERIES_WATCHLIST_JSON.read_text(encoding="utf-8")).get("series", [])
                if s.get("series_id") in SERIES_RULES]
    except (OSError, ValueError):
        return []


def _series_watch() -> dict:
    return next((s for s in _series_list() if s.get("series_id") == SERIES_WATCH_ID), {})


def series_candidate_info(c: dict):
    """定点観測シリーズの第○回候補か（ウォッチ対象 × 節目イベント）。最初に合ったシリーズについて
    {"series_id", "name", "no", "target", "milestones"} を返す。どれにも合わなければ None。"""
    text = c.get("title", "") + " " + (c.get("summary") or "")      # 本文（actual_content）は広すぎるので照合しない
    for s in _series_list():
        rule = SERIES_RULES[s["series_id"]]
        if c.get("genre") not in (s.get("candidate_genres") or [s.get("genre")]):
            continue
        sf = c.get("series_fit")
        if rule["series_fit_gate"] and sf is not None and _clamp5(sf) < 3:
            continue
        names = [t.get("name", "") for t in s.get("watch_targets", [])]
        target = next((n for n, pat in rule["targets"].items()
                       if any(x.startswith(n) for x in names) and re.search(pat, text)), None)
        if not target:
            continue
        ms = [m for m, pat in rule["milestones"].items() if re.search(pat, text, re.I)]
        if not ms:
            continue
        return {"series_id": s["series_id"], "name": s.get("name", s["series_id"]), "no": s.get("next_episode_no"),
                "target": target, "milestones": ms}
    return None


def presented_days(c: dict) -> list:
    return sorted(set(c.get("presented_on") or []))


def presentable(c: dict, today: str = None) -> bool:
    """下書きに載せてよいか。既に PRESENT_MAX_DAYS 日提示した候補は、今日の再実行で載るもの以外は載せない。"""
    today = today or _today()
    d = presented_days(c)
    return today in d or len(d) < PRESENT_MAX_DAYS


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
        # 2026-11-10: 海外分で入口（3）を越えた候補は、視聴者への合い方が FOREIGN_BOOST_MIN_FIT 以上のときだけ本命にする。
        # 満たさないときは日本だけの値で枠を決める（日本の視聴者に無関係な海外バズだけで本命にならない）
        # 2026-11-10（指示016）: YouTube の差の加点も同じ。視聴者への合い方が FOREIGN_BOOST_MIN_FIT 未満なら YouTube 分の加点を外して
        # 並べる（枠・core の両方）。差だけで日本の視聴者に無関係な話題が浮かない
        if bm is not None and c.get("buzz_yt_bonus") and fit(c) < FOREIGN_BOOST_MIN_FIT:
            bm = max(1, bm - int(c["buzz_yt_bonus"]))
        bm_lane = bm
        if bm is not None and c.get("buzz_foreign_boost") and fit(c) < FOREIGN_BOOST_MIN_FIT:
            bm_lane = c.get("buzz_jp_measured") or 1
        if gate:
            lane = "除外"
        elif bm is None:
            lane = "未計測"
        elif is_l2_type(c):
            lane = L2_LANE if topic_age_days(c) >= L2_MIN_TOPIC_AGE_DAYS else L2_WAIT_LANE
        elif bm_lane >= 3:
            lane = "本命"
        elif topic_age_days(c) * 24 <= BREAKING_HOURS and c.get("announcement_type") in BREAKING_TYPES:
            lane = "速報"
        elif fresh >= NICHE_MIN_FRESHNESS and _clamp5(c.get("hype_gap")) + _clamp5(c.get("debate")) >= NICHE_MIN_HYPE_DEBATE:
            lane = "ニッチ"
        else:
            lane = "注目度低"
        rows.append({"c": c, "fresh": fresh, "gate": gate, "lane": lane,
                     "core": fresh * bm * fit(c) if bm is not None else None,
                     "core_est": fresh * buzz_value(c)[0] * fit(c), "tb": tie_break(c), "interest": interest(c),
                     "old": overall(c, c.get("published", ""))[0]})
    ser = assign_series([r["c"] for r in rows if not r["gate"]])
    for r in rows:
        r["series"] = ser.get(r["c"]["id"], r["c"]["id"])
    return rows


def _sorted_core(rows: list) -> list:
    # 2026-11-07: 面白さ（interest）→ core（鮮度×注目×視聴者）→ 物×判断の数字＋手応え＋議論＋視聴者（tb）→ 媒体数。
    # 旬と注目度はゲート（本命の条件）で効かせ、条件を通った中は面白さで並べる（なるさんの決定。2026-10-11 の core 主役を置き換え）
    return sorted(rows, key=lambda r: (r["interest"], r["core"] if r["core"] is not None else -1, r["tb"],
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


BEST3_RELAXED_GENRE_MAX = 2     # 3件に満たないときだけ、同じジャンルをここまで許す
# ベスト3に入れる条件（2026-10-26、なるさんの指示）。ジャンルを分けるために視聴者に合わない候補・健康系が入り込まないように
BEST3_MIN_FIT = 3               # audience_fit（健康系は丸めた後の fit）がこれ未満の候補はベスト3に入れない（一覧には残す）
BEST3_HEALTH_MAX = 1            # ベスト3に入れる健康系（health: true）の上限
BEST3_MIN_PROMISE = 3           # 実現への手応え（promise）がこれ未満（誇張・宣伝が中心）の候補はベスト3に入れない（2026-10-26、構成 v4）
SLOT_HONMEI, SLOT_L2 = "本命", "答え合わせ"


def _primary_ok(c: dict) -> bool:
    """一次資料が確認済み（verify で True）。None（要確認）と未確認（primary_verified が無い）は補欠に回す。
    False（実在しない）はゲートで既に落ちている。"""
    return c.get("primary_verified") is True


def story_presentable(c: dict, rows: list) -> bool:
    """同一ストーリー（same_story で直接つながる兄弟）の提示日を合わせて数え、PRESENT_MAX_DAYS 日提示済みなら載せない。
    最後に提示した日より後の記事（続報）は、その候補自身の提示日だけで数える。ベスト3・答え合わせ候補の一覧の両方で使う（2026-11-10）。"""
    presented_rows = [r["c"] for r in rows if presented_days(r["c"])]
    d = set(presented_days(c))
    for o in presented_rows:
        if o is not c and same_story(c, o):
            d.update(presented_days(o))
    if d and _article_day(c) <= max(d) and _today() not in d and len(d) >= PRESENT_MAX_DAYS:
        return False
    return True


def best3(rows: list):
    """ベスト3の機械的な下書き（2026-10-15、混成）: 本命（core の順）→ 答え合わせ候補（実測の注目度→媒体数の順）を
    1列に並べ、本命の上位を優先して、ジャンルと系列が重ならないように選ぶ。
      1. 一次資料が確認済みの候補から、ジャンルが重ならないように
      2. 3件に満たなければ、同じジャンルを BEST3_RELAXED_GENRE_MAX 件まで許して補う（r['relaxed']）
      3. それでも満たなければ、一次資料が「要確認」・未確認の候補を最後の補欠に（r['reserve']、ジャンルは2件まで）
    それでも満たなければ満たないまま返し（注目度の低い候補で埋めない）、ニッチ枠の先頭を別に添える。
    再評価待ち（大手の製品発表で初出から2日未満）は入れない（決定4=(a)）。各行に r['slot']（〈本命〉／〈答え合わせ〉）を付ける。
    どの段でも、視聴者との合い方が BEST3_MIN_FIT 未満の候補は入れず、健康系は BEST3_HEALTH_MAX 件まで（2026-10-26）。"""
    honmei = [dict(r, slot=SLOT_HONMEI) for r in _sorted_core([r for r in rows if r["lane"] == "本命"])]
    l2 = [dict(r, slot=SLOT_L2) for r in sorted(
        [r for r in rows if r["lane"] == L2_LANE],
        key=lambda r: (r["interest"], r["core"] if r["core"] is not None else -1, r["c"].get("buzz_measured") or 0,
                       r["c"].get("buzz_outlets") or 0, r["tb"]), reverse=True)]
    order = [r for r in honmei + l2 if fit(r["c"]) >= BEST3_MIN_FIT and promise(r["c"]) >= BEST3_MIN_PROMISE
             and surprise_ok(r["c"])      # 2026-11-07: 驚きの1行が言い切れない候補は入れない
             and presentable(r["c"])      # 2026-11-08: 同じ候補は下書きに最大 PRESENT_MAX_DAYS 日まで
             and prior_art_ok(r["c"])]    # 2026-11-11: 先行事例あり（実現済み）で例外が言い切れない候補は入れない
    # 2026-11-08（管理担当の指摘）: 提示日数は同一ストーリー（same_story で直接つながる兄弟）で数える。兄弟が別々に2日ずつ載らないように。
    # 最後に提示した日より後の記事（続報）は、その候補自身の提示日だけで数える
    # 兄弟は直接つながる候補（same_story）だけ。topic_series は推移的に巨大になるので使わない（2026-11-08 管理担当の指摘）
    if not _TOKEN_DF:
        for c in load_candidates()["items"]:
            for t in _latin_tokens(_nfkc(c.get("title", ""))):
                _TOKEN_DF[t] = _TOKEN_DF.get(t, 0) + 1
    order = [r for r in order if story_presentable(r["c"], rows)]
    picks, series = [], set()
    from collections import Counter
    genres = Counter()

    def take(pool, genre_max, **flags):
        for r in pool:
            if len(picks) == 3:
                return
            g = r["c"].get("genre")
            ts = r["c"].get("topic_series")     # 2026-11-08: 同一ストーリー（topic_groups）も重ねない
            if r["series"] in series or (ts and ("topic:" + ts) in series) or genres[g] >= genre_max:
                continue
            if r["c"].get("health") and sum(1 for p in picks if p["c"].get("health")) >= BEST3_HEALTH_MAX:
                continue
            picks.append(dict(r, relaxed=genres[g] > 0, **flags))
            genres[g] += 1
            series.add(r["series"])
            if ts:
                series.add("topic:" + ts)

    ok = [r for r in order if _primary_ok(r["c"])]
    # 2026-11-04: 「物×判断の数字」の候補を最低1件（足りなければ空けたまま＝普通の選び方に戻る）。
    # 先に1件取り、他は従来どおり。最後に元の並び（order）に戻す
    # 2026-11-08: 先に新規優先枠（初回スキャンから48時間以内）を1件。無ければ空けたまま（呼び出し側が「新規候補なし」と明記する）
    # 2026-11-09: その前に、シリーズ候補の優先枠（定点観測シリーズ全般。2026-11-09-012 で人型ロボ以外に拡張）を1件。ok は入口条件を通った面白さ順なので、条件は迂回しない
    take([r for r in ok if series_candidate_info(r["c"])][:1], 1)
    if not any(is_new_candidate(p["c"]) for p in picks):
        for r in [r for r in ok if is_new_candidate(r["c"])]:     # take が受け入れる最初の1件（先頭が弾かれても次を試す）
            n0 = len(picks)
            take([r], 1)
            if len(picks) > n0:
                break
    if not any(is_tangible_pick(p["c"]) for p in picks):
        take([r for r in ok if is_tangible_pick(r["c"])][:1], 1)
    take(ok, 1)
    if len(picks) < 3:
        take(ok, BEST3_RELAXED_GENRE_MAX)
    if len(picks) < 3:
        unv = [r for r in order if not _primary_ok(r["c"])]
        take(unv, 1, reserve=True)
        take(unv, BEST3_RELAXED_GENRE_MAX, reserve=True)
    pos = {r["c"]["id"]: i for i, r in enumerate(order)}
    # 2026-11-11（指示2026-11-11-001）: 本命の絶対基準。驚き（先行事例の上限適用後）が HONMEI_MIN_WONDER 未満の候補は1位に置かない。
    # 強い候補（確認済みの入口条件を通ったもの）が選ばれていなければ、枠の競合で漏れた強い候補を最後の1枠と入れ替える。
    if picks and not any(honmei_strong(p["c"]) and not p.get("reserve") for p in picks):
        for r in ok:
            if not honmei_strong(r["c"]) or r["c"]["id"] in {p["c"]["id"] for p in picks}:
                continue
            rest = sorted(picks, key=lambda p: pos.get(p["c"]["id"], len(order)))
            keep = rest[:-1] if len(picks) == 3 else rest
            ts = r["c"].get("topic_series")
            if any(p["series"] == r["series"] or (ts and p["c"].get("topic_series") == ts) or p["c"].get("genre") == r["c"].get("genre")
                   for p in keep):
                continue
            if r["c"].get("health") and sum(1 for p in keep if p["c"].get("health")) >= BEST3_HEALTH_MAX:
                continue
            picks = keep + [dict(r, relaxed=False)]
            break
    # 表示は本命の上位を先に（元の並び order の順。補欠は最後）。強い候補（驚き4以上）を先頭に（絶対基準）
    picks.sort(key=lambda p: (bool(p.get("reserve")), not honmei_strong(p["c"]), pos.get(p["c"]["id"], len(order))))
    if picks and not any(honmei_strong(p["c"]) and not p.get("reserve") for p in picks):
        picks = [dict(p, weak_day=True) for p in picks]     # 基準に達する候補がない日。呼び出し側が「本命なし・弱い日」と明記する
    niche = _sorted_core([r for r in rows if r["lane"] == "ニッチ"])
    return picks, (niche[0] if niche and len(picks) < 3 else None)


def _slot_lines(r: dict) -> list:
    """ベスト3の各候補に付ける枠の注記（list・slack 共通）。"""
    c = r["c"]
    out = []
    si = series_candidate_info(c)
    if si:
        out.append(f"📌 シリーズ候補: {si['name']} 第{si['no']}回候補（ウォッチ対象: {si['target']}／節目の可能性: {'・'.join(si['milestones'])}。語の一致による目安）")
    if is_new_candidate(c):
        out.append("🆕 新規候補（初回スキャンから48時間以内）")
    n = len(presented_days(c))
    if n:      # 今日の再実行で載る場合は今日を含む。n は今日より前に提示した日数
        today_in = _today() in presented_days(c)
        out.append(f"提示 {n}日目（最大{PRESENT_MAX_DAYS}日。載せた日: {'・'.join(d[5:] for d in presented_days(c))}）" if today_in
                   else f"提示 {n + 1}日目（最大{PRESENT_MAX_DAYS}日）")
    if r.get("weak_day"):
        out.append(f"参考（{WEAK_DAY_LABEL}: 驚き{HONMEI_MIN_WONDER}以上の候補がないため、順位は付けず本命にしません）")
    if r.get("slot") == SLOT_L2:
        out.append("証拠: 未確認（第三者の検証・使った人の声を探す）")
        out.append(f"発表（初出）から{topic_age_days(c)}日")
    if r.get("relaxed"):
        out.append("ジャンルを緩めて補いました")
    if r.get("reserve"):
        out.append("補欠（一次資料が要確認。確認済みの候補で埋まらなかったため）")
    return out


def weak_day_note(picks: list) -> str:
    """本命の絶対基準（驚き HONMEI_MIN_WONDER 以上）を満たす候補が1件もない日の注記。ベスト3が空のときは呼び出し側が別に書く。"""
    return (f"【{WEAK_DAY_LABEL}】驚き{HONMEI_MIN_WONDER}以上の候補がありません。以下は順位なしの参考候補で、無理に本命1位は作りません"
            if picks and all(p.get("weak_day") for p in picks) else "")


def prior_art_rows(rows: list, states: tuple) -> list:
    """入口（本命・答え合わせ）を通ったが、先行事例チェックで外れた・保留になった候補（面白さ順）。提示上限を超えたものは出さない。"""
    out = [r for r in rows if r["lane"] in ("本命", L2_LANE) and prior_art_state(r["c"]) in states
           and presentable(r["c"]) and story_presentable(r["c"], rows)]
    return sorted(out, key=lambda r: -r["interest"])


NO_NEW_LINE = f"新規候補なし（初回スキャンから{NEW_WITHIN_HOURS}時間以内で、ゲートを通った候補がありません）"


def new_note(picks: list) -> str:
    """新規優先枠の注記。ベスト3に新規候補が1件も無いときだけ明記する。"""
    return "" if any(is_new_candidate(p["c"]) for p in picks) else NO_NEW_LINE


def _buzz_line(c: dict) -> str:
    if c.get("buzz_measured") is not None:
        t = c.get("buzz_trend")
        win = buzz_window(c.get("buzz_history") or [])
        if len(win) > 1:     # 2026-10-15: 測り直した候補は、直近の最大を採用している
            lat = win[0]
            hist = (f"直近{len(win)}回の最大、最新は実測{lat.get('measured')}・{lat.get('outlets', 0)}媒体"
                    + (f"、採用は{(c.get('buzz_adopted_at') or '')[:16]}計測" if c.get("buzz_adopted_at") != lat.get("at") else "") + "。")
        else:
            hist = ""
        return (f"注目度: 実測{c['buzz_measured']}（{hist}{c.get('buzz_outlets', 0)}媒体"
                f"{'・Yahoo!あり' if c.get('yahoo') else '・Yahoo!なし'}"
                + (f"・海外{c['buzz_outlets_foreign']}媒体" + ("＝海外分で入口超え" if c.get("buzz_foreign_boost") else "")
                   if c.get("buzz_outlets_foreign") is not None else "")
                + (f"・YouTube 英{c['buzz_yt']['en']['channels']}ch/日{c['buzz_yt']['ja']['channels']}ch 差{c['buzz_yt']['gap_log']}"
                   + (f"＝差あり+{c['buzz_yt_bonus']}" if c.get("buzz_yt_bonus") else "")
                   if c.get("buzz_yt") else "")
                + (f"、勢い{t:.2f}" if t is not None else "")
                + f"、{(c.get('buzz_measured_at') or '')[:16]}計測、検索語 {c.get('buzz_query', '')!r}）")
    msg = f"注目度: 推定{buzz_value(c)[0]}（未計測"
    if c.get("buzz_error"):
        msg += f"。実測失敗: {c['buzz_error']}"
    return msg + "）"


def _print_candidate(r: dict, short: bool = False):
    c = r["c"]
    fit_src = "" if c.get("audience_fit") is not None else "（暮らし・仕事で代用）"
    core = f"core {r['core']:3d}＝鮮度{r['fresh']}×注目{c['buzz_measured']}×視聴者{fit(c)}{fit_src}" if r["core"] is not None \
        else f"core —（鮮度{r['fresh']}、推定なら{r['core_est']}）"
    warn = "  ⚠️一次資料 要確認" if c.get("primary_verified", "未") is None else \
        ("  ⚠️一次資料 未確認" if "primary_verified" not in c else "")
    td, tb2 = tb_parts(r["tb"])
    intr = f"面白さ {r['interest']:2d}＝驚き{wonder_eff(c)}＋視聴者{fit(c)}＋見せる{_neutral3(c, 'tangible')}"
    print(f"[{intr}｜{core}｜物×数字 {td}｜手応え+議論+視聴者 {tb2}] {c['title'][:76]}"
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
    print(f"   驚き: {c.get('surprise_line') or ('（言い切れない）' if c.get('interest_version') == INTEREST_VERSION else '（未付与）')}")
    for ln in prior_art_lines(c):
        print(f"   {ln}")
    print(f"   見出し: {c.get('headline_claim')}")
    print(f"   実際: {c.get('actual_content')}")
    if c.get("hope_material"):
        print(f"   手応え: {c.get('hope_material')}（実現への手応え {c.get('promise', '未付与')}）")
    print(f"   ツッコミ: {c.get('tsukkomi_material')}  予想判定: {c.get('expected_verdicts')}")
    print(f"   一次資料: " + ", ".join((s["repaired_url"] + "（URLを自動で修復）") if s.get("repaired_url") else s.get("url", "")
                                  for s in c.get('primary_sources', [])))
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


def _print_primary_issues(rows: list):
    """一次資料の確認で問題があった候補を、理由つきで見せる（2026-11-12）。無言で消さない。"""
    conflicts = [r for r in rows if r["c"].get("primary_conflict") and r["c"].get("status") == "available"]
    if conflicts:
        print(f"\n==== 🔀 確認が食い違っている候補（夜間と再確認の結果が違う。落とすかは編集長・ユーザーが判断）: {len(conflicts)}件 ====")
        for r in conflicts:
            print(f"・{r['c']['title'][:60]}（id {r['c']['id']}、面白さ{r['interest']}）")
            for ln in conflict_lines(r["c"]):
                print(f"   {ln}")
    dropped = primary_gate_dropped(rows)
    if dropped:
        print(f"\n==== ❌ 一次資料の全URLが404でゲート落ちした候補: {len(dropped)}件（上位10件。「試行n回」は再確認の回数、無ければ旧方式の1回確認） ====")
        for r in sorted(dropped, key=lambda r: -r["interest"])[:10]:
            print(f"・{r['c']['title'][:60]}（id {r['c']['id']}、面白さ{r['interest']}）— {primary_drop_text(r['c'])}")


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


# ============================================================
# repair: 一次資料URLの自動修復（2026-10-15、NEWS_REDESIGN_2026-10-15.md §3.8「2週目の前倒し」）
# verify で primary_verified が false（全URLが404・ソフト404）の候補について、正しいURLを無料のHTTPだけで探す。
#   1. site-crawl   … 元の（404の）URLの発表元サイトを辿る（親ディレクトリ・トップ・RSS/Atom・robots.txt の sitemap、
#                     トップから「ニュース・お知らせ・IR」等の一覧へ1段）。リンク文と前後の文・URLに、候補の固有の語・
#                     what_it_states の語・発表日が合うリンク（PDFも）を拾う
#   2. pool-official… news_pool.json の同じ話題の記事のうち、公式・学術誌のフィード（news_sources.json で人が選んだ発表元）の
#                     もので、発表日が±3日のもの
#   3. media-link   … 同じ話題の報道記事（プールの記事・候補の gnews_link。Googleニュースのリダイレクトで本文が取れなければ飛ばす）の
#                     外向きのリンクのうち、発表元のドメインに向かうもの。**報道記事そのものは採用しない**（手がかりとしてだけ使う）
# 見つけたURLは verify と同じ判定（開ける・ソフト404でない・固有の語がある。DOIはハンドルAPI）に加えて、
# 「サイト共通でない語（what_it_states・見出しの語）か発表日」がページにあることを確かめ、確認できたものだけ採用する。
# PDFは本文の語を確かめられない（標準ライブラリに抽出手段がない。pdftotext があれば使う）ので、リンク文・前後の文に
# 固有でない語だけでなく what_it_states の語と発表日の両方が合うときだけ採用し、「本文は未確認」と記録する。
# primary_sources の元のURLは書き換えず、repaired_url 等を足す。repair が保証するのは「資料が実在し、語が合う」まで
# （見出しの主張が資料に書いてあるかは台本前のファクトチェックの役目）。
# ============================================================

REPAIR_DEFAULT_MAX = 12          # 1回の repair で扱う候補の上限
REPAIR_RETRY_DAYS = 7            # 前回の試行からこの日数以内は飛ばす（--force で再試行）
REPAIR_MAX_FETCH = 18            # 1候補あたりのHTTP取得の上限（ページ・robots・sitemap・確認を含む。一次資料が複数でも共通）
REPAIR_MAX_VERIFY = 4            # 1候補あたり、見つけたURLを確かめる上限
REPAIR_TIME_BUDGET = 300.0       # 秒。repair 全体の上限（夜間の所要時間を数分に収める）
REPAIR_DATE_WINDOW = 3           # 日。pool-official で発表日と比べる幅
REPAIR_MIN_LINK_SCORE = 4
REPAIR_NAV_WORDS = ("ニュース", "お知らせ", "プレスリリース", "報道", "トピックス", "新着", "ir", "news", "press",
                    "release", "topics", "newsroom", "blog", "決算", "投資家")
REPAIR_SECOND_LEVEL = ("co", "ac", "or", "go", "ne", "ed", "lg", "gr", "com", "org", "net", "gov", "edu")
REPAIR_STOP_TERMS = {"発表", "開始", "提供", "研究", "開発", "公開", "について", "お知らせ", "ニュース", "プレスリリース",
                     "with", "from", "this", "that", "their", "about", "release", "news"}
REPAIR_CAUTION = "資料の実在は確認。見出しの主張が書いてあるかは、台本前に資料で確かめる"
REPAIR_METHOD_LABEL = {"site-crawl": "発表元サイトを辿って", "pool-official": "プールの公式記事から",
                       "media-link": "報道記事のリンクを辿って", "locale-alt": "別の地域・言語の公式ページに差し替え"}


def _reg_domain(host: str) -> str:
    """登録ドメイン（簡易）。yaskawa.co.jp・tottori-u.ac.jp・blog.google・example.com"""
    parts = [p for p in (host or "").lower().split(".") if p]
    if len(parts) >= 3 and parts[-2] in REPAIR_SECOND_LEVEL and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def _date_variants(days) -> list:
    out = []
    for d in days:
        y, m, dd = d.year, d.month, d.day
        out += [f"{y}{m:02d}{dd:02d}", f"{y}/{m:02d}/{dd:02d}", f"{y}-{m:02d}-{dd:02d}", f"{y}.{m:02d}.{dd:02d}",
                f"{y}/{m}/{dd}", f"{y}.{m}.{dd}", f"{y}年{m}月{dd}日", f"{m}月{dd}日"]
    return list(dict.fromkeys(_nfkc(x) for x in out))


def _repair_terms(c: dict, src: dict) -> dict:
    """リンクを探す語。anchors（jp_title_anchor）・what（what_it_states の語）・title（見出しの語）・dates（発表日の表記）。"""
    what = _nfkc(src.get("what_it_states") or "")
    terms = set()
    for q in re.findall(r"[『「]([^』」]{3,30})[』」]", what):
        terms.add(q)
    terms |= set(re.findall(r"[ァ-ヶー]{4,}", what)) | set(re.findall(r"[一-鿿々]{3,}", what))
    terms |= {w for w in re.findall(r"[a-z][a-z0-9-]{3,}", what)}
    title_terms = set(re.findall(r"[ァ-ヶー]{4,}|[一-鿿々]{3,}|[a-z][a-z0-9-]{3,}", _nfkc(c.get("title", ""))))
    anchors = _verify_anchors(c)
    stop = REPAIR_STOP_TERMS | set(anchors)
    days = set()
    for fld in ("announced_on", "published"):
        d = _valid_day(c.get(fld))
        if d:
            days.add(d)
    for y, m, dd in re.findall(r"(20\d\d)年(\d{1,2})月(\d{1,2})日", what):
        try:
            days.add(datetime(int(y), int(m), int(dd)).date())
        except ValueError:
            pass
    return {"anchors": anchors, "what": sorted(t for t in terms if t not in stop),
            "title": sorted(t for t in title_terms if t not in stop and t not in terms),
            "dates": _date_variants(sorted(days)), "days": sorted(days),
            "slugs": [re.sub(r"[^a-z0-9]+", "-", a).strip("-") for a in anchors if re.fullmatch(r"[a-z0-9 .\-]+", a) and len(a) >= 4]}


class _RepairFetcher:
    """repair 用の取得（間隔は verify と同じ _HostPacer、robots.txt を守る、1候補あたりの取得回数に上限）。"""

    def __init__(self, pacer):
        self.pacer = pacer
        self.robots = {}
        self.sitemaps = {}
        self.count = 0
        self.log = []

    def _robots(self, base: str):
        if base in self.robots:
            return self.robots[base]
        import urllib.robotparser
        rp = urllib.robotparser.RobotFileParser()
        sm = []
        try:
            self.pacer.wait(base)
            self.count += 1
            raw = urllib.request.urlopen(urllib.request.Request(base + "/robots.txt", headers=BROWSER_UA), timeout=15).read(300_000)
            lines = raw.decode("utf-8", "replace").splitlines()
            rp.parse(lines)
            sm = [ln.split(":", 1)[1].strip() for ln in lines if ln.lower().startswith("sitemap:")]
        except urllib.error.HTTPError as e:
            # 4xx（robots.txt が無い等）は制限なし、5xx は一時的に全面禁止とみなす（Google の robots.txt の扱いと同じ）
            rp.parse(["User-agent: *", "Disallow: /"] if e.code >= 500 else [])
        except Exception:  # noqa: BLE001
            rp.parse([])
        self.robots[base] = rp
        self.sitemaps[base] = sm
        return rp

    def allowed(self, url: str) -> bool:
        sp = urllib.parse.urlsplit(url)
        return self._robots(f"{sp.scheme}://{sp.netloc}").can_fetch(BROWSER_UA["User-Agent"], url)

    def get(self, url: str, max_bytes: int = 1_500_000):
        """(最終URL, Content-Type, 本文の文字列) か None。PDFは取得しない（呼び出し側が判断する）。"""
        if self.count >= REPAIR_MAX_FETCH or not url.startswith("http"):
            return None
        if not self.allowed(url):
            self.log.append(f"robots.txt で禁止: {url}")
            return None
        self.pacer.wait(url)
        self.count += 1
        try:
            resp = _open(url, timeout=15)
            ctype = resp.headers.get("Content-Type", "")
            if "pdf" in ctype.lower():
                return resp.geturl() or url, ctype, ""
            raw = resp.read(max_bytes)
            if (resp.headers.get("Content-Encoding") or "").lower() == "gzip" or raw[:2] == b"\x1f\x8b":
                import gzip
                try:
                    raw = gzip.decompress(raw)
                except Exception:  # noqa: BLE001
                    pass
            return resp.geturl() or url, ctype, _decode(raw, ctype)
        except Exception as e:  # noqa: BLE001
            self.log.append(f"取得失敗 {url}: {type(e).__name__}")
            return None


def _open(url: str, timeout: int = 15):
    """urlopen。Python 3.9 の urllib は 308（恒久的な転送）をたどらないので、1回だけ自分でたどる（3.11 以降は不要）。"""
    try:
        return urllib.request.urlopen(urllib.request.Request(url, headers=BROWSER_UA), timeout=timeout)
    except urllib.error.HTTPError as e:
        loc = e.headers.get("Location") if e.code == 308 else None
        if not loc:
            raise
        return urllib.request.urlopen(urllib.request.Request(urllib.parse.urljoin(url, loc), headers=BROWSER_UA), timeout=timeout)


A_TAG = re.compile(r"<a\b[^>]*?href\s*=\s*[\"']([^\"'#]+)[\"'][^>]*>(.*?)</a>", re.I | re.S)


def _strip(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def _links(page_url: str, html: str) -> list:
    """[(絶対URL, リンク文, 前後の文)]。script・style は除く。"""
    html = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.I | re.S)
    out = []
    for m in A_TAG.finditer(html):
        href = m.group(1).strip()
        if href.startswith(("mailto:", "javascript:", "tel:")):
            continue
        url = urllib.parse.urljoin(page_url, href.replace("&amp;", "&"))
        text = _strip(m.group(2))
        ctx = _strip(html[max(0, m.start() - 500):m.start()])[-120:] + " " + _strip(html[m.end():m.end() + 300])[:80]
        out.append((url, text, ctx))
    return out


def _feed_links(xml_text: str) -> list:
    """RSS/Atom から [(URL, 見出し, 日付・要約)]"""
    out = []
    for it in re.findall(r"<(?:item|entry)\b.*?</(?:item|entry)>", xml_text, re.S | re.I):
        t = re.search(r"<title[^>]*>(.*?)</title>", it, re.S | re.I)
        ln = re.search(r"<link[^>]*>(.*?)</link>", it, re.S | re.I) or re.search(r"<link[^>]*href=[\"']([^\"']+)", it, re.I)
        d = re.search(r"<(?:pubDate|updated|published|dc:date)[^>]*>(.*?)</", it, re.S | re.I)
        if t and ln:
            title = _strip(re.sub(r"<!\[CDATA\[|\]\]>", "", t.group(1)))
            url = re.sub(r"<!\[CDATA\[|\]\]>", "", ln.group(1)).strip()
            out.append((url, title, d.group(1) if d else ""))
    return out


def _score_link(url: str, text: str, ctx: str, terms: dict, common: set) -> tuple:
    """(点, 当たった語)。サイト共通の語（common。サイトのトップ等の多くのリンクに出る語）は数えない。"""
    t = _nfkc(text + " " + ctx)
    u = _nfkc(urllib.parse.unquote(url))
    hits, score = [], 0
    for a in terms["anchors"]:
        if a in t and a not in common:
            score += 3
            hits.append(a)
    for w in terms["what"]:
        if w in t and w not in common:
            score += 2
            hits.append(w)
    tt = [w for w in terms["title"] if w in t and w not in common]
    score += min(len(tt), 2)
    hits += tt
    for s in terms["slugs"]:
        if s and s in u:
            score += 4
            hits.append(s)
    date_hit = any(d in t or d in u for d in terms["dates"])
    if date_hit:
        score += 2
        hits.append("発表日")
    return score, hits, date_hit


def _common_terms(links: list, terms: dict) -> set:
    """ページの多くのリンク（25%超）の文に出る語は、そのサイト共通の語（会社名など）として数えない。"""
    if len(links) < 8:
        return set()
    out = set()
    texts = [_nfkc(x[1] + " " + x[2]) for x in links]
    for w in terms["anchors"] + terms["what"] + terms["title"]:
        if sum(1 for t in texts if w in t) > 0.25 * len(texts):
            out.add(w)
    return out


def _is_pdf(url: str) -> bool:
    return urllib.parse.urlsplit(url).path.lower().endswith(".pdf")


def _pdf_text(raw: bytes) -> str:
    """pdftotext（poppler）があれば本文を取り出す。無ければ空（GitHub Actions の Ubuntu には標準では無い）。"""
    import shutil
    import subprocess
    if not shutil.which("pdftotext"):
        return ""
    try:
        p = subprocess.run(["pdftotext", "-l", "40", "-", "-"], input=raw, capture_output=True, timeout=30)
        return p.stdout.decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return ""


PAGE_DATE_PATTERNS = (
    re.compile(r"<meta[^>]+(?:property|name)=[\"'](?:article:published_time|og:published_time|pubdate|publishdate|date|dc\.date)[\"'][^>]*content=[\"'](\d{4}-\d{2}-\d{2})", re.I),
    re.compile(r"<meta[^>]+content=[\"'](\d{4}-\d{2}-\d{2})[^\"']*[\"'][^>]*(?:property|name)=[\"'](?:article:published_time|og:published_time|pubdate|date)[\"']", re.I),
    re.compile(r"[\"']datePublished[\"']\s*:\s*[\"'](\d{4}-\d{2}-\d{2})"),
)


def _page_date(html: str):
    """ページの公開日（メタデータ・構造化データにあれば）。無ければ None。"""
    for pat in PAGE_DATE_PATTERNS:
        m = pat.search(html[:300_000])
        if m:
            return _valid_day(m.group(1))
    return None


def _claim_terms(c: dict, text: str) -> dict:
    """任意: 見出しの主張の語（固有の語・見出しの数字や年）が資料の本文に含まれるかを数える（参考。判定には使わない）。"""
    t = _nfkc(text)
    want = list(dict.fromkeys(_verify_anchors(c) + re.findall(r"\d{2,}(?:\.\d+)?%?", _nfkc(
        (c.get("title") or "") + " " + (c.get("headline_claim") or "")))))
    return {"checked": want, "found": [w for w in want if w in t]}


def _confirm_found(url: str, link_info: dict, c: dict, terms: dict, common: set, fx: _RepairFetcher) -> dict:
    """見つけたURLを確かめる。採用なら ok=True の結果、そうでなければ ok を False/None にした結果を返す。"""
    anchors = terms["anchors"]
    if fx.count >= REPAIR_MAX_FETCH:
        return {"url": url, "ok": None, "status": "取得上限に達したため未確認"}
    if not fx.allowed(url):
        return {"url": url, "ok": None, "status": "robots.txt で禁止"}
    fx.pacer.wait(url)
    fx.count += 1
    if _is_pdf(url):
        try:
            resp = _open(url, timeout=20)
            raw = resp.read(8_000_000)
        except urllib.error.HTTPError as e:
            return {"url": url, "ok": False if e.code in (404, 410) else None, "status": f"HTTP {e.code}"}
        except Exception as e:  # noqa: BLE001
            return {"url": url, "ok": None, "status": f"取得失敗（{type(e).__name__}）"}
        if not raw.startswith(b"%PDF"):
            return {"url": url, "ok": False, "status": "PDFではない（ソフト404の可能性）"}
        text = _pdf_text(raw)
        r = {"url": url, "ok": True, "status": f"HTTP {resp.status}・PDF", "method": "http", "pdf": True}
        if text:
            r["anchor_hit"] = any(a in _nfkc(text) for a in anchors)
            r["claim_terms"] = _claim_terms(c, text)
            if not r["anchor_hit"]:
                r["ok"] = None
                r["status"] += "（本文に固有の語なし）"
            return r
        # 本文を読めないので、リンク文・前後の文に what_it_states の語と発表日の両方が合うときだけ採用する
        what_hit = [w for w in terms["what"] if w in link_info.get("hits", [])]
        r["pdf_text_checked"] = False
        if what_hit and link_info.get("date_hit"):
            r["status"] += f"（本文は未確認。リンク文の語「{what_hit[0]}」と発表日が一致）"
        else:
            r["ok"] = None
            r["status"] += "（本文は未確認。リンク文の語と発表日の両方は合わない）"
        return r
    doi = extract_doi(url)
    if doi and _host(url) in ("doi.org", "dx.doi.org"):
        return dict(check_doi(doi), url=url, method="doi_handle")
    try:
        resp = _open(url, timeout=15)
        raw = resp.read(400_000)
        html = _decode(raw, resp.headers.get("Content-Type", ""))
    except urllib.error.HTTPError as e:
        return {"url": url, "ok": False if e.code in (404, 410) else None, "status": f"HTTP {e.code}"}
    except Exception as e:  # noqa: BLE001
        return {"url": url, "ok": None, "status": f"取得失敗（{type(e).__name__}）"}
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    title = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    if title and SOFT404_TITLE.search(title):
        return {"url": url, "ok": False, "status": f"ソフト404（title「{title[:40]}」）"}
    final = resp.geturl() or url
    if final != url and urllib.parse.urlsplit(final).path in ("", "/"):
        return {"url": url, "ok": None, "status": f"トップページへ転送（{final[:60]}）"}
    body = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html[:400_000], flags=re.I | re.S)
    text = _nfkc(title + " " + _strip(body)[:60_000])
    head = text[:30_000]
    r = {"url": url, "ok": True, "status": f"HTTP {resp.status}" + (f"「{title[:30]}」" if title else ""),
         "page_title": title[:120], "method": "http", "anchor_hit": any(a in head for a in anchors) if anchors else None}
    specific = [w for w in terms["what"] + terms["title"] + terms["slugs"] if w not in common and w in text]
    date_hit = any(d in text or d in _nfkc(url) for d in terms["dates"])
    h1 = " ".join(_strip(x) for x in re.findall(r"<h1[^>]*>(.*?)</h1>", body, re.I | re.S)[:2])
    heading = _nfkc(title + " " + h1)
    strong = [a for a in anchors if a not in common and a in heading] + \
             [w for w in terms["what"] + terms["title"] if w not in common and len(w) >= 4 and w in heading]
    r["claim_terms"] = _claim_terms(c, text)
    pdate = _page_date(html)
    if pdate:
        r["page_date"] = pdate.isoformat()
    if r["anchor_hit"] is False:
        r["ok"] = None
        r["status"] += "（固有の語なし）"
    elif pdate and terms["days"] and min(abs((pdate - d).days) for d in terms["days"]) > REPAIR_DATE_WINDOW:
        # 例: Gemini 4 Argon の一般提供（10/13）の候補で、9/30 のプレビューの記事を拾った（同じ製品の別の発表）
        r["ok"] = None
        r["status"] += f"（ページの公開日 {pdate.isoformat()} が発表日と{REPAIR_DATE_WINDOW}日以上ずれる。別の発表の可能性）"
    elif not strong:
        r["ok"] = None
        r["status"] += "（見出しに候補の固有の語がない。一覧ページ・別の資料の可能性）"
    elif not specific and not date_hit:
        r["ok"] = None
        r["status"] += "（サイト共通の語しか合わない）"
    else:
        r["status"] += "（" + "・".join((specific[:3]) + (["発表日"] if date_hit else [])) + "が一致）"
    return r


def _issuer_domains(c: dict, src: dict, pool_official: list) -> set:
    doms = {_reg_domain(_host(src.get("url", "")))}
    doms |= {_reg_domain(_host(s.get("url", ""))) for s in c.get("primary_sources") or [] if s.get("url")}
    doms |= {_reg_domain(_host(p.get("url", ""))) for p in pool_official}
    return {d for d in doms if d and d not in ("doi.org",)}


def _same_topic_pool(c: dict, pool: list) -> list:
    """プールのうち、この候補と同じ話題の記事（固有の語をすべて含む・見出しの語の Jaccard・同じID）"""
    anchors = _topic_anchors(c)
    toks = _title_tokens(c.get("title", ""))
    ids = {c["id"]} | set(c.get("dup_ids") or [])
    out = []
    for p in pool:
        tn = _nfkc(p.get("title", ""))
        tk = _title_tokens(p.get("title", ""))
        if p.get("id") in ids or (anchors and all(a in tn for a in anchors)) or \
                (len(toks) >= 4 and len(tk) >= 4 and len(toks & tk) / len(toks | tk) >= DEDUP_JACCARD):
            out.append(p)
    return out


def repair_source(c: dict, src: dict, pool: list, fx: _RepairFetcher, deadline: float) -> dict:
    """1つの404のURLについて正しいURLを探す。見つかれば {url, method, from, check}、無ければ {tried: [...]}"""
    terms = _repair_terms(c, src)
    orig = (src.get("url") or "").strip()
    tried = []
    sp = urllib.parse.urlsplit(orig if "://" in orig else "https://" + orig)
    base = f"{sp.scheme or 'https'}://{sp.netloc}"
    same_topic = _same_topic_pool(c, pool)
    day0 = _valid_day(c.get("announced_on") or c.get("published"))

    def near(p, days):
        d = _valid_day(p.get("published"))
        return d is not None and day0 is not None and abs((d - day0).days) <= days

    pool_official = [p for p in same_topic if p.get("source_kind") in ("official", "journal") and p.get("url")
                     and near(p, REPAIR_DATE_WINDOW)]
    issuers = _issuer_domains(c, src, pool_official)

    def try_found(found: list, method: str):
        """found: [(点, URL, info)] を点の順に確かめる"""
        seen = set()
        n = 0
        for sc, url, info in sorted(found, key=lambda x: -x[0]):
            if url in seen or _norm_url(url) == _norm_url(orig) or n >= REPAIR_MAX_VERIFY or time.monotonic() > deadline:
                continue
            seen.add(url)
            n += 1
            r = _confirm_found(url, info, c, terms, info.get("common", set()), fx)
            tried.append(f"{method}: {url[:90]} → {r['status']}")
            if r.get("ok") is True:
                return {"url": url, "method": method, "from": info.get("from", ""), "check": r, "tried": list(tried)}
        return None

    # 1. site-crawl
    if sp.netloc and orig:
        fx._robots(base)
        seeds = []
        parts = [p for p in sp.path.split("/") if p]
        for k in range(len(parts) - 1, max(len(parts) - 3, 0) - 1, -1):    # 親ディレクトリ（深い方から2段まで）
            seeds.append(base + "/" + "/".join(parts[:k]) + ("/" if k else ""))
        if base + "/" not in seeds:
            seeds.append(base + "/")
        seeds = list(dict.fromkeys(seeds))
        found, nav, pages, feeds = [], [], 0, []
        crawled = []          # (ページのURL, リンク, ページの <title>)
        queue = list(seeds)
        visited = set()
        page_cap = fx.count + 8      # 1つのURLについて見るページは8枚まで
        while queue and fx.count < page_cap and time.monotonic() < deadline and fx.count < REPAIR_MAX_FETCH - REPAIR_MAX_VERIFY:
            page = queue.pop(0)
            if page in visited:
                continue
            visited.add(page)
            got = fx.get(page)
            pages += 1
            if not got or not got[2]:
                tried.append(f"site-crawl: {page[:80]} を開けない")
                continue
            final, ctype, html = got
            visited.add(final)
            head = html.lstrip()[:600].lower()
            ptitle = ""
            if "<sitemapindex" in html[:3000]:
                # sitemap index: URLに今年（無ければ発表年）を含む子のうち最後の1つ、無ければ先頭の1つだけ足す
                locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", html)
                yr = str((day0 or datetime.now().date()).year)
                pick = [u for u in locs if yr in u][-1:] or locs[:1]
                queue = pick + queue
                continue
            if "<urlset" in html[:3000]:
                links = [(u, "", "") for u in re.findall(r"<loc>\s*(.*?)\s*</loc>", html)]
            elif "rss" in ctype.lower() or "atom" in ctype.lower() or (head.startswith("<?xml") and ("<rss" in head or "<feed" in head)):
                links = [(u, t, d) for u, t, d in _feed_links(html)]
            else:
                links = _links(final, html)
                m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
                ptitle = _nfkc(m.group(1)) if m else ""
                for fm in re.finditer(r"<link[^>]+type=[\"']application/(?:rss|atom)\+xml[\"'][^>]*>", html, re.I):
                    h = re.search(r"href=[\"']([^\"']+)", fm.group(0))
                    if h:
                        feeds.append(urllib.parse.urljoin(final, h.group(1)))
            crawled.append((final, links, ptitle))
            if page in seeds:
                for u, t, _ in links:
                    nt = _nfkc(t + " " + urllib.parse.urlsplit(u).path)
                    if _host(u) == _host(final) and not _is_pdf(u) and any(w in nt for w in REPAIR_NAV_WORDS) \
                            and u not in nav and len(nav) < 6:
                        nav.append(u)
            if page == seeds[-1]:      # トップを読んだら、RSS/Atom → sitemap（固有の英語の語がURLにある場合） → 一覧ページの順に足す
                queue = list(dict.fromkeys(feeds[:2])) + queue
                if terms["slugs"]:
                    queue += [s for s in fx.sitemaps.get(base, [])[:1]]
                queue += [u for u in nav if u not in visited]
        # サイト共通の語: トップページの <title>、または2ページ以上の <title> にある語（会社名・大学名など）
        all_terms = terms["anchors"] + terms["what"] + terms["title"]
        titles = [t for _, _, t in crawled if t]
        top_title = next((t for u, _, t in crawled if urllib.parse.urlsplit(u).path in ("", "/")), "")
        site_common = {w for w in all_terms if w in top_title or sum(1 for t in titles if w in t) >= 2}
        exclude = visited | set(nav) | {_norm_url(x) for x in seeds}
        for final, links, _ in crawled:
            common = _common_terms(links, terms) | site_common
            for u, t, ctx in links:
                if _reg_domain(_host(u)) not in issuers or u in exclude or _norm_url(u) in exclude:
                    continue
                sc, hits, dh = _score_link(u, t, ctx, terms, common)
                if sc >= REPAIR_MIN_LINK_SCORE and any(h != "発表日" for h in hits):
                    found.append((sc, u, {"from": final, "hits": hits, "date_hit": dh, "common": common}))
        hit = try_found(found, "site-crawl")
        if hit:
            return hit
        if not found:
            tried.append(f"site-crawl: {pages}ページを見たが、語の合うリンクなし")

    # 2. pool-official（人が選んだ公式・学術誌のフィードの、同じ話題・発表日±3日の記事）
    if pool_official and time.monotonic() < deadline:
        hit = try_found([(10 + _score_link(p["url"], p.get("title", "") + " " + (p.get("summary") or ""), "", terms, set())[0],
                          p["url"], {"from": f"news_pool.json（{p.get('source', '')}）", "hits": [], "date_hit": True})
                         for p in pool_official], "pool-official")
        if hit:
            return hit
    elif not pool_official:
        tried.append("pool-official: 同じ話題の公式・学術誌の記事（発表日±3日）がプールにない")

    # 3. media-link（報道記事の外向きのリンクで、発表元のドメインに向かうもの。報道記事そのものは採用しない）
    media = [p.get("url") for p in same_topic if p.get("source_kind") == "media" and p.get("url") and near(p, 7)]
    media += [x for x in [c.get("gnews_link")] if x]
    media = list(dict.fromkeys(m for m in media if m))[:3]
    found = []
    for mu in media:
        if time.monotonic() > deadline or fx.count >= REPAIR_MAX_FETCH - 2:
            break
        got = fx.get(mu)
        if not got or not got[2]:
            tried.append(f"media-link: {mu[:70]} を開けない")
            continue
        final, _, html = got
        if _host(final) == "news.google.com":
            tried.append("media-link: Googleニュースのリダイレクトで本文が取れない（飛ばした）")
            continue
        media_dom = _reg_domain(_host(final))
        links = [x for x in _links(final, html) if _reg_domain(_host(x[0])) in issuers and _reg_domain(_host(x[0])) != media_dom]
        for u, t, ctx in links:
            sc, hits, dh = _score_link(u, t, ctx, terms, set())
            found.append((sc + 3, u, {"from": final, "hits": hits, "date_hit": dh, "common": set()}))
        if not links:
            tried.append(f"media-link: {_host(final)} の記事に発表元（{'・'.join(sorted(issuers))}）へのリンクなし")
    if found:
        hit = try_found(found, "media-link")
        if hit:
            return hit
    return {"tried": tried}


def repair_candidate(c: dict, pool: list, pacer, deadline: float) -> bool:
    """候補の404の一次資料を修復する。1件でも修復できれば primary_verified を true にする。"""
    now = datetime.now().isoformat(timespec="seconds")
    checks = {x.get("url"): x for x in c.get("primary_check") or []}
    srcs = [s for s in (c.get("primary_sources") or [])[:VERIFY_MAX_URLS] if s.get("url")]
    bad = [s for s in srcs if not s.get("repaired_url") and checks.get(s["url"], {}).get("ok") is False]
    log, fixed = [], []
    fx = _RepairFetcher(pacer)      # 取得回数の上限（REPAIR_MAX_FETCH）は候補ごと（一次資料が複数でも共通）
    for s in bad:
        if time.monotonic() > deadline:
            log.append("時間の上限に達したため中断")
            break
        if fx.count >= REPAIR_MAX_FETCH:
            log.append(f"{_host(s['url'])}: 取得の上限（候補あたり{REPAIR_MAX_FETCH}回）に達したため試していない")
            continue
        n_log = len(fx.log)
        r = repair_source(c, s, pool, fx, deadline)
        log += r.get("tried", []) + fx.log[n_log:n_log + 5]
        if r.get("url"):
            s["repaired_url"] = r["url"]
            s["repair_method"] = r["method"]
            s["repair_from"] = r["from"]
            s["repaired_at"] = now
            if r["check"].get("claim_terms"):
                s["repair_claim_terms"] = r["check"]["claim_terms"]
            if r["check"].get("pdf_text_checked") is False:
                s["repair_pdf_text_checked"] = False
            fixed.append((s, r))
    c["repair_tried"] = True
    c["repair_tried_at"] = now
    c["repair_log"] = log[-12:]
    if not fixed:
        c["repair_result"] = "見つからない"
        return False
    for s, r in fixed:
        new = dict(r["check"], kind=s.get("kind", ""), repaired=True, orig_url=s["url"], orig_status=checks.get(s["url"], {}).get("status", ""),
                   repair_method=r["method"], repair_from=r["from"])
        new.pop("claim_terms", None)
        new.pop("transient", None)
        new.pop("http", None)
        c["primary_check"] = [new if x.get("url") == s["url"] else x for x in c.get("primary_check") or []]
    c["primary_verified"] = primary_verdict(c["primary_check"])
    c["primary_verified_at"] = now
    c["primary_verified_note"] = "URLを自動で修復（repair）: " + " ／ ".join(
        f"{_host(s['url'])} → {s['repaired_url'][:80]}（{s['repair_method']}）" for s, _ in fixed)
    c["repair_result"] = "修復"
    oks = [x.get("ok") for x in c["primary_check"]]
    c["url_check"] = [{"url": x["url"], "ok": x.get("ok"), "status": x.get("status", "")} for x in c["primary_check"]]
    c["url_ok"] = False if False in oks else (True if all(oks) else None)
    c["url_status"] = " ／ ".join(f"{_host(x['url'])}: {x.get('status', '')}" for x in c["primary_check"])
    return c["primary_verified"] is True


def cmd_repair(ids: list, all_: bool, force: bool, max_n: int):
    """verify で一次資料URLが実在しない（primary_verified: false）候補の、正しいURLを無料のHTTPだけで探す（2026-10-15）。
    既定は false で一次資料以外のゲートを通る available な候補のうち、前回の試行から REPAIR_RETRY_DAYS 日を過ぎたもの。
    --all はゲートに関係なく false の候補すべて、--id は指定の候補、--force は最近試した候補も試す。"""
    cands = load_candidates()
    items = cands["items"]
    if ids:
        targets = [c for c in items if c["id"] in ids]
    else:
        used = used_source_urls(items)
        targets = [c for c in items if c.get("primary_verified") is False and c.get("status") == "available"
                   and (all_ or not [g for g in gate_reasons(c, used) if not g.startswith("一次資料")])]
    if not force:
        cutoff = datetime.now() - timedelta(days=REPAIR_RETRY_DAYS)
        skip = [c for c in targets if c.get("repair_tried_at") and datetime.fromisoformat(c["repair_tried_at"]) > cutoff]
        if skip:
            print(f"  前回の試行から{REPAIR_RETRY_DAYS}日以内のため飛ばす: {len(skip)}件（--force で再試行）")
        targets = [c for c in targets if c not in skip]
    targets.sort(key=lambda c: (-freshness_score(fresh_date(c)), -(c.get("buzz_measured") or buzz_value(c)[0])))
    if len(targets) > max_n:
        print(f"  対象が{len(targets)}件あるため、{max_n}件だけ試します（残りは次回）")
        targets = targets[:max_n]
    print(f"一次資料URLの自動修復: {len(targets)}件（発表元サイト → プールの公式記事 → 報道記事のリンク。HTTPのみ、"
          f"間隔{URL_CHECK_INTERVAL}秒・同じホスト{VERIFY_SAME_HOST_INTERVAL}秒、robots.txt を守る）")
    if not targets:
        return
    pool = _load_pool_items()
    pacer = _HostPacer()
    deadline = time.monotonic() + REPAIR_TIME_BUDGET
    n_ok = 0
    for c in targets:
        t0 = time.monotonic()
        ok = repair_candidate(c, pool, pacer, deadline)
        n_ok += ok
        dt = time.monotonic() - t0
        if ok:
            for s in c.get("primary_sources") or []:
                if s.get("repaired_url") and s.get("repaired_at") == c["repair_tried_at"]:
                    print(f"  [修復] {c['id']} {c['title'][:44]}（{dt:.0f}秒）\n         {s['url']}\n      → {s['repaired_url']}"
                          f"（{s['repair_method']}、{s['repair_from'][:70]}）")
        else:
            print(f"  [見つからない] {c['id']} {c['title'][:44]}（{dt:.0f}秒）")
            for ln in c.get("repair_log", [])[-6:]:
                print(f"         - {ln}")
    _save_candidates(cands)
    print(f"\n修復 {n_ok}件・見つからない {len(targets) - n_ok}件（{CANDIDATES_JSON.name} に保存）。{REPAIR_CAUTION}")


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
    _print_primary_issues(rows)

    picks, niche_extra = best3(rows)
    print(f"\n==== ベスト3の下書き（本命 面白さの順 → 答え合わせ候補、ジャンルと系列が重ならないように）: {len(picks)}件 ====")
    if any(r.get("relaxed") for r in picks):
        print(f"   ※ ジャンルを緩めて補いました（同じジャンルは{BEST3_RELAXED_GENRE_MAX}件まで）")
    if len(picks) < 3:
        print(f"   ※ 条件を満たす候補が{len(picks)}件しかない（3件に満たないまま出す）")
    if new_note(picks):
        print(f"   ※ {new_note(picks)}")
    if not picks:
        print(f"   ※ 【{WEAK_DAY_LABEL}】ゲートを通った本命・答え合わせ候補がありません（無理に1位は作りません）")
    if weak_day_note(picks):
        print(f"   ※ {weak_day_note(picks)}")
    for r in picks:
        print(f"〈{'参考' if r.get('weak_day') else r['slot']}〉", end="")
        _print_candidate(r, short=True)
        for ln in _slot_lines(r) + prior_art_lines(r["c"]):
            print(f"   {ln}")
    # 2026-11-11: 先行事例チェックで外れた・保留の候補（判定の根拠つき）
    for r in prior_art_rows(rows, ("realized_excluded",)):
        print(f"   🔁 先行事例ありのため本命から外した: {r['c']['title'][:50]}（面白さ{r['interest']}＝驚き{wonder_eff(r['c'])}"
              f"＜上限{PRIOR_ART_WONDER_CAP}適用＞）根拠: {prior_art_evidence_text(r['c'])}")
    for r in prior_art_rows(rows, ("realized_held",)):
        print(f"   😶 先行事例あり・「何が今回初めてか」が言い切れず保留: {r['c']['title'][:50]}（{(r['c'].get('prior_art') or {}).get('reason', '')}）")
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
          "本命の枠ではなく、ベスト3の空きに〈答え合わせ〉として入る（発表の紹介ではなく、発表の盛り vs 使った人の声・第三者の検証で扱う）")
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


SERIES_TRACE_JSON = BASE_DIR / "series_trace.json"   # シリーズ候補が「収集→採点→入口→提示」のどこまで進んだかの日次記録（gitで追跡）
SERIES_TRACE_KEEP_DAYS = 30
SERIES_TRACE_MAX_AGE = 21      # 記事の日付がこれより古いものは記録しない


def held_for_surprise(rows: list) -> list:
    """入口（本命・答え合わせ）と他の条件は通ったが、驚きの1行が空でベスト3に入れない候補（基準は緩めない。保留として見せる）。
    シリーズ候補を先に、次に面白さ順。提示上限を超えたものは出さない。"""
    out = [r for r in rows if r["lane"] in ("本命", L2_LANE) and not surprise_ok(r["c"])
           and fit(r["c"]) >= BEST3_MIN_FIT and promise(r["c"]) >= BEST3_MIN_PROMISE
           and presentable(r["c"]) and story_presentable(r["c"], rows)]
    return sorted(out, key=lambda r: (not series_candidate_info(r["c"]), -r["interest"]))


def series_funnel(rows: list, picks: list, pool: list, items: list) -> list:
    """シリーズ候補（語マッチ）ごとの進み具合。stage: 1収集 → 2採点済み → 3入口通過 → 4ベスト3。stopped は止まった理由。"""
    cutoff = (datetime.now().date() - timedelta(days=SERIES_TRACE_MAX_AGE)).isoformat()
    by_id = {c["id"]: c for c in items}
    row_by_id = {r["c"]["id"]: r for r in rows}
    pick_ids = {p["c"]["id"] for p in picks}
    out, seen = [], set()
    for c in items:
        if c.get("status") == "merged" or _article_day(c) < cutoff:
            continue
        si = series_candidate_info(c)
        if not si:
            continue
        e = {"id": c["id"], "title": c["title"][:70], "series": si["series_id"], "target": si["target"], "article": _article_day(c), "stage": 2}
        r = row_by_id.get(c["id"])
        if c.get("status") != "available":
            e["stopped"] = f"採点後に除外（{c.get('excluded_reason') or c.get('status')}）"
        elif r is None:
            e["stopped"] = f"状態 {c.get('status')}"
        elif r["gate"]:
            e["stopped"] = "ゲートで落ちた（" + "・".join(r["gate"])[:60] + "）"
        elif r["lane"] not in ("本命", L2_LANE):
            e["stopped"] = f"入口（注目度・枠）を通らず（{r['lane']}）"
        else:
            e["stage"] = 3
            if c["id"] in pick_ids:
                e["stage"], e["stopped"] = 4, "ベスト3に掲載"
            elif not surprise_ok(c):
                e["stopped"] = "驚きの1行が付かず保留（" + (c.get("surprise_hold_reason") or "理由の記録なし") + "）"
            elif not prior_art_ok(c):
                e["stopped"] = "先行事例あり（実現済み。" + prior_art_evidence_text(c, 1) + "）"
            elif fit(c) < BEST3_MIN_FIT or promise(c) < BEST3_MIN_PROMISE:
                e["stopped"] = "視聴者との合い方・手応えが基準未満"
            elif not presentable(c):
                e["stopped"] = f"提示{PRESENT_MAX_DAYS}日の上限を使い切り"
            elif not _primary_ok(c):
                e["stopped"] = "入口通過・一次資料が要確認（補欠）"
            else:
                e["stopped"] = "入口通過・ほかの候補との枠の競合で次点"
        seen.add(c["id"])
        seen.update(c.get("dup_ids") or [])
        out.append(e)
    for p in pool:
        if p["id"] in by_id or set(p.get("dup_ids") or []) & set(by_id) or p["id"] in seen:
            continue
        if (p.get("published") or "") < cutoff:
            continue
        si = pool_series_info(p)
        if si:
            out.append({"id": p["id"], "title": p["title"][:70], "series": si["series_id"], "target": si["target"],
                        "article": (p.get("published") or "")[:10], "stage": 1,
                        "stopped": "未採点（採点キュー待ち。採点枠は通常15件、シリーズ優先は最大4件）"})
    return out


def record_series_trace(funnel: list):
    """日次の記録を SERIES_TRACE_JSON に残す（同じ日の再実行は上書き）。古い日は捨てる。"""
    try:
        data = json.loads(SERIES_TRACE_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    days = data.get("days") or {}
    days[_today()] = funnel
    keep = sorted(days)[-SERIES_TRACE_KEEP_DAYS:]
    data = {"_comment": "シリーズ候補の進み具合の日次記録（指示 2026-11-10-015）。stage: 1=収集（未採点）→2=採点済み→3=入口通過→4=ベスト3に掲載。"
                        "stopped=止まった理由。kl_news_scan.py slack が書く。",
            "days": {d: days[d] for d in keep}}
    SERIES_TRACE_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def funnel_note(funnel: list) -> str:
    if not funnel:
        return "シリーズ候補: 今日はウォッチ対象×節目の語に当たる記事なし（収集・採点とも）"
    n = [sum(1 for e in funnel if e["stage"] >= s) for s in (1, 2, 3, 4)]
    sid = {s["series_id"]: s.get("name", s["series_id"]) for s in _series_list()}
    lines = [f"*📌 シリーズ候補の進み具合*　語に当たった{n[0]}件 → 採点済み{n[1]} → 入口通過{n[2]} → ベスト3 {n[3]}"]
    for e in sorted(funnel, key=lambda x: (-x["stage"], x["article"]))[:6]:
        lines.append(f"・[{sid.get(e['series'], e['series'])}] {e['title'][:34]}（{e['article'][5:]}）→ {e['stopped']}")
    if len(funnel) > 6:
        lines.append(f"…ほか{len(funnel) - 6}件（series_trace.json）")
    return "\n".join(lines)


def cmd_slack(note_path: str, record: bool = True):
    """夜間実行用: ベスト3の下書きをスマホで読める Slack の Block Kit にして標準出力へ JSON で出す（2026-10-14）。"""
    g = json.loads(GENRES_JSON.read_text(encoding="utf-8"))
    gen = {k: v for k, v in g["genres"]} if isinstance(g["genres"], list) else dict(g["genres"])
    vname = {"soon": "もうすぐ", "decade": "3年", "pending": "根拠待ち", "dubious": "眉唾"}
    cands = load_candidates()
    rows = classify(cands["items"])
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
        nwin = len(buzz_window(c.get("buzz_history") or []))
        buzz = (f"注目{c['buzz_measured']}（{c.get('buzz_outlets', 0)}媒体"
                f"{'・Yahoo!' if c.get('yahoo') else ''}{f'・直近{nwin}回の最大' if nwin > 1 else ''}）") \
            if c.get("buzz_measured") is not None else "注目 未計測"
        repaired_note = ""
        meta = " ・ ".join(x for x in [f"{gi.get('icon', '')}{gi.get('label', c.get('genre', '?'))}", day(c), first(c), buzz,
                                       "健康系" if c.get("health") else ""] if x)
        if "primary_verified" in c:     # 2026-10-15: verify の結果（1件でも開ければ確認済み）
            pv = c["primary_verified"]
            mark, label = {True: ("✅", "確認済み"), False: ("❌", "実在しない"), None: ("⚠️", "要確認")}[pv]
            ok_src = [x for x in c.get("primary_check") or [] if x.get("ok")]
            src = ok_src[0]["url"] if ok_src else (c.get("primary_sources") or [{}])[0].get("url", "")
            if c.get("primary_conflict"):
                label += "（確認が食い違い）"
                repaired_note = "🔀 " + esc(c["primary_conflict"].get("reason", ""))
            if ok_src and ok_src[0].get("repaired"):      # 2026-10-15: repair で修復したURL
                label += "（URLを自動で修復）"
                repaired_note = f"🔧 {REPAIR_CAUTION}"
        else:
            mark = {True: "✅", False: "❌", None: "⚠️"}[c.get("url_ok")] if c.get("url_status") else "⚠️"
            label = {True: "OK", False: "リンク切れ", None: "要確認"}[c.get("url_ok")] if c.get("url_status") else "未確認"
            src = (c.get("primary_sources") or [{}])[0].get("url", "")
        link = f"<{src}|一次資料 {label}>" if src else f"一次資料 {label}"
        if repaired_note:
            link += "\n" + repaired_note
        ev = c.get("expected_verdicts") or {}
        verdict = (f"大輔 {vname.get(ev.get('dreamer'), '?')} ／ 沙織 {vname.get(ev.get('skeptic'), '?')}") if ev else ""
        lines = [f"*{nums[i]} 〈{'参考・順位なし' if r.get('weak_day') else r.get('slot', SLOT_HONMEI)}〉{title}*", meta]
        lines += [esc(x) for x in _slot_lines(r)]
        lines += [f"💬 {esc(c.get('entry_question'))}"]
        # 2026-11-08: 面白さの内訳（wonder / audience_fit / tangible）と surprise_line を毎回出す（選定理由を制作者に見せる）
        lines.append(f"📊 面白さ{r['interest']}＝驚き{wonder_eff(c)}＋視聴者{fit(c)}＋見せる{_neutral3(c, 'tangible')}")
        lines.append(f"😲 驚き: {clip(c.get('surprise_line'), 60) if c.get('surprise_line') else '（未付与）'}")
        lines += [esc(x) for x in prior_art_lines(c)]
        if c.get("hope_material"):
            lines.append(f"🌱 手応え: {clip(c.get('hope_material'), 90)}")
        lines.append(f"🔎 ツッコミ: {clip(c.get('tsukkomi_material'), 90)}")
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
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"今夜はベスト3なし（ゲートを通った本命・答え合わせ候補がありません）。*{WEAK_DAY_LABEL}*"}})
    elif weak_day_note(picks):
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*{esc(weak_day_note(picks))}*"}})
    for i, r in enumerate(picks):
        blocks.append({"type": "divider"})
        blocks.append(card(i, r))
    notes = []
    if new_note(picks):
        notes.append(new_note(picks))
    if any(r.get("relaxed") for r in picks):
        notes.append(f"ジャンルを緩めて補いました（同じジャンルは{BEST3_RELAXED_GENRE_MAX}件まで）")
    if len(picks) < 3 and picks:
        notes.append(f"ベスト3が{len(picks)}件のみ（3件に満たないまま出しています）")
    if notes:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": "／".join(notes)}]})
    if niche:
        blocks.append({"type": "divider"})
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": "ニッチ（注目度は低い）: " + esc(niche["c"]["title"][:60])}]})
    # ベスト3に入った答え合わせ候補（と同じ系列）は、別枠に重ねて出さない
    in_best = {r["series"] for r in picks}
    # 2026-11-10 (handoff 2026-11-10-012): 答え合わせ候補の一覧も提示日数の上限を効かせ、載せた日も記録する
    #   （従来は一覧が上限の対象外・記録の対象外で、ベスト3に入らない候補が毎晩一覧に載り続けた）
    l2 = [r for r in collapse_series(_sorted_core([r for r in rows if r["lane"] == L2_LANE]))
          if r["series"] not in in_best and presentable(r["c"]) and story_presentable(r["c"], rows)][:3]
    if l2:
        blocks.append({"type": "divider"})
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": (
            f"*{L2_HEADING}*\n" + "\n".join(
                f"・{esc(r['c']['title'][:40])}（{first(r['c']) or day(r['c'])}、{r['c'].get('buzz_outlets', 0)}媒体"
                + ("、⚠️一次資料 要確認" if r["c"].get("primary_verified", "未") is None else "") + "）" for r in l2))[:2900]}]})
    # 2026-11-10 (handoff 2026-11-10-015): 驚きの1行が付かず保留の候補（基準は緩めない。ベスト3には入れず、理由つきで見せる）
    held = [r for r in held_for_surprise(rows) if r["series"] not in in_best][:3]
    if held:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": (
            "*😶 驚きの1行が付かず保留*（入口は通過。1行が言い切れないためベスト3には入れていません）\n" + "\n".join(
                f"・{'📌' if series_candidate_info(r['c']) else ''}{esc(r['c']['title'][:40])}（{first(r['c']) or day(r['c'])}）"
                f"再試行{len(r['c'].get('surprise_retry') or [])}回: {esc(r['c'].get('surprise_hold_reason') or '次の enrich で付け直します')}" for r in held))[:2900]}]})
    # 2026-11-11 (handoff 2026-11-11-001): 先行事例チェックで本命から外した候補・例外が言い切れず保留の候補（判定の根拠つき）
    pa_ex = [r for r in prior_art_rows(rows, ("realized_excluded",)) if r["series"] not in in_best][:3]
    pa_hold = [r for r in prior_art_rows(rows, ("realized_held",)) if r["series"] not in in_best][:3]
    if pa_ex or pa_hold:
        txt = []
        if pa_ex:
            txt.append("*🔁 先行事例あり（既に使える形で実現済み）のため本命から外しました*（驚きは上限2）\n" + "\n".join(
                f"・{esc(r['c']['title'][:40])}（{first(r['c']) or day(r['c'])}）根拠: {esc(prior_art_evidence_text(r['c']))}" for r in pa_ex))
        if pa_hold:
            txt.append("*😶 先行事例あり・「何が今回初めてか」が一次資料で言い切れず保留*\n" + "\n".join(
                f"・{esc(r['c']['title'][:40])}（{first(r['c']) or day(r['c'])}）{esc((r['c'].get('prior_art') or {}).get('reason', ''))[:60]}" for r in pa_hold))
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": "\n".join(txt)[:2900]}]})
    pool_items = _load_pool_items()
    funnel = series_funnel(rows, picks, pool_items, cands["items"])
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": esc(funnel_note(funnel))[:2900]}]})
    wait = [r for r in rows if r["lane"] == L2_WAIT_LANE][:3]
    if wait:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": f"再評価待ち（大手の製品発表、{L2_MIN_TOPIC_AGE_DAYS}日後に答え合わせ候補へ）: "
                                                       + " ／ ".join(esc(r["c"]["title"][:28]) for r in wait)}]})
    # 2026-11-12: 食い違い・ゲート落ちは理由つきで出す（無言で消さない）。件数の行（下）は従来どおり残す
    cf_rows = [r for r in rows if r["c"].get("primary_conflict") and r["c"].get("status") == "available"][:3]
    if cf_rows:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": (
            "*🔀 一次資料の確認が食い違っている候補*（夜間と再確認で結果が違う。落とすかは編集長・ユーザーが判断）\n" + "\n".join(
                f"・{esc(r['c']['title'][:40])}（面白さ{r['interest']}）{esc(r['c']['primary_conflict'].get('reason', ''))}" for r in cf_rows))[:2900]}]})
    dr_rows = sorted(primary_gate_dropped(rows), key=lambda r: -r["interest"])[:5]
    if dr_rows:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": (
            "*❌ 一次資料の全URLが404でゲート落ち*（「試行n回」は再確認の回数。無ければ旧方式の1回確認）\n" + "\n".join(
                f"・{esc(r['c']['title'][:40])}（面白さ{r['interest']}）{esc(primary_drop_text(r['c']))[:160]}" for r in dr_rows))[:2900]}]})
    n_false = sum(1 for r in rows if r["c"].get("primary_verified") is False)
    if n_false:
        n_tried = sum(1 for r in rows if r["c"].get("primary_verified") is False and r["c"].get("repair_tried"))
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": f"一次資料URLが実在しない（全URLが404）ため除外: {n_false}件"
                                                       + (f"（うち自動修復でも見つからず {n_tried}件）" if n_tried else "")}]})
    brk = [r for r in rows if r["lane"] == "速報"][:3]
    if brk:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": "速報（48時間後に再計測）: " + " ／ ".join(esc(r["c"]["title"][:28]) for r in brk)}]})
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": "朝の /kl-new で仕上げます（既視感・競合動画・一次資料の確認）"}]})
    if record:      # 2026-11-08: 載せた日を残す（同じ日の再実行では増えない）。保存は news_candidates.json のみ
        today = _today()
        for r in picks + l2:      # ベスト3＋答え合わせ候補の一覧（2026-11-10）
            d = presented_days(r["c"])
            if today not in d:
                r["c"]["presented_on"] = d + [today]
        _save_candidates(cands)
        record_series_trace(funnel)
    print(json.dumps({"text": "KL ネタ ベスト3の下書き", "blocks": blocks}, ensure_ascii=False))


_TOKEN_DF = {}      # 英数語 → その語を見出しに含む候補の数（cmd_dedupe が作る）


_RARE_STOP = {"introducing", "introduces", "launches", "launch", "announces", "announcing", "building", "using", "turns"}


def _latin_tokens(title_n: str) -> set:
    """製品名・固有名らしい英数語（数字を含む、または大文字を含む）。英語の見出し先頭の語と一般的な動詞は除く。"""
    out = set()
    for m in re.finditer(r"[A-Za-z0-9][A-Za-z0-9.+-]{3,}", title_n):
        t = m.group(0)
        if not (re.search(r"\d", t) or re.search(r"[A-Z]", t)):
            continue
        if t.lower() in _RARE_STOP:
            continue
        out.add(t.lower())
    return out


def _rare_tokens(title_n: str) -> set:
    return {t for t in _latin_tokens(title_n) if 0 < _TOKEN_DF.get(t, 0) <= 6}


def same_story(a: dict, b: dict) -> bool:
    """2件が直接同じストーリーか（topic_groups と同じ条件を2件だけで判定する）。topic_groups は推移的につなぐので、
    統合・状態の伝播には使わない（「GPT-6.1 Sol」の発表を核に別の発表までつながった。2026-11-08 の試験で確認）。"""
    ta, tb = _nfkc(a.get("title", "")), _nfkc(b.get("title", ""))
    if b["id"] in (a.get("dup_ids") or []) or a["id"] in (b.get("dup_ids") or []):
        return True
    if _distinct_numbers(a.get("title", ""), b.get("title", "")):
        return bool(a.get("series")) and a.get("series") == b.get("series")
    # 同じ時期（前後1日）の発表で、全候補の見出しに6件以下しか出ない固有の英数語（製品名など）を共有する
    # （見出しの言い回しが違う同じ発表。「1Password」「ugo Nova」。2026-11-08 管理担当の指摘）
    try:
        close = abs((datetime.fromisoformat(_article_day(a)) - datetime.fromisoformat(_article_day(b))).days) <= 1
    except ValueError:
        close = False
    if close and (_rare_tokens(ta) & _rare_tokens(tb)):
        return True
    qa, qb = (a.get("jp_news_query") or "").strip(), (b.get("jp_news_query") or "").strip()
    if close and qa and qa == qb:      # 同じ日本語検索語（enrich が付ける）で、前後1日の発表
        return True
    aa, ab = _topic_anchors(a), _topic_anchors(b)
    ka, kb = _title_tokens(a.get("title", "")), _title_tokens(b.get("title", ""))
    return ((bool(a.get("series")) and a.get("series") == b.get("series"))
            or bool(aa and ab and all(x in tb for x in aa) and all(x in ta for x in ab))    # 片方向だけだと「GPT-6.1 Sol」を含む別の発表がつながる
            or (len(ka) >= 4 and len(kb) >= 4 and len(ka & kb) / len(ka | kb) >= DEDUP_JACCARD))


def _article_day(c: dict) -> str:
    return ((c.get("announced_on") or c.get("published") or "")[:10]) or "0000-00-00"


def _canonical_key(c: dict):
    """重複統合で残す1件の選び方（最良のものを残す）: 一次資料確認済み → 驚きの1行がある → 面白さ → 実測の注目度 → 媒体数 → 初回スキャンが早い。"""
    fs = first_seen_dt(c)
    return (c.get("primary_verified") is True, bool((c.get("surprise_line") or "").strip()), interest(c),
            c.get("buzz_measured") if c.get("buzz_measured") is not None else -1, c.get("buzz_outlets") or 0,
            -(fs.timestamp() if fs else 1e18))


MERGE_FILL_KEYS = ("surprise_line", "wonder", "prior_art", "audience_fit", "tangible", "promise", "decision_number", "buzz_measured",
                   "buzz_outlets", "buzz_measured_at", "primary_verified", "entry_question")


def cmd_dedupe(dry_run: bool = False):
    """同一ネタの繰り返し対策（2026-11-08）。費用ゼロ・データは消さず status と欄の追加だけ:
      1. 下書きに PRESENT_MAX_DAYS 日提示して選ばれなかった候補を棚上げ（status=shelved、shelved_on）
      2. 同一ストーリー（same_story）に used / shelved があれば、記事の日付がその状態の日以前の available な兄弟も同じ状態に（続報は残す）
      3. 残った available な同一ストーリーの重複を、最良の1件（canonical）に統合（他は status=merged、merged_into）
    夜間実行では buzz の後・list の前に回す。"""
    cands = load_candidates()
    items = cands["items"]
    today = _today()
    log = []
    _TOKEN_DF.clear()
    for c in items:
        for t in _latin_tokens(_nfkc(c.get("title", ""))):
            _TOKEN_DF[t] = _TOKEN_DF.get(t, 0) + 1

    # 1. 棚上げ
    for c in items:
        d = presented_days(c)
        if c.get("status") == "available" and len(d) >= PRESENT_MAX_DAYS and today not in d:
            c.update(status=STATE_SHELVED, shelved_on=today, shelved_reason=f"下書きに{len(d)}日提示（{'・'.join(x[5:] for x in d)}）して選ばれなかった")
            log.append(f"棚上げ: {c['id']} {c['title'][:50]}（提示 {'・'.join(d)}）")

    # 2・3. ストーリー単位
    live = [c for c in items if c.get("status") in ("available", "used", STATE_SHELVED, STATE_MERGED)]
    # used / 棚上げの状態は、直接同じストーリー（same_story）の候補だけに効かせる（topic_series は推移的に巨大になるので使わない）
    for c in [x for x in items if x.get("status") == "available"]:
        for o in live:
            if o is c or o.get("status") not in ("used", STATE_SHELVED) or not same_story(c, o):
                continue
            if o.get("status") == STATE_SHELVED and _article_day(c) <= (o.get("shelved_on") or "0000"):
                c.update(status=STATE_SHELVED, shelved_on=o.get("shelved_on"), shelved_via=o["id"],
                         shelved_reason=f"同一ストーリー（{o['id']}）が棚上げ済み")
                log.append(f"棚上げ（ストーリー単位）: {c['id']} {c['title'][:50]} ← {o['id']} {o['title'][:30]}")
                break
            if o.get("status") == "used":
                fs = first_seen_dt(o)
                cut = (fs.date() + timedelta(days=USED_STORY_GRACE_DAYS)).isoformat() if fs else "9999"
                if _article_day(c) <= cut:
                    c.update(status=STATE_MERGED, merged_into=o["id"], merged_reason="同一ストーリーが使用済み")
                    log.append(f"使用済みのストーリーに吸収: {c['id']} {c['title'][:50]} ← {o['id']} {o['title'][:30]}")
                    break
    # 同一ストーリーで PRESENT_MAX_DAYS 日提示済みなら、最後の提示日以前の記事の兄弟も棚上げ（続報は残す）。
    # 提示日数は直接つながる兄弟（same_story）だけで数える。topic_series は推移的に巨大になる（68件）ので使わない
    for c in [x for x in items if x.get("status") == "available"]:
        mates = [o for o in live if o is not c and presented_days(o) and same_story(c, o)]
        sdays = set(presented_days(c))
        for o in mates:
            sdays.update(presented_days(o))
        if mates and len(sdays) >= PRESENT_MAX_DAYS and today not in sdays and _article_day(c) <= max(sdays):
            c.update(status=STATE_SHELVED, shelved_on=today, shelved_via="story",
                     shelved_reason=f"同一ストーリーが{len(sdays)}日提示済み（{'・'.join(x[5:] for x in sorted(sdays))}）")
            log.append(f"棚上げ（同一ストーリーの提示日数）: {c['id']} {c['title'][:50]}")
    # 3. 重複統合は available 全体で見る。残す1件と直接同じストーリー（same_story）の候補だけを寄せ、推移的にはつなげない
    avail = sorted([c for c in items if c.get("status") == "available"], key=_canonical_key, reverse=True)
    pairs = []      # (残す1件, 吸収する1件)
    left = list(avail)
    while left:
        h = left.pop(0)
        for o in [x for x in left if same_story(h, x)]:
            left.remove(o)
            pairs.append((h, o))
    for head, o in pairs:
        # 2026-11-10: 注目度の実測を補うときは、海外分の欄も同じ候補から一緒に写す（印だけ落ちて海外分のガードをすり抜けないように）。
        # head が自分の実測を持っているときは何も写さない（値が下がらない）
        if head.get("buzz_measured") in (None, "") and o.get("buzz_measured") not in (None, ""):
            for k in ("buzz_jp_measured", "buzz_outlets_foreign", "buzz_foreign_boost", "buzz_query_en"):
                if k in o:
                    head[k] = o[k]
                else:
                    head.pop(k, None)
        for k in MERGE_FILL_KEYS:     # 最良の1件に無い情報は、他の記事の値で補う
            if head.get(k) in (None, "") and o.get(k) not in (None, ""):
                head[k] = o[k]
        head["dup_ids"] = list(dict.fromkeys((head.get("dup_ids") or []) + [o["id"]] + (o.get("dup_ids") or [])))
        head["presented_on"] = sorted(set(presented_days(head)) | set(presented_days(o)))
        fo, fh = first_seen_dt(o), first_seen_dt(head)
        if fo and (not fh or fo < fh):
            head["first_seen_at"] = o.get("first_seen_at") or o.get("scored_at")
        o.update(status=STATE_MERGED, merged_into=head["id"], merged_reason="同一ストーリーの重複")
        log.append(f"重複統合: {o['id']} {o['title'][:46]} → 残す {head['id']} {head['title'][:30]}")
    print("\n".join(log) if log else "変更なし")
    print(f"\n棚上げ・統合: {len(log)}件" + ("（--dry-run: 保存しません）" if dry_run else ""))
    if log and not dry_run:
        _save_candidates(cands)


LANE_ORDER = {"本命": 0, L2_LANE: 1, "速報": 2, L2_WAIT_LANE: 3, "ニッチ": 4, "注目度低": 5, "未計測": 6}


def cmd_list_by_genre(per: int):
    """5ジャンルごとに、本命枠と同じゲート・同じ並び（core）で上位 per 件を出す。薄いときは薄いと表示する。"""
    g = json.loads(GENRES_JSON.read_text(encoding="utf-8"))
    rows = [r for r in classify(load_candidates()["items"]) if not r["gate"]]
    for key in g["order"]:
        mine = [r for r in rows if r["c"].get("genre") == key]
        mine = collapse_series(sorted(mine, key=lambda r: (-LANE_ORDER[r["lane"]], r["interest"], r["core"] if r["core"] is not None else -1, r["tb"],
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
    ap = argparse.ArgumentParser(description="ニュース起点のネタ選定（collect → score → verify → repair → tag → enrich → buzz → list）")
    ap.add_argument("command", choices=["collect", "score", "verify", "repair", "list", "tag", "enrich", "buzz", "check-urls", "slack", "yt", "dedupe", "prior-art"])
    ap.add_argument("--days", type=int, default=21)
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--by-genre", action="store_true", help="list: 5ジャンルごとに上位を出す（--top はジャンルあたりの件数）")
    ap.add_argument("--check-urls", action="store_true", help="list: ベスト3・本命枠の一次資料URLを確認してから出す（ソフト404も検出）")
    ap.add_argument("--max", type=int, default=None,
                    help=f"buzz: 1回で測る上限（既定・最大{GNEWS_MAX_PER_RUN}） / verify: 確かめる候補の上限（既定{VERIFY_DEFAULT_MAX}）"
                         f" / repair: 修復を試す候補の上限（既定{REPAIR_DEFAULT_MAX}）")
    ap.add_argument("--id", nargs="*", default=[],
                    help="buzz / check-urls / verify / repair / yt: 対象の候補ID（指定するとゲートに関係なく測る・確かめる）")
    ap.add_argument("--all", action="store_true", help="verify: 確認済みの候補も確かめ直す（既定は未確認だけ） / repair: ゲートに関係なく false の候補すべて")
    ap.add_argument("--count", type=int, default=None, help="yt: 日本語の解説動画の本数（手で数えた値）")
    ap.add_argument("--query", default="", help="yt: YouTube で検索した語（任意、記録用）")
    ap.add_argument("--force", action="store_true", help="enrich: 付与済みも付け直す / buzz: 最近測った候補も測り直す / repair: 7日以内に試した候補も試す")
    ap.add_argument("--remeasure-hours", type=float, default=24, help="buzz: これより最近に測った候補は飛ばす（既定24時間）")
    ap.add_argument("--dry-run", action="store_true", help="buzz: 測るが保存しない / score: 採点する候補を表示するだけ（課金なし）")
    ap.add_argument("--sources", type=Path, default=None, help="collect: news_sources.json の代わりに使う設定（試験用）")
    ap.add_argument("--no-gemini", action="store_true", help="collect: Gemini（話題の補完・分野の絞り込み）を呼ばない（試験用）")
    ap.add_argument("--no-record", action="store_true", help="slack: 提示した日（presented_on）を news_candidates.json に記録しない（試験用）")
    ap.add_argument("--confirm", default="", help="prior-art: 例外の確認。一次資料を読んで言い切れた「何が今回初めてか」の1行（--id と --by が必要）")
    ap.add_argument("--by", default="", help="prior-art --confirm: 確認者（例: kl-planner）")
    ap.add_argument("--note", default="", help="slack: ジャンルの間隔などを拾うテキスト（kl_concern_select.py の出力）")
    args = ap.parse_args()
    if args.command == "slack":
        cmd_slack(args.note, not args.no_record)
    elif args.command == "dedupe":
        cmd_dedupe(args.dry_run)
    elif args.command == "collect":
        cmd_collect(args.days, args.sources, args.no_gemini)
    elif args.command == "score":
        cmd_score(args.top, args.dry_run)
    elif args.command == "tag":
        cmd_tag()
    elif args.command == "enrich":
        cmd_enrich(args.force)
    elif args.command == "prior-art":
        cmd_prior_art(args.id, args.force, args.confirm, args.by)
    elif args.command == "buzz":
        cmd_buzz(args.max or GNEWS_MAX_PER_RUN, args.force, args.remeasure_hours, args.id, args.dry_run)
    elif args.command == "verify":
        cmd_verify(args.id, args.all, args.max or VERIFY_DEFAULT_MAX)
    elif args.command == "repair":
        cmd_repair(args.id, args.all, args.force, args.max or REPAIR_DEFAULT_MAX)
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
