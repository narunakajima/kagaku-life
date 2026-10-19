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
    "dream":    {"style": "narrative", "bgm_role": "intro"},   # 未来の一場面（v3 では任意・1つまで。現物がまだ無い回など）
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

# ── 構成 v2「論点ラウンド」（2026-10-16、DIALOGUE_REDESIGN_2026-10-16.md） ──────────────
# エピソードJSONのトップレベルに "structure": "rounds_v2" がある回だけ、下の追加ルールで確認する
# （kl031〜kl040 は旧来のチェックのまま。作り直さない）。
#   teaser → setup（お題と二人の予想、固定背景）→ 論点ラウンド2〜3 → verdict（予想からどう変わったか）→ closing
#   各ラウンドの最初のシーンに round_title、ラウンド内の全シーンに round（1始まり）。
#   一次資料の該当箇所は source_card（資料カード、Pillowで描く。正確な文字）で見せる。
STRUCTURE_V2 = "rounds_v2"
V2_TAGS = {
    "prediction": "setup で二人がそれぞれ言う、最初の予想（二人とも必要）",
    "turn": "予想・主張がひっくり返る／どちらかが譲る行（1話に1つ以上）",
    "vs_prediction": "verdict で、最初の予想からどう変わったかを言う行（二人とも必要）",
}
ROUND_TITLE_MAX = 22          # 論点の見出しの最大文字数（画面の帯に1行で出す）
ROUND_TITLE_SECONDS = 2.8     # ラウンドの頭に論点の見出しを出す秒数（台詞は遅らせない）
MAX_SAME_SPEAKER_RUN = 3      # 同じ人が続けて話す行数の上限（verdict は +1）
MAX_SPEAKER_SHARE = 0.70      # 1シーンで一人が話す文字数の割合の上限（4行以上のシーン。closing は除く）
# dream に年齢・容姿を固定した人物を描かない（旧形式の「主人公」の名残）。手元・後ろ姿・遠景はよい
import re as _re
_PERSONA_RE = _re.compile(r"\bin (his|her|their) (early |mid-|mid |late )?(teens|twenties|thirties|forties|fifties|sixties|seventies|eighties|[1-9]0s)\b"
                          r"|\b(a|an) (young |elderly |middle-aged )?(Japanese )?(man|woman|boy|girl) (in|with) ", _re.I)
# 意味を運ばない「比喩の小道具」だけの挿絵（虫めがね・南京錠・天秤）は使わない（kl033〜kl041で多用）
STOCK_METAPHORS = ("magnifying glass", "padlock", "balance scale")
CARD_KINDS = {  # 資料カードの種類 → 見出しの色
    "press":  ("発表資料", (64, 120, 176)),
    "blog":   ("技術ブログ", (48, 150, 140)),
    "terms":  ("利用規約", (150, 110, 70)),
    "docs":   ("説明書", (90, 100, 150)),
    "paper":  ("論文", (110, 80, 150)),
    "report": ("報告書", (120, 120, 120)),
}
CARD_DIR = BASE_DIR / "assets" / "cards"

# ── 構成 v3「使い道ラウンド」（2026-10-17、kl043 以降。CLAUDE.md「構成 v3」） ──────────────
# "structure": "rounds_v3" の回は、v2 の規則（validate_rounds_v2）をすべて引き継いだうえで、
#   - life_scene を必須から外し、dream シーンを任意・1つまでにする
#     （v2 までは「言い過ぎる→崩される→言い直す」の dream が12話中9話で型になっていた）
#   - use_case（大輔が論点の中で置く具体的な使い道。同じ論点の check で一次資料に当てる）を必須
#   - takeaway（verdict で「誰が・何に・どんな条件で／いつ」使えるかを言う行）を必須
#   - 「言い直」0回・「想像してみて」1回まで
# kl041・kl042（rounds_v2）と kl031〜kl040（structure なし）は従来の規則のまま。
STRUCTURE_V3 = "rounds_v3"
ROUND_STRUCTURES = (STRUCTURE_V2, STRUCTURE_V3)
V3_TAGS = {
    "use_case": "大輔（dreamer）が論点の中で置く具体的な使い道。同じ論点の check で一次資料に当てる",
    "takeaway": "verdict で言う「誰が・何に・どんな条件で／いつ」使えるか（どちらが言ってもよい）",
}
V3_PHRASE_LIMITS = {
    "言い直": 0,          # 「言い直す」「言い直し」。崩された夢を言い直す型をやめる
    "想像してみて": 1,    # 旧口癖。使うなら1回まで（dream を置く回だけ）
}
V3_MAX_DREAM = 1

VERDICT_KEYS = ("soon", "decade", "pending", "dubious")  # pending（根拠待ち）は2026-10-18追加
REQUIRED_TAGS = {
    "question": "冒頭の問い（teaser内）",
    "life_scene": "夢語りが描く具体的な生活の一場面（誰が・いつ・何をできるようになるか）",
    "weakness": "ツッコミが言う、この研究の一番の弱点",
    "barrier": "ツッコミが言う、実用化までの壁",
}


def required_tags(ep: dict) -> dict:
    """構成ごとの必須タグ。v3 は life_scene を外し、use_case・takeaway を足す。"""
    if ep.get("structure") == STRUCTURE_V3:
        tags = {k: v for k, v in REQUIRED_TAGS.items() if k != "life_scene"}
        tags.update(V3_TAGS)
        return tags
    return dict(REQUIRED_TAGS)


def phrase_limits(ep: dict) -> dict:
    limits = dict(PHRASE_LIMITS)
    if ep.get("structure") == STRUCTURE_V3:
        limits.update(V3_PHRASE_LIMITS)
    return limits


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


def card_text(card: dict) -> str:
    """資料カードに画面で出す文字の全文（ファクトチェック・レビュー用）。"""
    parts = [card.get("source", "")]
    if card.get("quote"):
        parts.append(f"「{card['quote']}」（{card.get('quote_type', '原文')}）")
    parts += [f"・{it}" for it in card.get("items") or []]
    if card.get("note"):
        parts.append(f"※{card['note']}")
    return " ".join(p for p in parts if p)


