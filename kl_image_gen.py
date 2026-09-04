"""
kl_image_gen.py — くらしを変える科学 静止画生成スクリプト

episodes/kl{NNN}.json の各シーンのimage_promptに、シーンtypeに応じた
BASE_CONTEXT（物語シーン用）またはCHART_CONTEXT（dataタイプ用）を付与して
gemini-3.1-flash-imageで静止画を生成する（CLAUDE.md「画像スタイル」参照）。
thumbnail_promptも同様にBASE_CONTEXTを付与して生成する。

生成後、Gemini Visionによる自動QA（sc_image_gen.pyと同じ考え方）を行い、
問題があれば指摘内容をプロンプトに反映して自動再生成する（最大2回試行）。

teaser画像について（2026-09-04〜）:
  teaser（および他の任意のシーン）に"reuse_scene_id"（同一エピソード内の別scene_id）
  があれば、その画像が既に存在する場合は再生成せずファイルコピーのみで済ませる
  （API呼び出しなし）。teaserはimpact等の内容を先出しするため、同じ画像を
  ティザーと本編の両方で使い回すのは自然な演出でもある。参照先が未生成の場合は
  独立生成にフォールバックする。

Shorts画像について（2026-09-04〜）:
  Shortsの各カットに"scene_id"（本編scene_idへの参照）があれば、本編(16:9)で
  既にQA承認済みの画像をGeminiで9:16に再構成する（ゼロから独立生成しない。
  samurai-chroniclesのsc_image_gen.pyと同じ仕組み）。scene_idが無い、または
  参照先の本編画像が未生成の場合は、Shorts独自のimage_promptから独立生成する
  旧方式にフォールバックする（kl001〜kl013はscene_id未対応のため）。

使い方:
  python3 kl_image_gen.py --episode kl001                  # 全シーン+サムネイル生成
  python3 kl_image_gen.py --episode kl001 --scenes 5,6,9    # 指定シーンのみ再生成
  python3 kl_image_gen.py --episode kl001 --thumbnail-only  # サムネイルのみ
  python3 kl_image_gen.py --episode kl001 --shorts-only     # Shortsのみ（9:16）
  python3 kl_image_gen.py --episode kl001 --no-qa           # QAをスキップ（旧動作）

出力: ~/Desktop/kagaku-life/images/S{NN}.png, thumbnail.png,
      shorts{M}_S{NN}.png（Shorts、9:16）
      ~/Desktop/kagaku-life/image_qa_result.json（QAレポート）
      （Desktopは常に最新1エピソード分の確認用。エピソードIDのサブフォルダは作らない）
"""

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image, ImageDraw, ImageFont

sys.stdout.reconfigure(line_buffering=True)

BASE_DIR = Path(__file__).parent
DESKTOP_DIR = Path.home() / "Desktop" / "kagaku-life"

API_KEY = os.environ.get("GEMINI_API_KEY_KL") or os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-3.1-flash-image"
QA_MODEL = "gemini-flash-latest"
REQUEST_TIMEOUT_MS = 60_000
MAX_QA_ATTEMPTS = 2  # SCの実績（89話分・3回目のリトライは効果薄）を踏襲し2回に抑える

# サムネイルテキスト合成（2026-08-22追加）。日本語はAI画像生成に任せず、
# lamp-whisperのmake_thumbnail_gemini.pyと同じ「背景はAI生成（無地）、
# テキストはPillowで実フォント合成」方式を踏襲する。
FONT_BOLD = Path("/System/Library/Fonts/ヒラギノ角ゴシック W8.ttc")
FONT_MEDIUM = Path("/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc")
THUMB_HEADLINE_COLOR = (255, 255, 255)
THUMB_SUB_COLOR = (240, 168, 104)  # チャンネル配色の暖色コーラルアクセント
THUMB_SHADOW_COLOR = (0, 0, 0)


