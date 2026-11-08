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

def _base(kind_label, kcol, source, W, H, bg_asset=None):
    """ぼかしたカフェ（bg）と、紙の層（影・紙・見出し。paper）を作る。
    bg_asset（例: "photos/kl055_S05_b"）を渡すと、カフェの代わりにその素材をぼかして下に敷く（scene.visuals 用、2026-11-08）"""
    bg_path = (D.BASE_DIR / "assets" / f"{bg_asset}.png") if bg_asset else D.CARD_BG_ASSET
    bg = Image.open(bg_path).convert("RGB").resize((W, H), Image.LANCZOS)
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
    kind_label, kcol = (D.CARD_KINDS.get(card.get("kind")) or D.SUMMARY_KINDS.get(card.get("kind"))
                        or ("資料", (110, 118, 130)))
    bg, paper, dr, top, pad = _base(kind_label, kcol, card.get("source", ""), W, H, card.get("bg_asset"))
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
    if card.get("footer"):  # まとめのカード（recap_card・step_card）は資料の引用ではないことを足元に書く
        tag = card["footer"]
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


def card_timing(parts: dict, dur: float, cues: dict = None) -> dict:
    """マーカーと箇条書きを出す時刻。台詞の長さ（dur）の中に散らす。"""
    n = len(parts["items"])
    has_marker = bool(parts["markers"])
    timing = {"marker_at": MARKER_AT, "items_at": []}
    if n:
        start = 2.4 if has_marker else 1.6
        end = max(start + n * 0.6, dur * 0.72)
        step = min(2.6, max(0.55, (end - start) / n))
        timing["items_at"] = [start + i * step for i in range(n)]
    # 台詞に合わせる指定（scene.motion_cues: marker＝マーカーを引く秒、items＝箇条書きを出す秒のリスト。シーンの頭から）
    cues = cues or {}
    if cues.get("marker") is not None:
        timing["marker_at"] = float(cues["marker"])
    for i, v in enumerate(cues.get("items") or []):
        if i < n:
            timing["items_at"][i] = float(v)
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
    _zoom_highlight(stack, parts["markers"], (t - timing["marker_at"] - MARKER_SECONDS) / 0.7)
    return _compose(parts, bg_big, stack, t, dur)


