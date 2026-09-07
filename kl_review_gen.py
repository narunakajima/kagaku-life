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


def _play_button(src: str, label: str, button_text: str) -> str:
    return (
        f'<button type="button" class="media-play" '
        f'data-src="{html.escape(src)}" data-label="{html.escape(label)}">'
        f'{html.escape(button_text)}</button>'
    )


def regen_controls(card_id: str, allow_narration: bool = True) -> str:
    """画像/ナレーションの再生成チェックボックス+理由欄。ページ下部の
    コピー ボタンを押すとチェック済み項目だけをクリップボードにコピーし、
    Claudeのデスクトップアプリに貼り付けて再生成を依頼する運用
    （サーバーを立てずに済ませるための設計、2026-09-07）。"""
    narration_checkbox = (
        '<label><input type="checkbox" class="regen-narration"> ナレーションを再生成</label>'
        if allow_narration else ""
    )
    return f"""
        <div class="regen-controls">
          <label><input type="checkbox" class="regen-image"> 画像を再生成</label>
          {narration_checkbox}
          <input type="text" class="regen-reason" placeholder="理由（例: 時間帯が夜になっている）">
        </div>
    """


def shorts_tile(label: str, sid_label: str, narration: str, img_rel: str,
                 audio_rel: str = None, card_id: str = None) -> str:
    """Shorts用の横並びタイル（顔アップフック含めて全て同じ幅・同じ見た目に
    揃える。samurai-chroniclesのsc_scene_review.py `.shorts-tile` と統一、
    2026-09-06〜）。audio_relが無い場合（顔アップフックは無音カットのため）は
    再生ボタンを出さない（ナレーション再生成チェックボックスも同様に省く）。"""
    play_row = ""
    if audio_rel:
        play_row = (
            '<div class="play-row">'
            + _play_button(audio_rel, f"{sid_label} ナレーション", "▶ 再生")
            + "</div>"
        )
    return f"""
    <div class="shorts-tile" data-card-id="{html.escape(card_id or sid_label)}">
      <img src="{html.escape(img_rel)}" loading="lazy" alt="{html.escape(sid_label)}">
      <div class="shorts-tile-label">{html.escape(label)} {html.escape(sid_label)}</div>
      <p class="shorts-tile-narration">{html.escape(narration)}</p>
      {play_row}
      {regen_controls(card_id or sid_label, allow_narration=bool(audio_rel))}
    </div>
    """


