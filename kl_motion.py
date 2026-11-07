#!/usr/bin/env python3
"""資料カードとグラフの「動き」（2026-11-07、なるさんの指摘「イラスト中心で動きがなくてつまらない」）。

これまで check シーン（資料カード・グラフ）は1枚の静止画だった。ここでは同じ見た目のまま、
  1. 紙がふわっと上がって落ち着き、背景のカフェがゆっくり流れる
  2. 引用の強調（黄色のマーカー）が、読み上げに合わせて引かれる
  3. 箇条書きが1行ずつ現れる
  4. グラフ（scene.chart）は、棒が伸び、数字がカウントアップする
という動きを、フレームごとに Pillow で描いて動画クリップにする。文字・数字は今までどおり実フォントで描く
（AIに描かせない＝数字の捏造・誤字が起きない）。最後のフレームは静止画（assets/cards/*.png）と同じ。

使い方:
  kl_video_gen.py が make_motion_clip() を呼ぶ（--no-motion で従来の静止に戻せる）。
  python3 kl_motion.py preview --episode kl053 --scene 7 --out /tmp/x.mp4   # 1シーンだけ確認
"""

import argparse
import math
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter

import kl_dialogue as D

W0, H0 = 1408, 768
DRIFT = 1.05          # 背景は5%大きく作り、その中をゆっくり流す
PAPER_RISE = 16       # 紙が落ち着くまでに上がる量（px）
PAPER_SECONDS = 0.9
MARKER_AT, MARKER_SECONDS = 1.3, 0.8
CHART_AT, CHART_GROW, CHART_STAGGER = 0.9, 1.1, 0.35
CHART_CHIP = ("グラフ", (200, 112, 52))
BAR_COLOR = (92, 120, 160)
BAR_HIGHLIGHT = (232, 128, 48)
INK = (28, 34, 46)


def _clip01(x):
    return min(1.0, max(0.0, x))


def ease_out(x):
    x = _clip01(x)
    return 1 - (1 - x) ** 3


def ease_io(x):
    x = _clip01(x)
    return x * x * (3 - 2 * x)


# ── 紙の下地（背景・影・見出し） ─────────────────────────────────────