def composite_thumbnail_text(image_path: Path, headline: str, sub: str = "") -> None:
    """サムネイル画像（テキストなしで生成済み）に、大きく太いアウトライン付き見出し
    （画面上部）と控えめなサブコピー（画面下部）をPillowで合成する。

    2026-08-25改訂: 従来は下部の暗い帯に控えめなドロップシャドウ付きテキストを
    小さめに配置していたが、ユーザーからSC（samurai-chronicles）のサムネイルの
    ように「テキストをバーンと出したほうがいい」との指摘があった。見出しを
    画面上部に大きく・太いアウトライン（stroke）付きで配置する構成に変更した。
    """
    img = Image.open(image_path).convert("RGBA")
    w, h = img.size

    top_band_h = int(h * 0.42)
    top_gradient = Image.new("L", (1, top_band_h), 0)
    for y in range(top_band_h):
        alpha = int(215 * (1 - y / top_band_h) ** 1.2)
        top_gradient.putpixel((0, y), alpha)
    top_gradient = top_gradient.resize((w, top_band_h))
    top_band = Image.new("RGBA", (w, top_band_h), (10, 20, 35, 0))
    top_band.putalpha(top_gradient)
    img.alpha_composite(top_band, (0, 0))

    draw = ImageDraw.Draw(img)
    margin_x = int(w * 0.05)

    headline_size = int(h * 0.19)
    font_headline = ImageFont.truetype(str(FONT_BOLD), headline_size)
    stroke_w = max(4, headline_size // 14)
    while (
        draw.textbbox((0, 0), headline, font=font_headline, stroke_width=stroke_w)[2] > w - margin_x * 2
        and headline_size > 48
    ):
        headline_size -= 4
        font_headline = ImageFont.truetype(str(FONT_BOLD), headline_size)
        stroke_w = max(4, headline_size // 14)

    hy = int(h * 0.06)
    draw.text(
        (margin_x, hy + int(headline_size * 0.06)), headline, font=font_headline,
        fill=THUMB_HEADLINE_COLOR, stroke_width=stroke_w, stroke_fill=THUMB_SHADOW_COLOR,
    )

    if sub:
        band_h = int(h * 0.22)
        gradient = Image.new("L", (1, band_h), 0)
        for y in range(band_h):
            alpha = int(190 * (y / band_h) ** 1.3)
            gradient.putpixel((0, y), alpha)
        gradient = gradient.resize((w, band_h))
        band = Image.new("RGBA", (w, band_h), (10, 20, 35, 0))
        band.putalpha(gradient)
        img.alpha_composite(band, (0, h - band_h))

        sub_size = int(h * 0.06)
        font_sub = ImageFont.truetype(str(FONT_MEDIUM), sub_size)
        sub_stroke = max(2, sub_size // 12)
        while (
            draw.textbbox((0, 0), sub, font=font_sub, stroke_width=sub_stroke)[2] > w - margin_x * 2
            and sub_size > 24
        ):
            sub_size -= 2
            font_sub = ImageFont.truetype(str(FONT_MEDIUM), sub_size)
            sub_stroke = max(2, sub_size // 12)
        sy = h - int(band_h * 0.5) - sub_size // 2
        draw.text(
            (margin_x, sy), sub, font=font_sub,
            fill=THUMB_SUB_COLOR, stroke_width=sub_stroke, stroke_fill=THUMB_SHADOW_COLOR,
        )

    img.convert("RGB").save(image_path, "PNG")

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
    "Simple, clean, minimalist flat infographic diagram or chart — like a basic data "
    "visualization slide, NOT an artistic or abstract illustration. Follow the scene "
    "description below for the actual diagram type/layout (it may or may not be a bar "
    "chart — do not default to a bar chart if the scene describes something else, e.g. "
    "arrows, icons converging on a shared point, a trend line, etc.). Plain solid flat "
    "colors only, no dramatic lighting, no light rays, no gradients, no texture, no "
    "decorative background shapes. Cool color palette (deep blue, teal) for baseline "
    "elements, one warm coral/orange color for the improved/highlighted element. "
    "If the scene description below specifies Japanese text labels (e.g. a short title "
    "or group names), render them directly in the image in a clean, legible sans-serif "
    "font as accurately-spelled Japanese text, matching the flat infographic style — do "
    "not omit them. Do NOT invent or add any text, numbers, or labels beyond exactly "
    "what the scene description specifies; if no specific number/percentage is given in "
    "the scene description, do not fabricate one. "
    "CRITICAL LAYOUT CONSTRAINT: leave the bottom 22% of the frame completely empty — "
    "plain flat background color and absolutely NOTHING else there: no bars, no icons, "
    "no text, no labels, no captions, no decorative elements of any kind, not even a "
    "single character. Do NOT invent a caption or label to fill that empty space — a "
    "burned-in Japanese subtitle is overlaid across that exact bottom strip in the final "
    "video and would collide with and obscure absolutely anything placed there. Keep the "
    "title, all bars/icons, and every text label confined entirely to the upper 78% of "
    "the frame; the bottom 22% must render as pure, untouched flat background."
)


def style_for(scene_type: str) -> str:
    return CHART_CONTEXT if scene_type == "data" else BASE_CONTEXT


def build_shorts_reframe_prompt(scene_prompt: str) -> str:
    """本編(16:9)で承認済みの画像を9:16に再構成するためのプロンプト。
    ゼロから独立生成せず、同一内容を縦構図に拡張するだけなのでMISMATCHが
    起きにくく、コスト面でも新規生成+QAの往復を避けられる
    （samurai-chroniclesのsc_image_gen.pyと同じ考え方、2026-09-04導入）。"""
    return (
        "Reframe this exact reference image into a 9:16 vertical portrait composition for "
        "mobile short-form video. Keep the same subject, character appearance, setting, "
        "lighting, and art style exactly as in the reference image — do not change the "
        "scene content. Extend/recompose the framing so the main subject is centered and "
        "prominent in a vertical frame, generating plausible additional scene content "
        "above/below as needed to fill the vertical canvas.\n\n"
        f"Scene: {scene_prompt}"
    )


def gen_image(client: genai.Client, prompt: str, out_path: Path, aspect_ratio: str = None,
              reference_image_path: Path = None) -> bool:
    config_kwargs = {"response_modalities": ["IMAGE"]}
    if aspect_ratio:
        config_kwargs["image_config"] = types.ImageConfig(aspect_ratio=aspect_ratio)
    contents = prompt
    if reference_image_path is not None:
        # 参照画像を渡して背景（部屋・窓・人物サイズ等）を踏襲させる。複数シーンに
        # わたって同じ「雲の外側」を独立生成すると細部が毎回ばらつく問題への対処
        # （2026-08-25追加、kl004 S14〜S16で発覚）。
        ref_bytes = reference_image_path.read_bytes()
        contents = [
            types.Part.from_bytes(data=ref_bytes, mime_type="image/png"),
            prompt,
        ]
    resp = client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(**config_kwargs),
    )
    candidate = resp.candidates[0] if resp.candidates else None
    parts = candidate.content.parts if (candidate and candidate.content) else None
    if not parts:
        return False
    for part in parts:
        if part.inline_data:
            out_path.write_bytes(part.inline_data.data)
            return True
    return False


# ── 画像QA（Gemini Vision） ──────────────────────────────────────────

QA_PROMPT_TEMPLATE = """You are a quality-control reviewer for AI-generated illustrations used in a
Japanese YouTube channel about AI/robotics research and its effect on everyday life
("幸せな未来のサイエンスチャンネル"). The house style is a warm, cozy editorial
illustration (or, for data/diagram scenes, a clean flat infographic) — see the scene
description for which applies.

Check the image against the intended scene description for these issue types:
- MISMATCH: the image does not match the scene description (wrong subject, action, or setting)
- DISTORTION: anatomical errors, malformed faces/hands/bodies, broken or warped objects
- TEXT: {text_rule}
- STYLE: the rendering does not match the intended house style described above (e.g. an
  artistic/dramatic illustration where a clean flat infographic was called for, or vice versa;
  photorealistic where illustration was called for; anime/manga style)
- FACE: if the scene description specifies a robot with a mechanical head/sensor (no human
  face), but the image instead shows the robot with a human-like face (eyes, nose, mouth,
  humanoid facial features) — this reads as unsettling/uncanny and must be flagged
- DUPLICATE_PERSON: if the scene description calls for multiple distinct/different people
  (e.g. different households, different researchers), but two or more of them look like the
  same person (same hairstyle, build, and clothing) in the image
- COMPOSITION: the spatial arrangement of objects/characters is physically or logically
  illogical for the real-world scene being depicted, even if each individual element looks
  fine on its own — e.g. a television or monitor screen facing directly out of the frame
  toward the viewer instead of naturally facing the people who are supposed to be watching
  it; a mirror, window, or screen showing a reflection/view that doesn't match its position;
  furniture or people arranged in a way that couldn't physically coexist in the described room

Scene description: {image_prompt}

Respond with ONLY a JSON object, no other text, in this exact format:
{{"ok": true, "issues": []}}
or
{{"ok": false, "issues": ["ISSUE_TYPE: brief description", ...]}}
"""


TEXT_RULE_NO_TEXT = (
    "any readable text, letters, numerals, captions, watermarks, or logos appear "
    "in the image"
)
TEXT_RULE_ALLOW_LABELS = (
    "the image contains text that was NOT called for by the scene description, OR "
    "contains garbled/misspelled/unreadable Japanese text, OR contains fabricated "
    "numbers/percentages not present in the scene description. Correctly-rendered, "
    "legible Japanese text labels that match what the scene description explicitly "
    "asks for (e.g. a short title, group names) are expected and must NOT be flagged."
)


def qa_image_with_gemini(client: genai.Client, image_path: Path, image_prompt: str,
                          allow_text: bool = False) -> dict:
    """生成画像をGemini Visionで自動チェックする。問題があれば issues に格納する。
    allow_text=True の場合（dataタイプ等、意図的に日本語テキストラベルを含める
    チャート）は、テキストの存在そのものではなく、ガーブレ・誤字・シーン記述に
    ない数値の捏造のみをTEXT issueとして扱う（2026-08-26追加。以前はdataタイプの
    チャートに一切テキストを入れない方針だったが、gemini-3.1-flash-imageの日本語
    テキスト描画精度が実用レベルに達したため、CLAUDE.mdの方針を改訂した）。
    """
    try:
        from PIL import Image
        image = Image.open(image_path)
        text_rule = TEXT_RULE_ALLOW_LABELS if allow_text else TEXT_RULE_NO_TEXT
        qa_prompt = QA_PROMPT_TEMPLATE.format(image_prompt=image_prompt, text_rule=text_rule)
        response = client.models.generate_content(
            model=QA_MODEL,
            contents=[qa_prompt, image],
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=0)
            ),
        )
        text = response.text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        result = json.loads(text)
        return {"ok": bool(result.get("ok", True)), "issues": result.get("issues", [])}
    except Exception as e:
        # QA自体が失敗した場合はサイレントにOK扱いせず、issueとして扱い
        # 既存のリトライ機構に乗せる（API障害等を「問題なし」と誤認しないため）。
        return {"ok": False, "issues": [f"QA_ERROR: {e}"]}


