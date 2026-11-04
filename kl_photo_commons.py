#!/usr/bin/env python3
"""
kl_photo_commons.py — Wikimedia Commons の写真を、ライセンスと出所を記録して台本の素材にする（2026-11-04）

実在の製品・機体の見た目が話の中心の回で、想像で描いたイメージ図の代わりに、ライセンスが明記された実物の写真を使う。
使えるのは、パブリックドメイン／CC0／CC BY／CC BY-SA だけ（NC・ND・GFDLのみ・フェアユース等は使わない）。
公式サイトや報道の写真は、許諾なく使わない（kl-new.md STEP2）。

使い方:
  # 1. 探す（ライセンスが使えるものに ○、使えないものに × が付く）
  python3 kl_photo_commons.py search --query "Tesla Optimus"

  # 2. 取り込む（assets/photos/{ep}_S{NN}.png と出所の記録 .json を作る。エピソードJSONはまだ変えない）
  python3 kl_photo_commons.py fetch --episode kl052 --scene 7 --file "File:Unitree G1.jpg" --note "2025年の機体"

  # 3. エピソードJSONに反映する（シーンの image_asset・real_photo と、概要欄の写真クレジット）
  python3 kl_photo_commons.py fetch ... --apply        # 取り込みと反映を一度に
  python3 kl_photo_commons.py apply --episode kl052 --scene 7   # 取り込み済みを反映だけ

  # 4. 記録と概要欄の整合を確認する
  python3 kl_photo_commons.py audit --episode kl052

注意:
  - 写真が、発表の時点の機体と同じとは限らない。古い世代・別の型なら --note で画面に注記する。
  - 人の顔が写る写真（肖像）は、このツールの対象外。使うなら制作者に確認する（Commons の Restrictions に出る）。
  - ライセンスの解釈で判断が分かれる使い方は、専門家に確認する。
"""

from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

BASE_DIR = Path(__file__).parent
PHOTO_DIR = BASE_DIR / "assets" / "photos"
API = "https://commons.wikimedia.org/w/api.php"
UA = "kagaku-life-research/1.0 (https://kagaku-life.com; naru.nakajima@gmail.com)"
MAX_BYTES = 20 * 1024 * 1024
MIN_WIDTH = 1280
W, H = 1920, 1080
FONT_MEDIUM = Path("/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc")

# 使えるライセンス（LicenseShortName の正規化後）。NC・ND・GFDLのみ・フェアユース・不明は使わない
ALLOWED = re.compile(r"^(cc0|public domain|pd\b|cc[ -]by(-sa)?[ -][0-9.]+)", re.I)
DENIED = re.compile(r"(\bnc\b|-nc|\bnd\b|-nd|gfdl|fair use|non-free|unknown)", re.I)
# 表示が必須のライセンス（CC BY / CC BY-SA）。CC0・パブリックドメインは表示不要だが、出所は常に画面に出す
NEEDS_ATTRIBUTION = re.compile(r"^cc[ -]by", re.I)

CREDIT_HEADER = "【写真クレジット】"


def _get(url: str, params: dict | None = None) -> bytes:
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise RuntimeError(f"ファイルが大きすぎます（{MAX_BYTES // 1024 // 1024}MB超）: {url}")
    return data


def _api(params: dict) -> dict:
    p = {"format": "json", "formatversion": "2", **params}
    return json.loads(_get(API, p))


def _strip(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s or ""))).strip()


def license_ok(short: str) -> bool:
    short = (short or "").strip()
    return bool(ALLOWED.match(short)) and not DENIED.search(short)


PERSON_CAT = re.compile(r"people|person|portrait|\bmen\b|\bwomen\b|\bmale\b|\bfemale\b|businesspe|speakers|ceos|billionaires|"
                        r"engineers|scientists|politicians|presidents|crowd|audience|children|\bboys\b|\bgirls\b", re.I)


