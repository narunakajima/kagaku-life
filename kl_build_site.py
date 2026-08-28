"""
kl_build_site.py — 幸せな未来のサイエンス 公式サイト生成

生成ファイル:
  index.html      トップページ（近日公開 or 新着 + About + Subscribe）
  episodes.html   全動画一覧
  shorts.html     ショート動画一覧
  playlists.html  カテゴリ別再生リスト（6カテゴリ固定）

データソース:
  episodes/kl*.json    各エピソードの youtube_url / shorts_url / scheduled_at / タイトル等
  topics_queue.json    episode_id → category（6カテゴリのどれか）の対応
  category_playlists.json  カテゴリごとのYouTube再生リストID（未作成の間はnull）

「公開済み」の判定は youtube_url が設定済み、かつ scheduled_at が過去（JST）であること。
scheduled_at が未来（予約公開待ち）の場合は「近日公開」として扱い、タイトル等は出さない。

使い方:
  python3 kl_build_site.py

/kl-upload 後に手動 or 自動実行。
"""

import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent
EPISODES_DIR = BASE_DIR / "episodes"
TOPICS_QUEUE_JSON = BASE_DIR / "topics_queue.json"
CATEGORY_PLAYLISTS_JSON = BASE_DIR / "category_playlists.json"
CHANNEL_URL = "https://www.youtube.com/@kagaku-life"
SITE_URL = "https://kagaku-life.com"
CHANNEL_NAME = "幸せな未来のサイエンス"
TAGLINE = "科学が届ける、くらしの小さな幸せ"
UPDATE_CADENCE = "週3回更新（火・木・土 19:00）"

# サイト表示順（2026-08-28: 家庭内ロボットを先頭に変更。ラベルはCLAUDE.md STAGE1と同じ）
CATEGORY_ORDER = [
    "home_robot", "aging_care", "medical_support",
    "mobility", "work", "disaster_safety",
]
CATEGORY_LABELS = {
    "aging_care": "高齢化・介護・自立支援",
    "home_robot": "家庭内ロボット・家事自動化",
    "medical_support": "医療補助技術",
    "mobility": "モビリティ・身体拡張",
    "work": "働き方の変化",
    "disaster_safety": "防災・安全",
}
CATEGORY_ICONS = {
    "aging_care": "🤝",
    "home_robot": "🏠",
    "medical_support": "🩺",
    "mobility": "🦾",
    "work": "💼",
    "disaster_safety": "🚨",
}
WEEKDAY_JA = ["月", "火", "水", "木", "金", "土", "日"]

# ──────────────────────────────────────────────
# データ読み込み
# ──────────────────────────────────────────────

def parse_scheduled_at(s: str):
    """'YYYY-MM-DD HH:MM' (JST) を aware UTC datetime に変換。パース不能なら None。"""
    if not s:
        return None
    try:
        dt_jst = datetime.strptime(s[:16], "%Y-%m-%d %H:%M")
        return dt_jst.replace(tzinfo=timezone.utc) - timedelta(hours=9)
    except Exception:
        return None


def is_published(ep: dict) -> bool:
    """youtube_url があり、かつ scheduled_at が現在時刻より過去（JST基準）なら公開済み。
    scheduled_at が空なら即時公開扱い。youtube_url がなければ未公開（アップロード前）。"""
    if not ep.get("youtube_url"):
        return False
    s = ep.get("scheduled_at") or ""
    if not s:
        return True
    dt_utc = parse_scheduled_at(s)
    if dt_utc is None:
        return True
    return datetime.now(timezone.utc) >= dt_utc


def load_category_map() -> dict:
    """episode_id -> category(key) の対応。topics_queue.json の queue から作る。"""
    if not TOPICS_QUEUE_JSON.exists():
        return {}
    data = json.loads(TOPICS_QUEUE_JSON.read_text(encoding="utf-8"))
    m = {}
    for item in data.get("queue", []):
        eid = item.get("episode_id")
        cat = item.get("category")
        if eid and cat:
            m[eid] = cat
    return m


def load_episodes() -> list[dict]:
    cat_map = load_category_map()
    eps = []
    for p in sorted(EPISODES_DIR.glob("kl[0-9]*.json")):
        if p.stat().st_size == 0:
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not (d.get("youtube_title") or d.get("episode_title")):
            continue
        d["_category"] = cat_map.get(d.get("episode_id", ""))
        d["_published"] = is_published(d)
        eps.append(d)
    eps.reverse()  # 最新（kl番号が大きい順）
    return eps