def _correction_note(issues: list, allow_text: bool = False) -> str:
    """QAで見つかった issue の種類ごとに、プロンプトへ追記する修正指示を組み立てる。"""
    notes = []
    seen = set()
    for issue in issues:
        prefix = issue.split(":", 1)[0].strip().upper()
        if prefix in seen:
            continue
        if prefix == "TEXT":
            if allow_text:
                notes.append(
                    "Fix the text: render ONLY correctly-spelled, legible "
                    "Japanese text exactly matching what the scene description "
                    "specifies — no garbled characters, no misspellings, no "
                    "extra text or fabricated numbers beyond what is specified."
                )
            else:
                notes.append(
                    "ABSOLUTELY NO readable text, letters, numerals, captions, "
                    "watermarks, or logos anywhere in the image."
                )
        elif prefix == "DISTORTION":
            notes.append(
                "Render all hands, faces, and anatomy with correct, natural "
                "proportions — no malformed or distorted body parts."
            )
        elif prefix == "MISMATCH":
            notes.append(
                "Follow the scene description exactly — do not add extra "
                "elements or deviate from the specified composition, subject, "
                "and setting."
            )
        elif prefix == "STYLE":
            notes.append(
                "Match the intended house style exactly as described in the "
                "context (warm editorial illustration or clean flat "
                "infographic) — do not deviate into a different rendering style."
            )
        elif prefix == "FACE":
            notes.append(
                "The robot's head/face must be clearly mechanical — a camera "
                "lens, sensor panel, or similar — with NO human-like face: no "
                "eyes, no nose, no mouth, nothing resembling a human head."
            )
        elif prefix == "DUPLICATE_PERSON":
            notes.append(
                "Every person in this scene must look visibly distinct from "
                "the others — different hairstyles, builds, ages, and "
                "clothing colors. Do not repeat the same-looking person."
            )
        elif prefix == "COMPOSITION":
            notes.append(
                "Fix the spatial arrangement so it is physically and "
                "logically consistent with a real version of this scene — "
                "objects like screens/mirrors/windows must be oriented and "
                "positioned the way they naturally would be relative to the "
                "people in the room, not artificially turned toward the "
                "camera. Prioritize a believable, natural composition over "
                "showing every element head-on."
            )
        seen.add(prefix)
    return " ".join(notes)