def is_person(i: dict) -> bool:
    """人物の肖像の可能性（Commons の制限表示、またはカテゴリー名）。完全ではないので、目視でも確認する"""
    return bool(re.search(r"person|portrait|identif", i["restrictions"], re.I)
                or any(PERSON_CAT.search(c) for c in i.get("categories", [])))


def _info(page: dict) -> dict:
    ii = (page.get("imageinfo") or [{}])[0]
    m = ii.get("extmetadata") or {}
    v = lambda k: _strip((m.get(k) or {}).get("value", ""))  # noqa: E731
    return {
        "title": page.get("title", ""),
        "page_url": ii.get("descriptionurl", ""),
        "orig_url": ii.get("url", ""),
        "thumb_url": ii.get("thumburl") or ii.get("url", ""),
        "width": ii.get("width", 0),
        "height": ii.get("height", 0),
        "mime": ii.get("mime", ""),
        "license": v("LicenseShortName"),
        "license_url": v("LicenseUrl"),
        "author": v("Artist"),
        "credit": v("Credit"),
        "restrictions": v("Restrictions"),
        "attribution_required": v("AttributionRequired"),
        "date": v("DateTimeOriginal"),
        "categories": [c.get("title", "") for c in (page.get("categories") or [])],
    }


def cmd_search(a):
    d = _api({"action": "query", "generator": "search", "gsrsearch": f"{a.query} filetype:bitmap",
              "gsrnamespace": "6", "gsrlimit": str(a.limit),
              "iiprop": "url|size|mime|extmetadata", "iiurlwidth": str(W),
              "prop": "imageinfo|categories", "cllimit": "max"})
    pages = sorted((d.get("query") or {}).get("pages") or [], key=lambda p: p.get("index", 0))
    if not pages:
        print("見つかりませんでした。別の語（英語の製品名など）で試してください。")
        return
    print(f"検索: {a.query}（○=ライセンスが使える ×=使えない。小さい画像は幅{MIN_WIDTH}px未満）")
    for p in pages:
        i = _info(p)
        mark = "○" if license_ok(i["license"]) else "×"
        small = "  ※小さい" if i["width"] < MIN_WIDTH else ""
        warn = f"  ※制限: {i['restrictions']}" if i["restrictions"] else ""
        if is_person(i):
            warn += "  ※人物の写真の可能性（使う前に制作者の確認が必要）"
        print(f"{mark} {i['title']}  [{i['license'] or '不明'}]  {i['width']}x{i['height']}{small}{warn}")
        print(f"    作者: {i['author'][:60] or '不明'} / 撮影: {i['date'][:30] or '不明'}")
        print(f"    {i['page_url']}")


def _fetch_info(title: str) -> dict:
    if not title.startswith("File:"):
        title = "File:" + title
    d = _api({"action": "query", "titles": title, "prop": "imageinfo|categories", "cllimit": "max",
              "iiprop": "url|size|mime|extmetadata", "iiurlwidth": str(W)})
    pages = (d.get("query") or {}).get("pages") or []
    if not pages or pages[0].get("missing"):
        sys.exit(f"❌ Commons にそのファイルがありません: {title}")
    return _info(pages[0])


def _credit_text(i: dict) -> str:
    lic = i["license"]
    if NEEDS_ATTRIBUTION.match(lic):
        return f"写真: {i['author'] or '作者不明'}／{lic}／Wikimedia Commons"
    return f"写真: Wikimedia Commons（{lic}）"


