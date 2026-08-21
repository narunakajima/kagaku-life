"""
kl_zoom_anchor.py — シーン画像の主被写体重心をGemini Visionで判定し、
episode JSONにzoom_anchorを書き込む。

samurai-chroniclesの sc_zoom_anchor.py と同じ考え方（Gemini Visionへ委任し、
メイン会話のコンテキストとClaude利用枠を圧迫しない）。SCは character_ref
（固定キャラクター）を前提に「顔〜胸」を対象にするが、kagaku-lifeは
エピソードごとに主人公が変わり、ロボットやチャート図解が主役になる
シーンもあるため、「画像内で視線が集まる主被写体（人物・ロボット・
図解の中心要素等）」を汎用的に判定する。

対象シーン: ken_burns が zoom_in / zoom_out のシーンのみ（pan/staticは対象外。
将来pan用のズームアンカーが必要になれば別途拡張する）。
kl_video_gen.py（今後実装）で Ken Burns のズーム焦点として使う想定。

使い方:
  python3 kl_zoom_anchor.py --episode kl001
  python3 kl_zoom_anchor.py --episode kl001 --scenes 3,7   # 特定シーンのみ再判定
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

from PIL import Image
from google import genai

sys.stdout.reconfigure(line_buffering=True)

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-3.6-flash"

BASE_DIR = Path(__file__).parent
DESKTOP_DIR = Path.home() / "Desktop" / "kagaku-life"

ZOOM_TYPES = {"zoom_in", "zoom_out"}


def is_target_scene(scene: dict) -> bool:
    return scene.get("ken_burns") in ZOOM_TYPES


def determine_zoom_anchor(client: genai.Client, image_path: Path) -> dict:
    """Gemini Visionで主被写体の重心を正規化座標で判定する。"""
    image = Image.open(image_path)
    prompt = (
        "This is a still illustration from a Japanese YouTube video about AI/robotics "
        "research and everyday life. Identify the single main visual subject that the "
        "viewer's eye should be drawn to — this may be a person's face/chest area, a "
        "robot, or (for infographic/chart scenes) the central diagram element — NOT "
        "background details or secondary/minor figures. Return its center of mass as "
        "normalized coordinates where x: 0.0=left edge, 1.0=right edge; "
        "y: 0.0=top edge, 1.0=bottom edge.\n\n"
        "Respond with ONLY a JSON object, no other text, in this exact format:\n"
        '{"x": 0.0, "y": 0.0}'
    )
    response = client.models.generate_content(
        model=MODEL,
        contents=[prompt, image],
    )
    text = response.text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    result = json.loads(text)
    return {"x": round(float(result["x"]), 2), "y": round(float(result["y"]), 2)}


def run(episode_id: str, scene_filter: list = None):
    if not API_KEY:
        print("❌ GEMINI_API_KEY が設定されていません")
        sys.exit(1)

    ep_json = BASE_DIR / "episodes" / f"{episode_id}.json"
    if not ep_json.exists():
        print(f"❌ エピソードJSONが見つかりません: {ep_json}")
        sys.exit(1)

    with open(ep_json, encoding="utf-8") as f:
        ep = json.load(f)

    images_dir = DESKTOP_DIR / episode_id / "images"
    client = genai.Client(api_key=API_KEY)

    targets = [s for s in ep["scenes"] if is_target_scene(s)]
    if scene_filter:
        targets = [s for s in targets if s["scene_id"] in scene_filter]

    print(f"\n{'━'*60}")
    print(f"  {episode_id} — zoom_anchor 判定（Gemini Vision）")
    print(f"  対象シーン: {len(targets)}/{len(ep['scenes'])}（ken_burns=zoom_in/zoom_out のみ）")
    print(f"{'━'*60}\n")

    updated = 0
    failed = []
    for scene in targets:
        scene_id = scene["scene_id"]
        img_path = images_dir / f"S{scene_id:02d}.png"
        if not img_path.exists():
            print(f"  ⚠️  S{scene_id:02d}: 画像が見つかりません（スキップ）")
            failed.append(scene_id)
            continue
        try:
            anchor = determine_zoom_anchor(client, img_path)
            scene["zoom_anchor"] = anchor
            updated += 1
            print(f"  S{scene_id:02d}: x={anchor['x']}, y={anchor['y']}")
        except Exception as e:
            print(f"  ⚠️  S{scene_id:02d}: 判定失敗（{e}）— zoom_anchorはなしのまま")
            failed.append(scene_id)

    with open(ep_json, "w", encoding="utf-8") as f:
        json.dump(ep, f, ensure_ascii=False, indent=2)

    print(f"\n{'━'*60}")
    print(f"  完了: {updated}/{len(targets)} シーンに zoom_anchor を書き込みました")
    if failed:
        print(f"  要確認: {', '.join(f'S{s:02d}' for s in failed)}")
    print(f"{'━'*60}\n")


def cli():
    parser = argparse.ArgumentParser(description="くらしを変える科学 zoom_anchor判定（Gemini Vision）")
    parser.add_argument("--episode", required=True, help="エピソードID（例: kl001）")
    parser.add_argument("--scenes", default=None, help="特定シーンのみ（例: 3,7）。省略時は全対象シーン")
    args = parser.parse_args()

    scene_filter = None
    if args.scenes:
        scene_filter = [int(x.strip()) for x in args.scenes.split(",")]

    run(args.episode, scene_filter=scene_filter)


if __name__ == "__main__":
    cli()