def scene_text(scene: dict, cast: dict = None) -> str:
    """シーンの台詞の全文（話者名つき）。ファクトチェック・確認書・レビューで使う。
    旧形式のシーンは narration をそのまま返す。資料カードがあれば、画面の文字も末尾に付ける。"""
    if "lines" not in scene:
        return scene.get("narration", "")
    cast = cast or load_cast()
    out = "\n".join(f"{speaker_name(cast, l['speaker'])}「{l['text']}」" for l in scene["lines"])
    if scene.get("source_card"):
        out += "\n［画面の資料カード］" + card_text(scene["source_card"])
    return out


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
    v3 = ep.get("structure") == STRUCTURE_V3
    v2 = ep.get("structure") in ROUND_STRUCTURES   # v3 は v2 の規則をすべて引き継ぐ
    # v2 ではツッコミを資料カードの答え合わせ（check）の中で言ってよいので、tsukkomi シーンは必須にしない
    # v3 では dream も必須にしない（任意・1つまで。下で上限を確認）
    if v3:
        need = (("check", 2),)
    elif v2:
        need = (("paper", 1), ("dream", 1), ("check", 2))
    else:
        need = (("paper", 1), ("dream", 1), ("tsukkomi", 1), ("check", 1))
    for t, n_min in need:
        if types_.count(t) < n_min:
            errs.append(f"{t} シーンが{n_min}つ以上必要です")
    if v3 and types_.count("dream") > V3_MAX_DREAM:
        errs.append(f"v3: dream シーンは任意で{V3_MAX_DREAM}つまでです（今は{types_.count('dream')}）。"
                    "未来の場面は、現物がまだ無い回など絵に価値があるときだけ")
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
    for tag, label in required_tags(ep).items():
        if tag not in tags_found:
            errs.append(f"tag '{tag}' の行がありません: {label}")
    for s in scenes:
        for l in s.get("lines") or []:
            if l.get("tag") in ("weakness", "barrier") and l.get("speaker") != "skeptic":
                errs.append(f"S{s['scene_id']}: tag '{l['tag']}' はツッコミ担当（skeptic）の台詞に付けてください")
            if l.get("tag") == "life_scene" and l.get("speaker") != "dreamer":
                errs.append(f"S{s['scene_id']}: tag 'life_scene' は夢語り担当（dreamer）の台詞に付けてください")

    for phrase, limit in phrase_limits(ep).items():
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
    if v2:
        errs += validate_rounds_v2(ep)
    if v3:
        errs += validate_rounds_v3(ep)
    return errs


def _card_asset_name(ep: dict, scene: dict) -> str:
    return f"cards/{ep.get('episode_id', 'klXXX')}_S{scene['scene_id']:02d}"


def validate_rounds_v3(ep: dict) -> list:
    """構成 v3（使い道ラウンド）の追加チェック。v2 の規則（validate_rounds_v2）は別に通す。"""
    errs = []
    scenes = ep["scenes"]
    for s in scenes:
        for i, l in enumerate(s.get("lines") or []):
            tag = l.get("tag")
            where = f"v3: S{s['scene_id']} 行{i + 1}"
            if tag == "use_case":
                if l.get("speaker") != "dreamer":
                    errs.append(f"{where}: tag 'use_case' は大輔（dreamer）の台詞に付けてください（使い道を置くのは期待担当）")
                n = s.get("round")
                if not isinstance(n, int):
                    errs.append(f"{where}: use_case は論点ラウンドの中（round のあるシーン）に置いてください")
                else:
                    # 同じ論点の、このシーン以降に check（資料・データで答え合わせ）があること
                    later = [t for t in scenes if t.get("round") == n and t["scene_id"] >= s["scene_id"]
                             and t.get("type") == "check"]
                    if not later:
                        errs.append(f"{where}: use_case を置いた論点{n}に、その後で資料に当てる check シーンがありません")
            elif tag == "takeaway" and s.get("type") != "verdict":
                errs.append(f"{where}: tag 'takeaway' は verdict シーンの台詞に付けてください")
            elif tag == "life_scene":
                # v3 では必須ではないが、使うなら dream の中だけ（未来の場面を論点に混ぜない）
                if s.get("type") != "dream":
                    errs.append(f"{where}: v3 では life_scene は dream シーンの中だけで使えます（使い道は use_case で）")
    return errs


def episode_warnings(ep: dict) -> list:
    """不合格にはしないが、STEP5で見てほしいこと（⚠ として表示する）。"""
    warns = []
    if ep.get("structure") == STRUCTURE_V3:
        # 大輔が正しかった論点（沙織が譲る turn）が1つ以上あるか。毎回大輔が論破されるだけの型を避ける
        if not any(l.get("tag") == "turn" and l.get("speaker") == "skeptic"
                   for s in ep["scenes"] for l in s.get("lines") or []):
            warns.append("v3: 沙織が譲る turn（大輔が正しかった論点）がありません。大輔が論破されるだけの回になっていないか、STEP5で確認")
    return warns