# ── シーン間の画風ドリフト検出（2026-09-01追加） ──────────────────────────
# 上記のQA_PROMPT_TEMPLATEによる単体チェックは「このシーンが文章で書かれた
# ハウススタイル（BASE_CONTEXT等）に合っているか」しか見ていないため、各シーンが
# 個別には「物語調イラストらしい」条件を満たしていても、エピソード内の他シーンと
# 比べて質感（グレインの強さ・線の太さ・陰影のつけ方・彩度）がズレているケースを
# 見逃す（前回制作で実際に発生）。同一エピソードの物語シーン画像を横並びでGemini
# Visionに渡し、相対比較で外れ値を検出する専用チェックを追加する。
STYLE_DRIFT_PROMPT_TEMPLATE = """You are a quality-control reviewer checking VISUAL CONSISTENCY across a set of
illustrations from the same Japanese YouTube episode. All images below are supposed to
share one consistent "house style" — a warm editorial illustration touch (soft grain/
noise texture, gentle gradient shading, muted desaturated palette, similar line weight).

Do NOT evaluate whether each image individually matches that style description in the
abstract — evaluate whether they are RENDERED CONSISTENTLY WITH EACH OTHER. Compare:
- grain/noise texture density
- line weight / edge sharpness
- shading approach (soft gradient vs flatter cel-shading vs more painterly/photoreal)
- color saturation and warmth
- overall rendering technique

Each image is preceded by its label (e.g. "S05"). Identify any image(s) whose rendering
touch clearly stands out from the consistent majority, even if that image looks fine on
its own. Minor scene-to-scene variation in lighting/color due to different times of day
or settings is normal and should NOT be flagged — only flag a genuinely different
rendering technique/touch.

Images to compare: {labels}

Respond with ONLY a JSON object, no other text, in this exact format:
{{"consistent": true, "outliers": []}}
or
{{"consistent": false, "outliers": [{{"label": "S05", "reason": "brief description of how its touch differs from the rest"}}]}}
"""

