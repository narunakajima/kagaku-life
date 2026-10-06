"""
kl_dialogue.py — 掛け合い形式（2026-10-04〜）の共通処理

番組を「1話限りの架空の生活者の一人称独白＋研究ボイスの解説」から、
「固定の二人（夢語り担当 dreamer／ツッコミ担当 skeptic）の掛け合い」に変えた
（CLAUDE.md「掛け合い形式」、cast.json）。エピソードJSONに "format": "dialogue" を持つ回が対象。
旧形式の回（kl001〜kl030）は従来どおり各スクリプトの旧経路で処理される。

ここに置くもの:
  - 台本の構造チェック（validate_episode）: STEP2直後の機械チェックをまとめたもの
  - シーンの台詞の全文（scene_text）: ファクトチェック・確認書・レビュー用
  - 行ごとの音声の連結（concat_line_wavs）: kl_tts_gen.py が使う
  - 画面の重ね合わせ（字幕・立ち絵・名札・判定ラベル・バッジ）の描画と、
    動画全体の重ね合わせトラックの組み立て（build_overlay_track）: kl_video_gen.py が使う
  - サムネイルの合成（composite_thumbnail_dialogue）: kl_image_gen.py が使う

エピソードJSON（掛け合い形式）のシーン:
  {"scene_id": 5, "type": "tsukkomi", "bgm_role": "main", "reference_index": 0,
   "image_prompt": "...",
   "lines": [
     {"speaker": "skeptic", "text": "で、それ何人で試したの？", "expression": "doubt",
      "react": "deflated", "tone": "dry, teasing", "tag": "weakness",
      "display": "（任意）字幕だけ別表記にしたい場合", "pause": 0.6},
     ...]}
  lines[].t0 / dur / cards は kl_tts_gen.py・kl_telop_gen.py が書き込む（手で書かない）。
"""

import hashlib
import io
import json
import shutil
import subprocess
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

BASE_DIR = Path(__file__).parent
CAST_JSON = BASE_DIR / "cast.json"
CAST_DIR = BASE_DIR / "assets" / "cast"

FONT_BOLD = Path("/System/Library/Fonts/ヒラギノ角ゴシック W8.ttc")
FONT_MEDIUM = Path("/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc")

ROLES = ("dreamer", "skeptic")

# シーンタイプ: 画風（narrative=物語調イラスト／chart=チャート調）と、bgm_role を省略したときの既定値。
# 掛け合い形式では並び順を固定しない（構成テンプレートを話ごとに選ぶ）ため、BGMの切り替えは
# シーンの type ではなく bgm_role で決める。bgm_role は本編の並び順で intro→main→outro の
# 順に後戻りしないこと（validate_episode が確認する）。
SCENE_TYPES = {
    "teaser":   {"style": "narrative", "bgm_role": "intro"},   # 冒頭の問い（数カットの先出し）
    "setup":    {"style": "narrative", "bgm_role": "intro"},   # 今日の問い・身近な困りごと・通説
    "paper":    {"style": "narrative", "bgm_role": "intro"},   # どんな研究か（出典・方法・結果）
    "dream":    {"style": "narrative", "bgm_role": "intro"},   # 夢語り: それが来た暮らしの一場面
    "tsukkomi": {"style": "narrative", "bgm_role": "main"},    # ツッコミ: 弱点・実用化の壁
    "check":    {"style": "chart",     "bgm_role": "main"},    # 答え合わせ: データで確かめる
    "verdict":  {"style": "narrative", "bgm_role": "outro"},   # 判定
    "closing":  {"style": "narrative", "bgm_role": "outro"},   # 締め・CTA
}
BGM_ORDER = {"intro": 0, "main": 1, "outro": 2}

# 締めの固定の掛け合い（2026-10-04、旧closing固定文「次はどんな研究が、誰かの幸せな未来を
# 運んでくるのでしょうか。…」を二人の声に分けたもの。情緒的な締めの固定文は廃止し、
# 次回への一言とCTAだけを固定する）。closing シーンの最後の2行はこのとおりにする。
CLOSING_CTA = [
    ("dreamer", "次はどんな研究が、誰かの幸せな未来を運んでくるのか。"),
    ("skeptic", "それが本物かどうか、また一緒に確かめましょう。論文は概要欄に載せています。チャンネル登録して、待っていてください。"),
]

# ニュース起点の回（source_type: "news"、2026-10-04〜）は論文ではなく公式発表を扱うので、2行目だけ言い換える
CLOSING_CTA_NEWS = [
    CLOSING_CTA[0],
    ("skeptic", "それが本物かどうか、また一緒に確かめましょう。元の発表は概要欄に載せています。チャンネル登録して、待っていてください。"),
]

# 常套句の禁止リスト（2026-10-04、診断レポートで旧形式の30話に繰り返し出ていた言い回し）。
# 値は1話あたりの上限回数。
PHRASE_LIMITS = {
    "頭ではわかって": 0,
    "胸の奥": 0,
    "ふっと": 0,
    "ささやか": 0,
    "それでも、": 2,
    "研究段階": 1,
    "かもしれません": 2,
}

VERDICT_KEYS = ("soon", "decade", "dubious")
REQUIRED_TAGS = {
    "question": "冒頭の問い（teaser内）",
    "life_scene": "夢語りが描く具体的な生活の一場面（誰が・いつ・何をできるようになるか）",
    "weakness": "ツッコミが言う、この研究の一番の弱点",
    "barrier": "ツッコミが言う、実用化までの壁",
}


def load_cast() -> dict:
    return json.loads(CAST_JSON.read_text(encoding="utf-8"))


def is_dialogue(ep: dict) -> bool:
    return ep.get("format") == "dialogue"


def scene_style(scene: dict) -> str:
    return SCENE_TYPES.get(scene.get("type"), {}).get("style", "narrative")


def scene_bgm_role(scene: dict) -> str:
    return scene.get("bgm_role") or SCENE_TYPES.get(scene.get("type"), {}).get("bgm_role", "main")


def speaker_name(cast: dict, role: str) -> str:
    return cast.get(role, {}).get("name", role)