def _compose(photo: Image.Image, credit: str, note: str) -> Image.Image:
    photo = photo.convert("RGB")
    # 背景: 写真を全面に引き伸ばして強くぼかし、少し暗くする。前景: 写真を全体が見える大きさで中央に置く
    cover = max(W / photo.width, H / photo.height)
    bg = photo.resize((round(photo.width * cover), round(photo.height * cover)), Image.LANCZOS)
    bg = bg.crop(((bg.width - W) // 2, (bg.height - H) // 2, (bg.width - W) // 2 + W, (bg.height - H) // 2 + H))
    bg = bg.filter(ImageFilter.GaussianBlur(40))
    bg = Image.eval(bg, lambda v: int(v * 0.55))
    contain = min(W / photo.width, H / photo.height)
    fg = photo.resize((round(photo.width * contain), round(photo.height * contain)), Image.LANCZOS)
    canvas = bg.copy()
    canvas.paste(fg, ((W - fg.width) // 2, (H - fg.height) // 2))
    # クレジット（右下の帯。出所は常に画面に出す）
    d = ImageDraw.Draw(canvas, "RGBA")
    font = ImageFont.truetype(str(FONT_MEDIUM), 26)
    lines = [credit] + ([note] if note else [])
    wmax = max(d.textlength(t, font=font) for t in lines)
    pad, lh = 14, 36
    x1, y1 = W - 24, H - 24
    x0, y0 = x1 - wmax - pad * 2, y1 - lh * len(lines) - pad * 2 + 6
    d.rounded_rectangle((x0, y0, x1, y1), radius=10, fill=(0, 0, 0, 170))
    for n, t in enumerate(lines):
        d.text((x0 + pad, y0 + pad - 2 + n * lh), t, font=font, fill=(255, 255, 255, 255))
    return canvas


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(BASE_DIR))
    except ValueError:
        return str(p)


def _paths(ep: str, scene: int) -> tuple[Path, Path]:
    stem = f"{ep}_S{scene:02d}"
    return PHOTO_DIR / f"{stem}.png", PHOTO_DIR / f"{stem}.json"


def cmd_fetch(a):
    i = _fetch_info(a.file)
    print(f"{i['title']}  [{i['license'] or '不明'}]  {i['width']}x{i['height']}  作者: {i['author'][:50] or '不明'}")
    if not license_ok(i["license"]):
        sys.exit(f"❌ このライセンスは使えません: {i['license'] or '不明'}（使えるのはパブリックドメイン・CC0・CC BY・CC BY-SA）")
    if i["width"] < MIN_WIDTH and not a.allow_small:
        sys.exit(f"❌ 画像が小さすぎます（幅{i['width']}px < {MIN_WIDTH}px）。ぼやけるため使いません（--allow-small で許可）")
    if i["restrictions"]:
        print(f"⚠️  Commons の制限表示: {i['restrictions']}（商標・肖像など。人の顔が写る場合は制作者に確認する）")

    if is_person(i) and not a.allow_person:
        sys.exit("❌ 人物の写真の可能性があります（Commons の制限表示またはカテゴリー）。使う前に制作者の確認が必要です"
                 "（確認済みなら --allow-person を付ける。人物は台詞の話題と無関係に使わない・悪く見える使い方をしない）。"
                 "この判定は完全ではないので、製品や街の写真でも、人が大きく写っていないか目視で確認する")
    data = _get(i["thumb_url"])
    photo = Image.open(io.BytesIO(data))
    credit = _credit_text(i)
    out_png, out_json = _paths(a.episode, a.scene)
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    _compose(photo, credit, a.note or "").save(out_png)
    rec = {**i, "episode": a.episode, "scene_id": a.scene, "credit_on_screen": credit, "note": a.note or "",
           "retrieved": date.today().isoformat(), "downloaded_sha256": hashlib.sha256(data).hexdigest(),
           "needs_attribution": bool(NEEDS_ATTRIBUTION.match(i["license"]))}
    out_json.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ {_rel(out_png)}（1920x1080。クレジット: {credit}）\n   記録: {_rel(out_json)}")
    if a.apply:
        cmd_apply(a)
    else:
        print(f"   エピソードJSONへは未反映。反映: python3 kl_photo_commons.py apply --episode {a.episode} --scene {a.scene}")


def _credit_line(rec: dict) -> str:
    name = rec["title"].removeprefix("File:")
    by = f" / {rec['author']}" if rec.get("author") and rec.get("needs_attribution") else ""
    return f"S{rec['scene_id']:02d}: 「{name}」{by} / {rec['license']} / {rec['page_url']}"


def cmd_apply(a):
    out_png, out_json = _paths(a.episode, a.scene)
    if not out_json.exists():
        sys.exit(f"❌ 取り込み済みの記録がありません: {out_json}（先に fetch）")
    rec = json.loads(out_json.read_text(encoding="utf-8"))
    ep_path = BASE_DIR / "episodes" / f"{a.episode}.json"
    ep = json.loads(ep_path.read_text(encoding="utf-8"))
    scene = next((s for s in ep["scenes"] if s["scene_id"] == a.scene), None)
    if scene is None:
        sys.exit(f"❌ {a.episode} に S{a.scene} がありません")
    scene["image_asset"] = f"photos/{a.episode}_S{a.scene:02d}"
    scene["real_photo"] = True
    scene.pop("shows_product", None)  # 想像のイメージ図ではないので、「イメージ図」の注記の対象から外す
    desc = ep.get("youtube_description", "")
    line = _credit_line(rec)
    if line not in desc:
        if CREDIT_HEADER not in desc:
            desc = desc.rstrip() + f"\n\n{CREDIT_HEADER}\n"
        else:
            desc = desc.rstrip() + "\n"
        desc += line + "\n"
    ep["youtube_description"] = desc
    ep_path.write_text(json.dumps(ep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"✅ {a.episode} の S{a.scene} に反映（image_asset・real_photo、概要欄の写真クレジット）")


def cmd_audit(a):
    ep = json.loads((BASE_DIR / "episodes" / f"{a.episode}.json").read_text(encoding="utf-8"))
    desc = ep.get("youtube_description", "")
    errs, n = [], 0
    for s in ep["scenes"]:
        if not s.get("real_photo"):
            continue
        n += 1
        sid = s["scene_id"]
        png, js = _paths(a.episode, sid)
        if not png.exists() or not js.exists():
            errs.append(f"S{sid}: 写真または出所の記録が無い（{png.name} / {js.name}）")
            continue
        rec = json.loads(js.read_text(encoding="utf-8"))
        if not license_ok(rec.get("license", "")):
            errs.append(f"S{sid}: 使えないライセンス: {rec.get('license')}")
        if _credit_line(rec) not in desc:
            errs.append(f"S{sid}: 概要欄に写真クレジットが無い")
        if s.get("image_asset") != f"photos/{a.episode}_S{sid:02d}":
            errs.append(f"S{sid}: image_asset が写真を指していない")
    print(f"写真シーン: {n}件")
    for e in errs:
        print("❌", e)
    if errs:
        sys.exit(1)
    print("✅ 記録・概要欄・image_asset の整合OK")


def main():
    p = argparse.ArgumentParser(description="Wikimedia Commons の写真を、ライセンスと出所を記録して使う")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search")
    s.add_argument("--query", required=True)
    s.add_argument("--limit", type=int, default=12)
    s.set_defaults(fn=cmd_search)
    f = sub.add_parser("fetch")
    f.add_argument("--episode", required=True)
    f.add_argument("--scene", type=int, required=True)
    f.add_argument("--file", required=True, help='例: "File:Unitree G1.jpg"')
    f.add_argument("--note", default="", help="画面に出す注記（例: 2025年の機体）")
    f.add_argument("--apply", action="store_true")
    f.add_argument("--allow-small", action="store_true")
    f.add_argument("--allow-person", action="store_true", help="人物の肖像に関わる制限表示がある写真を、制作者の確認後に使う")
    f.set_defaults(fn=cmd_fetch)
    ap = sub.add_parser("apply")
    ap.add_argument("--episode", required=True)
    ap.add_argument("--scene", type=int, required=True)
    ap.set_defaults(fn=cmd_apply)
    au = sub.add_parser("audit")
    au.add_argument("--episode", required=True)
    au.set_defaults(fn=cmd_audit)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
