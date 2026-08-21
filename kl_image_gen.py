"""
kl_image_gen.py — くらしを変える科学 静止画生成スクリプト

episodes/kl{NNN}.json の各シーンのimage_promptに、シーンtypeに応じた
BASE_CONTEXT（物語シーン用）またはCHART_CONTEXT（dataタイプ用）を付与して
gemini-3.1-flash-imageで静止画を生成する（CLAUDE.md「画像スタイル」参照）。
thumbnail_promptも同様にBASE_CONTEXTを付与して生成する。

使い方:
  python3 kl_image_gen.py --episode kl001                  # 全シーン+サムネイル生成
  python3 kl_image_gen.py --episode kl001 --scenes 5,6,9    # 指定シーンのみ再生成
  python3 kl_image_gen.py --episode kl001 --thumbnail-only  # サムネイルのみ

出力: ~/Desktop/kagaku-life/{episode}/images/S{NN}.png, thumbnail.png
"""

import argparse
import json
import os
import sys
from pathlib import Path

from google import genai
from google.genai import types

sys.stdout.reconfigure(line_buffering=True)

BASE_DIR = Path(__file__).parent
DESKTOP_DIR = Path.home() / "Desktop" / "kagaku-life"

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-3.1-flash-image"
REQUEST_TIMEOUT_MS = 60_000

# CLAUDE.md「画像スタイル（2026-08-21改訂）」確定版
BASE_CONTEXT = (
    "Rich flat editorial illustration style with soft warm lamp/window lighting and a "
    "subtle grain/noise texture overlay: naturalistic character proportions and skin "
    "tones, gentle shading gradients rather than flat cel-shading. Muted, sophisticated "
    "palette (slate blue, teal, warm gray) with one warm coral/amber accent light "
    "glowing softly within the scene. Cozy, intimate, magazine-editorial illustration "
    "quality. Not photorealistic, no anime style, no harsh dramatic light rays. "
    "Characters have authentically Japanese facial features (this is a Japanese-audience "
    "channel) — not Western or ambiguous."
)

CHART_CONTEXT = (
    "Simple, clean, minimalist flat infographic bar chart — like a basic data "
    "visualization slide, NOT an artistic or abstract illustration. Plain solid flat "
    "colors only, no dramatic lighting, no light rays, no gradients, no texture, no "
    "decorative background shapes. Cool color palette (deep blue, teal) for baseline "
    "values, one warm coral/orange color for the improved/highlighted value. No legible "
    "text or numerals — convey the difference through bar height/fill only."
)


def style_for(scene_type: str) -> str:
    return CHART_CONTEXT if scene_type == "data" else BASE_CONTEXT


def gen_image(client: genai.Client, prompt: str, out_path: Path) -> bool:
    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
    )
    for part in resp.candidates[0].content.parts:
        if part.inline_data:
            out_path.write_bytes(part.inline_data.data)
            print(f"✅ {out_path.name}")
            return True
    print(f"⚠️ 画像なし: {out_path.name}", file=sys.stderr)
    return False


def main():
    parser = argparse.ArgumentParser(description="くらしを変える科学 静止画生成")
    parser.add_argument("--episode", required=True, help="エピソードID（例: kl001）")
    parser.add_argument("--scenes", help="生成するscene_idをカンマ区切りで指定（省略時は全シーン）")
    parser.add_argument("--thumbnail-only", action="store_true", help="サムネイルのみ生成")
    parser.add_argument("--no-thumbnail", action="store_true", help="サムネイルを生成しない")
    args = parser.parse_args()

    if not API_KEY:
        print("❌ GEMINI_API_KEY が設定されていません", file=sys.stderr)
        sys.exit(1)

    ep_path = BASE_DIR / "episodes" / f"{args.episode}.json"
    if not ep_path.exists():
        print(f"❌ {ep_path} がありません", file=sys.stderr)
        sys.exit(1)
    ep = json.loads(ep_path.read_text())

    out_dir = DESKTOP_DIR / args.episode / "images"
    out_dir.mkdir(parents=True, exist_ok=True)

    client = genai.Client(api_key=API_KEY, http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))

    if not args.thumbnail_only:
        target_ids = None
        if args.scenes:
            target_ids = {int(s) for s in args.scenes.split(",")}

        for scene in ep["scenes"]:
            sid = scene["scene_id"]
            if target_ids is not None and sid not in target_ids:
                continue
            prompt = f"{style_for(scene['type'])}\n\nScene: {scene['image_prompt']}"
            out_path = out_dir / f"S{sid:02d}.png"
            gen_image(client, prompt, out_path)

    if not args.no_thumbnail and (args.thumbnail_only or args.scenes is None):
        thumb_prompt = f"{BASE_CONTEXT}\n\nThumbnail (16:9): {ep['thumbnail_prompt']}"
        gen_image(client, thumb_prompt, out_dir / "thumbnail.png")

    print(f"\n完了。保存先: {out_dir}")


if __name__ == "__main__":
    main()