def scene_text(scene: dict, cast: dict = None) -> str:
    """シーンの台詞の全文（話者名つき）。ファクトチェック・確認書・レビューで使う。
    旧形式のシーンは narration をそのまま返す。"""
    if "lines" not in scene:
        return scene.get("narration", "")
    cast = cast or load_cast()
    return "\n".join(f"{speaker_name(cast, l['speaker'])}「{l['text']}」" for l in scene["lines"])


def scene_char_count(scene: dict) -> int:
    if "lines" in scene:
        return sum(len(l["text"]) for l in scene["lines"])
    return len(scene.get("narration", ""))


def line_display(line: dict) -> str:
    return line.get("display") or line["text"]


def lines_hash(scene: dict) -> str:
    """台詞の中身（話者・本文・演技指示）が変わったかを見るためのハッシュ。
    音声生成時に記録し、動画生成時に一致を確認する（台詞を直したのに音声を作り直していない
    事故の検出用。memory: 台詞を直したら音声も作り直す）。"""
    payload = json.dumps([[l["speaker"], l["text"], l.get("tone", "")] for l in scene.get("lines", [])],
                         ensure_ascii=False)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


# ── 台本の構造チェック ───────────────────────────────────────────────

def _count(text: str, phrase: str) -> int:
    return text.count(phrase)


def validate_episode(ep: dict, cast: dict = None) -> list:
    """STEP2直後の機械チェック。問題の一覧（文字列）を返す。空なら合格。"""
    cast = cast or load_cast()
    errs = []
    if not is_dialogue(ep):
        return ["format が 'dialogue' ではありません"]
    scenes = ep.get("scenes") or []
    if not scenes:
        return ["scenes がありません"]

    types_ = [s.get("type") for s in scenes]
    for s in scenes:
        if s.get("type") not in SCENE_TYPES:
            errs.append(f"S{s.get('scene_id')}: 未知の type '{s.get('type')}'")
        if not s.get("lines"):
            errs.append(f"S{s.get('scene_id')}: lines がありません")
        if not s.get("image_prompt") and not s.get("reuse_scene_id") and not s.get("image_asset"):
            errs.append(f"S{s.get('scene_id')}: image_prompt・reuse_scene_id・image_asset のどれもありません")
    ids = [s.get("scene_id") for s in scenes]
    if ids != list(range(1, len(scenes) + 1)):
        errs.append(f"scene_id が1からの連番になっていません: {ids}")

    if types_[0] != "teaser":
        errs.append("最初のシーンは teaser にしてください（冒頭で問いを言い切る）")
    if types_[-1] != "closing":
        errs.append("最後のシーンは closing にしてください")
    first_main = next((i for i, t in enumerate(types_) if t != "teaser"), len(types_))
    if any(t == "teaser" for t in types_[first_main:]):
        errs.append("teaser は冒頭にまとめてください")
    for t, n_min in (("paper", 1), ("dream", 1), ("tsukkomi", 1), ("check", 1)):
        if types_.count(t) < n_min:
            errs.append(f"{t} シーンが{n_min}つ以上必要です")
    if types_.count("verdict") != 1:
        errs.append("verdict シーンはちょうど1つにしてください")

    # BGMの役割は本編の並びで intro→main→outro の順に後戻りしない
    prev = 0
    for s in scenes[first_main:]:
        role = scene_bgm_role(s)
        if role not in BGM_ORDER:
            errs.append(f"S{s['scene_id']}: bgm_role '{role}' が不正です")
            continue
        if BGM_ORDER[role] < prev:
            errs.append(f"S{s['scene_id']}: bgm_role が {role} に戻っています（intro→main→outro の順にしてください）")
        prev = max(prev, BGM_ORDER[role])
    for s in scenes[:first_main]:
        if scene_bgm_role(s) != "intro":
            errs.append(f"S{s['scene_id']}: teaser の bgm_role は intro にしてください")

    names = [cast[r]["name"] for r in ROLES] + [cast[r].get("full_name", "") for r in ROLES]
    tags_found = set()
    all_text = ""
    for s in scenes:
        for i, l in enumerate(s.get("lines") or []):
            sp = l.get("speaker")
            where = f"S{s.get('scene_id')} 行{i + 1}"
            if sp not in ROLES:
                errs.append(f"{where}: speaker '{sp}' が不正です（dreamer/skeptic）")
                continue
            if l.get("expression", "neutral") not in cast[sp]["expressions"]:
                errs.append(f"{where}: {sp} に表情 '{l.get('expression')}' はありません"
                            f"（{', '.join(cast[sp]['expressions'])}）")
            other = "skeptic" if sp == "dreamer" else "dreamer"
            if l.get("react") and l["react"] not in cast[other]["expressions"]:
                errs.append(f"{where}: 聞き手の react '{l['react']}' は {other} の表情にありません")
            for n in names:
                if n and n in l.get("text", ""):
                    errs.append(f"{where}: 台詞にキャラクター名「{n}」が入っています（名前は画面の名札だけに出す）")
            if l.get("tag"):
                tags_found.add(l["tag"])
            all_text += l.get("text", "") + "\n"
            if s.get("type") == "teaser" and len(l.get("text", "")) > 30:
                errs.append(f"{where}: teaser の台詞は30字以内にしてください（{len(l['text'])}字）")

    teaser_tags = {l.get("tag") for s in scenes[:first_main] for l in (s.get("lines") or [])}
    if "question" not in teaser_tags:
        errs.append("teaser のどこかに tag: 'question'（視聴者側の問い）の行を置いてください")
    for tag, label in REQUIRED_TAGS.items():
        if tag not in tags_found:
            errs.append(f"tag '{tag}' の行がありません: {label}")
    for s in scenes:
        for l in s.get("lines") or []:
            if l.get("tag") in ("weakness", "barrier") and l.get("speaker") != "skeptic":
                errs.append(f"S{s['scene_id']}: tag '{l['tag']}' はツッコミ担当（skeptic）の台詞に付けてください")
            if l.get("tag") == "life_scene" and l.get("speaker") != "dreamer":
                errs.append(f"S{s['scene_id']}: tag 'life_scene' は夢語り担当（dreamer）の台詞に付けてください")

    for phrase, limit in PHRASE_LIMITS.items():
        n = _count(all_text, phrase)
        if n > limit:
            errs.append(f"常套句「{phrase}」が{n}回あります（上限{limit}回）")

    # 判定
    v = ep.get("verdict") or {}
    for r in ROLES:
        if v.get(r) not in VERDICT_KEYS:
            errs.append(f"verdict.{r} は {VERDICT_KEYS} のどれかにしてください")
    vs = next((s for s in scenes if s.get("type") == "verdict"), None)
    if vs is not None:
        k = vs.get("verdict_from_line")
        if not isinstance(k, int) or not (1 <= k <= len(vs.get("lines") or [])):
            errs.append("verdict シーンに verdict_from_line（判定ラベルを出し始める行番号、1始まり）を付けてください")

    # 実在の製品・機体を絵に描く回（ニュース等）は、実物と違う姿を本物のように見せないよう「イメージ図」の表示を必須にする
    # （2026-10-05、kl032でFlourish 1の外観を想像で描いて実物と大きく違っていたとの指摘を受けて追加）
    if ep.get("depicts_real_product"):
        for s in scenes:
            if s.get("shows_product") and "イメージ" not in (s.get("badge_text") or ""):
                errs.append(f"S{s['scene_id']}: 実在の製品を描いたシーン（shows_product）には badge_text に「イメージ図」を入れてください")
        if "イメージ図" not in ep.get("youtube_description", ""):
            errs.append("実在の製品を描く回は、概要欄に「イメージ図」の注記を入れてください")
        for i, c in enumerate(shorts if False else (ep.get("shorts") or [{}])[0].get("scenes") or [], start=1):
            ref = next((s for s in scenes if s.get("scene_id") == c.get("scene_id")), None)
            if ref and ref.get("shows_product") and "イメージ" not in (c.get("badge_text") or ""):
                errs.append(f"Shorts {i}カット目: 製品を描いた場面には badge_text（イメージ図）を付けてください")

    # 締めの固定CTA
    closing_lines = scenes[-1].get("lines") or []
    tail = [(l.get("speaker"), l.get("text")) for l in closing_lines[-len(CLOSING_CTA):]]
    cta = CLOSING_CTA_NEWS if ep.get("source_type") == "news" else CLOSING_CTA
    if tail != cta:
        errs.append("closing の最後の2行が固定のCTA（kl_dialogue.CLOSING_CTA、ニュース回は CLOSING_CTA_NEWS）と一致しません")

    # タイトル・フック・Shorts
    title = ep.get("youtube_title", "")
    if "幸せな未来のサイエンス" in title or "【" in title:
        errs.append("youtube_title にチャンネル名・【】を入れないでください")
    if len(ep.get("hook_lines") or []) != 2:
        errs.append("hook_lines（2行）がありません")
    shorts = (ep.get("shorts") or [{}])[0].get("scenes") or []
    if not shorts:
        errs.append("shorts がありません")
    else:
        if len(shorts[0].get("narration", "")) > 15:
            errs.append(f"Shortsの1カット目は15字以内にしてください（{len(shorts[0].get('narration', ''))}字）")
        if "本編" not in shorts[-1].get("narration", ""):
            errs.append("Shortsの最後のカットのナレーションに「本編」を入れてください")
        for i, c in enumerate(shorts, start=1):
            if c.get("narrator") not in ROLES:
                errs.append(f"Shorts {i}カット目: narrator は dreamer/skeptic にしてください")
    return errs


