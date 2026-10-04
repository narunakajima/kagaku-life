"""
kl_cast_gen.py — 掛け合い形式の二人（夢語り担当・ツッコミ担当）の立ち絵を生成する

2026-10-04、番組を「1話限りの架空の生活者の独白」から「固定の二人の掛け合い」に
変えたのに伴い追加（CLAUDE.md「掛け合い形式」、cast.json）。毎回シーン画像の中に
二人を描かせると顔がぶれるため、二人は一度だけ立ち絵（表情差分つき）を作って固定素材にし、
kl_video_gen.py が背景画像の上に合成する。

流れ:
  1. 各キャラクターの基準の立ち絵（neutral）を、マゼンタ単色の背景で生成する
  2. 基準画像を参照画像として渡し、同じ人物・同じ服・同じ構図のまま表情と手振りだけを
     変えた差分を生成する（独立生成すると顔が変わるため）
  3. 背景色との色距離でアルファを作って切り抜き、全差分の大きさ・位置を揃えて
     assets/cast/{role}_{expression}.png に保存する

使い方:
  python3 kl_cast_gen.py                       # 未生成の分だけ生成
  python3 kl_cast_gen.py --role dreamer --expr excited --force   # 1枚だけ作り直す
  python3 kl_cast_gen.py --rekey               # 生成済みの生画像から切り抜きだけやり直す

生画像（切り抜き前）は assets/cast/raw/ に残す（切り抜きの調整をやり直せるように）。
"""

import argparse
import json
import os
import sys
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image, ImageFilter

sys.stdout.reconfigure(line_buffering=True)

BASE_DIR = Path(__file__).parent
CAST_JSON = BASE_DIR / "cast.json"
OUT_DIR = BASE_DIR / "assets" / "cast"
RAW_DIR = OUT_DIR / "raw"

API_KEY = os.environ.get("GEMINI_API_KEY_KL") or os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-3.1-flash-image"

KEY_COLOR = (255, 0, 255)
# 立ち絵の最終サイズ（高さ固定、幅は内容に合わせて切り詰める）
SPRITE_H = 900

STYLE = (
    "Rich flat editorial illustration style with gentle shading gradients, naturalistic "
    "proportions and skin tones, muted sophisticated palette (slate blue, teal, warm gray, "
    "mustard) — the same house style as a cozy Japanese magazine illustration. Not "
    "photorealistic, not anime, not chibi. Authentically Japanese facial features. "
    "Clean crisp edges on the character outline. "
    "BACKGROUND: one perfectly flat, uniform, pure magenta color (#FF00FF) filling the entire "
    "background edge to edge — no gradient, no texture, no shadow, no floor, no props, "
    "no frame. The character must not contain any magenta or pink. No text."
)


def load_cast() -> dict:
    return json.loads(CAST_JSON.read_text(encoding="utf-8"))


def gen(client, prompt: str, out: Path, ref: Path = None) -> bool:
    contents = prompt
    if ref is not None:
        contents = [types.Part.from_bytes(data=ref.read_bytes(), mime_type="image/png"), prompt]
    resp = client.models.generate_content(
        model=MODEL, contents=contents,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(aspect_ratio="3:4"),
        ),
    )
    cand = resp.candidates[0] if resp.candidates else None
    for part in (cand.content.parts if cand and cand.content else []) or []:
        if part.inline_data:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(part.inline_data.data)
            return True
    return False


def base_prompt(char: dict) -> str:
    return (
        f"{STYLE}\n\nCharacter bust portrait (head to mid-chest), facing three-quarters toward "
        f"the {char['faces']} side of the frame, shoulders fully inside the frame, head near the "
        f"top with a small margin, body cut off cleanly at the bottom edge of the frame.\n"
        f"Character: {char['appearance']}\n"
        f"Expression and gesture: {char['expressions']['neutral']}"
    )