def validate_rounds_v2(ep: dict) -> list:
    """構成 v2（論点ラウンド）の追加チェック。"structure": "rounds_v2" の回と、それを引き継ぐ rounds_v3 の回。"""
    errs = []
    scenes = ep["scenes"]
    by_id = {s["scene_id"]: s for s in scenes}
    main = [s for s in scenes if s.get("type") != "teaser"]
    if not main:
        return errs
    # 1) 冒頭は「お題と予想」: 最初の本編シーンは setup、二人とも prediction を言う
    if main[0].get("type") != "setup":
        errs.append("v2: 最初の本編シーンは setup（お題と二人の予想）にしてください")
    else:
        who = {l.get("speaker") for l in main[0].get("lines", []) if l.get("tag") == "prediction"}
        for r in ROLES:
            if r not in who:
                errs.append(f"v2: setup に {r} の予想（tag: 'prediction'）がありません")
    # 2) ラウンド: setup と verdict の間の全シーンに round、2〜3ラウンド、順に増える、頭に round_title
    vi = next((i for i, s in enumerate(main) if s.get("type") == "verdict"), len(main))
    body = main[1:vi]
    prev = 0
    rounds = {}
    for s in body:
        n = s.get("round")
        where = f"S{s['scene_id']}"
        if not isinstance(n, int) or n < 1:
            errs.append(f"v2: {where}: round（1始まりの論点の番号）がありません")
            continue
        if n < prev or n > prev + 1:
            errs.append(f"v2: {where}: round が {prev} → {n} です（1から順に、戻らずに）")
        if n != prev:
            t = s.get("round_title", "")
            if not t:
                errs.append(f"v2: {where}: 論点{n}の最初のシーンに round_title（見出し）がありません")
            elif len(t) > ROUND_TITLE_MAX:
                errs.append(f"v2: {where}: round_title は{ROUND_TITLE_MAX}字以内に（{len(t)}字）")
        elif s.get("round_title"):
            errs.append(f"v2: {where}: round_title は各論点の最初のシーンだけに付けてください")
        prev = max(prev, n)
        rounds.setdefault(n, []).append(s)
    for s in [main[0]] + main[vi:]:
        if s.get("round") or s.get("round_title"):
            errs.append(f"v2: S{s['scene_id']}: setup/verdict/closing に round を付けないでください")
    if not 2 <= len(rounds) <= 3:
        errs.append(f"v2: 論点ラウンドは2〜3にしてください（今は{len(rounds)}）")
    for n, ss in rounds.items():
        sp = {l.get("speaker") for s in ss for l in s.get("lines", [])}
        if sp != set(ROLES):
            errs.append(f"v2: 論点{n}: 二人とも話していません")
        if not any(s.get("type") == "check" for s in ss):
            errs.append(f"v2: 論点{n}: 資料・データで確かめる check シーンがありません")
    # 3) 予想からの変化・裏切り
    tags = [(s, l) for s in scenes for l in s.get("lines", []) if l.get("tag")]
    if not any(l["tag"] == "turn" for _, l in tags):
        errs.append("v2: tag 'turn'（予想・主張がひっくり返る／譲る行）がありません")
    vs = {l.get("speaker") for s, l in tags if l["tag"] == "vs_prediction" and s.get("type") == "verdict"}
    for r in ROLES:
        if r not in vs:
            errs.append(f"v2: verdict に {r} の「最初の予想からどう変わったか」（tag: 'vs_prediction'）がありません")
    # 4) 説明の分担にしない: 同じ人の連続・一人語りの割合
    for s in main:
        lines = s.get("lines") or []
        limit = MAX_SAME_SPEAKER_RUN + (1 if s.get("type") == "verdict" else 0)
        run, p = 0, None
        for l in lines:
            run = run + 1 if l.get("speaker") == p else 1
            p = l.get("speaker")
            if run > limit:
                errs.append(f"v2: S{s['scene_id']}: 同じ人が{run}行続いています（上限{limit}。相手の反応を挟む）")
                break
        if len(lines) >= 4 and s.get("type") not in ("closing",):
            cnt = {}
            for l in lines:
                cnt[l.get("speaker")] = cnt.get(l.get("speaker"), 0) + len(l.get("text", ""))
            tot = sum(cnt.values()) or 1
            top = max(cnt.items(), key=lambda kv: kv[1])
            if top[1] / tot > MAX_SPEAKER_SHARE:
                errs.append(f"v2: S{s['scene_id']}: {top[0]} が台詞の{top[1] / tot:.0%}を話しています"
                            f"（上限{MAX_SPEAKER_SHARE:.0%}。資料を持ってきた側が読み、相手が割って入る）")
    # 5) 画像: dream に固定の人物を描かない、比喩の小道具だけの挿絵にしない
    for s in scenes:
        p = s.get("image_prompt") or ""
        if s.get("type") == "dream" and _PERSONA_RE.search(p):
            errs.append(f"v2: S{s['scene_id']}: dream の絵に年齢・容姿を決めた人物がいます（旧形式の主人公の名残）。"
                        "手元・後ろ姿・遠景、または人のいない場面にする")
        for m in STOCK_METAPHORS:
            if m in p.lower():
                errs.append(f"v2: S{s['scene_id']}: 比喩の小道具「{m}」の挿絵は使わない。資料カード（source_card）か、話題の実物を描く")
    # 6) 資料カード
    card_ids = set()
    for s in scenes:
        c = s.get("source_card")
        if not c:
            continue
        card_ids.add(s["scene_id"])
        where = f"S{s['scene_id']}"
        if s.get("type") != "check":
            errs.append(f"v2: {where}: source_card は check シーンに置いてください（静止表示になるのは check だけ）")
        if c.get("kind") not in CARD_KINDS:
            errs.append(f"v2: {where}: source_card.kind は {tuple(CARD_KINDS)} のどれか")
        if not c.get("source"):
            errs.append(f"v2: {where}: source_card.source（資料名と日付）がありません")
        if not c.get("quote") and not c.get("items"):
            errs.append(f"v2: {where}: source_card に quote か items が必要です")
        if c.get("quote") and c.get("quote_type", "原文") not in ("原文", "要約"):
            errs.append(f"v2: {where}: source_card.quote_type は 原文 / 要約")
        if c.get("quote") and len(c["quote"]) > 90:
            errs.append(f"v2: {where}: source_card.quote は90字以内（{len(c['quote'])}字）")
        if c.get("highlight") and c["highlight"] not in (c.get("quote") or ""):
            errs.append(f"v2: {where}: source_card.highlight は quote の中の文字列にしてください")
        for it in c.get("items") or []:
            if sum(0.5 if ch.isascii() else 1 for ch in it) > 26:
                errs.append(f"v2: {where}: source_card.items の1行は26字以内（半角は0.5字）（{it[:12]}…）")
        if len(c.get("items") or []) > 5:
            errs.append(f"v2: {where}: source_card.items は5行まで")
        ri = c.get("reference_index", s.get("reference_index"))
        if not isinstance(ri, int) or not (0 <= ri < len(ep.get("references") or [])):
            errs.append(f"v2: {where}: source_card の reference_index が references にありません")
        want = _card_asset_name(ep, s)
        if s.get("image_asset") != want or not (BASE_DIR / "assets" / f"{want}.png").exists():
            errs.append(f"v2: {where}: 資料カードの画像がありません（python3 kl_dialogue.py cards --episode {ep.get('episode_id')}）")
        if s.get("image_prompt"):
            errs.append(f"v2: {where}: source_card のシーンに image_prompt は書かない（カードを使う）")
    # ティザー（ズームする）と Shorts（AIで縦に描き直す）では、文字のカードを使わない
    for s in scenes:
        if s.get("type") == "teaser" and s.get("reuse_scene_id") in card_ids:
            errs.append(f"v2: S{s['scene_id']}: ティザーで資料カードのシーン（S{s['reuse_scene_id']}）を流用しない（ズームで文字が切れる）")
    for i, c in enumerate((ep.get("shorts") or [{}])[0].get("scenes") or [], start=1):
        if c.get("scene_id") in card_ids:
            errs.append(f"v2: Shorts {i}カット目: 資料カードのシーンは使わない（縦に描き直すと文字が崩れる）")
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


def nameplate_rect(dr, cast: dict, role: str, x: int, spw: int, H: int, big: bool):
    """名札の位置と中身の寸法。立ち絵の左端 x・幅 spw から決まる。"""
    fn = _font(FONT_BOLD, 24 if big else 28)
    fr = _font(FONT_MEDIUM, 17 if big else 21)
    name, role_short = cast[role]["name"], cast[role].get("role_short", "")
    nw, rw = _text_w(dr, name, fn), (_text_w(dr, role_short, fr) if role_short else 0)
    gap = 10 if role_short else 0
    tw = nw + gap + rw
    px = x + (spw - tw) // 2 - 14
    py = H - 46
    return (px, py, px + tw + 28, py + 38), (fn, fr, name, role_short, nw, gap)


def draw_nameplate(dr, cast: dict, role: str, x: int, spw: int, H: int, big: bool, active: bool) -> None:
    """名札（名前＋肩書き）。話している方は役の色、聞いている方はグレー。"""
    (px, py, x1, y1), (fn, fr, name, role_short, nw, gap) = nameplate_rect(dr, cast, role, x, spw, H, big)
    col = tuple(cast[role]["color"]) if active else (110, 118, 130)
    dr.rounded_rectangle((px, py, x1, y1), radius=19, fill=col + (235,))
    dr.text((px + 14, py + 4), name, font=fn, fill=(255, 255, 255))
    if role_short:
        dr.text((px + 14 + nw + gap, py + 10), role_short, font=fr, fill=(255, 255, 255, 235))