# ── 行ごとの音声の連結 ───────────────────────────────────────────────

GAP_SPEAKER_CHANGE = 0.28   # 話者が替わるときの間（秒）
GAP_SAME_SPEAKER = 0.22     # 同じ人が続けて話すときの間
TARGET_RMS_DBFS = -20.0     # 二人の声の大きさをそろえる目標


def line_gap(prev_line, line) -> float:
    if prev_line is None:
        return 0.0
    if line.get("pause") is not None:
        return float(line["pause"])
    return GAP_SPEAKER_CHANGE if prev_line["speaker"] != line["speaker"] else GAP_SAME_SPEAKER


def _read_wav(path: Path):
    with wave.open(str(path), "rb") as wf:
        params = wf.getparams()
        frames = wf.readframes(wf.getnframes())
    return params, frames


def _rms_normalize(frames: bytes, sampwidth: int) -> bytes:
    import array
    import math
    if sampwidth != 2:
        return frames
    a = array.array("h", frames)
    if not a:
        return frames
    rms = math.sqrt(sum(x * x for x in a) / len(a)) or 1.0
    target = 32768 * (10 ** (TARGET_RMS_DBFS / 20))
    gain = min(4.0, target / rms)
    peak = max(abs(x) for x in a) or 1
    gain = min(gain, 32000 / peak)  # クリップさせない
    return array.array("h", (int(x * gain) for x in a)).tobytes()


def concat_line_wavs(line_wavs: list, lines: list, out_path: Path) -> list:
    """行ごとのWAVを、話者に応じた間を入れて1本のシーン音声にする。
    各行の音量をそろえ（RMS正規化）、各行の (t0, dur) を返す（シーン音声の先頭からの秒）。"""
    params0 = None
    chunks = []
    timings = []
    t = 0.0
    prev = None
    for wav_path, line in zip(line_wavs, lines):
        params, frames = _read_wav(wav_path)
        if params0 is None:
            params0 = params
        rate, sw, ch = params.framerate, params.sampwidth, params.nchannels
        gap = line_gap(prev, line)
        if gap > 0:
            chunks.append(b"\x00" * int(gap * rate) * sw * ch)
            t += gap
        frames = _rms_normalize(frames, sw)
        dur = len(frames) / (rate * sw * ch)
        timings.append((round(t, 3), round(dur, 3)))
        chunks.append(frames)
        t += dur
        prev = line
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(params0.nchannels)
        wf.setsampwidth(params0.sampwidth)
        wf.setframerate(params0.framerate)
        wf.writeframes(b"".join(chunks))
    return timings


# ── 画面の重ね合わせ（字幕・立ち絵・名札・判定ラベル） ──────────────────────

MAIN_LAYOUT = {
    "W": 1408, "H": 768,
    "sprite_h": 330, "sprite_h_chart": 240, "sprite_margin": 6,
    "bar_h": 150, "font": 40, "rows": 1, "teaser_font": 80,  # 2026-10-06: 字幕は1枚1行（2行にすると文字が縮んで読みにくい。なるさんの指示）
    "text_cy": None,  # None: 字幕帯の中央
}
SHORTS_LAYOUT = {
    "W": 768, "H": 1376,
    "sprite_h": 400, "sprite_h_chart": 400, "sprite_margin": 0,
    "bar_h": 0, "font": 48, "rows": 1, "teaser_font": 64,  # 2026-10-06: 1枚1行（長いカットは shorts_timeline で複数の字幕に分ける）
    "text_cy": 0.56,
}