def _base(kind_label, kcol, source, W, H):
    """ぼかしたカフェ（bg）と、紙の層（影・紙・見出し。paper）を作る。"""
    bg = Image.open(D.CARD_BG_ASSET).convert("RGB").resize((W, H), Image.LANCZOS)
    bg = ImageEnhance.Brightness(bg.filter(ImageFilter.GaussianBlur(14))).enhance(0.62).convert("RGBA")
    x0, y0, x1, y1 = D.CARD_BOX
    paper = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((x0 + 8, y0 + 10, x1 + 8, y1 + 10), radius=18, fill=(0, 0, 0, 110))
    paper.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(8)))
    dr = ImageDraw.Draw(paper)
    dr.rounded_rectangle((x0, y0, x1, y1), radius=18, fill=(252, 250, 245, 255))
    fk = D._font(D.FONT_BOLD, 28)
    pad = 36
    kw = D._text_w(dr, kind_label, fk)
    dr.rounded_rectangle((x0 + pad, y0 + 26, x0 + pad + kw + 32, y0 + 26 + 46), radius=10, fill=kcol)
    dr.text((x0 + pad + 16, y0 + 31), kind_label, font=fk, fill=(255, 255, 255))
    sx = x0 + pad + kw + 32 + 18
    ss = 26
    while ss > 19 and D._text_w(dr, source, D._font(D.FONT_MEDIUM, ss)) > x1 - pad - sx:  # 資料名は1行に収める
        ss -= 1
    dr.text((sx, y0 + 34 + (26 - ss) // 2), source, font=D._font(D.FONT_MEDIUM, ss), fill=(70, 78, 92))
    top = y0 + 26 + 46 + 26
    dr.line((x0 + pad, top - 12, x1 - pad, top - 12), fill=kcol + (255,), width=3)
    return bg, paper, dr, top, pad


def _footer(dr, text):
    x0, y0, x1, y1 = D.CARD_BOX
    ff = D._font(D.FONT_MEDIUM, 22)
    fw = D._text_w(dr, text, ff)
    dr.text((x1 - 36 - fw, y1 - 22 - 28), text, font=ff, fill=(120, 126, 138))


# ── 資料カード ────────────────────────────────────────────────────────

def card_parts(card: dict, W: int = W0, H: int = H0) -> dict:
    """資料カードを層に分けて作る: bg / paper（引用の文字まで）/ marker（強調の長方形のリスト）/ items（1行ずつの層）。"""
    x0, y0, x1, y1 = D.CARD_BOX
    kind_label, kcol = D.CARD_KINDS.get(card.get("kind"), ("資料", (110, 118, 130)))
    bg, paper, dr, top, pad = _base(kind_label, kcol, card.get("source", ""), W, H)
    # 本文の大きさを決めてから描く（大きい字から試し、箇条書きは1項目1行に収まるまで縮める）
    max_w = (x1 - x0) - pad * 2
    footer_h = 40
    avail = (y1 - 22 - footer_h) - top
    quote, items = card.get("quote", ""), card.get("items") or []
    size_q, size_i = 50, 42
    while True:
        fq, fi = D._font(D.FONT_MEDIUM, size_q), D._font(D.FONT_MEDIUM, size_i)
        q_rows = D._wrap_chars(f"「{quote}」", fq, max_w) if quote else []
        i_rows = [D._wrap_chars(it, fi, max_w - 34) for it in items]
        h = (len(q_rows) * int(size_q * 1.45) + (18 if quote and items else 0)
             + sum(len(r) for r in i_rows) * int(size_i * 1.42))
        if (h <= avail and all(len(r) == 1 for r in i_rows)) or size_q <= 28:
            break
        if any(len(r) > 1 for r in i_rows) and size_i > 26:
            size_i -= 1
        elif h > avail:
            size_q -= 2
            size_i = max(26, min(size_i, size_q - 6))
        else:
            break
    # 箇条書きだけのカードで余白が大きいときは、行の間を広げて紙面に散らす
    i_lh = int(size_i * 1.42)
    n_i = sum(len(r) for r in i_rows)
    if not quote and n_i and h < avail * 0.7:
        i_lh = min(int(size_i * 2.0), int(avail * 0.8 / n_i))
        h = n_i * i_lh
    y = top + max(0, (avail - h) // 2)
    markers = []
    if quote:
        qt = f"「{quote}」"
        hl = card.get("highlight")
        hs = qt.find(hl) if hl else -1
        he = hs + len(hl) if hs >= 0 else -1
        lh = int(size_q * 1.45)
        for a, b in q_rows:
            row = qt[a:b]
            if hs >= 0 and a < he and b > hs:
                s0, s1 = max(a, hs), min(b, he)
                hx0 = x0 + pad + dr.textlength(qt[a:s0], font=fq)
                hx1 = x0 + pad + dr.textlength(qt[a:s1], font=fq)
                markers.append((hx0 - 2, y + int(size_q * 0.55), hx1 + 2, y + int(size_q * 1.18)))
            dr.text((x0 + pad, y), row, font=fq, fill=INK)
            y += lh
        y += 18
    item_layers = []
    for rows, it in zip(i_rows, items):
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        ld.ellipse((x0 + pad + 4, y + size_i // 2 - 6, x0 + pad + 16, y + size_i // 2 + 6), fill=kcol)
        for a, b in rows:
            ld.text((x0 + pad + 34, y), it[a:b], font=fi, fill=INK)
            y += i_lh
        item_layers.append(layer)
    # 足元: 原文か要約か、注記
    q_orig = quote and card.get("quote_type", "原文") == "原文"
    if quote and items:
        tag = "「…」は原文から引用、・は要約" if q_orig else "要約"
    else:
        tag = "原文から引用" if q_orig else "要約"
    _footer(dr, tag + (f"　{card['note']}" if card.get("note") else ""))
    return {"kind": "card", "bg": bg, "paper": paper, "markers": markers, "items": item_layers, "W": W, "H": H}


def _apply_marker(stack: Image.Image, rects: list, p: float) -> None:
    """黄色のマーカーを左から右へ p（0〜1）だけ引く。文字の上ではなく下に敷いたように見える（暗い方を残す）。"""
    if p <= 0 or not rects:
        return
    total = sum(r[2] - r[0] for r in rects)
    left = total * p
    for (a, b, c, d) in rects:
        w = c - a
        use = min(w, left)
        left -= use
        if use <= 0:
            break
        box = (int(a), int(b), int(a + use), int(d))
        if box[2] <= box[0]:
            continue
        reg = stack.crop(box)
        r, g, bl, al = reg.split()
        rgb = ImageChops.darker(Image.merge("RGB", (r, g, bl)), Image.new("RGB", reg.size, (255, 214, 90)))
        stack.paste(Image.merge("RGBA", (*rgb.split(), al)), box[:2])


def card_timing(parts: dict, dur: float) -> dict:
    """マーカーと箇条書きを出す時刻。台詞の長さ（dur）の中に散らす。"""
    n = len(parts["items"])
    has_marker = bool(parts["markers"])
    timing = {"marker_at": MARKER_AT, "items_at": []}
    if n:
        start = 2.4 if has_marker else 1.6
        end = max(start + n * 0.6, dur * 0.72)
        step = min(2.6, max(0.55, (end - start) / n))
        timing["items_at"] = [start + i * step for i in range(n)]
    return timing


def _drift_bg(bg_big: Image.Image, t: float, dur: float, W: int, H: int) -> Image.Image:
    u = _clip01(t / max(dur, 0.1))
    ox = int((bg_big.width - W) * u)
    oy = int((bg_big.height - H) * (0.5 + 0.5 * u) * 0.8)
    return bg_big.crop((ox, oy, ox + W, oy + H))


def _prepare_bg_big(bg: Image.Image) -> Image.Image:
    return bg.resize((int(bg.width * DRIFT), int(bg.height * DRIFT)), Image.LANCZOS)


def final_stack(parts: dict) -> Image.Image:
    """動きが終わった状態（静止画と同じ）の紙の層。"""
    stack = parts["paper"].copy()
    if parts.get("kind") == "card":
        _apply_marker(stack, parts["markers"], 1.0)
        for layer in parts["items"]:
            stack.alpha_composite(layer)
    else:
        stack = chart_stack(parts, 1e9)
    return stack


def render_static(parts: dict) -> Image.Image:
    out = parts["bg"].copy()
    out.alpha_composite(final_stack(parts))
    return out.convert("RGB")


def card_frame(parts: dict, bg_big: Image.Image, t: float, dur: float, timing: dict) -> Image.Image:
    stack = parts["paper"].copy()
    _apply_marker(stack, parts["markers"], ease_io((t - timing["marker_at"]) / MARKER_SECONDS))
    for layer, at in zip(parts["items"], timing["items_at"]):
        a = ease_out((t - at) / 0.45)
        if a <= 0:
            continue
        if a < 1:
            moved = Image.new("RGBA", layer.size, (0, 0, 0, 0))
            moved.paste(layer, (int(-28 * (1 - a)), 0))
            alpha = moved.getchannel("A").point(lambda v: int(v * a))
            moved.putalpha(alpha)
            layer = moved
        stack.alpha_composite(layer)
    return _compose(parts, bg_big, stack, t, dur)


def _compose(parts, bg_big, stack, t, dur):
    W, H = parts["W"], parts["H"]
    frame = _drift_bg(bg_big, t, dur, W, H).copy()
    dy = int(PAPER_RISE * (1 - ease_out(t / PAPER_SECONDS)))
    frame.alpha_composite(stack, (0, dy)) if dy else frame.alpha_composite(stack)
    return frame.convert("RGB")


# ── グラフ ────────────────────────────────────────────────────────────

def _fmt(value: float, decimals: int) -> str:
    return f"{value:,.{decimals}f}" if decimals else f"{int(round(value)):,}"


def _decimals(v) -> int:
    s = repr(v)
    return len(s.split(".")[1]) if "." in s and not s.endswith(".0") else 0


def chart_text(chart: dict) -> str:
    """グラフに画面で出す文字の全文（ファクトチェック・初見レビュー・確認書用）。"""
    parts = [chart.get("source", ""), chart.get("title", "")]
    if chart.get("kind", "bar") == "number":
        parts.append(f"{chart.get('value')}{chart.get('unit', '')} {chart.get('caption', '')}")
    else:
        unit = chart.get("unit", "")
        parts += [f"・{it['label']} {it['value']}{unit}" for it in chart.get("items") or []]
    if chart.get("note"):
        parts.append(f"※{chart['note']}")
    return " ".join(p for p in parts if p)


def chart_parts(chart: dict, W: int = W0, H: int = H0) -> dict:
    x0, y0, x1, y1 = D.CARD_BOX
    label, kcol = CHART_CHIP
    bg, paper, dr, top, pad = _base(label, kcol, chart.get("source", ""), W, H)
    note = chart.get("note")
    _footer(dr, "資料の数字をそのまま図にしたもの" + (f"　{note}" if note else ""))
    # タイトル
    title = chart.get("title", "")
    ts = 40
    while ts > 26 and D._text_w(dr, title, D._font(D.FONT_BOLD, ts)) > (x1 - x0) - pad * 2:
        ts -= 2
    dr.text((x0 + pad, top + 4), title, font=D._font(D.FONT_BOLD, ts), fill=INK)
    body_top = top + 4 + int(ts * 1.5)
    body_bottom = y1 - 22 - 40
    parts = {"kind": "chart", "bg": bg, "paper": paper, "W": W, "H": H, "chart": chart,
             "body": (x0 + pad, body_top, x1 - pad, body_bottom), "kcol": kcol}
    if chart.get("kind", "bar") == "number":
        return parts
    items = chart["items"]
    unit = chart.get("unit", "")
    fl = D._font(D.FONT_MEDIUM, 34)
    label_w = min(380, max(int(D._text_w(dr, it["label"], fl)) for it in items))
    decs = [_decimals(it["value"]) for it in items]
    fv = D._font(D.FONT_BOLD, 38)
    val_w = max(int(D._text_w(dr, _fmt(it["value"], d) + unit, fv)) for it, d in zip(items, decs)) + 16
    bx0 = parts["body"][0] + label_w + 22
    bx1 = parts["body"][2] - val_w
    vmax = float(chart.get("max") or max(it["value"] for it in items)) or 1.0
    n = len(items)
    row_h = (body_bottom - body_top) / n
    bar_h = int(min(row_h * 0.62, 64))
    hl = chart.get("highlight")
    rows = []
    for i, (it, d) in enumerate(zip(items, decs)):
        cy = body_top + row_h * (i + 0.5)
        is_hl = (hl == i) if isinstance(hl, int) else (hl == it["label"])
        rows.append({"label": it["label"], "value": it["value"], "dec": d, "cy": cy, "hl": is_hl,
                     "len": (bx1 - bx0) * it["value"] / vmax})
    parts.update({"rows": rows, "bx0": bx0, "bar_h": bar_h, "unit": unit, "fl": fl, "fv": fv, "label_w": label_w})
    # ラベルは動かさない（紙の層に描く）。軸の線も
    pd = ImageDraw.Draw(paper)
    for r in rows:
        ty = r["cy"] - int(34 * 0.6)
        pd.text((parts["body"][0], ty), r["label"], font=fl, fill=INK)
    pd.line((bx0 - 3, body_top + 4, bx0 - 3, body_bottom - 4), fill=(190, 194, 202, 255), width=3)
    return parts


def chart_stack(parts: dict, t: float) -> Image.Image:
    stack = parts["paper"].copy()
    dr = ImageDraw.Draw(stack)
    chart = parts["chart"]
    if chart.get("kind", "bar") == "number":
        _draw_number(parts, dr, t)
        return stack
    for i, r in enumerate(parts["rows"]):
        p = ease_out((t - CHART_AT - i * CHART_STAGGER) / CHART_GROW)
        if p <= 0:
            continue
        bx0, bh = parts["bx0"], parts["bar_h"]
        length = max(2, int(r["len"] * p))
        col = BAR_HIGHLIGHT if r["hl"] else BAR_COLOR
        dr.rounded_rectangle((bx0, r["cy"] - bh / 2, bx0 + length, r["cy"] + bh / 2), radius=8, fill=col)
        txt = _fmt(r["value"] * p, r["dec"]) + parts["unit"]
        dr.text((bx0 + length + 14, r["cy"] - 24), txt, font=parts["fv"], fill=INK)
    return stack


def _draw_number(parts, dr, t):
    chart = parts["chart"]
    x0, bt, x1, bb = parts["body"]
    value, unit = chart["value"], chart.get("unit", "")
    dec = _decimals(value)
    big = D._font(D.FONT_BOLD, 200)
    fu = D._font(D.FONT_BOLD, 80)
    final = _fmt(value, dec)
    wn, wu = D._text_w(dr, final, big), D._text_w(dr, unit, fu)
    total = wn + (16 + wu if unit else 0)
    cx = (x0 + x1) / 2
    xr = cx - total / 2 + wn
    p = ease_out((t - CHART_AT) / 1.5)
    cur = _fmt(value * p, dec)
    y = bt - 8
    if p > 0:
        dr.text((xr, y + 200), cur, font=big, fill=BAR_HIGHLIGHT if p >= 1 else INK, anchor="rs")
    if unit:
        dr.text((xr + 16, y + 200), unit, font=fu, fill=INK, anchor="ls")
    cap = chart.get("caption", "")
    if cap:
        fc = D._font(D.FONT_MEDIUM, 40)
        a = ease_out((t - CHART_AT - 1.0) / 0.5)
        if a > 0:
            dr.text((cx, y + 262), cap, font=fc, fill=INK if a >= 1 else (90, 96, 108), anchor="mt")


def chart_frame(parts: dict, bg_big: Image.Image, t: float, dur: float) -> Image.Image:
    return _compose(parts, bg_big, chart_stack(parts, t), t, dur)


# ── 静止画（最後のフレームと同じ）と動画クリップ ──────────────────────

def scene_parts(scene: dict, W: int = W0, H: int = H0):
    if scene.get("source_card"):
        return card_parts(scene["source_card"], W, H)
    if scene.get("chart"):
        return chart_parts(scene["chart"], W, H)
    return None


def has_motion(scene: dict) -> bool:
    return bool(scene.get("source_card") or scene.get("chart"))


def render_card_static(card: dict, out_path: Path, W: int = W0, H: int = H0) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    render_static(card_parts(card, W, H)).save(out_path, "PNG")


def render_chart_static(chart: dict, out_path: Path, W: int = W0, H: int = H0) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    render_static(chart_parts(chart, W, H)).save(out_path, "PNG")


def make_motion_clip(scene: dict, dur: float, dst: Path, fps: int = 24, ffmpeg: str = "ffmpeg",
                     W: int = W0, H: int = H0) -> bool:
    """check シーン（資料カード／グラフ）の動くクリップを dst に書く。対象外のシーンなら False。"""
    parts = scene_parts(scene, W, H)
    if parts is None:
        return False
    bg_big = _prepare_bg_big(parts["bg"])
    timing = card_timing(parts, dur) if parts["kind"] == "card" else None
    n = max(1, int(dur * fps))
    cmd = [ffmpeg, "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
           "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p", str(dst)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        for k in range(n):
            t = k / fps
            if parts["kind"] == "card":
                fr = card_frame(parts, bg_big, t, dur, timing)
            else:
                fr = chart_frame(parts, bg_big, t, dur)
            proc.stdin.write(fr.tobytes())
        proc.stdin.close()
        err = proc.stderr.read().decode("utf-8", "ignore")
        if proc.wait() != 0:
            raise RuntimeError(f"動きのクリップ生成に失敗: {err[-600:]}")
    finally:
        if proc.poll() is None:
            proc.kill()
    return True


def main():
    import json
    ap = argparse.ArgumentParser(description="資料カード・グラフの動きを1シーンだけ確認する")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("preview")
    p.add_argument("--episode", required=True)
    p.add_argument("--scene", type=int, required=True)
    p.add_argument("--seconds", type=float, default=0, help="省略時はシーンの音声の長さ＋1.5秒（なければ14秒）")
    p.add_argument("--out", required=True)
    a = ap.parse_args()
    ep = json.loads((D.BASE_DIR / "episodes" / f"{a.episode}.json").read_text())
    sc = next(s for s in ep["scenes"] if s["scene_id"] == a.scene)
    dur = a.seconds
    if not dur:
        ls = sc.get("lines") or []
        dur = (ls[-1]["t0"] + ls[-1]["dur"] + 1.5) if ls and "t0" in ls[-1] else 14.0
    ok = make_motion_clip(sc, dur, Path(a.out))
    print(f"{'書き出し' if ok else '対象外（source_card も chart も無い）'}: {a.out}（{dur:.1f}秒）")


if __name__ == "__main__":
    sys.exit(main())