def scene_card(kind: str, sid: int, type_label: str, narrator: str, narration: str,
               img_rel: str, audio_rel: str, extra: str = "", bgm_role: str = None,
               bgm_uri: str = None, layout: str = "main", card_id: str = None) -> str:
    sid_label = f"S{sid:02d}"
    buttons = [_play_button(audio_rel, f"{sid_label} ナレーション", "▶ ナレーション再生")]
    if bgm_role and bgm_uri:
        buttons.append(_play_button(bgm_uri, f"BGM:{bgm_role}", f"▶ BGM:{bgm_role} 再生"))
    play_row = f'<div class="play-row">{"".join(buttons)}</div>'
    return f"""
    <section class="card layout-{layout}" data-card-id="{html.escape(card_id or sid_label)}">
      <div class="meta">
        <span class="badge badge-{kind}">{html.escape(kind)}</span>
        <span class="sid">{sid_label}</span>
        <span class="type">{html.escape(type_label)}</span>
        <span class="narrator">{html.escape(NARRATOR_LABEL.get(narrator, narrator))}</span>
        {extra}
      </div>
      <div class="body">
        <img src="{html.escape(img_rel)}" loading="lazy" alt="{sid_label}">
        <div class="text-col">
          <p class="narration">{html.escape(narration)}</p>
          {play_row}
          {regen_controls(card_id or sid_label)}
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
        <section class="card thumb-card layout-thumb" data-card-id="サムネイル">
          <div class="meta"><span class="badge badge-thumb">サムネイル</span></div>
          <div class="body">
            <img src="images/thumbnail.png" alt="thumbnail">
            <div class="text-col">
              <p class="narration">{html.escape(ep.get('thumbnail_headline', ''))}</p>
              <p class="narration sub">{html.escape(ep.get('thumbnail_subcopy', ''))}</p>
              {regen_controls("サムネイル", allow_narration=False)}
            </div>
          </div>
        </section>
        """)

    bgm_sources = ep.get("bgm_sources", {})

    # 表示順: サムネイル → Shorts（顔アップフック含む、横並びタイル） → 本編
    # （samurai-chroniclesのsc_scene_review.pyの.shorts-strip/.shorts-tileと
    # 統一、2026-09-06改訂: 縦積みカードから横並び同サイズタイルに変更）
    hook_lines = ep.get("hook_lines", [])
    for shorts in ep.get("shorts", []):
        mid = shorts["shorts_id"]
        tiles = []

        face_path = DESKTOP_DIR / "images" / f"shorts{mid}_S00_face.png"
        if shorts.get("face_hook_image_prompt") and face_path.exists():
            tiles.append(shorts_tile(
                f"Shorts{mid}", "S00（顔アップ）", " / ".join(hook_lines),
                f"images/shorts{mid}_S00_face.png",
                card_id=f"Shorts{mid} S00",
            ))

        for i, s in enumerate(shorts["scenes"], start=1):
            tiles.append(shorts_tile(
                f"Shorts{mid}", f"S{i:02d}", s["narration"],
                f"images/shorts{mid}_S{i:02d}.png",
                f"narration/shorts{mid}_S{i:02d}.wav",
                card_id=f"Shorts{mid} S{i:02d}",
            ))

        cards.append(f'<div class="shorts-strip">{"".join(tiles)}</div>')

    for scene in ep["scenes"]:
        sid = scene["scene_id"]
        bgm_role = TYPE_TO_BGM_ROLE.get(scene["type"])
        bgm_uri = _bgm_rel_path(bgm_sources, bgm_role) if bgm_role else None
        cards.append(scene_card(
            "本編", sid, TYPE_LABEL.get(scene["type"], scene["type"]), scene["narrator"],
            scene["narration"], f"images/S{sid:02d}.png", f"narration/S{sid:02d}.wav",
            bgm_role=bgm_role, bgm_uri=bgm_uri, layout="main", card_id=f"本編 S{sid:02d}",
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
  img {{ border-radius: 8px; flex-shrink: 0; display: block; }}
  .text-col {{ flex: 1; min-width: 0; }}
  /* サイズ・並び順はsamurai-chroniclesのsc_scene_review.pyと統一（2026-09-04〜） */
  .layout-main .body, .layout-thumb .body {{ flex-direction: column; }}
  .layout-main img, .layout-thumb img {{ width: 100%; max-width: 640px; }}
  /* Shorts横並びタイル（顔アップフック含め全て同じ幅、3列で折り返す。
     samurai-chroniclesの.shorts-strip/.shorts-tileと統一、2026-09-06〜） */
  .shorts-strip {{ display: flex; flex-wrap: wrap; gap: 14px; margin-bottom: 16px; }}
  .shorts-tile {{ flex: 0 0 calc((100% - 28px) / 3); background: #232a35; border-radius: 12px; padding: 12px; box-sizing: border-box; }}
  .shorts-tile img {{ width: 100%; border-radius: 8px; display: block; margin-bottom: 8px; }}
  .shorts-tile-label {{ font-size: 12px; font-weight: 600; color: #8ab4f8; margin-bottom: 4px; }}
  .shorts-tile-narration {{ font-size: 12px; color: #ccc; line-height: 1.5; margin: 0 0 8px; }}
  @media (max-width: 900px) {{
    .shorts-tile {{ flex: 0 0 calc((100% - 14px) / 2); }}
  }}
  @media (max-width: 560px) {{
    .shorts-tile {{ flex: 0 0 100%; }}
  }}
  .narration {{ font-size: 15px; line-height: 1.7; margin: 0 0 12px; }}
  .narration.sub {{ color: #9aa5b1; font-size: 13px; }}
  .play-row {{ display: flex; gap: 8px; align-items: center; margin-top: 10px; flex-wrap: wrap; }}
  .media-play {{
    font-size: 13px; padding: 4px 10px; border-radius: 6px; border: 1px solid #3a4453;
    background: #2f3846; color: #eee; cursor: pointer;
  }}
  .media-play.playing {{ background: #2f5d8a; border-color: #2f5d8a; }}
  .media-play:hover {{ background: #3a4453; }}
  @media (max-width: 700px) {{
    .body {{ flex-direction: column; }}
    img {{ width: 100%; max-width: 100%; }}
  }}
  body {{ padding-bottom: 84px; }}
  #media-player-bar {{
    position: fixed; left: 0; right: 0; bottom: 0; z-index: 10;
    display: flex; align-items: center; gap: 12px;
    background: #11151b; border-top: 1px solid #3a4453;
    padding: 10px 16px;
  }}
  #media-player-label {{ font-size: 12px; color: #9aa5b1; white-space: nowrap; flex-shrink: 0; }}
  #media-player {{ flex: 1; width: 100%; }}
  .regen-controls {{
    display: flex; gap: 12px; align-items: center; flex-wrap: wrap;
    margin-top: 10px; padding-top: 10px; border-top: 1px dashed #3a4453;
    font-size: 13px; color: #cdd5df;
  }}
  .shorts-tile .regen-controls {{ font-size: 11px; gap: 8px; }}
  .regen-controls label {{ display: flex; gap: 5px; align-items: center; cursor: pointer; white-space: nowrap; }}
  .regen-reason {{
    flex: 1; min-width: 120px; background: #1a1f27; border: 1px solid #3a4453;
    border-radius: 6px; color: #eee; font-size: 13px; padding: 5px 8px;
  }}
  #regen-panel {{
    position: fixed; right: 20px; bottom: 76px; z-index: 11;
    display: flex; flex-direction: column; align-items: flex-end; gap: 6px;
  }}
  #regen-copy-btn {{
    font-size: 14px; font-weight: 600; padding: 10px 18px; border-radius: 8px;
    border: none; background: #a86b1f; color: #fff; cursor: pointer;
    box-shadow: 0 2px 8px rgba(0,0,0,0.4);
  }}
  #regen-copy-btn:hover {{ background: #c17c22; }}
  #regen-status {{ font-size: 12px; color: #cdd5df; background: #11151b; padding: 4px 10px; border-radius: 6px; }}
</style>
</head>
<body>
<h1>{html.escape(ep.get('episode_title', args.episode))}（{html.escape(args.episode)}）— 画像+ナレーション確認</h1>
{''.join(cards)}
<div id="regen-panel">
  <span id="regen-status" hidden></span>
  <button type="button" id="regen-copy-btn">📋 再生成リクエストをコピー</button>
</div>
<div id="media-player-bar">
  <span id="media-player-label">未選択</span>
  <audio id="media-player" controls preload="none"></audio>
</div>
<script>
  // ナレーション・BGMどちらの再生ボタンも、ページ下部に固定した単一のaudio
  // 要素（ネイティブcontrols＝シークバー付き）を共有する（トグル式）。
  // 別のボタンで再生を押すと自動的に切り替わる（同時に複数音源が鳴らない
  // ように）。シークバーで任意の位置に早送り・巻き戻しできる。同じボタンを
  // もう一度押すと停止する。ナレーションとBGMを別々のバーにしても操作感は
  // 同じなので、1つのバーに統合した（2026-08-27）。
  const player = document.getElementById('media-player');
  const playerLabel = document.getElementById('media-player-label');
  const playButtons = document.querySelectorAll('.media-play');
  function clearPlayingState() {{
    playButtons.forEach(b => {{ b.classList.remove('playing'); b.textContent = b.dataset.idleText; }});
  }}
  playButtons.forEach(btn => {{
    btn.dataset.idleText = btn.textContent;
    btn.addEventListener('click', () => {{
      const src = btn.getAttribute('data-src');
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
      playerLabel.textContent = btn.getAttribute('data-label') || '';
    }});
  }});
  player.addEventListener('ended', clearPlayingState);

  // 再生成リクエストの収集・コピー。チェックした画像/ナレーションと理由を
  // まとめてクリップボードに書き込み、Claudeのデスクトップアプリ側チャットに
  // 貼り付けてもらう運用（サーバーを立てずに済ませるための設計、2026-09-07）。
  const regenStatus = document.getElementById('regen-status');
  function showRegenStatus(text) {{
    regenStatus.textContent = text;
    regenStatus.hidden = false;
  }}
  function copyText(text) {{
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    document.body.appendChild(ta);
    ta.select();
    let ok = false;
    try {{
      ok = document.execCommand('copy');
    }} catch (e) {{
      ok = false;
    }}
    document.body.removeChild(ta);
    return ok;
  }}
  document.getElementById('regen-copy-btn').addEventListener('click', () => {{
    const lines = [];
    document.querySelectorAll('[data-card-id]').forEach(card => {{
      const imgBox = card.querySelector('.regen-image');
      const narBox = card.querySelector('.regen-narration');
      const imgChecked = imgBox && imgBox.checked;
      const narChecked = narBox && narBox.checked;
      if (!imgChecked && !narChecked) return;
      const targets = [];
      if (imgChecked) targets.push('画像');
      if (narChecked) targets.push('ナレーション');
      const reasonBox = card.querySelector('.regen-reason');
      const reason = (reasonBox && reasonBox.value.trim()) || '(未記入)';
      lines.push(`- ${{card.dataset.cardId}}: ${{targets.join('・')}}再生成 / 理由: ${{reason}}`);
    }});
    if (lines.length === 0) {{
      showRegenStatus('チェックされた項目がありません');
      return;
    }}
    const text = `【{html.escape(args.episode)} 再生成リクエスト】\\n` + lines.join('\\n');
    if (copyText(text)) {{
      showRegenStatus(`✅ ${{lines.length}}件をコピーしました。Claudeに貼り付けてください`);
    }} else {{
      showRegenStatus('❌ コピーに失敗しました');
    }}
  }});
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