MIN_IMAGES_FOR_STYLE_DRIFT_CHECK = 3  # 比較対象が少なすぎると誤検知しやすいため


def check_style_drift(client: genai.Client, entries: list) -> dict:
    """entries: [{"label": str, "path": Path}, ...]（物語調イラストのみ、dataタイプは
    意図的にトーンが異なるため対象外）。戻り値: {label: reason} の外れ値マップ。"""
    if len(entries) < MIN_IMAGES_FOR_STYLE_DRIFT_CHECK:
        return {}
    try:
        from PIL import Image
        labels = [e["label"] for e in entries]
        prompt = STYLE_DRIFT_PROMPT_TEMPLATE.format(labels=", ".join(labels))
        contents = [prompt]
        for e in entries:
            contents.append(f"Image labeled {e['label']}:")
            contents.append(Image.open(e["path"]))
        response = client.models.generate_content(
            model=QA_MODEL, contents=contents,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=0)
            ),
        )
        text = response.text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        result = json.loads(text)
        outliers = {}
        for o in result.get("outliers", []):
            label = o.get("label")
            if label:
                outliers[label] = o.get("reason", "")
        return outliers
    except Exception as e:
        print(f"⚠️ 画風ドリフトチェックに失敗（スキップ）: {e}", file=sys.stderr)
        return {}


def build_retry_prompt(base_prompt: str, issues: list, allow_text: bool = False) -> str:
    note = _correction_note(issues, allow_text=allow_text)
    prompt = base_prompt
    if note:
        prompt = f"{prompt}\n\nIMPORTANT CORRECTIONS: {note}"
    if issues:
        specific = "\n".join(f"- {issue}" for issue in issues)
        prompt = (
            f"{prompt}\n\nSpecific issues detected by QA in the previous attempt "
            f"(fix these exactly):\n{specific}"
        )
    return prompt