def variant_prompt(char: dict, expr: str) -> str:
    return (
        "This reference image shows a character. Produce the SAME character — identical face, "
        "hairstyle, hair color, glasses (if any), clothing, colors, art style, framing, scale, "
        "head position and camera angle — on the same perfectly flat pure magenta (#FF00FF) "
        "background. Change ONLY the facial expression and, if described, the hand/arm gesture "
        "(hands may come up into the frame, but keep them fully inside the frame).\n"
        f"New expression and gesture: {char['expressions'][expr]}\n"
        "No text, no speech bubbles, no effects lines, no background objects."
    )


def key_out(raw: Path, dst: Path, faces: str) -> None:
    """マゼンタ背景を色距離で透過させる。背景のわずかなムラを拾わないよう、
    外周の色の中央値を背景色とみなし、距離に応じて柔らかくアルファを落とす。"""
    img = Image.open(raw).convert("RGB")
    w, h = img.size
    px = img.load()
    border = [px[x, 0] for x in range(0, w, 7)] + [px[0, y] for y in range(0, h, 7)] + \
             [px[w - 1, y] for y in range(0, h, 7)]
    bg = tuple(sorted(c[i] for c in border)[len(border) // 2] for i in range(3))

    alpha = Image.new("L", (w, h))
    ap = alpha.load()
    out = Image.new("RGBA", (w, h))
    op = out.load()
    lo, hi = 90.0, 175.0
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            d = ((r - bg[0]) ** 2 + (g - bg[1]) ** 2 + (b - bg[2]) ** 2) ** 0.5
            a = 0 if d <= lo else (255 if d >= hi else int((d - lo) / (hi - lo) * 255))
            # マゼンタのにじみ（縁のピンク）を抑える: 赤と青が緑より突出している分を削る。
            # 縁から数ピクセル内側までピンクが乗るため、不透明な画素にも弱く適用する
            spill = min(r, b) - g
            if spill > 0:
                k = 0.9 if a < 255 else 0.5
                r -= int(spill * k)
                b -= int(spill * k)
            ap[x, y] = a
            op[x, y] = (r, g, b, a)
    # 縁のにじみ: アルファを1px収縮させてから少しぼかす（ピンクの縁取りを消し、縁をなめらかに）
    alpha_clean = alpha.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))
    alpha_clean = alpha_clean.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.7))
    out.putalpha(alpha_clean)
    # 差分ごとに切り抜き範囲を変えると（手を上げた差分だけ上端が高い等）頭の大きさが
    # ぶれるため、切り抜きはせず、生成画像の全体を同じ倍率で縮小する（差分は同じ構図で
    # 生成しているので、これで全差分の頭の位置と大きさが揃う）
    scale = SPRITE_H / out.height
    out = out.resize((max(1, int(out.width * scale)), SPRITE_H), Image.LANCZOS)
    dst.parent.mkdir(parents=True, exist_ok=True)
    out.save(dst)


def main():
    ap = argparse.ArgumentParser(description="掛け合いの二人の立ち絵を生成")
    ap.add_argument("--role", choices=["dreamer", "skeptic"])
    ap.add_argument("--expr")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--rekey", action="store_true", help="生画像から切り抜きだけやり直す")
    args = ap.parse_args()

    cast = load_cast()
    client = genai.Client(api_key=API_KEY) if not args.rekey else None
    for role in ("dreamer", "skeptic"):
        if args.role and role != args.role:
            continue
        char = cast[role]
        exprs = list(char["expressions"].keys())
        base_raw = RAW_DIR / f"{role}_neutral.png"
        for expr in exprs:
            if args.expr and expr != args.expr:
                continue
            raw = RAW_DIR / f"{role}_{expr}.png"
            dst = OUT_DIR / f"{role}_{expr}.png"
            if not args.rekey and (args.force or not raw.exists()):
                if expr == "neutral":
                    ok = gen(client, base_prompt(char), raw)
                else:
                    if not base_raw.exists():
                        print(f"❌ 基準画像がありません: {base_raw}", file=sys.stderr)
                        sys.exit(1)
                    ok = gen(client, variant_prompt(char, expr), raw, ref=base_raw)
                print(("✅ " if ok else "❌ ") + raw.name)
                if not ok:
                    continue
            if raw.exists():
                key_out(raw, dst, char["faces"])
                print(f"   切り抜き → {dst.relative_to(BASE_DIR)}")


if __name__ == "__main__":
    main()
