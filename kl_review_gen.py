"""
kl_review_gen.py — くらしを変える科学 画像+ナレーション確認ページ生成スクリプト

episodes/kl{NNN}.json をもとに、各シーンの静止画・ナレーション文・音声を
1画面で並べたローカルHTMLを生成する。画像とナレーションを別々のフォルダで
見比べるのは判断しづらいという指摘（2026-08-25）を受けて追加した。

出力はDesktop側の画像・音声への相対パス参照（images/S01.png等）のため、
`~/Desktop/kagaku-life/` 直下に置いてブラウザで開く必要がある（file://でも
img/audioタグの相対パス読み込みは問題なく動作する）。

使い方:
  python3 kl_review_gen.py --episode kl001

出力先: ~/Desktop/kagaku-life/review.html
       （Desktopは常に最新1エピソード分の確認用のため、ファイル名は固定）
"""

import argparse
import html
import json
import sys
import webbrowser
from pathlib import Path

BASE_DIR = Path(__file__).parent
DESKTOP_DIR = Path.home() / "Desktop" / "kagaku-life"

TYPE_LABEL = {
    "teaser": "ティザー",
    "hook": "自己紹介",
    "citation": "出典明示",
    "context": "課題",
    "finding": "研究紹介",
    "data": "データ",
    "impact": "未来の暮らし",
    "closing": "締め",
}
NARRATOR_LABEL = {"persona": "生活者ボイス", "research": "研究ボイス"}


def scene_card(kind: str, sid: int, type_label: str, narrator: str, narration: str,
               img_rel: str, audio_rel: str, extra: str = "") -> str:
    return f"""
    <section class="card">
      <div class="meta">
        <span class="badge badge-{kind}">{html.escape(kind)}</span>
        <span class="sid">S{sid:02d}</span>
        <span class="type">{html.escape(type_label)}</span>
        <span class="narrator">{html.escape(NARRATOR_LABEL.get(narrator, narrator))}</span>
        {extra}
      </div>
      <div class="body">
        <img src="{html.escape(img_rel)}" loading="lazy" alt="S{sid:02d}">
        <div class="text-col">
          <p class="narration">{html.escape(narration)}</p>
          <audio controls preload="none" src="{html.escape(audio_rel)}"></audio>
        </div>
      </div>
    </section>
    """


def main():
    parser = argparse.ArgumentParser(description="くらしを変える科学 画像+ナレーション確認ページ生成")
    parser.add_argument("--episode", required=True, help="エピソードID（例: kl001）")
    parser.add_argument("--no-open", action="store_true", help="生成後にブラウザで自動オープンしない")
    args = parser.parse_args()

    ep_path = BASE_DIR / "episodes" / f"{args.episode}.json"
    if not ep_path.exists():
        print(f"❌ {ep_path} がありません", file=sys.stderr)
        sys.exit(1)
    ep = json.loads(ep_path.read_text())

    cards = []

    thumb_path = DESKTOP_DIR / "images" / "thumbnail.png"
    if thumb_path.exists():
        cards.append(f"""
        <section class="card thumb-card">
          <div class="meta"><span class="badge badge-thumb">サムネイル</span></div>
          <div class="body">
            <img src="images/thumbnail.png" alt="thumbnail">
            <div class="text-col">
              <p class="narration">{html.escape(ep.get('thumbnail_headline', ''))}</p>
              <p class="narration sub">{html.escape(ep.get('thumbnail_subcopy', ''))}</p>
            </div>
          </div>
        </section>
        """)

    for scene in ep["scenes"]:
        sid = scene["scene_id"]
        cards.append(scene_card(
            "本編", sid, TYPE_LABEL.get(scene["type"], scene["type"]), scene["narrator"],
            scene["narration"], f"images/S{sid:02d}.png", f"narration/S{sid:02d}.wav",
        ))

    for shorts in ep.get("shorts", []):
        mid = shorts["shorts_id"]
        for i, s in enumerate(shorts["scenes"], start=1):
            cards.append(scene_card(
                f"Shorts{mid}", i, s.get("style", "story"), s["narrator"], s["narration"],
                f"images/shorts{mid}_S{i:02d}.png", f"narration/shorts{mid}_S{i:02d}.wav",
            ))

    html_doc = f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>{html.escape(ep.get('episode_title', args.episode))} — 確認ページ</title>
<style>
  body {{ font-family: -apple-system, "Hiragino Kaku Gothic ProN", sans-serif; background: #1a1f27; color: #eee; margin: 0; padding: 24px; }}
  h1 {{ font-size: 18px; font-weight: 600; margin: 0 0 20px; color: #fff; }}
  .card {{ background: #232a35; border-radius: 12px; padding: 16px; margin-bottom: 16px; }}
  .meta {{ display: flex; gap: 8px; align-items: center; margin-bottom: 10px; font-size: 13px; color: #9aa5b1; }}
  .badge {{ padding: 2px 8px; border-radius: 6px; font-size: 12px; font-weight: 600; }}
  .badge-本編 {{ background: #2f5d8a; color: #fff; }}
  .badge-thumb {{ background: #a86b1f; color: #fff; }}
  .badge-Shorts1 {{ background: #5d2f8a; color: #fff; }}
  .sid {{ font-weight: 700; color: #fff; }}
  .body {{ display: flex; gap: 16px; align-items: flex-start; }}
  img {{ width: 320px; max-width: 40vw; border-radius: 8px; flex-shrink: 0; }}
  .text-col {{ flex: 1; min-width: 0; }}
  .narration {{ font-size: 15px; line-height: 1.7; margin: 0 0 12px; }}
  .narration.sub {{ color: #9aa5b1; font-size: 13px; }}
  audio {{ width: 100%; }}
  @media (max-width: 700px) {{
    .body {{ flex-direction: column; }}
    img {{ width: 100%; max-width: 100%; }}
  }}
</style>
</head>
<body>
<h1>{html.escape(ep.get('episode_title', args.episode))}（{html.escape(args.episode)}）— 画像+ナレーション確認</h1>
{''.join(cards)}
</body>
</html>
"""

    out_path = DESKTOP_DIR / "review.html"
    out_path.write_text(html_doc, encoding="utf-8")
    print(f"✅ 確認ページを生成しました: {out_path}")

    if not args.no_open:
        webbrowser.open(f"file://{out_path}")


if __name__ == "__main__":
    main()