# 自己紹介カードの出し方（2026-10-05、なるさんの指示: 両方同時だと読み切れないので、大輔→沙織の順に出す）。
# 大輔の吹き出しを0〜4秒、沙織の吹き出しを3〜7秒（1秒だけ重なる）。二人の関係の一文は7秒間ずっと出す。
# 台詞は吹き出しと関係なくシーンの頭から始まる（なるさんの指示。無音の間は作らない）。吹き出しは台詞・字幕に重ねて出す。
# 時刻は最初の本編シーンの開始からの秒数
INTRO_FIRST_SECONDS = 4.0
INTRO_SECOND_AT = 3.0
INTRO_SECOND_SECONDS = 4.0
INTRO_CARD_SECONDS = INTRO_SECOND_AT + INTRO_SECOND_SECONDS  # 7.0

BAR_COLOR = (10, 22, 38, 205)
INACTIVE_BRIGHTNESS = 0.55


class SpriteBank:
    def __init__(self, cast: dict):
        self.cast = cast
        self._cache = {}

    def get(self, role: str, expr: str, h: int, active: bool) -> Image.Image:
        key = (role, expr, h, active)
        if key not in self._cache:
            path = CAST_DIR / f"{role}_{expr}.png"
            if not path.exists():
                path = CAST_DIR / f"{role}_neutral.png"
            im = Image.open(path).convert("RGBA")
            hh = h if active else int(h * 0.94)
            im = im.resize((int(im.width * hh / im.height), hh), Image.LANCZOS)
            if not active:
                a = im.getchannel("A")
                im = ImageEnhance.Brightness(im.convert("RGB")).enhance(INACTIVE_BRIGHTNESS).convert("RGBA")
                im.putalpha(a)
            self._cache[key] = im
        return self._cache[key]


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def _text_w(draw, text, font, stroke=0) -> int:
    return draw.textbbox((0, 0), text, font=font, stroke_width=stroke)[2]