def load_category_playlists() -> dict:
    if not CATEGORY_PLAYLISTS_JSON.exists():
        return {}
    data = json.loads(CATEGORY_PLAYLISTS_JSON.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def video_id(url: str) -> str:
    m = re.search(r"(?:youtu\.be/|v=)([A-Za-z0-9_-]{11})", url or "")
    return m.group(1) if m else ""


def next_launch_label(episodes: list[dict]) -> str:
    """未公開だがアップロード済み（scheduled_at待ち）の中で最も早い日時を日本語表記に。"""
    candidates = []
    for ep in episodes:
        if ep.get("_published") or not ep.get("youtube_url"):
            continue
        dt_utc = parse_scheduled_at(ep.get("scheduled_at") or "")
        if dt_utc:
            candidates.append(dt_utc)
    if not candidates:
        return "近日公開"
    dt_utc = min(candidates)
    dt_jst = dt_utc + timedelta(hours=9)
    wd = WEEKDAY_JA[dt_jst.weekday()]
    return f"{dt_jst.month}月{dt_jst.day}日({wd}) {dt_jst.hour:02d}:{dt_jst.minute:02d}"


# ──────────────────────────────────────────────
# 共通パーツ
# ──────────────────────────────────────────────

COMMON_CSS = """
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root {
      --navy: #0f2438; --navy-dark: #0a1826; --teal: #1f6f78; --teal-light: #2f8f96;
      --coral: #ff8a65; --coral-light: #ffab91; --coral-dim: #d97456;
      --ink: #0f2438; --paper: #faf7f2; --paper-dim: #ece5da;
      --white: #ffffff;
    }
    html { scroll-behavior: smooth; }
    body { background: var(--paper); color: var(--ink); font-family: 'Noto Sans JP', sans-serif; overflow-x: hidden; }

    /* ── reveal ── */
    .reveal { opacity: 0; transform: translateY(24px); transition: opacity .7s ease, transform .7s ease; }
    .reveal.visible { opacity: 1; transform: none; }
    .reveal-delay-1 { transition-delay: .1s; }
    .reveal-delay-2 { transition-delay: .2s; }
    .reveal-delay-3 { transition-delay: .3s; }
    .reveal-delay-4 { transition-delay: .4s; }

    /* ── NAV ── */
    .site-nav {
      position: sticky; top: 0; z-index: 100;
      background: rgba(15,36,56,.94); backdrop-filter: blur(8px);
      border-bottom: 1px solid rgba(255,138,101,.2);
      padding: 0 24px; height: 60px;
      display: flex; align-items: center; justify-content: space-between;
    }
    .nav-logo {
      display: flex; align-items: center; gap: 10px;
      font-family: 'Zen Maru Gothic', sans-serif; font-weight: 700; font-size: .85rem;
      letter-spacing: .04em; color: var(--white); text-decoration: none;
    }
    .nav-logo img { width: 30px; height: 30px; border-radius: 50%; display: block; }
    .nav-links { display: flex; gap: 22px; }
    .nav-link {
      font-family: 'Zen Maru Gothic', sans-serif; font-size: .78rem; letter-spacing: .04em;
      color: rgba(250,247,242,.65); text-decoration: none;
      transition: color .2s;
    }
    .nav-link:hover, .nav-link.active { color: var(--coral-light); }

    /* ── section base ── */
    section { padding: 80px 24px; }
    .section-inner { max-width: 920px; margin: 0 auto; }
    .section-label {
      font-family: 'Zen Maru Gothic', sans-serif; font-size: .72rem; letter-spacing: .18em;
      color: var(--teal-light); text-transform: uppercase; text-align: center; margin-bottom: 14px;
    }
    .section-heading {
      font-family: 'Zen Maru Gothic', sans-serif; font-weight: 700;
      font-size: clamp(1.3rem, 4.5vw, 1.9rem); text-align: center;
      letter-spacing: .02em; color: var(--navy); margin-bottom: 40px;
    }
    .coral-rule {
      width: 56px; height: 3px; border-radius: 2px;
      background: linear-gradient(to right, var(--coral), var(--teal-light));
      margin: 22px auto;
    }

    /* ── button ── */
    .btn-primary {
      display: inline-block; padding: 14px 32px;
      background: var(--coral); border: none;
      color: var(--white); font-family: 'Zen Maru Gothic', sans-serif; font-weight: 700;
      font-size: .88rem; letter-spacing: .04em; text-decoration: none;
      border-radius: 999px; transition: all .3s; box-shadow: 0 6px 24px rgba(255,138,101,.35);
    }
    .btn-primary:hover { background: var(--coral-dim); transform: translateY(-2px); box-shadow: 0 8px 30px rgba(255,138,101,.45); }
    .btn-outline {
      display: inline-block; padding: 12px 28px;
      border: 1.5px solid var(--teal); color: var(--teal);
      font-family: 'Zen Maru Gothic', sans-serif; font-weight: 700; font-size: .85rem; letter-spacing: .04em;
      text-decoration: none; border-radius: 999px; transition: all .3s;
    }
    .btn-outline:hover { background: rgba(31,111,120,.08); border-color: var(--teal-light); }

    /* ── stats strip ── */
    .stats-strip {
      background: var(--navy);
      padding: 30px 24px;
    }
    .stats-inner {
      max-width: 860px; margin: 0 auto;
      display: flex; justify-content: center; gap: clamp(28px,7vw,72px); flex-wrap: wrap;
    }
    .stat-item { text-align: center; }
    .stat-num {
      font-family: 'Zen Maru Gothic', sans-serif; font-weight: 700;
      font-size: clamp(1.5rem,4.5vw,2rem); color: var(--coral-light); line-height: 1;
    }
    .stat-label {
      font-family: 'Zen Maru Gothic', sans-serif; font-size: .68rem; letter-spacing: .1em;
      color: rgba(250,247,242,.7); margin-top: 8px;
    }

    /* ── card grid ── */
    .cards-grid {
      display: grid; grid-template-columns: repeat(auto-fill, minmax(240px,1fr)); gap: 22px;
    }
    .cards-grid.shorts-grid { grid-template-columns: repeat(auto-fill, minmax(170px,1fr)); }
    .content-card {
      display: block; text-decoration: none;
      background: var(--white); border: 1px solid var(--paper-dim);
      border-radius: 12px; overflow: hidden; transition: all .3s;
      box-shadow: 0 2px 10px rgba(15,36,56,.05);
    }
    .content-card:hover {
      border-color: var(--coral); transform: translateY(-4px);
      box-shadow: 0 14px 34px rgba(15,36,56,.14);
    }
    .card-thumb {
      width: 100%; aspect-ratio: 16/9; background: var(--navy);
      display: flex; align-items: center; justify-content: center;
      position: relative; overflow: hidden;
    }
    .shorts-grid .card-thumb { aspect-ratio: 9/16; }
    .card-thumb img {
      width: 100%; height: 100%; object-fit: cover; display: block;
      transition: transform .4s;
    }
    .content-card:hover .card-thumb img { transform: scale(1.05); }
    .card-thumb-icon { font-size: 2rem; opacity: .5; }
    .card-thumb::after {
      content: '▶'; position: absolute; font-size: 1.5rem;
      color: rgba(255,255,255,0); transition: color .3s, transform .3s;
      text-shadow: 0 2px 12px rgba(0,0,0,.6); pointer-events: none;
    }
    .content-card:hover .card-thumb::after { color: rgba(255,255,255,.92); transform: scale(1.12); }
    .card-info { padding: 14px 16px; }
    .card-eyebrow {
      font-family: 'Zen Maru Gothic', sans-serif; font-size: .62rem; letter-spacing: .1em;
      color: var(--coral-dim); margin-bottom: 6px; text-transform: uppercase;
    }
    .card-title { font-size: .88rem; color: var(--ink); line-height: 1.55; }

    /* ── category card ── */
    .category-card {
      display: block; text-decoration: none; position: relative;
      background: linear-gradient(150deg, var(--navy) 0%, var(--teal) 130%);
      border-radius: 14px; overflow: hidden; padding: 28px 22px;
      transition: all .3s; min-height: 170px;
    }
    .category-card:hover { transform: translateY(-4px); box-shadow: 0 14px 34px rgba(15,36,56,.22); }
    .category-card.is-locked { opacity: .55; cursor: default; }
    .category-icon { font-size: 1.8rem; margin-bottom: 14px; }
    .category-label {
      font-family: 'Zen Maru Gothic', sans-serif; font-weight: 700; font-size: 1rem;
      color: var(--white); line-height: 1.5; margin-bottom: 10px;
    }
    .category-count {
      font-family: 'Zen Maru Gothic', sans-serif; font-size: .68rem; letter-spacing: .08em;
      color: var(--coral-light);
    }

    /* ── coming soon ── */
    .coming-soon-box {
      text-align: center; padding: 56px 24px; border: 1.5px dashed var(--teal-light);
      border-radius: 16px; background: var(--white);
    }
    .coming-soon-badge {
      display: inline-block; padding: 8px 20px; border-radius: 999px;
      background: rgba(255,138,101,.12); color: var(--coral-dim);
      font-family: 'Zen Maru Gothic', sans-serif; font-weight: 700; font-size: .78rem;
      letter-spacing: .1em; margin-bottom: 18px;
    }
    .coming-soon-date {
      font-family: 'Zen Maru Gothic', sans-serif; font-weight: 700;
      font-size: clamp(1.3rem,5vw,1.8rem); color: var(--navy); margin-bottom: 10px;
    }
    .coming-soon-note { color: #5c6b78; font-size: .92rem; line-height: 1.8; max-width: 480px; margin: 0 auto 26px; }

    /* ── footer ── */
    footer {
      background: var(--navy-dark);
      padding: 44px 24px; text-align: center;
    }
    .footer-logo {
      display: flex; align-items: center; justify-content: center; gap: 10px;
      font-family: 'Zen Maru Gothic', sans-serif; font-weight: 700; font-size: 1rem;
      color: var(--white); margin-bottom: 18px;
    }
    .footer-logo img { width: 32px; height: 32px; border-radius: 50%; }
    .footer-links { display: flex; justify-content: center; gap: 22px; margin-bottom: 20px; flex-wrap: wrap; }
    .footer-link { color: rgba(250,247,242,.7); text-decoration: none; font-size: .85rem; transition: color .2s; }
    .footer-link:hover { color: var(--coral-light); }
    .footer-copy { font-family: 'Zen Maru Gothic', sans-serif; font-size: .68rem; letter-spacing: .06em; color: rgba(250,247,242,.4); }

    /* ── responsive ── */
    @media (max-width: 480px) {
      .cards-grid { grid-template-columns: 1fr 1fr; gap: 12px; }
      .cards-grid.shorts-grid { grid-template-columns: 1fr 1fr; }
      section { padding: 56px 18px; }
    }
    @media (max-width: 320px) { .cards-grid:not(.shorts-grid) { grid-template-columns: 1fr; } }
"""

COMMON_FONTS = """
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Zen+Maru+Gothic:wght@500;700&family=Noto+Sans+JP:wght@400;500;700&display=swap" rel="stylesheet">"""

REVEAL_JS = """
  <script>
    const obs = new IntersectionObserver(es => {
      es.forEach(e => { if (e.isIntersecting) { e.target.classList.add('visible'); obs.unobserve(e.target); } });
    }, { threshold: 0.08, rootMargin: '0px 0px -40px 0px' });
    document.querySelectorAll('.reveal').forEach(el => obs.observe(el));
  </script>"""


def nav_html(active: str) -> str:
    links = [("/", "top"), ("/episodes", "動画"), ("/shorts", "ショート"), ("/playlists", "プレイリスト")]
    items = ""
    for href, label in links:
        cls = ' class="nav-link active"' if label == active else ' class="nav-link"'
        items += f'<a{cls} href="{href}">{label}</a>'
    return f"""
  <nav class="site-nav">
    <a class="nav-logo" href="/"><img src="/LOGO.PNG" alt=""> {CHANNEL_NAME}</a>
    <div class="nav-links">{items}</div>
  </nav>"""


def footer_html() -> str:
    return f"""
  <footer>
    <p class="footer-logo"><img src="/LOGO.PNG" alt="">{CHANNEL_NAME}</p>
    <div class="footer-links">
      <a class="footer-link" href="{CHANNEL_URL}" target="_blank" rel="noopener">YouTube</a>
      <a class="footer-link" href="/episodes">動画一覧</a>
      <a class="footer-link" href="/shorts">ショート</a>
      <a class="footer-link" href="/playlists">プレイリスト</a>
    </div>
    <p class="footer-copy">&copy; 2026 {CHANNEL_NAME}. All rights reserved.</p>
  </footer>"""


def head_html(title: str, desc: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <meta name="description" content="{desc}">
  <meta property="og:title" content="{title}">
  <meta property="og:description" content="{desc}">
  <meta property="og:image" content="{SITE_URL}/LOGO.PNG">{COMMON_FONTS}
  <link rel="icon" href="/LOGO.PNG">
  <style>{COMMON_CSS}</style>
</head>
<body>"""


def coming_soon_html(launch_label: str, extra_note: str = "") -> str:
    note = extra_note or "収録は完了しています。公開まで今しばらくお待ちください。"
    return f"""
      <div class="coming-soon-box reveal">
        <span class="coming-soon-badge">近日公開</span>
        <p class="coming-soon-date">{launch_label} 〜</p>
        <p class="coming-soon-note">{note}</p>
        <a class="btn-primary" href="{CHANNEL_URL}" target="_blank" rel="noopener">チャンネル登録して待つ &rarr;</a>
      </div>"""


# ──────────────────────────────────────────────
# index.html — トップ
# ──────────────────────────────────────────────

def build_index(episodes: list[dict], published: list[dict], categories: list[dict]):
    ep_count = len(published)
    cat_count = len(CATEGORY_ORDER)
    launch_label = next_launch_label(episodes)

    if published:
        latest = published[0]
        ep_num = latest.get("episode_id", "").replace("kl", "").lstrip("0") or "?"
        ep_title = latest.get("youtube_title") or latest.get("episode_title", "")
        ep_url = latest.get("youtube_url") or CHANNEL_URL
        vid = video_id(ep_url)
        thumb = f'<img src="https://img.youtube.com/vi/{vid}/mqdefault.jpg" alt="{ep_title}" loading="lazy" style="width:100%;height:100%;object-fit:cover;">' if vid else '<span class="card-thumb-icon">▶</span>'

        recent_cards = ""
        for i, ep in enumerate(published[1:4]):
            n = ep.get("episode_id", "").replace("kl", "")
            u = ep.get("youtube_url") or CHANNEL_URL
            v = video_id(u)
            t = f'<img src="https://img.youtube.com/vi/{v}/mqdefault.jpg" alt="" loading="lazy">' if v else '<span class="card-thumb-icon">▶</span>'
            tl = ep.get("youtube_title") or ep.get("episode_title", "")
            delay = f" reveal-delay-{i+1}"
            recent_cards += f"""
        <a class="content-card reveal{delay}" href="{u}" target="_blank" rel="noopener">
          <div class="card-thumb">{t}</div>
          <div class="card-info">
            <p class="card-eyebrow">EPISODE {n}</p>
            <p class="card-title">{tl}</p>
          </div>
        </a>"""

        latest_section = f"""
      <div class="reveal reveal-delay-2" style="max-width:640px;margin:0 auto 40px;">
        <a href="{ep_url}" target="_blank" rel="noopener" style="display:block;border:1px solid var(--paper-dim);border-radius:12px;overflow:hidden;text-decoration:none;transition:all .3s;background:var(--white);box-shadow:0 2px 10px rgba(15,36,56,.05);">
          <div class="card-thumb" style="border-radius:0;">{thumb}</div>
          <div style="padding:20px 24px;">
            <p style="font-family:'Zen Maru Gothic',sans-serif;font-size:.62rem;letter-spacing:.1em;color:var(--coral-dim);margin-bottom:8px;">EPISODE {ep_num}</p>
            <p style="font-family:'Zen Maru Gothic',sans-serif;font-weight:700;font-size:clamp(1rem,3vw,1.2rem);color:var(--navy);line-height:1.6;">{ep_title}</p>
          </div>
        </a>
      </div>
      <div class="cards-grid" style="grid-template-columns:repeat(3,1fr);">{recent_cards}
      </div>
      <div class="reveal" style="display:flex;justify-content:center;gap:16px;flex-wrap:wrap;margin-top:40px;">
        <a class="btn-outline" href="/episodes">動画をすべて見る &rarr;</a>
        <a class="btn-outline" href="/playlists">プレイリストを見る &rarr;</a>
      </div>"""
        hero_sub_label = "Latest"
        hero_sub_heading = "New Episode"
    else:
        latest_section = coming_soon_html(launch_label, "第1弾は6エピソード同時公開予定です。公開までチャンネル登録してお待ちください。")
        hero_sub_label = "Coming Soon"
        hero_sub_heading = "配信準備中"

    stat_ep = str(ep_count) if ep_count else "近日"
    stat_ep_label = "公開動画" if ep_count else "公開予定"

    html = head_html(
        f"{CHANNEL_NAME} | AI・ロボティクス研究が変えるくらしの未来",
        f"最新のAI・ロボティクス論文が、10年後のくらしをどう変えるか——{CHANNEL_NAME}が分かりやすく解説します。"
    )
    html += nav_html("top")
    html += f"""

  <!-- ── HERO ── -->
  <section style="min-height:100svh;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:60px 24px 80px;background:radial-gradient(ellipse at 50% 0%,rgba(31,111,120,.25) 0%,transparent 65%),var(--paper);position:relative;">
    <div style="width:min(180px,45vw);height:min(180px,45vw);border-radius:50%;overflow:hidden;box-shadow:0 0 0 3px rgba(255,138,101,.35),0 0 0 6px rgba(31,111,120,.2),0 20px 60px rgba(15,36,56,.25);animation:fadeInDown 1s ease both;position:relative;z-index:1;">
      <img src="LOGO.PNG" alt="{CHANNEL_NAME}" style="width:100%;height:100%;object-fit:cover;display:block;">
    </div>
    <div style="margin-top:36px;animation:fadeInUp 1s .25s ease both;position:relative;z-index:1;">
      <h1 style="font-family:'Zen Maru Gothic',sans-serif;font-weight:700;font-size:clamp(1.5rem,5.5vw,2.3rem);color:var(--navy);letter-spacing:.02em;margin-bottom:14px;">{CHANNEL_NAME}</h1>
      <div class="coral-rule"></div>
      <p style="font-family:'Zen Maru Gothic',sans-serif;font-size:clamp(1rem,3.6vw,1.2rem);letter-spacing:.03em;color:var(--teal);line-height:1.8;">
        {TAGLINE}
      </p>
    </div>
    <div style="margin-top:32px;animation:fadeInUp 1s .45s ease both;display:flex;gap:16px;flex-wrap:wrap;justify-content:center;">
      <a class="btn-primary" href="{CHANNEL_URL}" target="_blank" rel="noopener">YouTubeで見る &rarr;</a>
      <a class="btn-outline" href="/episodes">動画一覧へ</a>
    </div>
  </section>

  <!-- ── STATS ── -->
  <div class="stats-strip reveal">
    <div class="stats-inner">
      <div class="stat-item"><p class="stat-num">{stat_ep}</p><p class="stat-label">{stat_ep_label}</p></div>
      <div class="stat-item"><p class="stat-num">{cat_count}</p><p class="stat-label">カテゴリ</p></div>
      <div class="stat-item"><p class="stat-num">週3回</p><p class="stat-label">火・木・土 19時更新</p></div>
    </div>
  </div>

  <!-- ── LATEST / COMING SOON ── -->
  <section style="background:var(--paper);">
    <div class="section-inner">
      <p class="section-label reveal">{hero_sub_label}</p>
      <h2 class="section-heading reveal reveal-delay-1">{hero_sub_heading}</h2>
      {latest_section}
    </div>
  </section>

  <!-- ── ABOUT ── -->
  <section style="background:var(--white);border-top:1px solid var(--paper-dim);border-bottom:1px solid var(--paper-dim);">
    <div class="section-inner">
      <p class="section-label reveal">About</p>
      <h2 class="section-heading reveal reveal-delay-1">論文が、10年後のくらしを変える</h2>
      <p class="reveal reveal-delay-2" style="text-align:center;font-size:clamp(1rem,3vw,1.1rem);line-height:2;color:#4a5866;max-width:600px;margin:0 auto 48px;">
        世界中のAI・ロボティクス研究から、暮らしを変えるかもしれない論文を選び、
        <strong style="color:var(--coral-dim);font-weight:700;">ひとりの生活者の物語</strong>
        として分かりやすく解説します。まだ研究段階の技術も、信頼できる情報として誠実に伝えます。
      </p>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:20px;max-width:720px;margin:0 auto;">
        <div class="reveal reveal-delay-1" style="text-align:center;padding:26px 16px;border:1px solid var(--paper-dim);border-radius:12px;background:var(--paper);">
          <div style="font-size:1.8rem;margin-bottom:12px;">📄</div>
          <p style="font-family:'Zen Maru Gothic',sans-serif;font-weight:700;font-size:.82rem;color:var(--teal);">確かな出典</p>
          <p style="font-size:.85rem;color:#5c6b78;line-height:1.7;margin-top:8px;">大学・研究機関の実際の論文にもとづく解説</p>
        </div>
        <div class="reveal reveal-delay-2" style="text-align:center;padding:26px 16px;border:1px solid var(--paper-dim);border-radius:12px;background:var(--paper);">
          <div style="font-size:1.8rem;margin-bottom:12px;">🏡</div>
          <p style="font-family:'Zen Maru Gothic',sans-serif;font-weight:700;font-size:.82rem;color:var(--teal);">くらしの物語</p>
          <p style="font-size:.85rem;color:#5c6b78;line-height:1.7;margin-top:8px;">ひとりの生活者の日常を通して、技術の意味を伝える</p>
        </div>
        <div class="reveal reveal-delay-3" style="text-align:center;padding:26px 16px;border:1px solid var(--paper-dim);border-radius:12px;background:var(--paper);">
          <div style="font-size:1.8rem;margin-bottom:12px;">✨</div>
          <p style="font-family:'Zen Maru Gothic',sans-serif;font-weight:700;font-size:.82rem;color:var(--teal);">小さな幸せ</p>
          <p style="font-size:.85rem;color:#5c6b78;line-height:1.7;margin-top:8px;">科学がもたらす、日々のささやかな喜びに光を当てる</p>
        </div>
      </div>
    </div>
  </section>

  <!-- ── SUBSCRIBE ── -->
  <section style="background:var(--paper);">
    <div class="section-inner" style="text-align:center;">
      <p class="section-label reveal">Subscribe</p>
      <h2 class="section-heading reveal reveal-delay-1">見逃さないために</h2>
      <p class="reveal reveal-delay-2" style="color:#4a5866;line-height:1.9;margin-bottom:32px;">{UPDATE_CADENCE}。チャンネル登録して新着をお見逃しなく。</p>
      <div class="reveal reveal-delay-3">
        <a class="btn-primary" href="{CHANNEL_URL}" target="_blank" rel="noopener">
          YouTubeでチャンネル登録 &rarr;
        </a>
      </div>
    </div>
  </section>

  <style>
    @keyframes fadeInDown {{ from {{ opacity:0;transform:translateY(-24px); }} to {{ opacity:1;transform:none; }} }}
    @keyframes fadeInUp {{ from {{ opacity:0;transform:translateY(24px); }} to {{ opacity:1;transform:none; }} }}
  </style>
"""
    html += footer_html()
    html += REVEAL_JS
    html += "\n</body>\n</html>"
    (BASE_DIR / "index.html").write_text(html, encoding="utf-8")
    print("  ✓ index.html")


# ──────────────────────────────────────────────
# episodes.html — 全動画一覧
# ──────────────────────────────────────────────

def build_episodes(episodes: list[dict], published: list[dict]):
    launch_label = next_launch_label(episodes)
    if published:
        cards = ""
        for i, ep in enumerate(published):
            num = ep.get("episode_id", "").replace("kl", "")
            url = ep.get("youtube_url") or CHANNEL_URL
            vid = video_id(url)
            thumb = f'<img src="https://img.youtube.com/vi/{vid}/mqdefault.jpg" alt="" loading="lazy">' if vid else '<span class="card-thumb-icon">▶</span>'
            title = ep.get("youtube_title") or ep.get("episode_title", "")
            cat = ep.get("_category")
            cat_label = CATEGORY_LABELS.get(cat, "")
            delay = f" reveal-delay-{(i % 4) + 1}" if (i % 4) != 0 else ""
            cards += f"""
        <a class="content-card reveal{delay}" href="{url}" target="_blank" rel="noopener">
          <div class="card-thumb">{thumb}</div>
          <div class="card-info">
            <p class="card-eyebrow">EPISODE {num}{' · ' + cat_label if cat_label else ''}</p>
            <p class="card-title">{title}</p>
          </div>
        </a>"""
        body = f'<div class="cards-grid">{cards}\n      </div>'
    else:
        body = coming_soon_html(launch_label)

    html = head_html(
        f"動画一覧 | {CHANNEL_NAME}",
        f"{CHANNEL_NAME}の全エピソード一覧。AI・ロボティクス研究が変えるくらしの未来を、生活者の物語として解説します。"
    )
    html += nav_html("動画")
    html += f"""

  <section style="padding-top:60px;">
    <div class="section-inner">
      <p class="section-label reveal">All Episodes</p>
      <h1 class="section-heading reveal reveal-delay-1" style="font-size:clamp(1.3rem,4.5vw,1.9rem);">すべてのエピソード</h1>
      {body}
    </div>
  </section>
"""
    html += footer_html()
    html += REVEAL_JS
    html += "\n</body>\n</html>"
    (BASE_DIR / "episodes.html").write_text(html, encoding="utf-8")
    print(f"  ✓ episodes.html（公開{len(published)}件 / 全{len(episodes)}件）")


# ──────────────────────────────────────────────
# shorts.html — ショート動画一覧
# ──────────────────────────────────────────────

def build_shorts(episodes: list[dict], published: list[dict]):
    launch_label = next_launch_label(episodes)
    pub_with_shorts = [ep for ep in published if ep.get("shorts_url")]
    if pub_with_shorts:
        cards = ""
        for i, ep in enumerate(pub_with_shorts):
            num = ep.get("episode_id", "").replace("kl", "")
            url = ep.get("shorts_url")
            vid = video_id(url)
            thumb = f'<img src="https://img.youtube.com/vi/{vid}/mqdefault.jpg" alt="" loading="lazy">' if vid else '<span class="card-thumb-icon">▶</span>'
            title = ep.get("youtube_title") or ep.get("episode_title", "")
            delay = f" reveal-delay-{(i % 4) + 1}" if (i % 4) != 0 else ""
            cards += f"""
        <a class="content-card reveal{delay}" href="{url}" target="_blank" rel="noopener">
          <div class="card-thumb">{thumb}</div>
          <div class="card-info">
            <p class="card-eyebrow">EPISODE {num}</p>
            <p class="card-title">{title}</p>
          </div>
        </a>"""
        body = f'<div class="cards-grid shorts-grid">{cards}\n      </div>'
    else:
        body = coming_soon_html(launch_label)

    html = head_html(
        f"ショート | {CHANNEL_NAME}",
        f"{CHANNEL_NAME}のショート動画一覧。1分でわかる、くらしを変える科学の話。"
    )
    html += nav_html("ショート")
    html += f"""

  <section style="padding-top:60px;">
    <div class="section-inner">
      <p class="section-label reveal">Shorts</p>
      <h1 class="section-heading reveal reveal-delay-1" style="font-size:clamp(1.3rem,4.5vw,1.9rem);">ショート動画</h1>
      {body}
    </div>
  </section>
"""
    html += footer_html()
    html += REVEAL_JS
    html += "\n</body>\n</html>"
    (BASE_DIR / "shorts.html").write_text(html, encoding="utf-8")
    print(f"  ✓ shorts.html（公開{len(pub_with_shorts)}件）")


# ──────────────────────────────────────────────
# playlists.html — カテゴリ別再生リスト（6カテゴリ固定）
# ──────────────────────────────────────────────

def build_playlists(published: list[dict], category_playlists: dict):
    by_cat = {}
    for ep in published:
        cat = ep.get("_category")
        if cat:
            by_cat.setdefault(cat, []).append(ep)

    cards = ""
    for i, cat in enumerate(CATEGORY_ORDER):
        label = CATEGORY_LABELS[cat]
        icon = CATEGORY_ICONS.get(cat, "🔬")
        eps = by_cat.get(cat, [])
        pl_info = category_playlists.get(cat, {})
        pl_id = pl_info.get("playlist_id")
        delay = f" reveal-delay-{(i % 3) + 1}" if (i % 3) != 0 else ""

        if pl_id:
            href = f"https://www.youtube.com/playlist?list={pl_id}"
            locked_cls = ""
            count_label = f"{len(eps)}本の動画"
        elif eps:
            href = eps[0].get("youtube_url") or CHANNEL_URL
            locked_cls = ""
            count_label = f"{len(eps)}本の動画"
        else:
            href = CHANNEL_URL
            locked_cls = " is-locked"
            count_label = "近日公開"

        cards += f"""
        <a class="category-card reveal{delay}{locked_cls}" href="{href}" target="_blank" rel="noopener">
          <div class="category-icon">{icon}</div>
          <p class="category-label">{label}</p>
          <p class="category-count">{count_label}</p>
        </a>"""

    html = head_html(
        f"プレイリスト | {CHANNEL_NAME}",
        f"{CHANNEL_NAME}をカテゴリ別に見る——高齢化・介護、家庭内ロボット、医療補助技術、モビリティ、働き方、防災・安全の6カテゴリ。"
    )
    html += nav_html("プレイリスト")
    html += f"""

  <section style="padding-top:60px;">
    <div class="section-inner">
      <p class="section-label reveal">By Category</p>
      <h1 class="section-heading reveal reveal-delay-1" style="font-size:clamp(1.3rem,4.5vw,1.9rem);">カテゴリで選ぶ</h1>
      <p class="reveal reveal-delay-2" style="text-align:center;color:#4a5866;line-height:1.9;margin-bottom:48px;max-width:520px;margin-left:auto;margin-right:auto;">
        気になるテーマから、くらしを変える研究をまとめて見られます。
      </p>
      <div class="cards-grid" style="grid-template-columns:repeat(auto-fill,minmax(220px,1fr));">{cards}
      </div>
    </div>
  </section>
"""
    html += footer_html()
    html += REVEAL_JS
    html += "\n</body>\n</html>"
    (BASE_DIR / "playlists.html").write_text(html, encoding="utf-8")
    print(f"  ✓ playlists.html（{len(CATEGORY_ORDER)}カテゴリ）")


# ──────────────────────────────────────────────
# エントリポイント
# ──────────────────────────────────────────────

def build():
    episodes = load_episodes()
    if not episodes:
        print("❌ エピソードが見つかりませんでした")
        sys.exit(1)
    published = [ep for ep in episodes if ep.get("_published")]
    category_playlists = load_category_playlists()

    print(f"  エピソード: 全{len(episodes)}件 / 公開済み{len(published)}件")
    build_index(episodes, published, CATEGORY_ORDER)
    build_episodes(episodes, published)
    build_shorts(episodes, published)
    build_playlists(published, category_playlists)
    print("  ✓ サイト生成完了")


if __name__ == "__main__":
    build()