def render_layer(state: dict, layout: dict, cast: dict, bank: SpriteBank,
                 sprites: bool = True, bar: bool = True, nameplates: bool = True) -> Image.Image:
    """1つの画面状態（誰が話しているか・表情・字幕・ラベル）を透明PNGに描く。
    state のキー: mode('normal'|'teaser'|'blank'), speaker, exprs{role: expr}, text,
                  chart(bool), badge(str|None), stamps(list[Image]|None), cta(str|None),
                  intro(bool: 本編の冒頭に出す二人の自己紹介の吹き出しと関係の一文)
    sprites=False: 立ち絵を描かない（動画の立ち絵を別トラックで重ねるとき。名札・吹き出しの位置は
                   立ち絵があるときと同じ）。bar=False: 字幕帯を描かない（立ち絵の下に別に重ねるとき）"""
    W, H = layout["W"], layout["H"]
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if state.get("mode") == "blank":
        return im
    dr = ImageDraw.Draw(im)
    teaser = state.get("mode") == "teaser"
    sh = layout["sprite_h_chart"] if state.get("chart") else layout["sprite_h"]

    # 字幕帯（本編のみ。Shortsは帯なしで画面中央に字幕）
    if bar and layout["bar_h"] and not teaser:
        draw_bar(im, dr, layout)

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
        if sprites:
            im.alpha_composite(sp, (x, H - sp.height))
        sprite_pos[role] = (x, sp.width, H - sp.height)
        # 名札（名前＋肩書き。初めて見た人が「この人は誰か」を分かるように肩書きを常に添える）。
        # 動画の立ち絵のときは立ち絵のトラックに入れる（明暗の切り替えを立ち絵と同じクロスフェードにするため）
        if nameplates:
            draw_nameplate(dr, cast, role, x, sp.width, H, W > 1000, active)

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

    # 論点の見出し（構成 v2。ラウンドの頭の数秒だけ、画面の中ほどに帯で出す。台詞は止めない）
    if state.get("round_title"):
        n, title = state["round_title"]
        big = W > 1000
        fl = _font(FONT_BOLD, 30 if big else 32)
        ft = _font(FONT_BOLD, 52 if big else 44)
        label = f"論点{n}"
        lw, tw = _text_w(dr, label, fl), _text_w(dr, title, ft, 4)
        if tw > W * 0.86:  # 長い見出しは縮める
            size = 52 if big else 44
            while size > 28 and _text_w(dr, title, _font(FONT_BOLD, size), 4) > W * 0.86:
                size -= 2
            ft = _font(FONT_BOLD, size)
            tw = _text_w(dr, title, ft, 4)
        band_h = (ft.size + fl.size) + 54
        y0 = int(H * (0.30 if big else 0.30)) - band_h // 2
        dr.rectangle((0, y0, W, y0 + band_h), fill=(10, 22, 38, 215))
        dr.line((0, y0, W, y0), fill=(240, 168, 104, 230), width=3)
        dr.line((0, y0 + band_h, W, y0 + band_h), fill=(240, 168, 104, 230), width=3)
        dr.text(((W - lw) // 2, y0 + 14), label, font=fl, fill=(240, 168, 104))
        dr.text(((W - tw) // 2, y0 + 14 + fl.size + 12), title, font=ft, fill=(255, 255, 255),
                stroke_width=4, stroke_fill=(0, 0, 0))

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


def draw_bar(im: Image.Image, dr: ImageDraw.ImageDraw, layout: dict) -> None:
    """本編の字幕帯（画面下の半透明の帯と、上辺のオレンジの線）。立ち絵より下に描く。"""
    W, H = layout["W"], layout["H"]
    band = Image.new("RGBA", (W, layout["bar_h"]), BAR_COLOR)
    im.alpha_composite(band, (0, H - layout["bar_h"]))
    dr.line((0, H - layout["bar_h"], W, H - layout["bar_h"]), fill=(240, 168, 104, 200), width=3)


def _state_key(state: dict, sprites: bool = True) -> str:
    s = dict(state)
    s["stamps"] = len(state.get("stamps") or [])
    s.pop("talk_end", None)  # 口パクの時刻は重ね合わせ（PNG）の見た目に影響しない
    if not sprites:
        s.pop("exprs", None)  # 立ち絵を描かないなら表情は見た目に影響しない（名札も立ち絵のトラックに入る）
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
        if scene.get("round_title") and not teaser:
            # 構成 v2: 論点の見出し。自己紹介カードと同じ仕組みで、台詞の状態に重ねて出す
            intro_windows.append((off, off + ROUND_TITLE_SECONDS,
                                  ("round", scene.get("round"), scene["round_title"])))
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
            talk_end = round(off + narr_delay_s + line["t0"] + line["dur"], 3)  # 口パク: この行を話し終える時刻
            for c in cards:
                t = off + narr_delay_s + line["t0"] + c["start"]
                events.append((round(t, 3), dict(base, speaker=sp, exprs=exprs, text=c["text"],
                                                 stamps=st, talk_end=talk_end)))
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
            active = [r for (s, e, r) in intro_windows if s <= t < e]
            roles = [r for r in active if r in ROLES]
            rounds = [r for r in active if isinstance(r, tuple) and r[0] == "round"]
            if roles:
                st = dict(st, intro=roles)
            if rounds:
                st = dict(st, round_title=[rounds[-1][1], rounds[-1][2]])
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
    # 2026-10-16: 数字の直後では分けない（kl041 Shorts で「1分に6／回。」と数字と助数詞が分かれた）
    cands = {b for b in cands if not (text[b - 1].isdigit() or (text[b].isdigit() and text[b - 1] in ".．"))}
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
                    cast: dict, narr_durs: list = None) -> list:
    """narr_durs: 各カットの台詞の長さ（秒）。渡すと、口パク用に話し終える時刻（talk_end）を付ける"""
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
        talk_end = round(t0 + narr_durs[i], 3) if narr_durs else None
        total_chars = sum(len(c) for c in chunks) or 1
        pos = 0
        for ci, chunk in enumerate(chunks):
            events.append((round(t0 + span * pos / total_chars, 3),
                           {"mode": "normal", "speaker": sp, "exprs": exprs, "text": chunk,
                            "chart": cut.get("style") == "chart",
                            "stamps": st, "cta": "↓ 続きは本編で" if last else None,
                            "badge": cut.get("badge_text"), "talk_end": talk_end}))
            pos += len(chunk)
    events.sort(key=lambda e: e[0])
    return events


def _prepare_events(events: list, blank_after: float = None) -> list:
    """時刻表を整える: blank_after 以降を空にし、同時刻の重複は後勝ち、頭が0秒でなければ空の状態を足す。"""
    if blank_after is not None:
        events = [e for e in events if e[0] < blank_after] + [(blank_after, {"mode": "blank"})]
    dedup = []
    for t, st in events:
        if dedup and abs(dedup[-1][0] - t) < 1e-3:
            dedup[-1] = (t, st)
        else:
            dedup.append((t, st))
    if not dedup or dedup[0][0] > 0:
        dedup.insert(0, (0.0, {"mode": "blank"}))
    return dedup


def build_overlay_track(events: list, total_dur: float, layout: dict, cast: dict, tmp: Path,
                        out_mov: Path, fps: int, ffmpeg: str = "ffmpeg",
                        blank_after: float = None, sprites: bool = True, bar: bool = True) -> None:
    """時刻表から透明な重ね合わせ動画（qtrle .mov）を作る。同じ画面状態のPNGは使い回す。
    blank_after を指定すると、その時刻以降は何も重ねない（本編のロゴアウトロ用）。
    sprites=False・bar=False は、動画の立ち絵（build_sprite_tracks）と組み合わせるときに使う
    （字幕帯 → 立ち絵 → この重ね合わせ、の順に重ねるため、帯と立ち絵をここから外す）。"""
    bank = SpriteBank(cast)
    dedup = _prepare_events(events, blank_after)
    cache = {}
    entries = []
    for i, (t, st) in enumerate(dedup):
        t_next = dedup[i + 1][0] if i + 1 < len(dedup) else total_dur
        dur = max(0.0, t_next - t)
        if dur <= 0:
            continue
        key = _state_key(st, sprites)
        if key not in cache:
            p = tmp / f"layer_{len(cache):04d}.png"
            render_layer(st, layout, cast, bank, sprites=sprites, bar=bar, nameplates=sprites).save(p)
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


# ── 立ち絵の動画化（2026-10-17、パイロット） ────────────────────────────
# 二人の立ち絵を、静止画の代わりに待機ループの動画（assets/cast/video/{role}_{expr}.webm、
# kl_cast_video.py で作る）で重ねる。字幕・名札・判定ラベルなどは従来の重ね合わせ（PNGの状態トラック）のまま。
# 重ねる順: 背景 → 字幕帯（PNG、enable で区間指定）→ 大輔のトラック → 沙織のトラック → 状態トラック。

CAST_VIDEO_DIR = CAST_DIR / "video"
CAST_LOOPS_JSON = CAST_VIDEO_DIR / "loops.json"
STATIC_VARIANT_FRAMES = 96   # 動画の無い表情（静止画）を何フレームの「ループ」として扱うか（4秒）
BLANK_VARIANT_FRAMES = 24


def cast_video_path(role: str, expr: str, kind: str = "idle"):
    """立ち絵のループ動画。kind="idle" は待機ループ、"talk" は話している間のループ（口パク）。無ければ None"""
    p = CAST_VIDEO_DIR / (f"{role}_{expr}.webm" if kind == "idle" else f"{role}_{expr}_talk.webm")
    return p if p.exists() else None


def cast_video_available() -> bool:
    return any(cast_video_path(r, e) for r in ROLES for e in (load_cast()[r].get("expressions") or {}))


def _loop_frames(path: Path, ffmpeg: str) -> int:
    try:
        loops = json.loads(CAST_LOOPS_JSON.read_text(encoding="utf-8"))
        key = path.stem
        if key in loops and loops[key].get("frames"):
            return int(loops[key]["frames"])
    except Exception:
        pass
    ffprobe = shutil.which("ffprobe") or "ffprobe"
    r = subprocess.run([ffprobe, "-v", "error", "-c:v", "libvpx-vp9", "-count_frames", "-select_streams", "v:0",
                        "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    return int(r.stdout.strip())


def _us_ceil(frames: int, fps: int) -> str:
    us = -(-frames * 1_000_000 // fps)
    return f"{us // 1_000_000}.{us % 1_000_000:06d}"


def _us_floor(frames: int, fps: int) -> str:
    us = frames * 1_000_000 // fps
    return f"{us // 1_000_000}.{us % 1_000_000:06d}"


SPRITE_XFADE_FRAMES = 3   # 立ち絵の見た目の切り替え（口パク・明暗・大きさ）を重ねるフレーム数（0.125秒）
SPRITE_XFADE_EXPR_FRAMES = 4  # 表情（手のポーズ）が変わる切り替えを重ねるフレーム数（0.17秒。長いと手・頭が二重に見える時間が延びる）
TALK_HOLD_GAP = 0.6       # 台詞の合間がこれより短ければ、口パクを止めずに続ける（秒）


def _write_phase_list(path: Path, segs: list, variants: dict, fps: int) -> int:
    """区間 [f0, f1, key] の列を ffconcat に書く。ループの何フレーム目を出すかは「全体のフレーム番号 mod 周期」。"""
    body = ["ffconcat version 1.0"]
    n_entries = 0
    for f0, f1, key in segs:
        v = variants[key]
        n = v["frames"]
        f = f0
        while f < f1:
            ph = f % n
            take = min(n - ph, f1 - f)
            body += [f"file '{v['path']}'", f"inpoint {_us_ceil(ph, fps)}", f"outpoint {_us_floor(ph + take, fps)}"]
            n_entries += 1
            f += take
    path.write_text("\n".join(body) + "\n", encoding="utf-8")
    return n_entries


def sprite_track_filter(track: dict, k: int, fps: int, out_label: str):
    """build_sprite_tracks の1役分を ffmpeg の入力とフィルタにする。k は最初の入力番号。
    返り値: (入力引数のリスト, フィルタ文字列, 使った入力の数)。出力は [out_label]（RGBA、立ち絵のキャンバス大）。
    クロスフェードがある場合は、前の見た目のトラックと新しい見た目のトラックを、アルファで重みづけ（premultiply）して
    重みのトラックで混ぜる（maskedmerge）。"""
    inputs = ["-f", "concat", "-safe", "0", "-i", str(track["list"])]
    if not track.get("prev_list"):
        return inputs, f"[{k}:v]fps={fps},format=rgba[{out_label}]", 1
    inputs += ["-f", "concat", "-safe", "0", "-i", str(track["prev_list"]),
               "-f", "concat", "-safe", "0", "-i", str(track["mask_list"])]
    flt = (f"[{k}:v]fps={fps},format=gbrap,premultiply=inplace=1[{out_label}_a];"
           f"[{k + 1}:v]fps={fps},format=gbrap,premultiply=inplace=1[{out_label}_p];"
           f"[{k + 2}:v]fps={fps},format=gbrap[{out_label}_m];"
           f"[{out_label}_p][{out_label}_a][{out_label}_m]maskedmerge,unpremultiply=inplace=1,format=rgba[{out_label}]")
    return inputs, flt, 3


def build_sprite_tracks(events: list, total_dur: float, layout: dict, cast: dict, tmp: Path,
                        fps: int, ffmpeg: str = "ffmpeg", blank_after: float = None, talk: bool = True) -> dict:
    """立ち絵を役ごとの透明な動画トラックにする。返り値:
      {"tracks": [{"role", "list": ffconcat のパス, "x", "y"}], "bar": {"png", "x", "y", "spans"} or None}
    tracks の list は `-f concat -safe 0 -i` でそのまま入力にできる（kl_video_gen.overlay_dialogue）。

    仕組み:
    - 役ごとに、時刻表から「表情・話しているか（明るさと大きさ）・グラフ時の縮小・表示するか」の区間を作る
    - 区間の見た目（variant）ごとに、立ち絵を最終の大きさ・明るさにした1周期分の短い動画（PNGコーデックの
      mov、全フレームがキーフレーム）を先に作る。キャンバスは役ごとに固定の大きさ（通常時の立ち絵の箱）で、
      立ち絵は下端・画面の外側にそろえて置く（render_layer と同じ位置）
    - 位相: ループの何フレーム目を出すかは「全体の時刻（フレーム番号）mod 周期」で決める。話し手が替わって
      明るさ・大きさが変わっても、同じ表情なら動きは途切れず続く。表情が変わるときだけ別のループに切り替わる
      （静止画のときと同じく、表情の切り替えはカット）
    - 区間を ffconcat の inpoint/outpoint で並べる（全フレームがキーフレームなので切り出しはフレーム単位で正確）。
      数百の区間でもフィルタグラフは大きくならない
    - webm の無い表情は静止画を STATIC_VARIANT_FRAMES の「動かないループ」として同じ仕組みで扱う
    - 口パク（2026-10-17、talk=True）: その役が実際に台詞を話している間（状態の talk_end まで。台詞の
      t0〜t0+dur、main_timeline / shorts_timeline が付ける）は「話しているループ」（{role}_{expr}_talk.webm、
      明るい・通常の大きさ）、それ以外（聞いている間は暗い・0.94倍、話し手でも台詞の合間は明るい）は待機ループ。
      talk ループの無い表情は待機ループのまま。talk と idle は周期が違うので、それぞれ全体のフレーム番号 mod
      自分の周期で位相を決める（同じ種類のループに戻ると動きは続きから）。切り替えはカット（どちらも同じ静止画
      から作っているので頭の位置はほぼ同じ。kl042 で確認）"""
    from concurrent.futures import ThreadPoolExecutor
    bank = SpriteBank(cast)
    W, H = layout["W"], layout["H"]
    dedup = _prepare_events(events, blank_after)
    total_frames = int(round(total_dur * fps))
    vdir = tmp / "sprite_variants"
    vdir.mkdir(parents=True, exist_ok=True)

    # 字幕帯（本編のみ）: mode が normal の区間だけ出す
    bar_info = None
    if layout["bar_h"]:
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw_bar(im, ImageDraw.Draw(im), layout)
        bb = im.getbbox()
        bar_png = vdir / "bar.png"
        im.crop(bb).save(bar_png)
        spans = []
        for i, (t, st) in enumerate(dedup):
            t1 = dedup[i + 1][0] if i + 1 < len(dedup) else total_dur
            on = st.get("mode") == "normal"
            if on and t1 > t:
                if spans and abs(spans[-1][1] - t) < 1e-6:
                    spans[-1][1] = t1
                else:
                    spans.append([t, t1])
        bar_info = {"png": bar_png, "x": bb[0], "y": bb[1], "spans": spans}

    variants = {}   # key -> {"path", "frames"}
    jobs = []
    tracks = []
    for role in ROLES:
        left = cast[role]["screen_side"] == "left"
        big = W > 1000
        _dr = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

        def sprite_x(spw):  # 立ち絵の左端（画面の座標）。render_layer と同じ
            return layout["sprite_margin"] if left else W - spw - layout["sprite_margin"]
        # キャンバス: 立ち絵（通常・グラフ時、明るい・暗い）と名札がすべて収まる範囲（画面の座標）
        xs0, xs1 = [], []
        for hh in {layout["sprite_h"], layout["sprite_h_chart"]}:
            for act in (True, False):
                spw = bank.get(role, "neutral", hh, act).width
                x = sprite_x(spw)
                r, _ = nameplate_rect(_dr, cast, role, x, spw, H, big)
                xs0 += [x, r[0]]
                xs1 += [x + spw, r[2]]
        cx, cx1 = max(0, min(xs0)), min(W, max(xs1))
        cw = cx1 - cx
        ch = layout["sprite_h"]
        cy = H - ch
        blank_key = (role, "__blank__")
        if blank_key not in variants:
            p = vdir / f"{role}_blank.mov"
            variants[blank_key] = {"path": p, "frames": BLANK_VARIANT_FRAMES}
            jobs.append([ffmpeg, "-y", "-v", "error", "-f", "lavfi",
                         "-i", f"color=c=black@0.0:s={cw}x{ch}:r={fps},format=rgba",
                         "-frames:v", str(BLANK_VARIANT_FRAMES), "-c:v", "png",
                         "-video_track_timescale", str(fps), str(p)])
        # 区間（フレーム単位）。話している区間（talk_end まで）と、その後の区間に分ける
        pieces = []
        for i, (t, st) in enumerate(dedup):
            f0 = int(round(t * fps))
            f1 = int(round(dedup[i + 1][0] * fps)) if i + 1 < len(dedup) else total_frames
            f1 = min(f1, total_frames)
            if f1 <= f0:
                continue
            speaking = st.get("mode") != "blank" and (st.get("speaker") == role or st.get("speaker") == "both")
            te = st.get("talk_end")
            if talk and speaking and te is not None:
                fm = min(f1, max(f0, int(round(te * fps))))
                if fm > f0:
                    pieces.append((f0, fm, st, True))
                if f1 > fm:
                    pieces.append((fm, f1, st, False))
            else:
                pieces.append((f0, f1, st, False))
        segs = []
        for f0, f1, st, talking in pieces:
            if st.get("mode") == "blank":
                key = blank_key
            else:
                active = st.get("speaker") == role or st.get("speaker") == "both"
                expr = (st.get("exprs") or {}).get(role, "neutral")
                sh = layout["sprite_h_chart"] if st.get("chart") else layout["sprite_h"]
                kind = "talk" if talking and cast_video_path(role, expr, "talk") is not None else "idle"
                key = (role, expr, sh, active, kind)
                if key not in variants:
                    sp = bank.get(role, expr, sh, active)
                    sx = sprite_x(sp.width) - cx
                    sy = ch - sp.height
                    # 名札（立ち絵の上に重ねる。明暗の切り替えを立ち絵と同じクロスフェードにするため、ここに入れる）
                    plate = vdir / f"{role}_plate_{sh}_{'a' if active else 'i'}.png"
                    if not plate.exists():
                        pim = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
                        draw_nameplate(ImageDraw.Draw(pim), cast, role, sprite_x(sp.width) - cx, sp.width, ch, big, active)
                        pim.save(plate)
                    vf = (f"[0:v]scale={sp.width}:{sp.height}:flags=lanczos,format=rgba"
                          + ("" if active else f",colorchannelmixer=rr={INACTIVE_BRIGHTNESS}:gg={INACTIVE_BRIGHTNESS}:bb={INACTIVE_BRIGHTNESS}")
                          + f",pad={cw}:{ch}:{sx}:{sy}:color=black@0.0,setsar=1[sp];[sp][1:v]overlay=0:0:format=rgb,format=rgba")
                    p = vdir / f"{role}_{expr}_{sh}_{'a' if active else 'i'}_{kind}.mov"
                    src = cast_video_path(role, expr, kind)
                    if src is not None:
                        n = _loop_frames(src, ffmpeg)
                        inp = ["-c:v", "libvpx-vp9", "-i", str(src)]
                    else:
                        n = STATIC_VARIANT_FRAMES
                        png = CAST_DIR / f"{role}_{expr}.png"
                        if not png.exists():
                            png = CAST_DIR / f"{role}_neutral.png"
                        inp = ["-loop", "1", "-framerate", str(fps), "-i", str(png)]
                    variants[key] = {"path": p, "frames": n}
                    jobs.append([ffmpeg, "-y", "-v", "error"] + inp + ["-loop", "1", "-i", str(plate)] +
                                ["-filter_complex", vf, "-frames:v", str(n), "-r", str(fps), "-an", "-c:v", "png",
                                 "-video_track_timescale", str(fps), str(p)])
            if segs and segs[-1][2] == key and segs[-1][1] == f0:
                segs[-1][1] = f1
            else:
                segs.append([f0, f1, key])
        # 口パクのヒステリシス（2026-10-17）: 台詞の合間の短い間（TALK_HOLD_GAP 秒未満）で talk→待機→talk と
        # 細かく切り替わらないよう、その間は直前の talk のまま口を動かし続ける
        if talk:
            # 話し終わりの直後に短い待機だけはさんで別の見た目に替わる場合も同じ（kl042 の大輔は、台詞の後
            # 0.2〜0.3秒だけ待機ループになってから聞き手の表情に替わり、短い間に2回切り替わっていた）
            gap = int(round(TALK_HOLD_GAP * fps))
            for i in range(1, len(segs)):
                a, b = segs[i - 1], segs[i]
                if (len(a[2]) == 5 and len(b[2]) == 5 and a[2][4] == "talk" and b[2][4] == "idle"
                        and b[2][:4] == a[2][:4] and b[1] - b[0] < gap):
                    b[2] = a[2]
            merged = []
            for sg in segs:
                if merged and merged[-1][2] == sg[2] and merged[-1][1] == sg[0]:
                    merged[-1][1] = sg[1]
                else:
                    merged.append(list(sg))
            segs = merged
        lst = tmp / f"sprites_{role}.ffconcat"
        n_entries = _write_phase_list(lst, segs, variants, fps)
        info = {"role": role, "list": lst, "x": cx, "y": cy, "segments": len(segs), "entries": n_entries,
                "segs": [(f0, f1, key) for f0, f1, key in segs]}
        # 切り替えのクロスフェード（2026-10-17）: 区間の境目から SPRITE_XFADE_FRAMES フレームかけて、前の見た目
        # （同じ位相で続けたもの）から新しい見た目へ重ねて移る。前の見た目のトラック（境目を後ろへずらしたもの）と
        # 重みのトラックを作り、kl_video_gen.overlay_dialogue が maskedmerge で混ぜる
        K = SPRITE_XFADE_FRAMES
        if K > 0 and len(segs) > 1:
            last = len(segs) - 1

            def kb(i):  # 境目 i（segs[i] の頭）を重ねるフレーム数。表情（手のポーズ）が変わるときは長め
                a, b = segs[i - 1][2], segs[i][2]
                return SPRITE_XFADE_EXPR_FRAMES if (len(a) == 5 and len(b) == 5 and a[1] != b[1]) else K
            prev_segs = []
            for i, (f0, f1, key) in enumerate(segs):
                g0 = 0 if i == 0 else min(total_frames, f0 + kb(i))
                g1 = total_frames if i == last else min(total_frames, f1 + kb(i + 1))
                if g1 > g0:
                    prev_segs.append([g0, g1, key])
            plst = tmp / f"sprites_{role}_prev.ffconcat"
            _write_phase_list(plst, prev_segs, variants, fps)
            # 重み（0〜255）: 境目の直後 K フレームは (j+1)/(K+1)、それ以外は 255
            wt = []
            bounds = [f0 for f0, _, _ in segs[1:]]
            cur = 0
            for bi, b in enumerate(bounds):
                if b > cur:
                    wt.append([cur, b, ("mask", 255)])
                nb = bounds[bi + 1] if bi + 1 < len(bounds) else total_frames
                kk = kb(bi + 1)
                for j in range(kk):
                    fj = b + j
                    if fj >= nb or fj >= total_frames:
                        break
                    # なめらかに（smoothstep）
                    x = (j + 1) / (kk + 1)
                    wt.append([fj, fj + 1, ("mask", int(round(255 * x * x * (3 - 2 * x))))])
                cur = min(nb, b + kk, total_frames)
            if cur < total_frames:
                wt.append([cur, total_frames, ("mask", 255)])
            for _, _, mk in wt:
                if (role, mk) not in variants:
                    v = mk[1]
                    nfr = 24 if v == 255 else 1
                    mp = vdir / f"{role}_mask_{v:03d}.mov"
                    png = vdir / f"{role}_mask_{v:03d}.png"
                    Image.new("RGBA", (cw, ch), (v, v, v, v)).save(png)
                    variants[(role, mk)] = {"path": mp, "frames": nfr}
                    jobs.append([ffmpeg, "-y", "-v", "error", "-loop", "1", "-framerate", str(fps), "-i", str(png),
                                 "-frames:v", str(nfr), "-r", str(fps), "-c:v", "png",
                                 "-video_track_timescale", str(fps), str(mp)])
            mlst = tmp / f"sprites_{role}_mask.ffconcat"
            _write_phase_list(mlst, [[a, b, (role, mk)] for a, b, mk in wt], variants, fps)
            info.update({"prev_list": plst, "mask_list": mlst, "xfades": len(bounds)})
        tracks.append(info)

    def run(cmd):
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError("立ち絵のループの準備に失敗: " + " ".join(cmd[-1:]) + "\n" + r.stderr[-1500:])
    with ThreadPoolExecutor(6) as ex:
        list(ex.map(run, jobs))
    looks = [k for k in variants if len(k) == 5]
    n_video = sum(1 for k in looks if cast_video_path(k[0], k[1], k[4]))
    n_talk = sum(1 for k in looks if k[4] == "talk")
    print(f"  ▶ 立ち絵トラック: 見た目{len(looks)}種類（うち動画{n_video}、話しているループ{n_talk}）/ "
          + " / ".join(f"{t['role']} 区間{t['segments']}・並び{t['entries']}・重ねる切り替え{t.get('xfades', 0)}" for t in tracks))
    return {"tracks": tracks, "bar": bar_info}


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


# ── 資料カード（構成 v2） ────────────────────────────────────────────

CARD_BG_ASSET = BASE_DIR / "assets" / "base_cafe.png"
CARD_BOX = (196, 34, 1212, 592)   # 1408×768 上の位置。左右の立ち絵（check では高さ240・幅約180）と下の字幕帯（618〜）を避ける
_NO_HEAD = set("、。，．！？!?」』）)…ーゃゅょっぁぃぅぇぉャュョッァィゥェォ ")


def _wrap_chars(text: str, font, max_w: int) -> list:
    """折り返し（行頭禁則つき）。文節の切れ目（kl_telop_gen の形態素境界）と句読点を優先し、
    数字・英単語の途中では切らない。[(start, end), ...] を返す。"""
    d = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    n = len(text)
    try:
        from kl_telop_gen import _token_boundaries
        good = {b for b in _token_boundaries(text) if 0 < b < n}
    except Exception:  # janome が無い環境
        good = set()
    good |= {i + 1 for i, ch in enumerate(text) if ch in "、。，．）」』・ "}
    alnum = lambda c: c.isascii() and (c.isalnum() or c in ".-%")
    # 形態素解析が英単語の途中に切れ目を付けることがある（"cod|e"）。英数字どうしの間は切れ目にしない
    good = {b for b in good if not (alnum(text[b - 1]) and alnum(text[b]))}
    rows, i = [], 0
    while i < n:
        j = i + 1
        while j < n and d.textlength(text[i:j + 1], font=font) <= max_w:
            j += 1
        if j < n:
            # 行の後ろ1/3以内に文節の切れ目があればそこで切る
            cands = [b for b in good if i + (j - i) * 2 // 3 <= b <= j]
            if cands:
                j = max(cands)
            else:
                while j - i > 1 and alnum(text[j - 1]) and alnum(text[j]):
                    j -= 1
            while j < n and text[j] == " ":  # 行頭の空白は読み飛ばす（戻ると英単語の途中で切れる）
                j += 1
            while j < n and text[j] in _NO_HEAD and text[j] != " " and j - i > 1:  # 次の行頭に句読点を置かない
                j -= 1
        rows.append((i, j))
        i = j
    return rows


def render_source_card(card: dict, out_path: Path, W: int = 1408, H: int = 768) -> None:
    """一次資料の該当箇所を、いつものカフェ（ぼかし）の上に置いた紙の資料として描く。
    文字はAIに描かせず、実フォントで正確に描く（数字・引用の捏造・誤字を防ぐ）。
    card: {kind, source, quote?, quote_type(原文/要約)?, highlight?, items?[], note?}"""
    bg = Image.open(CARD_BG_ASSET).convert("RGB").resize((W, H), Image.LANCZOS)
    from PIL import ImageFilter
    bg = ImageEnhance.Brightness(bg.filter(ImageFilter.GaussianBlur(14))).enhance(0.62).convert("RGBA")
    x0, y0, x1, y1 = CARD_BOX
    # 影と紙
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((x0 + 8, y0 + 10, x1 + 8, y1 + 10), radius=18, fill=(0, 0, 0, 110))
    bg.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(8)))
    dr = ImageDraw.Draw(bg)
    dr.rounded_rectangle((x0, y0, x1, y1), radius=18, fill=(252, 250, 245, 255))
    kind_label, kcol = CARD_KINDS.get(card.get("kind"), ("資料", (110, 118, 130)))
    # 見出し: 種類のチップ＋資料名
    fk, fs = _font(FONT_BOLD, 28), _font(FONT_MEDIUM, 26)
    pad = 36
    kw = _text_w(dr, kind_label, fk)
    dr.rounded_rectangle((x0 + pad, y0 + 26, x0 + pad + kw + 32, y0 + 26 + 46), radius=10, fill=kcol)
    dr.text((x0 + pad + 16, y0 + 31), kind_label, font=fk, fill=(255, 255, 255))
    src = card.get("source", "")
    sx = x0 + pad + kw + 32 + 18
    ss = 26
    while ss > 19 and _text_w(dr, src, _font(FONT_MEDIUM, ss)) > x1 - pad - sx:  # 資料名は1行に収める
        ss -= 1
    dr.text((sx, y0 + 34 + (26 - ss) // 2), src, font=_font(FONT_MEDIUM, ss), fill=(70, 78, 92))
    top = y0 + 26 + 46 + 26
    dr.line((x0 + pad, top - 12, x1 - pad, top - 12), fill=kcol + (255,), width=3)
    # 本文の大きさを決めてから描く（大きい字から試し、箇条書きは1項目1行に収まるまで縮める）
    max_w = (x1 - x0) - pad * 2
    footer_h = 40
    avail = (y1 - 22 - footer_h) - top
    quote, items = card.get("quote", ""), card.get("items") or []
    size_q, size_i = 50, 42
    while True:
        fq, fi = _font(FONT_MEDIUM, size_q), _font(FONT_MEDIUM, size_i)
        q_rows = _wrap_chars(f"「{quote}」", fq, max_w) if quote else []
        i_rows = [_wrap_chars(it, fi, max_w - 34) for it in items]
        h = len(q_rows) * int(size_q * 1.45) + (18 if quote and items else 0) + sum(len(r) for r in i_rows) * int(size_i * 1.42)
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
                dr.rectangle((hx0 - 2, y + int(size_q * 0.55), hx1 + 2, y + int(size_q * 1.18)), fill=(255, 214, 90))
            dr.text((x0 + pad, y), row, font=fq, fill=(28, 34, 46))
            y += lh
        y += 18
    for rows, it in zip(i_rows, items):
        lh = i_lh
        dr.ellipse((x0 + pad + 4, y + size_i // 2 - 6, x0 + pad + 16, y + size_i // 2 + 6), fill=kcol)
        for a, b in rows:
            dr.text((x0 + pad + 34, y), it[a:b], font=fi, fill=(28, 34, 46))
            y += lh
    # 足元: 原文か要約か、注記
    ff = _font(FONT_MEDIUM, 22)
    q_orig = quote and card.get("quote_type", "原文") == "原文"
    if quote and items:
        tag = "「…」は原文から引用、・は要約" if q_orig else "要約"
    else:
        tag = "原文から引用" if q_orig else "要約"
    foot = tag + (f"　{card['note']}" if card.get("note") else "")
    fw = _text_w(dr, foot, ff)
    dr.text((x1 - pad - fw, y1 - 22 - 28), foot, font=ff, fill=(120, 126, 138))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    bg.convert("RGB").save(out_path, "PNG")


def render_episode_cards(ep: dict) -> list:
    """source_card を持つシーンのカードを assets/cards/{episode}_S{NN}.png に描き、image_asset を書き込む。"""
    done = []
    for s in ep.get("scenes", []):
        if not s.get("source_card"):
            continue
        name = _card_asset_name(ep, s)
        render_source_card(s["source_card"], BASE_DIR / "assets" / f"{name}.png")
        s["image_asset"] = name
        s.pop("image_prompt", None)
        done.append((s["scene_id"], BASE_DIR / "assets" / f"{name}.png"))
    return done


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
    ap = argparse.ArgumentParser(description="掛け合い形式の台本チェック／資料カードの描画")
    ap.add_argument("command", choices=["check", "cards"],
                    help="check: 構造チェック（narration を同期）／cards: 資料カード（source_card）を描いて image_asset を書き込む")
    ap.add_argument("--episode", required=True)
    ap.add_argument("--path", help="episodes/ 以外のJSONを確認するとき（試し書き・テスト用）。指定したファイルに narration を同期する")
    args = ap.parse_args()
    path = Path(args.path) if args.path else BASE_DIR / "episodes" / f"{args.episode}.json"
    ep = json.loads(path.read_text(encoding="utf-8"))
    cast = load_cast()
    if args.command == "cards":
        done = render_episode_cards(ep)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(ep, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        for sid, p in done:
            print(f"✅ S{sid:02d}: {p}")
        print(f"資料カード {len(done)}枚。kl_image_gen.py が image_asset としてコピーする"
              f"（Desktop に古い S{{NN}}.png があるときは --scenes で指定して上書きする）")
        return
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
    st = ep.get("structure")
    if st == STRUCTURE_V3:
        print("構成: rounds_v3（使い道ラウンド。v2 の規則＋下記）")
        print(f"  必須タグ: {', '.join(required_tags(ep))}（life_scene は不要）")
        print(f"  dream: 任意・{V3_MAX_DREAM}つまで／use_case は大輔・論点の中・その後に同じ論点の check／takeaway は verdict")
        print(f"  常套句の上限（v3 追加）: " + "、".join(f"「{k}」{v}回" for k, v in V3_PHRASE_LIMITS.items()))
    elif st == STRUCTURE_V2:
        print("構成: rounds_v2（論点ラウンド。kl041・kl042。新しい回は rounds_v3）")
    else:
        print("構成: 従来（structure なし。kl031〜kl040）")
    for w in episode_warnings(ep):
        print("⚠ " + w)
    if errs:
        print(f"❌ {len(errs)}件の問題:")
        for e in errs:
            print("  - " + e)
        sys.exit(1)
    print("✅ 構造チェックOK（narration/narrator を同期しました）")


if __name__ == "__main__":
    main()