def wrap_rows(text: str, font, max_w: int, max_rows: int) -> list:
    """字幕を max_rows 行以内に折り返す。句読点・文節の切れ目を優先し、行の長さをそろえる。"""
    d = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    if _text_w(d, text, font) <= max_w:
        return [text]
    try:
        from kl_telop_gen import _token_boundaries
        cands = [b for b in _token_boundaries(text) if 0 < b < len(text)]
    except Exception:  # janome が無い環境
        cands = list(range(1, len(text)))
    punct = {i + 1 for i, ch in enumerate(text) if ch in "、。！？!?」』"}
    # 行頭禁則: 句読点・閉じ括弧・長音・小書き文字を次の行の頭に置かない
    no_head = set("、。，．！？!?」』）)…ーゃゅょっぁぃぅぇぉャュョッァィゥェォ ")
    cands = [b for b in cands if text[b] not in no_head] or cands
    best = None
    for b in cands:
        w = max(_text_w(d, text[:b], font), _text_w(d, text[b:], font))
        score = w - (font.size * 3 if b in punct else 0)
        if best is None or score < best[0]:
            best = (score, b)
    b = best[1] if best else len(text) // 2
    rows = [text[:b], text[b:]]
    if max_rows >= 3 and any(_text_w(d, r, font) > max_w for r in rows):
        n = len(text)
        rows = [text[: n // 3], text[n // 3: 2 * n // 3], text[2 * n // 3:]]
    return rows


def _fit_rows(text: str, font_path: Path, size: int, max_w: int, max_rows: int):
    while size >= 26:
        f = _font(font_path, size)
        rows = wrap_rows(text, f, max_w, max_rows)
        d = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        if len(rows) <= max_rows and all(_text_w(d, r, f, 5) <= max_w for r in rows):
            return rows, f
        size -= 2
    f = _font(font_path, 26)
    return wrap_rows(text, f, max_w, max_rows), f


def _tint(color, k=0.35):
    """話者の色を、字幕で読みやすいよう白寄りにする。"""
    return tuple(int(c + (255 - c) * k) for c in color)


def draw_stamp(label: str, color, scale: float = 1.0, header: str = "判定") -> Image.Image:
    """判定ラベル（固定デザイン）: 上に小さく「判定」、下に色付きの角丸の札に大きく判定文言。
    わずかに傾けて、はんこのような見た目にする。"""
    fh = _font(FONT_BOLD, int(30 * scale))
    fl = _font(FONT_BOLD, int(64 * scale))
    d = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    lw = _text_w(d, label, fl)
    hw = _text_w(d, header, fh)
    pad_x, pad_y = int(34 * scale), int(18 * scale)
    w = max(lw, hw) + pad_x * 2
    h_head = int(46 * scale)
    h_label = int(64 * scale) + pad_y * 2
    im = Image.new("RGBA", (w + 20, h_head + h_label + 20), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    x0, y0 = 10, 10
    dr.rounded_rectangle((x0, y0, x0 + w, y0 + h_head + h_label), radius=int(18 * scale),
                         fill=(255, 255, 255, 245))
    dr.text((x0 + (w - hw) // 2, y0 + int(8 * scale)), header, font=fh, fill=(40, 50, 70))
    inner = (x0 + int(8 * scale), y0 + h_head, x0 + w - int(8 * scale), y0 + h_head + h_label - int(8 * scale))
    dr.rounded_rectangle(inner, radius=int(14 * scale), fill=tuple(color) + (255,))
    ty = inner[1] + (inner[3] - inner[1] - int(64 * scale)) // 2 - int(6 * scale)
    dr.text((x0 + (w - lw) // 2, ty), label, font=fl, fill=(255, 255, 255),
            stroke_width=max(2, int(3 * scale)), stroke_fill=tuple(int(c * 0.6) for c in color))
    return im.rotate(-4, resample=Image.BICUBIC, expand=True)


def verdict_stamps(cast: dict, verdict: dict, scale: float = 1.0) -> list:
    """verdict = {"dreamer": key, "skeptic": key}。二人の判定が同じなら1枚、割れたら2枚
    （それぞれ「大輔の判定」「沙織の判定」）を返す。"""
    vd = cast["verdicts"]
    if verdict.get("dreamer") == verdict.get("skeptic"):
        k = verdict["dreamer"]
        return [draw_stamp(vd[k]["label"], vd[k]["color"], scale)]
    return [draw_stamp(vd[verdict[r]]["label"], vd[verdict[r]]["color"], scale,
                       header=f"{speaker_name(cast, r)}の判定") for r in ROLES]


def _draw_intro(im: Image.Image, dr: ImageDraw.ImageDraw, W: int, H: int, cast: dict, sprite_pos: dict,
                roles=ROLES) -> None:
    """二人の自己紹介: 上部に関係の一文、立ち絵の上にそれぞれの吹き出し（尻尾は立ち絵の頭を指す）。
    音声は付けず、画面の文字だけで見せる（2026-10-05、なるさんの指示: 「誰？」とならないように）。"""
    rel = cast.get("relationship", "")
    if rel:
        fb = _font(FONT_BOLD, 34)
        bw = _text_w(dr, rel, fb)
        x0 = (W - bw) // 2 - 24
        dr.rounded_rectangle((x0, 26, x0 + bw + 48, 26 + 62), radius=14, fill=(10, 22, 38, 215),
                             outline=(240, 168, 104, 235), width=3)
        dr.text(((W - bw) // 2, 26 + 11), rel, font=fb, fill=(255, 255, 255))
    ft = _font(FONT_BOLD, 28)
    line_h, pad = 38, 22
    for role in ROLES:
        lines = cast[role].get("intro") or []
        if not lines or role not in sprite_pos or role not in roles:
            continue
        sx, sw, sy = sprite_pos[role]
        bw = max(_text_w(dr, ln, ft) for ln in lines) + pad * 2
        bh = line_h * len(lines) + pad * 2 - 6
        bottom = sy - 26
        if cast[role]["screen_side"] == "left":
            bx = max(16, sx + 6)
        else:
            bx = min(W - 16 - bw, sx + sw - bw - 6)
        by = bottom - bh
        col = tuple(cast[role]["color"])
        # 尻尾（吹き出しの下辺から立ち絵の頭へ）
        tx = sx + sw // 2
        tx = min(max(tx, bx + 40), bx + bw - 40)
        dr.polygon([(tx - 18, bottom - 2), (tx + 18, bottom - 2), (tx + (6 if cast[role]["screen_side"] == "left" else -6), sy + 34)],
                   fill=(255, 255, 255, 245), outline=col + (255,))
        dr.rounded_rectangle((bx, by, bx + bw, bottom), radius=20, fill=(255, 255, 255, 245),
                             outline=col + (255,), width=4)
        # 尻尾の付け根の枠線を白で消して、吹き出しとつなげる
        dr.line((tx - 15, bottom, tx + 15, bottom), fill=(255, 255, 255, 255), width=5)
        for i, ln in enumerate(lines):
            dr.text((bx + pad, by + pad - 4 + i * line_h), ln, font=ft,
                    fill=(30, 40, 62) if i else tuple(int(c * 0.62) for c in col))


def render_layer(state: dict, layout: dict, cast: dict, bank: SpriteBank) -> Image.Image:
    """1つの画面状態（誰が話しているか・表情・字幕・ラベル）を透明PNGに描く。
    state のキー: mode('normal'|'teaser'|'blank'), speaker, exprs{role: expr}, text,
                  chart(bool), badge(str|None), stamps(list[Image]|None), cta(str|None),
                  intro(bool: 本編の冒頭に出す二人の自己紹介の吹き出しと関係の一文)"""
    W, H = layout["W"], layout["H"]
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if state.get("mode") == "blank":
        return im
    dr = ImageDraw.Draw(im)
    teaser = state.get("mode") == "teaser"
    sh = layout["sprite_h_chart"] if state.get("chart") else layout["sprite_h"]

    # 字幕帯（本編のみ。Shortsは帯なしで画面中央に字幕）
    if layout["bar_h"] and not teaser:
        bar = Image.new("RGBA", (W, layout["bar_h"]), BAR_COLOR)
        im.alpha_composite(bar, (0, H - layout["bar_h"]))
        dr.line((0, H - layout["bar_h"], W, H - layout["bar_h"]), fill=(240, 168, 104, 200), width=3)

    # 立ち絵（話している方は明るく大きく、聞いている方は少し暗く小さく）
    sprite_w = 0
    sprite_pos = {}
    for role in ROLES:
        active = state.get("speaker") == role or state.get("speaker") == "both"
        expr = (state.get("exprs") or {}).get(role, "neutral")
        sp = bank.get(role, expr, sh, active)
        sprite_w = max(sprite_w, sp.width)
        if cast[role]["screen_side"] == "left":
            x = layout["sprite_margin"]
        else:
            x = W - sp.width - layout["sprite_margin"]
        im.alpha_composite(sp, (x, H - sp.height))
        sprite_pos[role] = (x, sp.width, H - sp.height)
        # 名札（名前＋肩書き。初めて見た人が「この人は誰か」を分かるように肩書きを常に添える）
        fn = _font(FONT_BOLD, 24 if W > 1000 else 28)
        fr = _font(FONT_MEDIUM, 17 if W > 1000 else 21)
        name, role_short = cast[role]["name"], cast[role].get("role_short", "")
        nw, rw = _text_w(dr, name, fn), (_text_w(dr, role_short, fr) if role_short else 0)
        gap = 10 if role_short else 0
        tw = nw + gap + rw
        px = x + (sp.width - tw) // 2 - 14
        py = H - 46
        col = tuple(cast[role]["color"]) if active else (110, 118, 130)
        dr.rounded_rectangle((px, py, px + tw + 28, py + 38), radius=19, fill=col + (235,))
        dr.text((px + 14, py + 4), name, font=fn, fill=(255, 255, 255))
        if role_short:
            dr.text((px + 14 + nw + gap, py + 10), role_short, font=fr, fill=(255, 255, 255, 235))

    # 自己紹介（本編の冒頭の数秒だけ。二人の関係の一文と、それぞれの吹き出し）
    if state.get("intro"):
        intro_roles = state["intro"] if isinstance(state["intro"], (list, tuple)) else ROLES
        _draw_intro(im, dr, W, H, cast, sprite_pos, roles=intro_roles)

    # バッジ（左上、夢語りの場面などで常時表示）
    if state.get("badge"):
        fb = _font(FONT_MEDIUM, 28 if W > 1000 else 30)
        bw = _text_w(dr, state["badge"], fb)
        dr.rounded_rectangle((24, 22, 24 + bw + 28, 22 + 48), radius=10, fill=(0, 0, 0, 120))
        dr.text((38, 29), state["badge"], font=fb, fill=(255, 255, 255))

    # 判定ラベル
    stamps = state.get("stamps") or []
    if stamps:
        total_w = sum(s.width for s in stamps) + 40 * (len(stamps) - 1)
        x = (W - total_w) // 2
        y = int(H * (0.06 if W > 1000 else 0.24))
        for s in stamps:
            im.alpha_composite(s, (x, y))
            x += s.width + 40

    # 字幕
    text = state.get("text")
    if text:
        color = _tint(cast[state["speaker"]]["color"]) if state.get("speaker") in ROLES else (255, 255, 255)
        if teaser:
            rows, f = _fit_rows(text, FONT_BOLD, layout["teaser_font"], int(W * 0.86), 2)
            stroke = 9
            line_h = int(f.size * 1.25)
            y = int(H * 0.40) - (line_h * len(rows)) // 2
        else:
            max_w = W - 2 * (sprite_w + 24) if layout["bar_h"] else int(W * 0.9)
            rows, f = _fit_rows(text, FONT_MEDIUM, layout["font"], max_w, layout["rows"])
            stroke = 6
            line_h = int(f.size * 1.32)
            if layout["text_cy"] is None:
                cy = H - layout["bar_h"] // 2
            else:
                cy = int(H * layout["text_cy"])
            y = cy - (line_h * len(rows)) // 2
        for r in rows:
            rw = _text_w(dr, r, f, stroke)
            dr.text(((W - rw) // 2, y), r, font=f, fill=color, stroke_width=stroke, stroke_fill=(0, 0, 0))
            y += line_h

    # Shortsの最後の誘導など
    if state.get("cta"):
        fc = _font(FONT_BOLD, 56)
        cw = _text_w(dr, state["cta"], fc, 7)
        dr.text(((W - cw) // 2, int(H * 0.66)), state["cta"], font=fc, fill=(240, 168, 104),
                stroke_width=7, stroke_fill=(0, 0, 0))
    return im


def _state_key(state: dict) -> str:
    s = dict(state)
    s["stamps"] = len(state.get("stamps") or [])
    return json.dumps(s, ensure_ascii=False, sort_keys=True)


def main_timeline(ep: dict, scenes: list, offsets: list, durs: list, narr_delay: float,
                  total_dur: float, cast: dict) -> list:
    """本編の重ね合わせの時刻表 [(t_start, state), ...] を作る（時刻はグローバル秒）。"""
    events = []
    stamps = None
    intro_windows = []  # (開始, 終了, 吹き出しを出す人) 自己紹介カード。台詞の状態に重ねて後で付ける
    for scene, off, dur in zip(scenes, offsets, durs):
        teaser = scene["type"] == "teaser"
        chart = scene_style(scene) == "chart"
        badge = scene.get("badge_text")
        base = {"mode": "teaser" if teaser else "normal", "chart": chart, "badge": badge,
                "speaker": None, "exprs": {"dreamer": "neutral", "skeptic": "neutral"}, "text": None}
        lead = scene.get("_lead_in", 0.0)  # 台詞の開始を遅らせたいときだけ使う（通常は0。自己紹介カードでは遅らせない）
        events.append((off, dict(base)))
        narr_delay_s = narr_delay + lead
        if scene.get("_intro_card"):
            intro_windows.append((off, off + INTRO_FIRST_SECONDS, "dreamer"))
            intro_windows.append((off + INTRO_SECOND_AT, off + INTRO_CARD_SECONDS, "skeptic"))
        lines = scene.get("lines") or []
        v_from = scene.get("verdict_from_line") if scene["type"] == "verdict" else None
        for li, line in enumerate(lines):
            if "t0" not in line:
                raise RuntimeError(f"S{scene['scene_id']:02d} 行{li + 1}: t0 がありません（kl_tts_gen.py を先に実行）")
            sp = line["speaker"]
            other = "skeptic" if sp == "dreamer" else "dreamer"
            exprs = {sp: line.get("expression", "neutral"), other: line.get("react", "neutral")}
            st = None
            if v_from and li + 1 >= v_from:
                if stamps is None:
                    stamps = verdict_stamps(cast, ep["verdict"])
                st = stamps
            cards = line.get("cards") or [{"text": line_display(line), "start": 0.0, "end": line["dur"]}]
            for c in cards:
                t = off + narr_delay_s + line["t0"] + c["start"]
                events.append((round(t, 3), dict(base, speaker=sp, exprs=exprs, text=c["text"],
                                                 stamps=st)))
        # シーンの終わり（次のシーンの開始）まで最後の状態を保つ。後続シーンの開始で切り替わる
    events.sort(key=lambda e: e[0])
    if intro_windows:
        # 自己紹介の吹き出しの出入りの時刻にも、その時点の台詞の状態を複製して切り替え点を作り、
        # 各状態に「その時刻に出ている吹き出し」を付ける
        times = {t for (s, e, _r) in intro_windows for t in (s, e)}
        orig = list(events)  # 時刻順。複製元はここだけから選ぶ（複製を足しながら探すと順序が崩れる）
        have = {round(t, 3) for t, _ in orig}
        for b in sorted(times):
            b = round(b, 3)
            if b in have:
                continue
            prev = [st for t, st in orig if t <= b]
            if prev:
                events.append((b, dict(prev[-1])))
        events.sort(key=lambda e: e[0])
        out = []
        for t, st in events:
            roles = [r for (s, e, r) in intro_windows if s <= t < e]
            if roles:
                st = dict(st, intro=roles)
            out.append((t, st))
        events = out
    return events


_SUB_MAXW_CACHE = {}


def subtitle_max_w(layout: dict, cast: dict = None) -> int:
    """字幕1行の最大幅（px）。render_layer と同じ式（立ち絵を避ける幅、立ち絵なしなら画面の9割）。"""
    key = (layout["W"], layout["bar_h"], layout["sprite_h"])
    if key not in _SUB_MAXW_CACHE:
        if layout["bar_h"]:
            cast = cast or load_cast()
            bank = SpriteBank(cast)
            sw = max(bank.get(r, "neutral", layout["sprite_h"], a).width for r in ROLES for a in (True, False))
            _SUB_MAXW_CACHE[key] = layout["W"] - 2 * (sw + 24)
        else:
            _SUB_MAXW_CACHE[key] = int(layout["W"] * 0.9)
    return _SUB_MAXW_CACHE[key]


def split_to_width(text: str, layout: dict, cast: dict = None) -> list:
    """字幕を、実際の描画幅で1行に収まる最少の枚数に分ける（2026-10-06、なるさんの指示: 2行にすると
    文字が縮んで読みにくいので、1行で次の字幕に切り替える）。分け目は句読点・文節の境界を優先し、
    枚数が同じなら幅がそろう分け方を選ぶ。行頭に句読点・閉じ括弧などが来る分け方はしない。"""
    d = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    f = _font(FONT_MEDIUM, layout["font"])
    max_w = subtitle_max_w(layout, cast)
    stroke = 6
    if _text_w(d, text, f, stroke) <= max_w:
        return [text]
    n = len(text)
    no_head = set("、。，．！？!?」』）)…ーゃゅょっぁぃぅぇぉャュョッァィゥェォ ")
    try:
        from kl_telop_gen import _token_boundaries
        cands = {b for b in _token_boundaries(text) if 0 < b < n}
    except Exception:  # janome が無い環境
        cands = set(range(1, n))
    cands |= {i + 1 for i, ch in enumerate(text) if ch in "、。！？!?" and i + 1 < n}
    cands = {b for b in cands if text[b] not in no_head}
    pts = sorted(cands | {0, n})

    def solve(points):
        INF = (10 ** 9, 0.0)
        best = {0: ((0, 0.0), None)}
        for j in points[1:]:
            cur = None
            for i in points:
                if i >= j or i not in best:
                    continue
                w = _text_w(d, text[i:j], f, stroke)
                if w > max_w:
                    continue
                pc, pen = best[i][0]
                bonus = 40.0 if text[j - 1] in "、。！？!?" else 0.0
                cost = (pc + 1, pen + (w / 100.0) ** 2 - bonus)
                if cur is None or cost < cur[0]:
                    cur = (cost, i)
            if cur:
                best[j] = cur
        return best

    best = solve(pts)
    if n not in best:  # 文節単位では収まらない → 文字単位で分ける
        best = solve(list(range(0, n + 1)))
    out, j = [], n
    while j > 0:
        i = best[j][1]
        out.append(text[i:j])
        j = i
    return out[::-1]


def split_for_one_row(text: str, layout: dict) -> list:
    return split_to_width(text, layout)


def shorts_timeline(ep: dict, cuts: list, offsets: list, durs: list, narr_delay: float,
                    cast: dict) -> list:
    events = []
    for i, (cut, off, dur) in enumerate(zip(cuts, offsets, durs)):
        last = i == len(cuts) - 1
        st = None
        if last:
            st = [draw_stamp("本編で", (110, 118, 130), 1.0, header="判定は")]
        sp = cut.get("narrator")
        other = "skeptic" if sp == "dreamer" else "dreamer"
        exprs = {sp: cut.get("expression", "neutral"), other: cut.get("react", "neutral")}
        events.append((round(off, 3), {"mode": "normal", "speaker": sp, "exprs": exprs,
                                       "text": None, "chart": cut.get("style") == "chart",
                                       "stamps": st, "cta": None, "badge": cut.get("badge_text")}))
        # 2026-10-06: 字幕は1枚1行（2行にすると文字が縮んで読みにくい）。長いカットは句読点・文節で
        # SHORTS_CARD_MAX 字以内に分け、カットの発話区間（遅延後〜カット終わり）を文字数に比例して配分する
        text = cut.get("telop_text", cut["narration"])
        chunks = split_for_one_row(text, SHORTS_LAYOUT)
        t0 = off + narr_delay
        span = max(0.1, (off + dur) - t0)
        total_chars = sum(len(c) for c in chunks) or 1
        pos = 0
        for ci, chunk in enumerate(chunks):
            events.append((round(t0 + span * pos / total_chars, 3),
                           {"mode": "normal", "speaker": sp, "exprs": exprs, "text": chunk,
                            "chart": cut.get("style") == "chart",
                            "stamps": st, "cta": "↓ 続きは本編で" if last else None,
                            "badge": cut.get("badge_text")}))
            pos += len(chunk)
    events.sort(key=lambda e: e[0])
    return events


def build_overlay_track(events: list, total_dur: float, layout: dict, cast: dict, tmp: Path,
                        out_mov: Path, fps: int, ffmpeg: str = "ffmpeg",
                        blank_after: float = None) -> None:
    """時刻表から透明な重ね合わせ動画（qtrle .mov）を作る。同じ画面状態のPNGは使い回す。
    blank_after を指定すると、その時刻以降は何も重ねない（本編のロゴアウトロ用）。"""
    bank = SpriteBank(cast)
    if blank_after is not None:
        events = [e for e in events if e[0] < blank_after] + [(blank_after, {"mode": "blank"})]
    # 同時刻の重複は後勝ち
    dedup = []
    for t, st in events:
        if dedup and abs(dedup[-1][0] - t) < 1e-3:
            dedup[-1] = (t, st)
        else:
            dedup.append((t, st))
    if not dedup or dedup[0][0] > 0:
        dedup.insert(0, (0.0, {"mode": "blank"}))
    cache = {}
    entries = []
    for i, (t, st) in enumerate(dedup):
        t_next = dedup[i + 1][0] if i + 1 < len(dedup) else total_dur
        dur = max(0.0, t_next - t)
        if dur <= 0:
            continue
        key = _state_key(st)
        if key not in cache:
            p = tmp / f"layer_{len(cache):04d}.png"
            render_layer(st, layout, cast, bank).save(p)
            cache[key] = p
        entries.append((cache[key], dur))
    lst = tmp / "layers.ffconcat"
    body = ["ffconcat version 1.0"]
    for p, d in entries:
        body += [f"file '{p}'", f"duration {d:.3f}"]
    body.append(f"file '{entries[-1][0]}'")
    lst.write_text("\n".join(body) + "\n", encoding="utf-8")
    cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
           "-vf", f"fps={fps},format=argb", "-t", f"{total_dur:.3f}",
           "-c:v", "qtrle", str(out_mov)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("重ね合わせトラックの生成に失敗: " + r.stderr[-2000:])
    print(f"  ▶ 重ね合わせトラック: 画面状態{len(cache)}種類 / 切り替え{len(entries)}回")


# ── サムネイル ──────────────────────────────────────────────────────

def composite_thumbnail_dialogue(image_path: Path, ep: dict, cast: dict = None) -> None:
    """掛け合い形式のサムネイル: 背景画像の上に、見出し（上部）、二人の立ち絵（左下・右下）、
    判定ラベル（中央下寄り）を合成する。表情は thumbnail_exprs（無ければ excited/doubt）。"""
    cast = cast or load_cast()
    img = Image.open(image_path).convert("RGBA")
    w, h = img.size
    # 上部の暗幕（見出しを読みやすく）
    band_h = int(h * 0.45)
    grad = Image.new("L", (1, band_h))
    for y in range(band_h):
        grad.putpixel((0, y), int(220 * (1 - y / band_h) ** 1.1))
    band = Image.new("RGBA", (w, band_h), (10, 20, 35, 0))
    band.putalpha(grad.resize((w, band_h)))
    img.alpha_composite(band, (0, 0))

    exprs = ep.get("thumbnail_exprs") or {"dreamer": "excited", "skeptic": "doubt"}
    bank = SpriteBank(cast)
    sh = int(h * 0.62)
    for role in ROLES:
        sp = bank.get(role, exprs.get(role, "neutral"), sh, True)
        x = 0 if cast[role]["screen_side"] == "left" else w - sp.width
        img.alpha_composite(sp, (x, h - sp.height))

    dr = ImageDraw.Draw(img)
    headline = ep.get("thumbnail_headline", "")
    # thumbnail_badge: 製品名などを見出しの上に大きく目立たせる（2026-10-06、kl034「Dots」。なるさんの指示）
    badge = ep.get("thumbnail_badge", "")
    badge_h = 0
    if badge:
        bsize = int(h * 0.24)
        while bsize > 60:
            bf = _font(FONT_BOLD, bsize)
            bstroke = max(6, bsize // 10)
            if _text_w(dr, badge, bf, bstroke) <= w - int(w * 0.08) * 2:
                break
            bsize -= 4
        bw = _text_w(dr, badge, bf, bstroke)
        dr.text(((w - bw) // 2, int(h * 0.02)), badge, font=bf, fill=(255, 214, 10),
                stroke_width=bstroke, stroke_fill=(20, 20, 20))
        badge_h = int(bsize * 1.12)
    if headline:
        size = int(h * (0.13 if badge else 0.15))
        margin = int(w * 0.04)
        while size > 40:
            f = _font(FONT_BOLD, size)
            stroke = max(4, size // 12)
            rows = headline.split("\n")
            if all(_text_w(dr, r, f, stroke) <= w - margin * 2 for r in rows):
                break
            size -= 4
        y = int(h * 0.05) + (badge_h if badge else 0)
        for r in headline.split("\n"):
            rw = _text_w(dr, r, f, stroke)
            dr.text(((w - rw) // 2, y), r, font=f, fill=(255, 255, 255), stroke_width=stroke,
                    stroke_fill=(0, 0, 0))
            y += int(size * 1.15)
    if ep.get("verdict"):
        # 判定ラベルは二人の立ち絵の間に収める（顔に重ねない）。収まらなければ縮める
        gap = w - 2 * bank.get("dreamer", exprs.get("dreamer", "neutral"), sh, True).width - 20
        scale = 1.15
        while True:
            stamps = verdict_stamps(cast, ep["verdict"], scale=scale)
            total = sum(s.width for s in stamps) + 16 * (len(stamps) - 1)
            if total <= gap or scale <= 0.6:
                break
            scale -= 0.05
        x = (w - total) // 2
        for s in stamps:
            img.alpha_composite(s, (x, h - s.height - int(h * 0.03)))
            x += s.width + 16
    img.convert("RGB").save(image_path, "PNG")


# ── コマンドライン ────────────────────────────────────────────────

def sync_derived(ep: dict, cast: dict = None) -> None:
    """旧形式用のスクリプト（ファクトチェック・確認書・レビュー）が読めるように、各シーンに
    narration（話者名つきの台詞全文）と narrator="dialogue" を書き込む。台詞を直したら毎回
    `kl_dialogue.py check` で作り直す（正は lines。narration は派生物で手で直さない）。"""
    cast = cast or load_cast()
    for s in ep.get("scenes", []):
        if "lines" in s:
            s["narration"] = scene_text(s, cast)
            s["narrator"] = "dialogue"


def main():
    import argparse
    import sys
    ap = argparse.ArgumentParser(description="掛け合い形式の台本チェック")
    ap.add_argument("command", choices=["check"])
    ap.add_argument("--episode", required=True)
    args = ap.parse_args()
    path = BASE_DIR / "episodes" / f"{args.episode}.json"
    ep = json.loads(path.read_text(encoding="utf-8"))
    cast = load_cast()
    errs = validate_episode(ep, cast)
    sync_derived(ep, cast)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(ep, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    chars = sum(scene_char_count(s) for s in ep["scenes"])
    print(f"台詞の総文字数: {chars}字（目安の尺: 約{chars / 330:.1f}〜{chars / 290:.1f}分）")
    tags = {}
    for s in ep["scenes"]:
        for l in s.get("lines", []):
            if l.get("tag"):
                tags.setdefault(l["tag"], []).append(f"S{s['scene_id']:02d}")
    print("タグ:", ", ".join(f"{k}={v}" for k, v in tags.items()))
    if errs:
        print(f"❌ {len(errs)}件の問題:")
        for e in errs:
            print("  - " + e)
        sys.exit(1)
    print("✅ 構造チェックOK（narration/narrator を同期しました）")


if __name__ == "__main__":
    main()
