"""
kl_zoom_anchor.py — シーン画像の主被写体重心をGemini Visionで判定し、
episode JSONにzoom_anchorを書き込む。

samurai-chroniclesの sc_zoom_anchor.py と同じ考え方（Gemini Visionへ委任し、
メイン会話のコンテキストとClaude利用枠を圧迫しない）。SCは character_ref
（固定キャラクター）とimage_promptのテキスト（"on the left"/"on the right"）
から構図タイプを機械的に判定するが、kagaku-lifeはcharacter_refの概念が
なく主人公も毎回変わるため、画像そのものをGemini Visionに見せて判定させる。

判定内容は2つ: (1) 主被写体の重心、(2) 構図タイプ（1人/2人/その他）。
SCと完全に同じ仕様にする（2026-08-25、ユーザー指示で「SCと同じ仕様に」と
確定）: SCのinfer_zoom_anchor()は全シーンに対して必ず何らかのeffect
（pan_zoom_out_lr/rl・zoom_in・zoom_out）を返すため、STEP2でJSON側に
static/pan_left/pan_rightを書いても実質使われることがない（常に上書き
される）。kagaku-lifeもこれに合わせ、**全シーンを対象に**scene.ken_burnsを
判定結果で上書きする: 1人構図→zoom_in（zoom_anchorが焦点）、2人構図→
pan_zoom_out（片側→反対側へパン→ズームアウト）、0人/3人以上（チャート
図解等）→zoom_out（中央固定）。static/pan_left/pan_rightは実質使われなく
なる。

対象シーン: 全シーン（SCと同じ「常に上書き」仕様）。ただし`type`が`data`
（グラフ・比較図）のシーンだけは例外で、人数判定を行わず常に完全静止
（`ken_burns="static"`）にする（2026-08-25追加。グラフをズーム/パンで
動かすと数値の位置関係が読み取りにくくなるという指摘のため）。
kl_video_gen.pyがKen Burnsのズーム焦点・カメラワークとして使う。

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

from google import genai
from google.genai import types

sys.stdout.reconfigure(line_buffering=True)

API_KEY = os.environ.get("GEMINI_API_KEY_KL") or os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-flash-latest"


def atomic_write_json(path: Path, data) -> None:
    """同じディレクトリに一時ファイルを書いてからos.replaceでアトミックに置き換える。
    書き込み中にプロセスが落ちても、既存のJSONが壊れた状態で残らないようにする
    （2026-09-04追加、Fable 5.1監査の指摘）。"""
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_path, path)


def sniff_image_mime(data: bytes) -> str:
    """出力は拡張子が.pngでも実体がJPEGのことがあるため、ファイル先頭バイトから
    実際の画像形式を判定する（拡張子は信用しない。sc_image_gen.pyと同じ関数）。"""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    return "image/png"  # フォールバック


def image_part_from_path(path: Path) -> types.Part:
    """画像ファイルを生バイト列のままPartとして渡す。PIL.Imageオブジェクトを渡すと
    SDK内部でJPEG q75に再エンコードされてしまうため2026-09-04修正
    （Fable 5.1監査の指摘、sc_image_gen.pyと同じ対応）。"""
    data = path.read_bytes()
    return types.Part.from_bytes(data=data, mime_type=sniff_image_mime(data))

BASE_DIR = Path(__file__).parent
DESKTOP_DIR = Path.home() / "Desktop" / "kagaku-life"

def is_target_scene(scene: dict) -> bool:
    # SCと同じ仕様にする（2026-08-25改訂）: SCのinfer_zoom_anchor()は
    # 全シーンに対して必ず何らかのeffect（pan_zoom_out_lr/rl・zoom_in・
    # zoom_out）を返すため、JSON側でstatic/pan_left/pan_rightを指定しても
    # 実質使われることがない（常に上書きされる）。kagaku-lifeもこの
    # 「人数に応じて自動決定」を全シーン一律に適用し、static/pan_left/
    # pan_rightを廃止する。全シーンが対象（毎回再判定する）。
    return True


def determine_zoom_anchor(client: genai.Client, image_path: Path) -> dict:
    """Gemini Visionで主被写体の重心と構図タイプ（人数）を判定する。

    samurai-chroniclesは character_ref とimage_promptのテキスト（"on the
    left"/"on the right"）から機械的に構図タイプを判定するが、kagaku-lifeは
    character_refの概念がなく主人公も毎回変わるため、画像そのものをGemini
    Visionに見せて判定させる（2026-08-25追加。SCと同じ「1人＝ズームイン、
    2人＝パン+ズームアウト、0人/3人以上＝中央からズームアウト」という
    カメラワークのルールをkagaku-lifeにも適用するため）。
    """
    image = image_part_from_path(image_path)
    prompt = (
        "This is a still illustration from a Japanese YouTube video about AI/robotics "
        "research and everyday life.\n\n"
        "1. Count how many clearly distinct human figures (or a single robot counts as "
        "one figure) are prominent foreground subjects in this image — ignore tiny, "
        "blurred, or background/crowd figures. Classify as exactly one of: "
        "\"one\" (a single clear main subject), \"two\" (exactly two clear subjects, "
        "roughly positioned on opposite sides of the frame, e.g. facing each other or "
        "side by side), or \"other\" (zero subjects, three or more subjects, or a "
        "chart/infographic scene with no clear individual figures).\n"
        "2. If \"one\", identify that single main visual subject's center of mass "
        "(face/chest area for a person, the main body for a robot, or the central "
        "diagram element for an infographic/chart scene) as normalized coordinates "
        "where x: 0.0=left edge, 1.0=right edge; y: 0.0=top edge, 1.0=bottom edge. If "
        "not \"one\", just return {\"x\": 0.5, \"y\": 0.5}.\n\n"
        "Respond with ONLY a JSON object, no other text, in this exact format:\n"
        '{"subject_count": "one", "x": 0.0, "y": 0.0}'
    )
    response = client.models.generate_content(
        model=MODEL,
        contents=[prompt, image],
        config=genai.types.GenerateContentConfig(
            thinking_config=genai.types.ThinkingConfig(thinking_budget=0)
        ),
    )
    text = response.text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    result = json.loads(text)
    return {
        "subject_count": result.get("subject_count", "one"),
        "x": round(float(result.get("x", 0.5)), 2),
        "y": round(float(result.get("y", 0.5)), 2),
    }


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

    images_dir = DESKTOP_DIR / "images"
    client = genai.Client(api_key=API_KEY)

    targets = [s for s in ep["scenes"] if is_target_scene(s)]
    if scene_filter:
        targets = [s for s in targets if s["scene_id"] in scene_filter]

    print(f"\n{'━'*60}")
    print(f"  {episode_id} — zoom_anchor判定・カメラワーク自動決定（Gemini Vision）")
    print(f"  対象シーン: {len(targets)}/{len(ep['scenes'])}（SCと同じ仕様: 全シーン一律）")
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
        if scene.get("type") == "data":
            # グラフ・比較図（typeがdata）はズーム/パンで動かすと数値の位置
            # 関係が読み取りにくくなり不自然という指摘があった（2026-08-25）。
            # 人数判定に関わらず常に完全な静止（ken_burns="static"）にする
            # （Gemini Vision呼び出しも不要なためスキップしてコストを節約する）。
            scene["ken_burns"] = "static"
            scene.pop("zoom_anchor", None)
            updated += 1
            print(f"  S{scene_id:02d}: dataタイプ → ken_burns=static（完全静止、判定スキップ）")
            continue
        try:
            result = determine_zoom_anchor(client, img_path)
            updated += 1
            if result["subject_count"] == "two":
                # SCと同じカメラワークルール: 2人構図は単一焦点のズームではなく
                # 「片側→反対側へパン→ズームアウトで全体を見せる」演出に切り替える
                # （kl_video_gen.pyのmake_ken_burnsが実際のlr/rl方向をランダムに
                # 決める）。zoom_anchorは使わないシーンになるため書き込まない。
                scene["ken_burns"] = "pan_zoom_out"
                scene.pop("zoom_anchor", None)
                print(f"  S{scene_id:02d}: 2人構図と判定 → ken_burns=pan_zoom_out")
            elif result["subject_count"] == "one":
                # 1人構図（人物・ロボット等の単一主被写体）→ ズームイン
                # （SCの「character_ref あり→zoom_in」と同じ）
                scene["ken_burns"] = "zoom_in"
                anchor = {"x": result["x"], "y": result["y"]}
                scene["zoom_anchor"] = anchor
                print(f"  S{scene_id:02d}: 1人構図と判定 → ken_burns=zoom_in x={anchor['x']}, y={anchor['y']}")
            else:
                # 0人・3人以上（チャート図解等含む）→ 中央からズームアウト
                # （SCの「人物なし・3人以上→中央からズームアウト」と同じ、
                # 焦点は常に中央固定）
                scene["ken_burns"] = "zoom_out"
                anchor = {"x": 0.5, "y": 0.5}
                scene["zoom_anchor"] = anchor
                print(f"  S{scene_id:02d}: 0人/3人以上と判定 → ken_burns=zoom_out（中央固定）")
        except Exception as e:
            print(f"  ⚠️  S{scene_id:02d}: 判定失敗（{e}）— zoom_anchorはなしのまま")
            failed.append(scene_id)

    atomic_write_json(ep_json, ep)

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