def generate_with_qa(client: genai.Client, base_prompt: str, image_prompt_for_qa: str,
                      out_path: Path, aspect_ratio: str = None, skip_qa: bool = False,
                      reference_image_path: Path = None, allow_text: bool = False) -> dict:
    """生成→QA→（NGなら）修正指示付きで再生成、を最大MAX_QA_ATTEMPTS回試行する。"""
    prompt = base_prompt
    result = {"ok": False, "issues": ["画像生成失敗（QA未実行）"], "attempts": 0}
    for attempt in range(1, MAX_QA_ATTEMPTS + 1):
        suffix = f"（{attempt}回目）" if attempt > 1 else ""
        ok = gen_image(client, prompt, out_path, aspect_ratio=aspect_ratio,
                        reference_image_path=reference_image_path)
        if not ok:
            print(f"⚠️ {out_path.name}: 画像データなし{suffix}", file=sys.stderr)
            result = {"ok": False, "issues": ["画像データなし"], "attempts": attempt}
            return result
        if skip_qa:
            print(f"✅ {out_path.name}")
            return {"ok": True, "issues": [], "attempts": attempt}
        qa = qa_image_with_gemini(client, out_path, image_prompt_for_qa, allow_text=allow_text)
        qa["attempts"] = attempt
        if qa["ok"]:
            print(f"✅ {out_path.name}{suffix} [QA: OK]")
            return qa
        print(f"⚠️  {out_path.name}{suffix} [QA: {len(qa['issues'])}件] " + "; ".join(qa["issues"]))
        result = qa
        if attempt < MAX_QA_ATTEMPTS:
            prompt = build_retry_prompt(base_prompt, qa["issues"], allow_text=allow_text)
    print(f"   → {MAX_QA_ATTEMPTS}回試行して未解決。目視確認してください: {out_path.name}")
    return result