def _zoom_highlight(stack: Image.Image, rects: list, p: float, scale: float = 1.07) -> None:
    """引用の強調箇所を、マーカーが引き終わったあとにわずかに拡大して見せる（最大 1.07 倍）。
    動きの途中だけの見せ方で、静止画（最終フレーム）には適用しない。"""
    if p <= 0 or not rects:
        return
    if p >= 1:
        return          # 拡大して戻る（パルス）。最終フレームは等倍で静止画と一致する
    p = math.sin(math.pi * p)
    x0 = min(r[0] for r in rects) - 10
    y0 = min(r[1] for r in rects) - 10
    x1 = max(r[2] for r in rects) + 10
    y1 = max(r[3] for r in rects) + 10
    if (y1 - y0) > 220:
        return
    box = tuple(int(v) for v in (max(0, x0), max(0, y0), min(stack.width, x1), min(stack.height, y1)))
    reg = stack.crop(box)
    k = 1 + (scale - 1) * p
    nw, nh = int(reg.width * k), int(reg.height * k)
    big = reg.resize((nw, nh), Image.LANCZOS)
    stack.alpha_composite(big, (box[0] - (nw - reg.width) // 2, box[1] - (nh - reg.height) // 2))


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
    parts += [f"［注釈］{an['text']}" for an in chart.get("annotations") or [] if an.get("text")]
    if chart.get("note"):
        parts.append(f"※{chart['note']}")
    return " ".join(p for p in parts if p)


def chart_parts(chart: dict, W: int = W0, H: int = H0) -> dict:
    x0, y0, x1, y1 = D.CARD_BOX
    label, kcol = CHART_CHIP
    bg, paper, dr, top, pad = _base(label, kcol, chart.get("source", ""), W, H, chart.get("bg_asset"))
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
    if chart.get("kind") == "line":
        _line_parts(parts, dr, items, unit, body_bottom)
        return parts
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


def _line_parts(parts, dr, items, unit, body_bottom):
    """折れ線: 点の位置を決め、横軸のラベルと軸線は紙の層（動かさない）に描く。"""
    bx0, bt, bx1, _ = parts["body"]
    paper = parts["paper"]
    fl = D._font(D.FONT_MEDIUM, 30)
    fv = D._font(D.FONT_BOLD, 34)
    chart = parts["chart"]
    top, bottom = bt + 44, body_bottom - 46          # 値ラベルの余白と、横軸ラベルの余白
    lo = float(chart.get("min", 0))
    vmax = float(chart.get("max") or max(it["value"] for it in items))
    span = (vmax - lo) or 1.0
    n = len(items)
    left, right = bx0 + 50, bx1 - 50
    pts = []
    hl = chart.get("highlight")
    for i, it in enumerate(items):
        x = left + (right - left) * (i / (n - 1))
        y = bottom - (bottom - top) * ((it["value"] - lo) / span)
        is_hl = (hl == i) if isinstance(hl, int) else (hl == it["label"])
        pts.append({"x": x, "y": y, "label": it["label"], "value": it["value"], "dec": _decimals(it["value"]), "hl": is_hl})
    pd = ImageDraw.Draw(paper)
    pd.line((left - 24, bottom + 6, right + 24, bottom + 6), fill=(190, 194, 202, 255), width=3)
    for p in pts:
        pd.text((p["x"], bottom + 14), p["label"], font=fl, fill=INK, anchor="mt")
    parts.update({"pts": pts, "unit": unit, "fv": fv})


def _target_index(chart: dict, target) -> int:
    items = chart["items"]
    return target if isinstance(target, int) else [i["label"] for i in items].index(target)


def _anchor_box(parts: dict, idx: int):
    """注釈の囲みで囲む範囲（値の文字）の (cx, cy, rx, ry) と、その値の文字を描き終わる時刻のための番号。"""
    fv = parts["fv"]
    tmp = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    if parts["chart"].get("kind") == "line":
        p = parts["pts"][idx]
        txt = _fmt(p["value"], p["dec"]) + parts["unit"]
        w = D._text_w(tmp, txt, fv)
        return p["x"], p["y"] - 41, w / 2 + 20, 32
    r = parts["rows"][idx]
    txt = _fmt(r["value"], r["dec"]) + parts["unit"]
    w = D._text_w(tmp, txt, fv)
    return parts["bx0"] + r["len"] + 14 + w / 2, r["cy"], w / 2 + 20, 32


def _annotations_start(parts: dict) -> float:
    n = len(parts.get("rows") or parts.get("pts") or [])
    return parts.get("chart_at", CHART_AT) + max(0, n - 1) * CHART_STAGGER + CHART_GROW + 0.5


def _draw_annotations(parts: dict, dr, t: float) -> None:
    """注釈の出現（台詞の順）: 値の周りに囲みが描かれ、矢印が伸びて短い一言が出る。注釈ごとに 1.4 秒ずつずらす。
    scene の chart.annotations: [{"target": 番号かラベル, "text": 12字以内, "at": 出す秒（省略可）}]"""
    ann = parts["chart"].get("annotations") or []
    t0 = _annotations_start(parts)
    for k, an in enumerate(ann):
        at = float(an.get("at", t0 + k * 1.4))
        cx, cy, rx, ry = _anchor_box(parts, _target_index(parts["chart"], an["target"]))
        pc = ease_io((t - at) / 0.6)
        if pc <= 0:
            continue
        col = (214, 60, 52)
        # 囲み: 上から時計回りに一周描く（PIL の arc は 3時の位置が 0 度）
        dr.arc((cx - rx, cy - ry, cx + rx, cy + ry), start=-90, end=-90 + 360 * pc, fill=col, width=5)
        text = an.get("text", "")
        pa = ease_out((t - at - 0.5) / 0.5)
        if text and pa > 0:
            ft = D._font(D.FONT_BOLD, 32)
            tw = D._text_w(dr, text, ft)
            x0, bt, x1, _ = parts["body"]
            tx = min(max(cx, x0 + tw / 2 + 6), x1 - tw / 2 - 6)
            ty = max(bt + 6, cy - ry - 74)
            ay0, ay1 = ty + 40, cy - ry - 4          # 文字の下から囲みの上へ、矢印が伸びる
            if ay1 <= ay0:
                # 上に余白がない（折れ線の高い点など）: 囲みの左に一言を置き、横向きの矢印を伸ばす
                ty = cy - 18
                tx = max(x0 + tw / 2 + 6, cx - rx - 70 - tw / 2)
                ax0, ax1 = tx + tw / 2 + 8, cx - rx - 4
                if ax1 > ax0:
                    ex = ax0 + (ax1 - ax0) * pa
                    dr.line((ax0, cy, ex, cy), fill=col, width=5)
                    if pa >= 1:
                        dr.polygon([(ax1 + 2, cy), (ax1 - 14, cy - 9), (ax1 - 14, cy + 9)], fill=col)
            elif ay1 > ay0:
                ey = ay0 + (ay1 - ay0) * pa
                dr.line((cx, ay0, cx, ey), fill=col, width=5)
                if pa >= 1:
                    dr.polygon([(cx, ay1 + 2), (cx - 9, ay1 - 14), (cx + 9, ay1 - 14)], fill=col)
            dr.text((tx, ty), text, font=ft, fill=col if pa >= 1 else (180, 90, 84), anchor="mt")


def chart_stack(parts: dict, t: float) -> Image.Image:
    stack = parts["paper"].copy()
    dr = ImageDraw.Draw(stack)
    chart = parts["chart"]
    if chart.get("kind", "bar") == "number":
        _draw_number(parts, dr, t)
        return stack
    if chart.get("kind") == "line":
        _draw_line(parts, dr, t)
        _draw_annotations(parts, dr, t)
        return stack
    for i, r in enumerate(parts["rows"]):
        p = ease_out((t - parts.get("chart_at", CHART_AT) - i * CHART_STAGGER) / CHART_GROW)
        if p <= 0:
            continue
        bx0, bh = parts["bx0"], parts["bar_h"]
        length = max(2, int(r["len"] * p))
        col = BAR_HIGHLIGHT if r["hl"] else BAR_COLOR
        dr.rounded_rectangle((bx0, r["cy"] - bh / 2, bx0 + length, r["cy"] + bh / 2), radius=8, fill=col)
        txt = _fmt(r["value"] * p, r["dec"]) + parts["unit"]
        dr.text((bx0 + length + 14, r["cy"] - 24), txt, font=parts["fv"], fill=INK)
    _draw_annotations(parts, dr, t)
    return stack


def _draw_line(parts, dr, t):
    """折れ線が左から右へ伸び、点の値が順に出る。"""
    pts = parts["pts"]
    p = ease_io((t - parts.get("chart_at", CHART_AT)) / 1.8)
    n = len(pts)
    pos = p * (n - 1)               # 何番目の点まで線が届いたか（小数）
    col = BAR_COLOR
    for i in range(n - 1):
        f = _clip01(pos - i)
        if f <= 0:
            break
        a, b = pts[i], pts[i + 1]
        dr.line((a["x"], a["y"], a["x"] + (b["x"] - a["x"]) * f, a["y"] + (b["y"] - a["y"]) * f), fill=col, width=7, joint="curve")
    for i, q in enumerate(pts):
        if pos < i - 1e-6:
            break
        r = 12 if q["hl"] else 9
        dr.ellipse((q["x"] - r, q["y"] - r, q["x"] + r, q["y"] + r), fill=BAR_HIGHLIGHT if q["hl"] else col)
        dr.text((q["x"], q["y"] - 24), _fmt(q["value"], q["dec"]) + parts["unit"], font=parts["fv"], fill=INK, anchor="mb")


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
    p = ease_out((t - parts.get("chart_at", CHART_AT)) / 1.5)
    cur = _fmt(value * p, dec)
    y = bt - 8
    if p > 0:
        dr.text((xr, y + 200), cur, font=big, fill=BAR_HIGHLIGHT if p >= 1 else INK, anchor="rs")
    if unit:
        dr.text((xr + 16, y + 200), unit, font=fu, fill=INK, anchor="ls")
    cap = chart.get("caption", "")
    if cap:
        fc = D._font(D.FONT_MEDIUM, 40)
        a = ease_out((t - parts.get("chart_at", CHART_AT) - 1.0) / 0.5)
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
    cues = dict(scene.get("motion_cues") or {})
    # 完成形で静止する時間を残すため、指定の秒は「シーンの長さ − 3.5秒」までに切り詰める（昇順にもそろえる）
    cap = max(0.0, dur - 3.5)
    if cues.get("marker") is not None:
        cues["marker"] = min(float(cues["marker"]), max(0.0, cap - MARKER_SECONDS))
    if cues.get("items"):
        cues["items"] = [min(float(v), cap) for v in sorted(cues["items"])]
    if cues.get("chart") is not None:
        # グラフは「伸びる時間＋注釈の時間」も引く（完成形で2秒以上静止させる）
        ch = scene.get("chart") or {}
        n = len(parts.get("rows") or parts.get("pts") or [])
        grow = {"line": 1.8, "number": 2.0}.get(ch.get("kind", "bar"), max(0, n - 1) * CHART_STAGGER + CHART_GROW)
        na = len(ch.get("annotations") or [])
        ann = (0.5 + (na - 1) * 1.4 + 1.1) if na else 0.0
        cues["chart"] = max(0.0, min(float(cues["chart"]), dur - 2.0 - grow - ann))
    timing = card_timing(parts, dur, cues) if parts["kind"] == "card" else None
    if parts["kind"] != "card" and cues.get("chart") is not None:
        parts["chart_at"] = cues["chart"]
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
    d = sub.add_parser("demo", help="見本のグラフ（bar／line／number、注釈つき）を書き出して動きを確認する")
    d.add_argument("--kind", choices=["bar", "line", "number"], default="line")
    d.add_argument("--seconds", type=float, default=12.0)
    d.add_argument("--out", required=True, help="出力の mp4（同名の .png に最後のフレーム）")
    s2 = sub.add_parser("subtitle-demo", help="字幕のポップイン（3フレーム＋最終）と数字の黄色を PNG で書き出す")
    s2.add_argument("--text", default="42.5%の人が3年以内に変わった")
    s2.add_argument("--outdir", required=True)
    s3 = sub.add_parser("ambient-demo", help="イラストの光の揺らぎ（ken burns + ambient）を1枚の画像から2秒だけ作る")
    s3.add_argument("--image", required=True)
    s3.add_argument("--out", required=True)
    s4 = sub.add_parser("focus-demo", help="話者フォーカス（話し手 1.07 倍）の立ち絵トラックを短い疑似イベントで作り、1フレームずつ PNG にする")
    s4.add_argument("--outdir", required=True)
    a = ap.parse_args()
    if a.cmd == "focus-demo":
        import tempfile
        cast = D.load_cast()
        od = Path(a.outdir)
        od.mkdir(parents=True, exist_ok=True)
        base = {"mode": "normal", "chart": False, "badge": None, "stamps": None, "cta": None,
                "exprs": {"dreamer": "neutral", "skeptic": "neutral"}, "text": "テスト"}
        events = [(0.0, dict(base, speaker="dreamer")), (2.0, dict(base, speaker="skeptic"))]
        with tempfile.TemporaryDirectory() as tmp:
            tp = Path(tmp)
            sp = D.build_sprite_tracks(events, 4.0, D.MAIN_LAYOUT, cast, tp, 24, "ffmpeg", talk=False, focus=True)
            for t in sp["tracks"]:
                print("  トラック", t["role"], "x=", t["x"], "y=", t["y"])
            ins = []
            chain, prev, k = [], "bg", 1
            for t in sp["tracks"]:
                i2, flt, used = D.sprite_track_filter(t, k, 24, f"s{k}")
                ins += i2
                chain.append(f"{flt};[{prev}][s{k}]overlay={t['x']}:{t['y']}:eof_action=pass[o{k}]")
                prev, k = f"o{k}", k + used
            for name, ts in (("dreamer_speaks", 1.0), ("skeptic_speaks", 3.0)):
                cmd = (["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=0x3c465a:s=1408x768:r=24"] + ins
                       + ["-filter_complex", chain[0].replace("[bg]", "[0:v]") if len(chain) == 1 else
                          ";".join(chain).replace("[bg]", "[0:v]"),
                          "-map", f"[{prev}]", "-ss", str(ts), "-frames:v", "1", str(od / f"focus_{name}.png")])
                r = subprocess.run(cmd, capture_output=True, text=True)
                if r.returncode != 0:
                    print(r.stderr[-800:])
                    return 1
        print(f"書き出し: {od}/focus_dreamer_speaks.png, focus_skeptic_speaks.png")
        return 0
    if a.cmd == "subtitle-demo":
        cast = D.load_cast()
        bank = D.SpriteBank(cast)
        od = Path(a.outdir)
        od.mkdir(parents=True, exist_ok=True)
        for name, extra in [("pop1", {"pop": D.POP_SCALES[0]}), ("pop3", {"pop": D.POP_SCALES[2]}), ("final", {})]:
            st = {"mode": "normal", "chart": False, "badge": None, "stamps": None, "cta": None, "speaker": "dreamer",
                  "exprs": {"dreamer": "neutral", "skeptic": "neutral"}, "text": a.text, "kw": True, **extra}
            im = D.render_layer(st, D.MAIN_LAYOUT, cast, bank, sprites=False, bar=False, nameplates=False)
            bg = Image.new("RGBA", im.size, (60, 70, 90, 255))
            bg.alpha_composite(im)
            bg.convert("RGB").save(od / f"subtitle_{name}.png")
        print(f"書き出し: {od}/subtitle_pop1.png, subtitle_pop3.png, subtitle_final.png")
        return 0
    if a.cmd == "ambient-demo":
        import kl_video_gen as V
        V.make_ken_burns(Path(a.image), Path(a.out), 2.0, "zoom_in", ambient=True)
        print(f"書き出し: {a.out}")
        return 0
    if a.cmd == "demo":
        base = {"source": "見本の資料（2026-11-07）", "title": "見本のグラフ", "unit": "%", "highlight": 2,
                "annotations": [{"target": 2, "text": "ここが転機"}]}
        if a.kind == "number":
            base = {"source": base["source"], "title": "見本の数字", "kind": "number", "value": 42.5, "unit": "%",
                    "caption": "見本のキャプション"}
        else:
            base["kind"] = a.kind
            base["items"] = [{"label": "2021", "value": 12}, {"label": "2022", "value": 18.5},
                             {"label": "2023", "value": 41}, {"label": "2024", "value": 57}]
        out = Path(a.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        render_chart_static(base, out.with_suffix(".png"))
        make_motion_clip({"chart": base}, a.seconds, out)
        print(f"書き出し: {out}（{a.seconds:.1f}秒）と {out.with_suffix('.png')}")
        return 0
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
