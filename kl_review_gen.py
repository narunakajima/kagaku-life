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
DRIVE_BGM_DIR = (
    Path.home()
    / "Library/CloudStorage"
    / "GoogleDrive-naru.nakajima@gmail.com"
    / "マイドライブ"
    / "Kagaku-Life"
    / "BGM"
)

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

# シーンtype→BGM役割（CLAUDE.md「シーンタイプ体系とBGM3曲構成の対応」表と同じ）
TYPE_TO_BGM_ROLE = {
    "teaser": "intro", "hook": "intro", "context": "intro",
    "citation": "main", "finding": "main", "data": "main",
    "impact": "outro", "closing": "outro",
}


def _bgm_rel_path(bgm_sources: dict, role: str) -> str:
    """bgm_sources[role]（例: "BGM/kl005-BGM-intro.mp3"、Google Drive基準の
    相対パス）が指す実ファイルを ~/Desktop/kagaku-life/BGM/ にコピーし、
    review.htmlから images/narration と同じ相対パスで参照できるようにする。

    当初はGoogle Drive上のファイルをfile://の絶対パスで直接参照していたが、
    ブラウザ（Chrome等）はfile://で開いたページと異なるディレクトリツリー
    配下のローカルファイルへのアクセスをセキュリティ上ブロックするため、
    BGMが再生されない不具合が実際に発生した（2026-08-26、kl005で発覚）。
    画像・ナレーションは既にDesktop配下の相対パスで動いているため、BGMも
    同じ方式に合わせて解消した。ファイルが存在しない場合はNoneを返す
    （BGM未選定＝STEP10未実行のエピソードでもレビューページ自体は動くように）。
    """
    rel = bgm_sources.get(role)
    if not rel:
        return None
    filename = rel.split("/")[-1]
    src = DRIVE_BGM_DIR / filename
    if not src.exists():
        return None
    dst_dir = DESKTOP_DIR / "BGM"
    dst_dir.mkdir(exist_ok=True)
    dst = dst_dir / filename
    if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
        import shutil
        shutil.copyfile(src, dst)
    return f"BGM/{filename}"


def scene_card(kind: str, sid: int, type_label: str, narrator: str, narration: str,
               img_rel: str, audio_rel: str, extra: str = "", bgm_role: str = None,
               bgm_uri: str = None) -> str:
    bgm_html = ""
    if bgm_role and bgm_uri:
        bgm_html = f"""
          <div class="bgm-row">
            <span class="bgm-label">BGM:{html.escape(bgm_role)}</span>
            <button type="button" class="bgm-play" data-bgm-src="{html.escape(bgm_uri)}">▶ 再生</button>
          </div>
        """
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
          {bgm_html}
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

    bgm_sources = ep.get("bgm_sources", {})

    for scene in ep["scenes"]:
        sid = scene["scene_id"]
        bgm_role = TYPE_TO_BGM_ROLE.get(scene["type"])
        bgm_uri = _bgm_rel_path(bgm_sources, bgm_role) if bgm_role else None
        cards.append(scene_card(
            "本編", sid, TYPE_LABEL.get(scene["type"], scene["type"]), scene["narrator"],
            scene["narration"], f"images/S{sid:02d}.png", f"narration/S{sid:02d}.wav",
            bgm_role=bgm_role, bgm_uri=bgm_uri,
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
  img {{ width: 560px; max-width: 60vw; border-radius: 8px; flex-shrink: 0; }}
  .text-col {{ flex: 1; min-width: 0; }}
  .narration {{ font-size: 15px; line-height: 1.7; margin: 0 0 12px; }}
  .narration.sub {{ color: #9aa5b1; font-size: 13px; }}
  audio {{ width: 100%; }}
  .bgm-row {{ display: flex; gap: 8px; align-items: center; margin-top: 10px; }}
  .bgm-label {{ font-size: 12px; color: #9aa5b1; }}
  .bgm-play {{
    font-size: 13px; padding: 4px 10px; border-radius: 6px; border: 1px solid #3a4453;
    background: #2f3846; color: #eee; cursor: pointer;
  }}
  .bgm-play.playing {{ background: #2f5d8a; border-color: #2f5d8a; }}
  .bgm-play:hover {{ background: #3a4453; }}
  @media (max-width: 700px) {{
    .body {{ flex-direction: column; }}
    img {{ width: 100%; max-width: 100%; }}
  }}
</style>
</head>
<body>
<h1>{html.escape(ep.get('episode_title', args.episode))}（{html.escape(args.episode)}）— 画像+ナレーション確認</h1>
{''.join(cards)}
<audio id="bgm-player"></audio>
<script>
  // シーンごとのBGM再生ボタン（トグル式）。ページ全体で単一のaudio要素を
  // 共有し、別カードで再生を押すと自動的に切り替わる（同時に複数BGMが
  // 鳴らないように）。同じボタンをもう一度押すと停止する。
  const player = document.getElementById('bgm-player');
  const playButtons = document.querySelectorAll('.bgm-play');
  function clearPlayingState() {{
    playButtons.forEach(b => {{ b.classList.remove('playing'); b.textContent = '▶ 再生'; }});
  }}
  playButtons.forEach(btn => {{
    btn.addEventListener('click', () => {{
      const src = btn.getAttribute('data-bgm-src');
      if (btn.classList.contains('playing')) {{
        player.pause();
        clearPlayingState();
        return;
      }}
      clearPlayingState();
      player.src = src;
      player.currentTime = 0;
      player.play();
      btn.classList.add('playing');
      btn.textContent = '⏸ 停止';
    }});
  }});
  player.addEventListener('ended', clearPlayingState);
</script>
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