def main():
    parser = argparse.ArgumentParser(description="くらしを変える科学 静止画生成")
    parser.add_argument("--episode", required=True, help="エピソードID（例: kl001）")
    parser.add_argument("--scenes", help="生成するscene_idをカンマ区切りで指定（省略時は全シーン）")
    parser.add_argument("--thumbnail-only", action="store_true", help="サムネイルのみ生成")
    parser.add_argument("--no-thumbnail", action="store_true", help="サムネイルを生成しない")
    parser.add_argument("--shorts-only", action="store_true", help="Shortsのみ生成")
    parser.add_argument("--shorts-scenes", help="Shorts内の生成する番号をカンマ区切りで指定（例: 4）。指定時は自動的に--shorts-only扱い")
    parser.add_argument("--no-qa", action="store_true", help="Gemini Vision QAをスキップ（旧動作）")
    parser.add_argument("--reference-scene", type=int,
                         help="指定したscene_idの生成済み画像を参照画像として渡し、背景の一貫性を高める（--scenesで対象を絞って使う）")
    args = parser.parse_args()

    if not API_KEY:
        print("❌ GEMINI_API_KEY が設定されていません", file=sys.stderr)
        sys.exit(1)

    ep_path = BASE_DIR / "episodes" / f"{args.episode}.json"
    if not ep_path.exists():
        print(f"❌ {ep_path} がありません", file=sys.stderr)
        sys.exit(1)
    ep = json.loads(ep_path.read_text())

    out_dir = DESKTOP_DIR / "images"
    out_dir.mkdir(parents=True, exist_ok=True)
    DESKTOP_DIR.mkdir(parents=True, exist_ok=True)
    (DESKTOP_DIR / ".current_episode").write_text(args.episode, encoding="utf-8")

    client = genai.Client(api_key=API_KEY, http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))

    qa_results = []

    shorts_only = args.shorts_only or bool(args.shorts_scenes)

    if not args.thumbnail_only and not shorts_only:
        target_ids = None
        if args.scenes:
            target_ids = {int(s) for s in args.scenes.split(",")}

        ref_path = (out_dir / f"S{args.reference_scene:02d}.png") if args.reference_scene else None
        if ref_path is not None and not ref_path.exists():
            print(f"❌ 参照画像が見つかりません: {ref_path}", file=sys.stderr)
            sys.exit(1)

        scenes_to_run = [s for s in ep["scenes"] if target_ids is None or s["scene_id"] in target_ids]
        # reuse_scene_id を持つシーン（teaser等、他シーンと同じ画像を使い回す）は、
        # 参照先の画像が先に存在している必要があるため後回しにする（2026-09-04〜）。
        normal_scenes = [s for s in scenes_to_run if not s.get("reuse_scene_id")]
        reuse_scenes = [s for s in scenes_to_run if s.get("reuse_scene_id")]

        for scene in normal_scenes:
            sid = scene["scene_id"]
            prompt = f"{style_for(scene['type'])}\n\nScene: {scene['image_prompt']}"
            out_path = out_dir / f"S{sid:02d}.png"
            r = generate_with_qa(client, prompt, scene["image_prompt"], out_path, skip_qa=args.no_qa,
                                  reference_image_path=ref_path, allow_text=(scene["type"] == "data"))
            r["name"] = out_path.name
            qa_results.append(r)

        if reuse_scenes:
            all_scenes_by_id = {s["scene_id"]: s for s in ep["scenes"]}
        for scene in reuse_scenes:
            sid = scene["scene_id"]
            out_path = out_dir / f"S{sid:02d}.png"
            src_id = scene["reuse_scene_id"]
            src_path = out_dir / f"S{src_id:02d}.png"
            if src_path.exists():
                shutil.copy(src_path, out_path)
                print(f"✅ {out_path.name}（S{src_id:02d}.pngを流用、API呼び出しなし）")
                qa_results.append({"name": out_path.name, "ok": True, "issues": [], "attempts": 0})
                continue
            print(f"⚠️  S{src_id:02d}.png が見つからないため独立生成にフォールバック: {out_path.name}",
                  file=sys.stderr)
            src_scene = all_scenes_by_id.get(src_id)
            image_prompt = scene.get("image_prompt") or (src_scene["image_prompt"] if src_scene else None)
            if not image_prompt:
                print(f"❌ S{sid:02d}: image_promptもreuse_scene_id参照先も見つかりません", file=sys.stderr)
                sys.exit(1)
            prompt = f"{style_for(scene['type'])}\n\nScene: {image_prompt}"
            r = generate_with_qa(client, prompt, image_prompt, out_path, skip_qa=args.no_qa,
                                  reference_image_path=ref_path, allow_text=(scene["type"] == "data"))
            r["name"] = out_path.name
            qa_results.append(r)

    if not args.thumbnail_only and not shorts_only and not args.no_qa:
        narrative_entries = []
        for scene in ep["scenes"]:
            if scene["type"] == "data":
                continue
            p = out_dir / f"S{scene['scene_id']:02d}.png"
            if p.exists():
                narrative_entries.append({"label": p.stem, "path": p, "scene": scene})

        outliers = check_style_drift(client, narrative_entries)
        if outliers:
            print(f"\n⚠️ 画風ドリフト検出: {len(outliers)}件 " +
                  "; ".join(f"{label}: {reason}" for label, reason in outliers.items()))
            ok_entries = [e for e in narrative_entries if e["label"] not in outliers]
            ref_entry = ok_entries[0] if ok_entries else None
            for e in narrative_entries:
                if e["label"] not in outliers:
                    continue
                scene = e["scene"]
                base_prompt = f"{style_for(scene['type'])}\n\nScene: {scene['image_prompt']}"
                drift_note = (
                    "\n\nIMPORTANT: A consistency reviewer flagged this image's illustration "
                    "touch (grain texture, line weight, shading approach, color saturation) as "
                    f"visibly different from the rest of this episode's images: {outliers[e['label']]}. "
                    "Match the same rendering technique used across the rest of the episode — "
                    "the reference image provided shows the correct touch to match."
                )
                retry_prompt = base_prompt + drift_note
                ref_path = ref_entry["path"] if ref_entry else None
                ok = gen_image(client, retry_prompt, e["path"], reference_image_path=ref_path)
                if ok:
                    qa = qa_image_with_gemini(client, e["path"], scene["image_prompt"], allow_text=False)
                    status = "OK" if qa["ok"] else "; ".join(qa["issues"])
                    print(f"   → {e['path'].name} 画風修正のうえ再生成 [QA: {status}]")
                    qa_results.append({"name": f"{e['path'].name}（画風ドリフト修正）",
                                        "ok": qa["ok"], "issues": qa["issues"]})
                else:
                    print(f"   → {e['path'].name} 画風修正の再生成に失敗", file=sys.stderr)
                    qa_results.append({"name": f"{e['path'].name}（画風ドリフト修正）",
                                        "ok": False, "issues": ["画像データなし"]})
        elif narrative_entries:
            print(f"✅ 画風ドリフトチェック: {len(narrative_entries)}枚 一貫性OK")

    if not args.no_thumbnail and not shorts_only and (args.thumbnail_only or args.scenes is None):
        thumb_prompt = f"{BASE_CONTEXT}\n\nThumbnail (16:9): {ep['thumbnail_prompt']}"
        thumb_path = out_dir / "thumbnail.png"
        r = generate_with_qa(client, thumb_prompt, ep["thumbnail_prompt"], thumb_path,
                              skip_qa=args.no_qa)
        r["name"] = "thumbnail.png"
        qa_results.append(r)
        headline = ep.get("thumbnail_headline")
        if headline and r["ok"]:
            composite_thumbnail_text(thumb_path, headline, ep.get("thumbnail_subcopy", ""))
            print(f"   → テキスト合成: 「{headline}」")

    if shorts_only or (not args.thumbnail_only and args.scenes is None):
        scenes_by_id = {sc["scene_id"]: sc for sc in ep["scenes"]}
        shorts_target_ids = None
        if args.shorts_scenes:
            shorts_target_ids = {int(s) for s in args.shorts_scenes.split(",")}
        for shorts in ep.get("shorts", []):
            mid = shorts["shorts_id"]
            for i, s in enumerate(shorts["scenes"], start=1):
                if shorts_target_ids is not None and i not in shorts_target_ids:
                    continue
                out_path = out_dir / f"shorts{mid}_S{i:02d}.png"

                # scene_idがあれば本編シーンの切り出し（再構成、独立生成しない）。
                # 無い場合は旧方式（Shorts専用のimage_promptから独立生成）に
                # フォールバックする（kl001〜kl013はscene_id未対応のため）。
                ref_scene_id = s.get("scene_id")
                main_scene = scenes_by_id.get(ref_scene_id) if ref_scene_id else None
                main_img_path = (out_dir / f"S{ref_scene_id:02d}.png") if ref_scene_id else None

                if main_scene is not None and main_img_path.exists():
                    image_prompt = main_scene["image_prompt"]
                    is_chart = main_scene["type"] == "data"
                    prompt = build_shorts_reframe_prompt(image_prompt)
                    r = generate_with_qa(client, prompt, image_prompt, out_path,
                                          aspect_ratio="9:16", skip_qa=args.no_qa,
                                          reference_image_path=main_img_path, allow_text=is_chart)
                else:
                    if ref_scene_id and main_scene is None:
                        print(f"⚠️  shorts{mid} scene{i}: scene_id={ref_scene_id} が本編scenesに"
                              f"見つかりません。独立生成にフォールバック", file=sys.stderr)
                    elif ref_scene_id and main_scene is not None:
                        print(f"⚠️  S{ref_scene_id:02d}.png が未生成のため独立生成にフォールバック "
                              f"（本編を先に生成すると再構成でコストを抑えられます）: {out_path.name}",
                              file=sys.stderr)
                    image_prompt = s.get("image_prompt") or (main_scene["image_prompt"] if main_scene else None)
                    if not image_prompt:
                        print(f"❌ shorts{mid} scene{i}: image_promptもscene_id参照先も"
                              f"見つかりません", file=sys.stderr)
                        sys.exit(1)
                    is_chart = s.get("style") == "chart" or (main_scene and main_scene["type"] == "data")
                    style = CHART_CONTEXT if is_chart else BASE_CONTEXT
                    prompt = f"{style}\n\nScene: {image_prompt}"
                    r = generate_with_qa(client, prompt, image_prompt, out_path,
                                          aspect_ratio="9:16", skip_qa=args.no_qa, allow_text=is_chart)
                r["name"] = out_path.name
                qa_results.append(r)

    if not args.no_qa and qa_results:
        ng = [r for r in qa_results if not r["ok"]]
        print(f"\n画像QA結果: {len(qa_results) - len(ng)}/{len(qa_results)} 件 OK")
        if ng:
            print(f"⚠️ 要確認: {len(ng)}件")
            for r in ng:
                print(f"  - {r['name']}: " + "; ".join(r["issues"]))
        qa_report_path = out_dir.parent / "image_qa_result.json"
        qa_report_path.write_text(
            json.dumps({"total": len(qa_results), "ng_count": len(ng), "results": qa_results},
                       ensure_ascii=False, indent=2)
        )

    print(f"\n完了。保存先: {out_dir}")


if __name__ == "__main__":
    main()
