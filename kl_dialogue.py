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
    "transcript": ("書き起こし", (176, 96, 64)),   # 発言・説明会の書き起こし（2026-11-03、kl051）
    "web":    ("製品ページ", (60, 130, 90)),       # 会社の製品紹介ページ（2026-11-03、kl051）
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
# ── 構成 v4「実現ラウンド」（2026-10-26、kl049 以降。DIALOGUE_REDESIGN_2026-10-26.md） ──────────────
# なるさんの指摘「沙織の意見が強くて、結局は夢を潰す感じになる」を受けて、問いを「本当か？」から
# 「どこまで来た？ どうすれば使える？」に変えた。v3 の規則をすべて引き継いだうえで、
#   - 各論点は「壁 → 越え方（workaround）→ 残った手応え（hope、論点の最後の行）」で終える
#   - 沙織も「本物なら私はこれに使いたい」（skeptic_wish）を言う。沙織が譲る turn を必須にする（v3 は ⚠）
#   - 画面の札は verdict（二人が育てた使い道への札）だけ。claim_verdict（発表の言い方の見立て）は記録用で、画面に出さない
#     （2026-10-26、kl049 の初見レビューと制作者の「札が2組あって追いにくい。分かりやすくしよう」で、2組表示をやめた）
#   - 判定の後に、視聴者が今日・今月できる一歩（next_step）を言う
STRUCTURE_V4 = "rounds_v4"
V3_FAMILY = (STRUCTURE_V3, STRUCTURE_V4)          # v3 の規則が効く構成（v4 は v3 を引き継ぐ）
ROUND_STRUCTURES = (STRUCTURE_V2, STRUCTURE_V3, STRUCTURE_V4)
V3_TAGS = {
    "use_case": "大輔（dreamer）が論点の中で置く具体的な使い道。同じ論点の check で一次資料に当てる",
    "takeaway": "verdict で言う「誰が・何に・どんな条件で／いつ」使えるか（どちらが言ってもよい）",
}
V3_PHRASE_LIMITS = {
    "言い直": 0,          # 「言い直す」「言い直し」。崩された夢を言い直す型をやめる
    "想像してみて": 1,    # 旧口癖。使うなら1回まで（dream を置く回だけ）
}
V3_MAX_DREAM = 1
V4_TAGS = {
    "workaround": "壁に対する越え方（条件・使い方・待てば変わること）。各論点に1つ以上",
    "hope": "論点の最後の行で言う「残った手応え」（資料で確かめられた、前向きに使える事実）",
    "skeptic_wish": "沙織（skeptic）が言う「本物なら、私はこれに使いたい」",
    "next_step": "判定の後に言う、視聴者が今日・今月できる一歩（verdict か closing の中）",
}
# 論点の最後の3行に置くと「潰して終わる」形になりやすい言い回し（⚠）
V4_DOWNBEAT_PHRASES = ("測ってない", "測っていない", "分からない", "わからない", "資料は無い", "資料は、まだ無い",
                       "まだ無い", "条件つき", "確かめていない")
# 大輔が夢を小さくして終わる言い回し（⚠。「だったら、こう使う」と条件をつけて前に進む）
V4_RETREAT_PHRASES = ("狭める", "危ない", "無理", "諦め", "あきらめ")
V4_DOWNBEAT_VERDICTS = ("pending", "dubious")
# 2026-10-26: 大輔の旧口癖。発表元がもう決めている使い道を大輔の思いつきのように言い直す決まり文句になっていた（なるさんの指摘）
V4_PHRASE_LIMITS = {
    "僕なら、これに使う": 0,
    "次は、どこで使える": 1,    # 新しい口癖。決まり文句にしない
}

VERDICT_KEYS = ("soon", "decade", "pending", "dubious")  # pending（根拠待ち）は2026-10-18追加
REQUIRED_TAGS = {
    "question": "冒頭の問い（teaser内）",
    "life_scene": "夢語りが描く具体的な生活の一場面（誰が・いつ・何をできるようになるか）",
    "weakness": "ツッコミが言う、この研究の一番の弱点",
    "barrier": "ツッコミが言う、実用化までの壁",
}


def required_tags(ep: dict) -> dict:
    """構成ごとの必須タグ。v3 は life_scene を外し、use_case・takeaway を足す。v4 はさらに V4_TAGS を足す。"""
    if ep.get("structure") in V3_FAMILY:
        tags = {k: v for k, v in REQUIRED_TAGS.items() if k != "life_scene"}
        tags.update(V3_TAGS)
        if ep.get("structure") == STRUCTURE_V4:
            tags.update(V4_TAGS)
        return tags
    return dict(REQUIRED_TAGS)


def phrase_limits(ep: dict) -> dict:
    limits = dict(PHRASE_LIMITS)
    if ep.get("structure") in V3_FAMILY:
        limits.update(V3_PHRASE_LIMITS)
    if ep.get("structure") == STRUCTURE_V4:
        limits.update(V4_PHRASE_LIMITS)
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
    if scene.get("chart"):
        import kl_motion
        out += "\n［画面のグラフ］" + kl_motion.chart_text(scene["chart"])
    for v in scene_visuals(scene):
        t = visual_text(v)
        if t:
            out += "\n" + t
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
    v4 = ep.get("structure") == STRUCTURE_V4
    v3 = ep.get("structure") in V3_FAMILY           # v4 は v3 の規則をすべて引き継ぐ
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
            if s.get("shows_product") and not s.get("real_photo") and "イメージ" not in (s.get("badge_text") or ""):
                errs.append(f"S{s['scene_id']}: 実在の製品を描いたシーン（shows_product）には badge_text に「イメージ図」を入れてください")
        if "イメージ図" not in ep.get("youtube_description", ""):
            errs.append("実在の製品を描く回は、概要欄に「イメージ図」の注記を入れてください")
        for i, c in enumerate(shorts if False else (ep.get("shorts") or [{}])[0].get("scenes") or [], start=1):
            ref = next((s for s in scenes if s.get("scene_id") == c.get("scene_id")), None)
            if ref and ref.get("shows_product") and not ref.get("real_photo") and "イメージ" not in (c.get("badge_text") or ""):
                errs.append(f"Shorts {i}カット目: 製品を描いた場面には badge_text（イメージ図）を付けてください")

    # 実物の写真（kl_photo_commons.py、2026-11-04）: 出所の記録・使えるライセンス・概要欄のクレジットが揃っていること
    for s in scenes:
        if not s.get("real_photo"):
            continue
        sid = s["scene_id"]
        rec_path = BASE_DIR / "assets" / "photos" / f"{ep.get('episode_id', '')}_S{sid:02d}.json"
        if s.get("image_asset") != f"photos/{ep.get('episode_id', '')}_S{sid:02d}" or not rec_path.exists():
            errs.append(f"S{sid}: 写真シーン（real_photo）の画像または出所の記録が見つかりません。"
                        f"`python3 kl_photo_commons.py fetch --episode {ep.get('episode_id', 'klNNN')} --scene {sid} --file ... --apply` で取り込んでください")
            continue
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
        lic = rec.get("license", "")
        if not _re.match(r"^(cc0|public domain|pd\b|cc[ -]by(-sa)?[ -][0-9.]+)", lic, _re.I) or _re.search(r"(\bnc\b|-nc|\bnd\b|-nd|gfdl|fair use|non-free)", lic, _re.I):
            errs.append(f"S{sid}: 使えないライセンスの写真です: {lic or '不明'}")
        name = rec.get("title", "").removeprefix("File:")
        if name not in ep.get("youtube_description", ""):
            errs.append(f"S{sid}: 概要欄に写真クレジットがありません（`python3 kl_photo_commons.py apply --episode {ep.get('episode_id', 'klNNN')} --scene {sid}`）")

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
    errs += validate_visuals(ep)
    if v2:
        errs += validate_rounds_v2(ep)
    if v3:
        errs += validate_rounds_v3(ep)
    if v4:
        errs += validate_rounds_v4(ep)
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


def _round_lines(ep: dict) -> dict:
    """論点の番号 → その論点の台詞（シーン順）の [(scene, line_index, line)]。"""
    out = {}
    for s in ep["scenes"]:
        n = s.get("round")
        if isinstance(n, int):
            out.setdefault(n, []).extend((s, i, l) for i, l in enumerate(s.get("lines") or []))
    return out


def validate_rounds_v4(ep: dict) -> list:
    """構成 v4（実現ラウンド）の追加チェック。v2・v3 の規則は別に通す。"""
    errs = []
    scenes = ep["scenes"]
    for n, ls in sorted(_round_lines(ep).items()):
        if not ls:
            continue
        s, i, last = ls[-1]
        if last.get("tag") != "hope":
            errs.append(f"v4: 論点{n}の最後の行（S{s['scene_id']} 行{i + 1}）に tag 'hope'（残った手応え）を付けてください。"
                        "限界はその前に言い終え、資料で確かめられた前向きに使える事実で論点を終える")
        if not any(l.get("tag") == "workaround" for _, _, l in ls):
            errs.append(f"v4: 論点{n}に tag 'workaround'（壁の越え方）の行がありません")
    for s in scenes:
        for i, l in enumerate(s.get("lines") or []):
            tag, where = l.get("tag"), f"v4: S{s['scene_id']} 行{i + 1}"
            if tag == "skeptic_wish" and l.get("speaker") != "skeptic":
                errs.append(f"{where}: tag 'skeptic_wish' は沙織（skeptic）の台詞に付けてください")
            if tag == "hope" and not isinstance(s.get("round"), int):
                errs.append(f"{where}: tag 'hope' は論点の中（各論点の最後の行）に付けてください")
            if tag == "next_step" and s.get("type") not in ("verdict", "closing"):
                errs.append(f"{where}: tag 'next_step' は verdict か closing の台詞に付けてください（判定の後に言う）")
    if not any(l.get("tag") == "turn" and l.get("speaker") == "skeptic" for s in scenes for l in s.get("lines") or []):
        errs.append("v4: 沙織が譲る turn（大輔の側を支える資料で、沙織が認める論点）がありません")
    cv = ep.get("claim_verdict") or {}
    for r in ROLES:
        if cv.get(r) not in VERDICT_KEYS:
            errs.append(f"v4: claim_verdict.{r}（発表の言い方の見立て、記録用・画面には出さない）は {VERDICT_KEYS} のどれかにしてください。"
                        "verdict は二人が育てた使い道への札")
    return errs


def recent_downbeat_share(ep: dict, n: int = 5) -> tuple:
    """この回を含む直近 n 話（rounds_v4）の、使い道への札（verdict、二人分）のうち根拠待ち・まだ眉唾の割合。"""
    try:
        num = int(str(ep.get("episode_id", ""))[2:])
    except ValueError:
        return 0, 0
    votes = []
    for k in range(num, 0, -1):
        if len(votes) >= n * 2:
            break
        p = BASE_DIR / "episodes" / f"kl{k:03d}.json"
        e = ep if k == num else (json.loads(p.read_text(encoding="utf-8")) if p.exists() else None)
        if not e or e.get("structure") != STRUCTURE_V4:
            continue
        votes += [(e.get("verdict") or {}).get(r) for r in ROLES]
    bad = sum(1 for v in votes if v in V4_DOWNBEAT_VERDICTS)
    return bad, len(votes)


def episode_warnings(ep: dict) -> list:
    """不合格にはしないが、STEP5で見てほしいこと（⚠ として表示する）。"""
    warns = []
    if ep.get("structure") == STRUCTURE_V4:
        for n, ls in sorted(_round_lines(ep).items()):
            for s, i, l in ls[-3:]:
                hit = [p for p in V4_DOWNBEAT_PHRASES if p in l.get("text", "")]
                if hit:
                    warns.append(f"v4: 論点{n}の終わり（S{s['scene_id']} 行{i + 1}）に「{hit[0]}」。限界は越え方の前に言い、"
                                 "論点を「残った手応え」で終える形になっているか確認")
        for s in ep["scenes"]:
            for i, l in enumerate(s.get("lines") or []):
                if l.get("speaker") == "dreamer":
                    hit = [p for p in V4_RETREAT_PHRASES if p in l.get("text", "")]
                    if hit:
                        warns.append(f"v4: S{s['scene_id']} 行{i + 1}: 大輔の「{hit[0]}」。夢を小さくして終わらず、"
                                     "「だったら、こう使う」と条件をつけて前に進む言い方にできないか")
        bad, tot = recent_downbeat_share(ep)
        if tot >= 6 and bad * 2 > tot:
            warns.append(f"v4: 直近の v4 の回で、使い道への札の{bad}/{tot}が根拠待ち・まだ眉唾です。"
                         "ネタ選び（本物の進歩で使い道を描けるか）を見直す合図")
    elif ep.get("structure") == STRUCTURE_V3:
        # 大輔が正しかった論点（沙織が譲る turn）が1つ以上あるか。毎回大輔が論破されるだけの型を避ける
        if not any(l.get("tag") == "turn" and l.get("speaker") == "skeptic"
                   for s in ep["scenes"] for l in s.get("lines") or []):
            warns.append("v3: 沙織が譲る turn（大輔が正しかった論点）がありません。大輔が論破されるだけの回になっていないか、STEP5で確認")
    # ニュース回のタイトルと概要欄1行目（2026-11-04、なるさんの決定）。タイトルは月だけ（「（11月時点）」）、発表日は書かない。
    # 概要欄の1行目に、発表日と判定の時点を書く。不合格にはしない（過去の回は旧形式のまま）
    if ep.get("source_type") == "news":
        title = ep.get("youtube_title", "")
        if _re.search(r"\d{1,2}月\d{1,2}日", title):
            warns.append(f"タイトルに日付（月日）が入っています: 「{title}」。タイトルは「（11月時点）」のように月だけにし、発表日は概要欄の1行目へ")
        first = next((ln for ln in (ep.get("youtube_description") or "").splitlines() if ln.strip()), "")
        if "時点" not in first or "発表" not in first:
            warns.append("概要欄の1行目に、発表日と判定の時点がありません（例「2026年10月21日の発表を、11月2日時点で確認した二人の見立て」）")
    # 画面の単調さ（2026-11-09、kl054 の全面作り直しの反省。不合格にはしない）。音声ができた後（t0 がある）に確かめる:
    # カフェの固定背景が40秒を超えて出ている区間、本編に実写真が1枚もない回
    if ep.get("structure") in (STRUCTURE_V2, STRUCTURE_V3, STRUCTURE_V4):
        has_photo = False
        for sc in ep.get("scenes", []):
            lines_ = sc.get("lines") or []
            base = str(sc.get("image_asset") or "")
            if base.startswith("photos/") or sc.get("real_photo"):
                has_photo = True
            for v in scene_visuals(sc):
                if (v.get("image_asset") or "").startswith("photos/") or (v.get("bg_asset") or "").startswith("photos/"):
                    has_photo = True
            if sc.get("type") == "teaser" or not lines_ or not all("t0" in l for l in lines_):
                continue
            dur_ = 0.5 + lines_[-1]["t0"] + lines_[-1].get("dur", 0) + 1.0
            vis_ = scene_visuals(sc)
            segs = [(a, b, v) for a, b, v in visual_segments(sc, dur_, 0.5)] if vis_ else [(0.0, dur_, None)]
            for a, b, v in segs:
                cafe = base.startswith("base_cafe") and (v is None or v.get("scene_image"))
                if cafe and b - a > 40:
                    warns.append(f"画面: S{sc.get('scene_id')} でカフェの固定背景が{b - a:.0f}秒続きます（40秒まで）。"
                                 "写真・資料カード・グラフ・まとめのカードを scene.visuals で挟んでください")
        if not has_photo and any("t0" in l for sc in ep.get("scenes", []) for l in sc.get("lines") or []):
            warns.append("画面: 本編に実写真が1枚もありません。製品・場所・人の実物の写真（kl-new.md STEP2 の写真の手順）を探してください")
    # 問いゲート（2026-11-09〜、kl054 の全面作り直しの反省）。kl055 以降は script_prep/klNNN_question.md に「承認:」の行が必要
    try:
        _num = int(str(ep.get("episode_id", ""))[2:])
    except ValueError:
        _num = 0
    if _num >= 55:
        _qp = BASE_DIR / "script_prep" / f"{ep.get('episode_id')}_question.md"
        if not _qp.exists() or "承認:" not in _qp.read_text(encoding="utf-8"):
            warns.append(f"問いゲート: script_prep/{ep.get('episode_id')}_question.md が無いか、承認の記録（「承認:」の行）がありません。"
                         "kl-new.md「STEP 1.5 — 問いゲート」を先に済ませてください")
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
    # 6b) グラフ（scene.chart。棒が伸びて数字が増える動き。値は資料の数字そのまま）
    for s in scenes:
        c = s.get("chart")
        if not c:
            continue
        card_ids.add(s["scene_id"])
        where = f"S{s['scene_id']}"
        if s.get("type") != "check":
            errs.append(f"v2: {where}: chart は check シーンに置いてください")
        if s.get("source_card"):
            errs.append(f"v2: {where}: chart と source_card は同じシーンに置けません（別のシーンに分ける）")
        kind = c.get("kind", "bar")
        if kind not in ("bar", "line", "number"):
            errs.append(f"v2: {where}: chart.kind は bar / line / number")
        if not c.get("source"):
            errs.append(f"v2: {where}: chart.source（資料名と日付）がありません")
        if not c.get("title") or len(c["title"]) > 30:
            errs.append(f"v2: {where}: chart.title は1〜30字")
        if len(c.get("unit", "")) > 6:
            errs.append(f"v2: {where}: chart.unit は6字以内")
        for an in c.get("annotations") or []:
            # 注釈（囲み・矢印）: target は items の番号かラベル、text は12字以内（省略可）。bar / line のみ
            tg = an.get("target")
            its_ = c.get("items") or []
            if kind == "number" or not (isinstance(tg, int) and 0 <= tg < len(its_) or tg in [i.get("label") for i in its_]):
                errs.append(f"v2: {where}: chart.annotations の target は items の番号かラベル（bar / line のみ）")
            at_ = an.get("at")
            if at_ is not None and (not isinstance(at_, (int, float)) or at_ < 0 or at_ > 20):
                errs.append(f"v2: {where}: chart.annotations の at は 0〜20 秒（シーンの頭から。描き終わりに 1.1 秒かかるので、台詞の終わりの前に出す）")
            if len(an.get("text", "")) > 12:
                errs.append(f"v2: {where}: chart.annotations の text は12字以内")
        if kind in ("bar", "line"):
            its = c.get("items") or []
            if not (2 <= len(its) <= (8 if kind == "line" else 6)):
                errs.append(f"v2: {where}: chart.items は2〜{8 if kind == 'line' else 6}本")
            for it in its:
                v = it.get("value")
                if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0:
                    errs.append(f"v2: {where}: chart.items の value は0以上の数（{it.get('label')}）")
                if not it.get("label") or len(it["label"]) > 14:
                    errs.append(f"v2: {where}: chart.items の label は1〜14字（{str(it.get('label'))[:8]}…）")
            hl = c.get("highlight")
            if hl is not None and not (isinstance(hl, int) and 0 <= hl < len(its)) and hl not in [i.get("label") for i in its]:
                errs.append(f"v2: {where}: chart.highlight は items の番号（0始まり）かラベル")
        else:
            if not isinstance(c.get("value"), (int, float)) or isinstance(c.get("value"), bool) or c["value"] < 0:
                errs.append(f"v2: {where}: chart.value は0以上の数")
            if len(c.get("caption", "")) > 26:
                errs.append(f"v2: {where}: chart.caption は26字以内")
        ri = c.get("reference_index", s.get("reference_index"))
        if not isinstance(ri, int) or not (0 <= ri < len(ep.get("references") or [])):
            errs.append(f"v2: {where}: chart の reference_index が references にありません")
        want = _card_asset_name(ep, s)
        if s.get("image_asset") != want or not (BASE_DIR / "assets" / f"{want}.png").exists():
            errs.append(f"v2: {where}: グラフの静止画がありません（python3 kl_dialogue.py cards --episode {ep.get('episode_id')}）")
        if s.get("image_prompt"):
            errs.append(f"v2: {where}: chart のシーンに image_prompt は書かない（グラフは数字から描く）")
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


FOCUS_ACTIVE = 1.07   # 話している側を少し大きく・前に（動画の立ち絵のみ。聞き手は 0.94 倍＋暗く。2026-11-07）


class SpriteBank:
    def __init__(self, cast: dict, focus: float = 1.0):
        self.cast = cast
        self.focus = focus   # 話し手の拡大率（1.0 は従来どおり）
        self._cache = {}

    def get(self, role: str, expr: str, h: int, active: bool) -> Image.Image:
        key = (role, expr, h, active)
        if key not in self._cache:
            path = CAST_DIR / f"{role}_{expr}.png"
            if not path.exists():
                path = CAST_DIR / f"{role}_neutral.png"
            im = Image.open(path).convert("RGBA")
            hh = int(h * self.focus) if active else int(h * 0.94)
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
        y = state.get("stamp_y") or int(H * (0.06 if W > 1000 else 0.24))
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
        pop = state.get("pop")
        if pop and not teaser:
            # 出現の瞬間だけ少し小さい字から大きくなる（ポップイン。2026-11-07）。行の折り返しは最終の大きさと同じにするため、
            # 最終の f で行を決めたあと、同じ行を pop 倍の字で描く
            f = _font(FONT_MEDIUM, max(8, int(f.size * pop)))
            line_h = int(f.size * 1.32)
            y = cy - (line_h * len(rows)) // 2
        for r in rows:
            if state.get("kw") and not teaser:
                _draw_row_keywords(dr, r, f, color, stroke, W, y)
            else:
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


_KW_RE = _re.compile(r"\d[\d,.]*(?:[万億兆]|%|％|倍|割|年|か月|ヶ月|カ月|日|時間|分|秒|人|件|円|ドル|歳|回|台|個|kg|km|cm|mm|m)?")
KW_COLOR = (255, 214, 90)   # 数字（と単位）は黄色で目立たせる（字幕の話者色の代わりに）


def _draw_row_keywords(dr, row: str, f, color, stroke: int, W: int, y: int) -> None:
    """字幕の1行を、数字＋単位だけ黄色にして描く（全体は中央ぞろえ）。"""
    segs, pos = [], 0
    for m in _KW_RE.finditer(row):
        if m.start() > pos:
            segs.append((row[pos:m.start()], color))
        segs.append((m.group(0), KW_COLOR))
        pos = m.end()
    if pos < len(row):
        segs.append((row[pos:], color))
    x = (W - _text_w(dr, row, f, stroke)) // 2
    for text, col in segs:
        dr.text((x, y), text, font=f, fill=col, stroke_width=stroke, stroke_fill=(0, 0, 0))
        x += dr.textlength(text, font=f)


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
        vis = scene_visuals(scene)
        if vis:
            # 画像の列（2026-11-08）: カード・グラフの間だけ、立ち絵を check と同じ小さい大きさにする
            vmap = visual_line_map(scene)
            events[-1] = (off, dict(base, chart=visual_small_cast(vis[0])))
        v_from = scene.get("verdict_from_line") if scene["type"] == "verdict" else None
        for li, line in enumerate(lines):
            if "t0" not in line:
                raise RuntimeError(f"S{scene['scene_id']:02d} 行{li + 1}: t0 がありません（kl_tts_gen.py を先に実行）")
            sp = line["speaker"]
            other = "skeptic" if sp == "dreamer" else "dreamer"
            exprs = {sp: line.get("expression", "neutral"), other: line.get("react", "neutral")}
            st = None
            extra = {}
            if v_from and li + 1 >= v_from:
                if stamps is None:
                    stamps = verdict_stamps(cast, ep["verdict"])
                st = stamps
                photo = line_photo_asset(scene, li, vis, vmap if vis else None)
                if photo:
                    # 写真の右上のクレジットを隠さないよう、判定ラベルをクレジットの箱の下に下げる（2026-11-08）。
                    # 写真の無い回（kl031〜kl053）はこのキーが付かず、位置は従来どおり
                    extra["stamp_y"] = photo_credit_bottom(photo, MAIN_LAYOUT["H"]) + 10
            cards = line.get("cards") or [{"text": line_display(line), "start": 0.0, "end": line["dur"]}]
            talk_end = round(off + narr_delay_s + line["t0"] + line["dur"], 3)  # 口パク: この行を話し終える時刻
            for c in cards:
                t = off + narr_delay_s + line["t0"] + c["start"]
                ln_chart = visual_small_cast(vis[vmap[li]]) if vis else chart
                events.append((round(t, 3), dict(base, speaker=sp, exprs=exprs, text=c["text"],
                                                 stamps=st, talk_end=talk_end, chart=ln_chart, **extra)))
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


POP_SCALES = (0.88, 0.95, 1.04)   # 字幕のポップイン（3フレーム。その後 1.0 で静止）


def build_overlay_track(events: list, total_dur: float, layout: dict, cast: dict, tmp: Path,
                        out_mov: Path, fps: int, ffmpeg: str = "ffmpeg",
                        blank_after: float = None, sprites: bool = True, bar: bool = True, pop: bool = False) -> None:
    """時刻表から透明な重ね合わせ動画（qtrle .mov）を作る。同じ画面状態のPNGは使い回す。
    blank_after を指定すると、その時刻以降は何も重ねない（本編のロゴアウトロ用）。
    sprites=False・bar=False は、動画の立ち絵（build_sprite_tracks）と組み合わせるときに使う
    （字幕帯 → 立ち絵 → この重ね合わせ、の順に重ねるため、帯と立ち絵をここから外す）。"""
    bank = SpriteBank(cast)
    dedup = _prepare_events(events, blank_after)
    cache = {}
    entries = []

    def layer_png(st):
        key = _state_key(st, sprites)
        if key not in cache:
            p = tmp / f"layer_{len(cache):04d}.png"
            render_layer(st, layout, cast, bank, sprites=sprites, bar=bar, nameplates=sprites).save(p)
            cache[key] = p
        return cache[key]

    prev_text = None
    for i, (t, st) in enumerate(dedup):
        t_next = dedup[i + 1][0] if i + 1 < len(dedup) else total_dur
        dur = max(0.0, t_next - t)
        if dur <= 0:
            continue
        text = st.get("text")
        if (pop and text and text != prev_text and st.get("mode") == "normal"
                and dur > len(POP_SCALES) / fps + 0.3):
            # 字幕の出現: 数フレームだけ小さい字から大きくなる。数字は黄色（kw）。残りは最終の大きさで静止
            fr = 1.0 / fps
            for sc in POP_SCALES:
                entries.append((layer_png(dict(st, pop=sc, kw=True)), fr))
            entries.append((layer_png(dict(st, kw=True)), dur - fr * len(POP_SCALES)))
        else:
            entries.append((layer_png(dict(st, kw=True) if (pop and text and st.get("mode") == "normal") else st), dur))
        prev_text = text
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
                        fps: int, ffmpeg: str = "ffmpeg", blank_after: float = None, talk: bool = True, focus: bool = True) -> dict:
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
    bank = SpriteBank(cast, focus=FOCUS_ACTIVE if focus else 1.0)
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
        ch = int(layout["sprite_h"] * (FOCUS_ACTIVE if focus else 1.0)) + 2   # 話し手を拡大しても収まる高さ
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
        # 濃さは回ごとに thumbnail_band_alpha で変えられる（既定220。kl052: 明るい背景が暗く沈むため140）
        grad.putpixel((0, y), int(int(ep.get("thumbnail_band_alpha", 220)) * (1 - y / band_h) ** 1.1))
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
    # カタカナ語の途中も切れ目にしない（janome が「ド|ローン」と切ることがある。kl052）
    kata = lambda c: "ァ" <= c <= "ヺ" or c == "ー"
    good = {b for b in good if not (kata(text[b - 1]) and kata(text[b]))}
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
    """一次資料の該当箇所を、いつものカフェ（ぼかし）の上に置いた紙の資料として描く（静止画）。
    文字はAIに描かせず、実フォントで正確に描く（数字・引用の捏造・誤字を防ぐ）。
    描画は kl_motion.py（動画の動きの最後のフレームと同じ絵になる。2026-11-07）。
    card: {kind, source, quote?, quote_type(原文/要約)?, highlight?, items?[], note?}"""
    import kl_motion
    kl_motion.render_card_static(card, out_path, W, H)


def render_episode_cards(ep: dict) -> list:
    """source_card / chart を持つシーンの静止画を assets/cards/{episode}_S{NN}.png に描き、image_asset を書き込む。
    （動画では kl_motion.py が同じ見た目を動かす。この静止画は確認ページ・サムネイル・--no-motion 用）"""
    import kl_motion
    done = []
    for s in ep.get("scenes", []):
        if not (s.get("source_card") or s.get("chart")):
            continue
        name = _card_asset_name(ep, s)
        if s.get("source_card"):
            render_source_card(s["source_card"], BASE_DIR / "assets" / f"{name}.png")
        else:
            kl_motion.render_chart_static(s["chart"], BASE_DIR / "assets" / f"{name}.png")
        s["image_asset"] = name
        s.pop("image_prompt", None)
        done.append((s["scene_id"], BASE_DIR / "assets" / f"{name}.png"))
    done += render_visual_cards(ep)
    return done


# ── 1シーンの中の画像の列（scene.visuals、2026-11-08） ───────────────────────────
# なるさんの指摘（kl054）「冒頭でずっとカフェの静止画で二人がおしゃべりだけだと、つまらないので離脱する。写真が一枚もない。
# 最後のカフェのシーンも動きがなくてつまらない」を受けて、1シーンの中で、台詞の流れに合わせて画像を替えられるようにした。
# シーンを分けない（type・bgm_role・round_title・verdict_from_line・締めの固定文・lines_hash・初見レビューのハッシュは
# シーン単位のまま変わらない）。書き方:
#   "visuals": [
#     {"from_line": 1, "scene_image": true},                         # シーン自体の画像（image_prompt / image_asset / reuse）
#     {"from_line": 4, "image_asset": "photos/kl055_S05_b", "real_photo": true},   # 写真（kl_photo_commons.py --slot b）
#     {"from_line": 7, "source_card": {...}, "reference_index": 0},  # 資料カード（コードで描く。動く）
#     {"from_line": 9, "chart": {...}, "reference_index": 1},        # グラフ
#     {"from_line": 12, "recap_card": {"title": "...", "items": [...]}},  # まとめ（論点の振り返り）
#     {"from_line": 15, "step_card": {"title": "...", "items": [...]}},   # 今日できる一歩
#   ]
#   from_line は1始まり（verdict_from_line と同じ）。最初の要素は 1。昇順。その行の話し始めの少し前（VISUAL_XFADE/2）から
#   クロスフェードで次の画像に替わる。任意: ken_burns・zoom_anchor（写真・シーン画像）、motion_cues（カード。画像の頭からの秒）、
#   small_cast（立ち絵を check と同じ小さい大きさにするか。カード・グラフ・まとめは既定で true）、bg_asset（カードの下に敷く素材）。
#   recap_card・step_card の任意の badge: 左上の見出しの文言（既定は「ふりかえり」「今日の一歩」。例: 台詞が「今月の一歩」なら
#   "badge": "今月の一歩"。2026-11-08、kl054 で見出し・台詞とバッジが食い違ったため。色は変わらない）。
VISUAL_SOURCES = ("scene_image", "image_asset", "source_card", "chart", "recap_card", "step_card")
VISUAL_DRAWN = ("source_card", "chart", "recap_card", "step_card")   # コードで描く（AI生成なし・費用ゼロ）
VISUAL_XFADE = 0.6          # 画像の切り替えのクロスフェード（秒）
VISUAL_MIN_SECONDS = 3.0    # 1枚の画像を出す最短の秒数（これより短いと読めない・せわしない）
SUMMARY_KINDS = {           # まとめのカード（資料の引用ではない）の見出しと色
    "recap": ("ふりかえり", (196, 120, 40)),
    "step":  ("今日の一歩", (52, 140, 96)),
}
SUMMARY_FOOTER = "二人のまとめ（資料の引用ではありません）"


def scene_visuals(scene: dict) -> list:
    v = scene.get("visuals")
    return v if isinstance(v, list) and v and scene.get("type") != "teaser" else []


def visual_source(v: dict):
    keys = [k for k in VISUAL_SOURCES if v.get(k)]
    return keys[0] if len(keys) == 1 else None


def visual_asset_name(ep: dict, scene: dict, k: int) -> str:
    """コードで描く画像（カード・グラフ・まとめ）の静止画の名前（k は0始まり）。"""
    return f"cards/{ep.get('episode_id', 'klXXX')}_S{scene['scene_id']:02d}_v{k + 1}"


def visual_small_cast(v: dict) -> bool:
    if "small_cast" in v:
        return bool(v["small_cast"])
    return visual_source(v) in VISUAL_DRAWN


def summary_card(spec: dict, kind: str) -> dict:
    """recap_card / step_card を、資料カードの描画（kl_motion.card_parts）に渡せる形にする。"""
    return {"kind": kind, "source": spec.get("title", ""), "items": list(spec.get("items") or []),
            "footer": spec.get("footer") or SUMMARY_FOOTER, "note": spec.get("note", ""),
            "bg_asset": spec.get("bg_asset"), "badge": spec.get("badge")}


def photo_credit(asset: str) -> str:
    """写真の素材（photos/...）の、画面に出すクレジット（出所の記録の credit_on_screen）。記録が無ければ空。"""
    rec_path = BASE_DIR / "assets" / f"{asset}.json"
    if not asset or not rec_path.exists():
        return ""
    return json.loads(rec_path.read_text(encoding="utf-8")).get("credit_on_screen", "")


def line_photo_asset(scene: dict, li: int, vis: list = None, vmap: list = None) -> str:
    """行 li（0始まり）を話している間に画面に出ている写真の素材名（photos/...、real_photo のもの）。写真でなければ空。"""
    vis = scene_visuals(scene) if vis is None else vis
    if vis:
        vmap = visual_line_map(scene) if vmap is None else vmap
        v = vis[vmap[li]]
        if v.get("real_photo") and (v.get("image_asset") or "").startswith("photos/"):
            return v["image_asset"]
        if not v.get("scene_image"):
            return ""
    if scene.get("real_photo") and (scene.get("image_asset") or "").startswith("photos/"):
        return scene["image_asset"]
    return ""


def photo_credit_bottom(asset: str, H: int) -> int:
    """横長の写真（kl_photo_commons._compose、1920×1080）の右上に焼き込んだクレジットの箱の下端を、画面の高さ H の画素で返す。
    判定ラベルをこの下に置くのに使う（2026-11-08、kl054 S12: ラベルがクレジットを隠した）。"""
    import kl_photo_commons as P
    rec_path = BASE_DIR / "assets" / f"{asset}.json"
    note = ""
    if rec_path.exists():
        note = json.loads(rec_path.read_text(encoding="utf-8")).get("note", "")
    n = 2 if note else 1
    bottom = P.CREDIT_TOP + 36 * n + 14 * 2 - 6   # _compose の lh=36・pad=14 と同じ
    return int(round(bottom * H / P.H))


def visual_motion_scene(v: dict) -> dict:
    """カード・グラフ・まとめの画像を、kl_motion.make_motion_clip / scene_parts に渡す疑似シーンにする。
    写真を下に敷く（bg_asset）ときは、ぼかしで見えなくなる写真のクレジットを、カードの足元の注記に足す。"""
    src = visual_source(v)
    out = {"motion_cues": v.get("motion_cues") or {}}
    credit = photo_credit(v.get("bg_asset") or "") if (v.get("bg_asset") or "").startswith("photos/") else ""
    if credit:
        v = dict(v)
        for key in ("source_card", "chart", "recap_card", "step_card"):
            if v.get(key):
                c = dict(v[key])
                c["note"] = (c.get("note", "") + "　" if c.get("note") else "") + f"背景{credit}"
                v[key] = c
    if src == "source_card":
        out["source_card"] = dict(v["source_card"], **({"bg_asset": v["bg_asset"]} if v.get("bg_asset") else {}))
    elif src == "chart":
        out["chart"] = dict(v["chart"], **({"bg_asset": v["bg_asset"]} if v.get("bg_asset") else {}))
    elif src in ("recap_card", "step_card"):
        card = summary_card(v[src], "recap" if src == "recap_card" else "step")
        if v.get("bg_asset"):
            card["bg_asset"] = v["bg_asset"]
        out["source_card"] = card
    return out


def visual_line_map(scene: dict) -> list:
    """各行（0始まり）がどの画像（visuals の番号）の間に話されるか。visuals が無ければ []。"""
    vis = scene_visuals(scene)
    if not vis:
        return []
    starts = [int(v.get("from_line") or 1) for v in vis]
    out = []
    for li in range(len(scene.get("lines") or [])):
        k = 0
        for j, st in enumerate(starts):
            if li + 1 >= st:
                k = j
        out.append(k)
    return out


def visual_segments(scene: dict, dur: float, narr_delay: float) -> list:
    """動画の中の、各画像の区間 [(開始秒, 終了秒, visual)]（シーンの頭からの秒。クロスフェード前の境目）。
    台詞の行の t0（kl_tts_gen.py が書く）が要る。境目は、その行の話し始めの VISUAL_XFADE/2 秒前。"""
    vis = scene_visuals(scene)
    lines = scene.get("lines") or []
    lead = narr_delay + scene.get("_lead_in", 0.0)
    bounds = [0.0]
    for v in vis[1:]:
        li = int(v["from_line"]) - 1
        t0 = lines[li].get("t0")
        if t0 is None:
            raise RuntimeError(f"S{scene['scene_id']:02d} 行{li + 1}: t0 がありません（kl_tts_gen.py を先に実行）")
        bounds.append(max(bounds[-1], lead + t0 - VISUAL_XFADE / 2))
    bounds.append(dur)
    return [(bounds[k], bounds[k + 1], v) for k, v in enumerate(vis)]


def visual_text(v: dict) -> str:
    """画面に出る文字（plain・scene_text 用）。写真・シーン画像は文字なし。"""
    src = visual_source(v)
    if src == "source_card":
        return "［画面の資料カード］" + card_text(v["source_card"])
    if src == "chart":
        import kl_motion
        return "［画面のグラフ］" + kl_motion.chart_text(v["chart"])
    if src in ("recap_card", "step_card"):
        c = v[src]
        label = c.get("badge") or SUMMARY_KINDS["recap" if src == "recap_card" else "step"][0]
        return f"［画面のまとめカード（{label}）］" + " ".join([c.get("title", "")] + [f"・{it}" for it in c.get("items") or []])
    return ""


def render_visual_cards(ep: dict) -> list:
    """visuals のカード・グラフ・まとめを assets/cards/{episode}_S{NN}_v{k}.png に描く（確認ページ・--no-motion 用の静止画）。"""
    import kl_motion
    done = []
    for s in ep.get("scenes", []):
        for k, v in enumerate(scene_visuals(s)):
            if visual_source(v) not in VISUAL_DRAWN:
                continue
            path = BASE_DIR / "assets" / f"{visual_asset_name(ep, s, k)}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            kl_motion.render_static(kl_motion.scene_parts(visual_motion_scene(v))).save(path, "PNG")
            done.append((s["scene_id"], path))
    return done


_LIC_OK = _re.compile(r"^(cc0|public domain|pd\b|cc[ -]by(-sa)?[ -][0-9.]+)", _re.I)
_LIC_NG = _re.compile(r"(\bnc\b|-nc|\bnd\b|-nd|gfdl|fair use|non-free)", _re.I)


def photo_record_errors(ep: dict, where: str, asset: str) -> list:
    """写真の出所の記録（assets/{asset}.json。kl_photo_commons.py fetch / import が書く）を確かめる。"""
    errs = []
    rec_path = BASE_DIR / "assets" / f"{asset}.json"
    if not rec_path.exists():
        return [f"{where}: 写真の出所の記録がありません（{rec_path.name}。kl_photo_commons.py fetch / import で取り込む）"]
    rec = json.loads(rec_path.read_text(encoding="utf-8"))
    desc = ep.get("youtube_description", "")
    if rec.get("origin") == "import":
        # 公式・プレス素材（kl_photo_commons.py import）。条件の記録・確認の印・クレジットを確かめる
        for k in ("source_url", "credit", "terms", "terms_url"):
            if not rec.get(k):
                errs.append(f"{where}: 取り込んだ素材の記録に {k} がありません")
        if not rec.get("checked_no_watermark") or not rec.get("checked_not_stock"):
            errs.append(f"{where}: 取り込んだ素材の、透かし・有料ストックでないことの確認の記録がありません")
        if rec.get("credit") and rec["credit"] not in desc:
            errs.append(f"{where}: 概要欄に素材のクレジット「{rec['credit']}」がありません（kl_photo_commons.py apply）")
        return errs
    lic = rec.get("license", "")
    if not _LIC_OK.match(lic) or _LIC_NG.search(lic):
        errs.append(f"{where}: 使えないライセンスの写真です: {lic or '不明'}")
    name = rec.get("title", "").removeprefix("File:")
    if name and name not in desc:
        errs.append(f"{where}: 概要欄に写真クレジット（{name}）がありません（kl_photo_commons.py apply）")
    return errs


def validate_visuals(ep: dict) -> list:
    """scene.visuals の確認（visuals が無い回は何もしない＝既存の回の結果は変わらない）。"""
    errs = []
    refs = ep.get("references") or []
    for s in ep.get("scenes", []):
        vis = s.get("visuals")
        if vis is None:
            continue
        sid = s.get("scene_id")
        lines = s.get("lines") or []
        n0 = len(errs)
        if not isinstance(vis, list) or not vis:
            errs.append(f"S{sid}: visuals は1つ以上の要素のリストにしてください")
            continue
        if s.get("type") == "teaser":
            errs.append(f"S{sid}: teaser に visuals は使えません（ティザーは数秒。1枚で見せる）")
            continue
        if s.get("source_card") or s.get("chart"):
            errs.append(f"S{sid}: visuals のあるシーンでは、source_card・chart は visuals の要素として書いてください")
        prev = 0
        for k, v in enumerate(vis):
            where = f"S{sid} visuals[{k}]"
            if not isinstance(v, dict):
                errs.append(f"{where}: 要素は辞書にしてください")
                continue
            fl = v.get("from_line")
            if not isinstance(fl, int) or isinstance(fl, bool) or not (1 <= fl <= len(lines)):
                errs.append(f"{where}: from_line は 1〜{len(lines)} の整数（1始まりの行番号）")
            elif k == 0 and fl != 1:
                errs.append(f"{where}: 最初の画像の from_line は 1 にしてください（シーンの頭から何かを出す）")
            elif fl <= prev:
                errs.append(f"{where}: from_line は前の画像より大きくしてください（昇順・重複なし）")
            if isinstance(fl, int):
                prev = max(prev, fl)
            src = visual_source(v)
            if src is None:
                errs.append(f"{where}: {' / '.join(VISUAL_SOURCES)} のどれか1つだけを書いてください")
                continue
            if src == "scene_image":
                if not (s.get("image_prompt") or s.get("reuse_scene_id") or s.get("image_asset")):
                    errs.append(f"{where}: scene_image ですが、シーンに画像（image_prompt / image_asset / reuse_scene_id）がありません")
            elif src == "image_asset":
                asset = v["image_asset"]
                if not (BASE_DIR / "assets" / f"{asset}.png").exists():
                    errs.append(f"{where}: 画像がありません: assets/{asset}.png")
                if asset.startswith("photos/") and not v.get("real_photo"):
                    errs.append(f"{where}: 写真（photos/）には real_photo: true を付けてください（出所とクレジットを確かめるため）")
                if v.get("real_photo"):
                    errs += photo_record_errors(ep, where, asset)
            else:
                ri = v.get("reference_index", (v.get(src) or {}).get("reference_index", s.get("reference_index")))
                if src in ("source_card", "chart") and not (isinstance(ri, int) and 0 <= ri < len(refs)):
                    errs.append(f"{where}: {src} の reference_index が references にありません（画面に出す資料の出所）")
                c = v[src]
                if src == "source_card":
                    if c.get("kind") not in CARD_KINDS:
                        errs.append(f"{where}: source_card.kind は {tuple(CARD_KINDS)} のどれか")
                    if not c.get("source"):
                        errs.append(f"{where}: source_card.source（資料名と日付）がありません")
                    if not c.get("quote") and not c.get("items"):
                        errs.append(f"{where}: source_card に quote か items が必要です")
                    if c.get("quote") and len(c["quote"]) > 90:
                        errs.append(f"{where}: source_card.quote は90字以内")
                    if c.get("highlight") and c["highlight"] not in (c.get("quote") or ""):
                        errs.append(f"{where}: source_card.highlight は quote の中の文字列にしてください")
                elif src == "chart":
                    if c.get("kind", "bar") not in ("bar", "line", "number") or not c.get("source") or not c.get("title"):
                        errs.append(f"{where}: chart には kind（bar/line/number）・source・title が要ります")
                    if c.get("kind", "bar") in ("bar", "line") and not (2 <= len(c.get("items") or []) <= 8):
                        errs.append(f"{where}: chart.items は2本以上")
                else:
                    if not c.get("title") or len(c["title"]) > 24:
                        errs.append(f"{where}: {src}.title は1〜24字")
                    if not (1 <= len(c.get("items") or []) <= 5):
                        errs.append(f"{where}: {src}.items は1〜5行")
                    if c.get("badge") is not None and not (1 <= len(str(c["badge"])) <= 10):
                        errs.append(f"{where}: {src}.badge（見出しの文言）は1〜10字")
                if src in ("source_card", "recap_card", "step_card"):
                    for it in c.get("items") or []:
                        if sum(0.5 if ch.isascii() else 1 for ch in it) > 26:
                            errs.append(f"{where}: {src}.items の1行は26字以内（半角は0.5字）（{it[:12]}…）")
                    if src == "source_card" and len(c.get("items") or []) > 5:
                        errs.append(f"{where}: {src}.items は5行まで")
                name = visual_asset_name(ep, s, k)
                if not (BASE_DIR / "assets" / f"{name}.png").exists():
                    errs.append(f"{where}: カードの静止画がありません（python3 kl_dialogue.py cards --episode {ep.get('episode_id')}）")
            if v.get("bg_asset") and not (BASE_DIR / "assets" / f"{v['bg_asset']}.png").exists():
                errs.append(f"{where}: bg_asset の画像がありません: assets/{v['bg_asset']}.png")
            if (v.get("bg_asset") or "").startswith("photos/"):
                errs += photo_record_errors(ep, where + " bg_asset", v["bg_asset"])
        # 音声ができた後（t0 がある）なら、1枚の画像の長さを確かめる
        if all("t0" in l for l in lines) and lines and len(errs) == n0:
            last = lines[-1]
            dur = 0.5 + last["t0"] + last.get("dur", 0) + 1.0
            for a, b, v in visual_segments(s, dur, 0.5):
                if b - a < VISUAL_MIN_SECONDS:
                    errs.append(f"S{sid}: visuals の from_line {v.get('from_line')} の画像が{b - a:.1f}秒しか出ません"
                                f"（{VISUAL_MIN_SECONDS:.0f}秒以上。行をまとめるか、画像を減らす）")
    return errs


# ── 初見の視聴者向けの台詞テキスト（plain）と、読みやすさの機械チェック ────────────────
# 2026-10-19、kl046 で制作者から「主語がない」「用語が分からない」「たとえが分からない」の指摘が
# 1つずつ10回近く続いた。原因は「初めて聞く人として台本を読む工程」が無かったこと（書き手もレビューも
# 資料を知っている）。そこで (1) 資料を見ていない別の Opus に、台詞だけのテキスト（plain）を読ませる
# 初見レビューを STEP5.5 の必須ゲートにし（kl_prompts/beginner_review_prompt.md）、(2) 機械で拾える
# 分かりにくさの手がかりを check に ⚠ として足した（不合格にはしない。初見レビューに渡す材料）。

GLOSSARY_JSON = BASE_DIR / "kl_prompts" / "glossary_terms.json"
_QUOTE_LABEL_RE = _re.compile(r"「([^」]{1,40})」")


def load_glossary() -> dict:
    try:
        return json.loads(GLOSSARY_JSON.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def _figure_labels(prompt: str) -> list:
    """チャート調の図の image_prompt から、画面に出る日本語ラベル（「…」で指定したもの）だけを取り出す。"""
    out = []
    for m in _QUOTE_LABEL_RE.findall(prompt or ""):
        if any(ord(ch) > 0x3000 for ch in m) and m not in out:
            out.append(m)
    return out


def plain_text(ep: dict, cast: dict = None, only_scenes=None) -> str:
    """初見レビュー用: 視聴者が見聞きするものだけ（タイトル・サムネイルの見出し・台詞・画面の資料カード／
    図のラベル／論点の見出し／判定ラベル）を順に並べたテキスト。概要欄・資料・image_prompt の英文は含めない。"""
    cast = cast or load_cast()
    name = {r: speaker_name(cast, r) for r in ROLES}
    labels = {k: v.get("label", k) for k, v in (cast.get("verdicts") or {}).items()}
    out = []
    out.append(f"【動画のタイトル】{ep.get('youtube_title', '')}")
    if ep.get("thumbnail_headline"):
        out.append(f"【サムネイルの見出し】{ep['thumbnail_headline'].replace(chr(10), ' ')}")
    rel = []
    for r in ROLES:
        c = cast.get(r, {})
        rel.append(f"{name[r]}（{c.get('role_short') or c.get('role_label', '')}）")
    out.append("")
    out.append("登場するのは二人。" + "と".join(rel) + "。大学の研究室の同期で、気になる話題を持ち寄って語り合う。"
               "名前と肩書きは画面の名札に出る（台詞では名前を呼ばない）。")
    by_id = {s.get("scene_id"): s for s in ep.get("scenes", [])}
    for s in ep.get("scenes", []):
        if only_scenes is not None and s.get("scene_id") not in only_scenes:
            continue  # 差分レビュー（2周目以降）: 変更したシーンだけを出す
        out.append("")
        head = f"=== シーン{s.get('scene_id')}"
        if s.get("round_title"):
            head += f"（見出し画面: {s['round_title']}）"
        if s.get("type") == "teaser":
            head += "（冒頭の予告）"
        out.append(head + " ===")
        c = s.get("source_card")
        if c:
            parts = [c.get("source", "")]
            if c.get("quote"):
                parts.append(f"引用: 「{c['quote']}」")
            if c.get("items"):
                parts.append("箇条書き: " + " / ".join(c["items"]))
            if c.get("note"):
                parts.append(f"注: {c['note']}")
            out.append("[画面に出る資料カード] " + " ／ ".join(p for p in parts if p))
        elif s.get("chart"):
            import kl_motion
            out.append("[画面に出るグラフ（棒が伸び、数字が増えていく）] " + kl_motion.chart_text(s["chart"]))
        else:
            src = s
            if s.get("reuse_scene_id") and not s.get("image_prompt"):
                src = by_id.get(s["reuse_scene_id"], s)
            if scene_style(src) == "chart" and src.get("image_prompt"):
                labs = _figure_labels(src["image_prompt"])
                if labs:
                    out.append("[画面に出る図の文字] " + " / ".join(labs))
        starts = {}
        for v in scene_visuals(s):
            if isinstance(v.get("from_line"), int):
                starts.setdefault(v["from_line"], []).append(v)
        for li, l in enumerate(s.get("lines") or [], start=1):
            for v in starts.get(li, []):
                src = visual_source(v)
                if src in VISUAL_DRAWN:
                    out.append("[画面が替わる] " + visual_text(v))
                elif src == "image_asset" and v.get("real_photo"):
                    out.append("[画面が替わる] 写真" + (f"（{v['caption']}）" if v.get("caption") else ""))
            out.append(f"{name.get(l.get('speaker'), l.get('speaker'))}：{line_display(l)}")
        if s.get("type") == "verdict":
            v = ep.get("verdict") or {}
            out.append("[画面に判定ラベル: " + "、".join(f"{name[r]}「{labels.get(v.get(r), v.get(r))}」" for r in ROLES if v.get(r))
                       + "（ラベルの種類: " + "／".join(labels.values()) + "）]")
    return "\n".join(out) + "\n"


_NUM_RE = _re.compile(r"\d+(?:[.,]\d+)*")
_DATE_RE = _re.compile(r"\d+年\d+月(?:\d+日)?|\d+月\d+日|\d+年\d+月|\d+[〜~～]\d+")
_FINE_NUM_RE = _re.compile(r"\d+億\d+万?|\d+万\d+|\d{5,}|\d{1,3}(?:,\d{3}){1,}")


def _too_fine(num: str) -> bool:
    """有効数字が4桁以上か（1億2284万・31万4001・314,001 は細かい。1億2000万・1,250 は可）。"""
    digits = _re.sub(r"\D", "", num).rstrip("0")
    return len(digits) >= 4
_ASCII_RE = _re.compile(r"[A-Za-z][A-Za-z0-9.\-]*[A-Za-z0-9]|[A-Za-z]")
_ATTR_QUOTE_RE = _re.compile(r"(?:さん|氏|自身)(?:が|の)?(?:言う|いう|言った)?「([^」]{2,40})」|「([^」]{2,40})」(?:と|って)(?:言|話)")


def _norm(t: str) -> str:
    return _re.sub(r"[、。，．・！？!?\s「」『』…ー〜]", "", t)


def readability_warnings(ep: dict) -> list:
    """初見の視聴者がつまずきやすい所の機械的な手がかり（⚠）。誤検出もあるので、不合格にはしない。
    結果は STEP5.5 の初見レビューと、制作者に見せる前のセルフチェックの材料にする。"""
    from difflib import SequenceMatcher
    g = load_glossary()
    if not g:
        return ["読みやすさチェック: kl_prompts/glossary_terms.json がありません"]
    scenes = ep.get("scenes") or []
    # 本編の行（ティザーは見出しの役目なので、用語・比喩・指示語の判定からは外す）
    seq = []   # (scene_id, 行番号1始まり, text, type)
    for s in scenes:
        for i, l in enumerate(s.get("lines") or []):
            seq.append((s.get("scene_id"), i + 1, l.get("text", ""), s.get("type")))
    main = [x for x in seq if x[3] != "teaser"]
    warns = []

    def near(k):  # その行と次の行
        return main[k][2] + (main[k + 1][2] if k + 1 < len(main) else "")

    # (a) 初出の専門用語
    ex = g.get("explain_markers", [])
    for term in g.get("terms", []):
        k = next((k for k, x in enumerate(main) if term in x[2]), None)
        if k is None:
            continue
        if not any(m in near(k) for m in ex):
            sid, ln, t, _ = main[k]
            warns.append(f"用語: S{sid:02d} 行{ln}「{term}」が初出で、その行・次の行に言い換えの手がかり（つまり／っていうのは／〜のこと 等）がありません: {t[:40]}")
    # (a') 英字の固有名
    allow = set(g.get("ascii_allow", [])) | set(g.get("terms", []))
    pm = g.get("proper_markers", [])
    seen = set()
    for k, (sid, ln, t, _) in enumerate(main):
        for w in _ASCII_RE.findall(t):
            if w in seen or w in allow or len(w) < 2:
                seen.add(w)
                continue
            seen.add(w)
            if not any(m in near(k) for m in pm):
                warns.append(f"固有名: S{sid:02d} 行{ln}「{w}」が初出で、何者か（〜という研究機関 等）の説明がありません: {t[:40]}")
    # (b) 前に出ていない発言の引用（「〇〇さんの『…』」「『…』と言った」の形だけを見る）
    earlier = ""
    for sid, ln, t, _ in seq:
        for m in _ATTR_QUOTE_RE.finditer(t):
            q = _norm(m.group(1) or m.group(2))
            ctx = _norm(earlier)
            hit = SequenceMatcher(None, q, ctx, autojunk=False).find_longest_match(0, len(q), 0, len(ctx)).size if ctx else 0
            if hit < max(2, int(len(q) * 0.6)):
                warns.append(f"引用: S{sid:02d} 行{ln} の「{m.group(1) or m.group(2)}」は、それより前の台詞に出ていない発言です（初出なら、誰が何と言ったかを先に紹介する）")
        earlier += t + "\n"
    # (c) 行頭の指示語（情報として一覧）
    dem = sorted(g.get("demonstratives", []), key=len, reverse=True)
    hits = []
    for sid, ln, t, _ in main:
        skip = g.get("demonstrative_skip", [])
        head = _re.sub(r"^(……|でも、|じゃあ、|ただ、)", "", t)
        d = next((d for d in dem if head.startswith(d)), None)
        if d and not any(head.startswith(x) for x in skip):
            hits.append(f"S{sid:02d}行{ln}「{t[:14]}…」")
    if hits:
        warns.append(f"指示語（情報）: 行頭の指示語 {len(hits)}件。何を指すか、前の行だけで分かるか確認: " + "、".join(hits))
    # (d) 数字の多さ・細かさ
    th = g.get("number_thresholds", {"line": 4, "scene": 10})
    for s in scenes:
        n_scene = 0
        if s.get("type") == "teaser":
            continue
        for i, l in enumerate(s.get("lines") or []):
            t = l.get("text", "")
            t2 = _DATE_RE.sub("#", t)
            n = len(_NUM_RE.findall(t2)) + t2.count("#")
            n_scene += n
            if n >= th["line"]:
                warns.append(f"数字: S{s['scene_id']:02d} 行{i + 1} に数字が{n}つ（耳で追えるか。分けるか減らす）: {t[:40]}")
            for f in [f for f in _FINE_NUM_RE.findall(t) if _too_fine(f)]:
                warns.append(f"数字: S{s['scene_id']:02d} 行{i + 1}「{f}」は細かすぎないか（およそ〇〇 に丸める）")
        if n_scene >= th["scene"]:
            warns.append(f"数字: S{s['scene_id']:02d} に数字が{n_scene}つ（1シーンに多い。大きさの感覚を添えるか、カードに任せる）")
    # (e) 比喩語を3回以上使うのに定義が無い
    dm = g.get("definition_markers", [])
    for w in g.get("metaphor_words", []):
        lines_w = [x for x in main if w in x[2]]
        if len(lines_w) >= 3 and not any(any(m in x[2] for m in dm) for x in lines_w):
            warns.append(f"比喩語: 「{w}」が{len(lines_w)}行に出るのに、定義の行（この回では〜と呼ぶ／〜っていうのは 等）がありません（初出 S{lines_w[0][0]:02d} 行{lines_w[0][1]}）")
    # (f) 判定が何を指すか
    vs = next((s for s in scenes if s.get("type") == "verdict"), None)
    timed = any(v in ("soon", "decade") for v in (ep.get("verdict") or {}).values())
    if vs is not None and timed:
        txt = "".join(l.get("text", "") for l in vs.get("lines") or [])
        if not any(m in txt for m in g.get("verdict_scope_markers", [])):
            warns.append("判定: 時期を言うラベル（もうすぐ来る／3年はかかる）なのに、verdict の台詞に、そのラベルが何を指すか"
                         "（何が・いつまでに。例「この3年は、〜までの話」「〜のは、もう始まってる」）を言う手がかりがありません")
    return warns


def lines_digest(ep: dict) -> str:
    """全シーンの台詞（話者・本文・字幕表記）のハッシュ。初見レビューの合格記録が、今の台詞に対するものかを見る。"""
    payload = json.dumps([[s.get("scene_id"), l.get("speaker"), l.get("text"), l.get("display", "")]
                          for s in ep.get("scenes", []) for l in s.get("lines") or []], ensure_ascii=False)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def beginner_review_state(ep: dict) -> tuple:
    """初見レビュー（STEP5.5）の状態。("missing"|"stale"|"ok", 表示文)。
    check の表示と、kl_tts_gen.py・kl_video_gen.py の入口の判定（enforce_beginner_review）が同じこの関数を使う。"""
    r = ep.get("beginner_review") or {}
    if not r:
        return "missing", "未実施（STEP5.5。制作者に見せる前に必須）"
    if r.get("lines_digest") != lines_digest(ep):
        return "stale", f"無効（{r.get('passed_at', '?')} の合格の後に台詞が変わった。STEP5.5 をやり直す）"
    return "ok", f"済（{r.get('passed_at', '?')}、{r.get('rounds', '?')}周、{r.get('report', '')}）"


def beginner_review_status(ep: dict) -> str:
    return beginner_review_state(ep)[1]


# 初見レビュー未通過なら音声・動画の生成を止める（2026-10-19、なるさんの指示「しばらくはそうしてほしい」）。
# 対象は rounds_v3・rounds_v4 で、エピソード番号が46以上の回だけ（kl045 以前・旧形式は止めない）。
BEGINNER_REVIEW_GATE_FROM = 46
SKIP_BEGINNER_REVIEW_HELP = ("初見レビュー（kl-new STEP5.5）が「済」でなくても続行する（警告だけ出す）。"
                             "rounds_v3・rounds_v4 の kl046 以降は、しばらくは必須（なるさんの指示、2026-10-19）。"
                             "制作者の了承なしに使わない。環境変数 KL_SKIP_BEGINNER_REVIEW=1 でも同じ")


def beginner_review_required(ep: dict, episode_id: str = None) -> bool:
    if ep.get("structure") not in V3_FAMILY:
        return False
    m = _re.search(r"(\d+)", episode_id or ep.get("episode_id", ""))
    return bool(m) and int(m.group(1)) >= BEGINNER_REVIEW_GATE_FROM


def enforce_beginner_review(ep: dict, episode_id: str, skip: bool = False, tool: str = "") -> None:
    """kl_tts_gen.py・kl_video_gen.py の入口（API呼び出し・ファイル書き込みの前）で呼ぶ。
    対象の回で初見レビューが「済」でなければ、理由とやることを表示して終了コード2で止める。"""
    import os
    import sys
    if not beginner_review_required(ep, episode_id):
        return
    state, text = beginner_review_state(ep)
    if state == "ok":
        return
    skip = skip or os.environ.get("KL_SKIP_BEGINNER_REVIEW") == "1"
    reason = ("初見レビューがまだ行われていません" if state == "missing"
              else "初見レビューに合格した後に台詞が変わったため、合格の記録が無効になっています")
    if skip:
        print(f"⚠ {tool}: {episode_id} の初見レビュー（STEP5.5）: {text}。--skip-beginner-review（または "
              "KL_SKIP_BEGINNER_REVIEW=1）が指定されたので続行します。制作者の了承を得ていることを確かめてください。",
              file=sys.stderr)
        return
    print(f"""❌ {tool}: {episode_id} は初見レビュー（kl-new STEP5.5）が「済」でないため止めました。
   状態: {text}
   理由: {reason}。
   しばらくは、rounds_v3 の kl046 以降で、初見レビューの合格が音声・動画の生成の条件です（なるさんの指示、2026-10-19）。

   やること（kl-new.md STEP5.5）:
     1. python3 kl_dialogue.py plain --episode {episode_id} --out {{scratchpad}}/{episode_id}_plain.txt
     2. kl_prompts/beginner_review_prompt.md の依頼文で、資料を見ていない Opus に plain テキストだけを読ませる
     3. 書き手に直させ、致命的ゼロになるまで（最大2周）初見レビューをやり直す
     4. python3 kl_dialogue.py review-pass --episode {episode_id} --rounds N --report {{レビュー結果のパス}}

   どうしても飛ばす場合だけ --skip-beginner-review（または KL_SKIP_BEGINNER_REVIEW=1）を付ける。制作者の了承なしに使わない。""",
          file=sys.stderr)
    sys.exit(2)


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
    ap.add_argument("command", choices=["check", "cards", "plain", "review-pass"],
                    help="check: 構造チェック（narration を同期）／cards: 資料カード（source_card）を描いて image_asset を書き込む／"
                         "plain: 初見レビュー用に、視聴者が見聞きするもの（台詞・画面の文字・判定ラベル）だけのテキストを出す")
    ap.add_argument("--out", help="plain の出力先（省略時は標準出力）")
    ap.add_argument("--scenes", help="plain: 差分レビュー用に、指定シーン（scene_id をカンマ区切り）だけを出す。review-pass: "
                                     "合格後に変えたシーンだけを再チェックして記録し直したときの、そのシーン")
    ap.add_argument("--rounds", type=int, help="review-pass: 初見レビューを何周して合格したか")
    ap.add_argument("--report", help="review-pass: 合格した回の初見レビュー結果のパス")
    ap.add_argument("--episode", required=True)
    ap.add_argument("--path", help="episodes/ 以外のJSONを確認するとき（試し書き・テスト用）。指定したファイルに narration を同期する")
    args = ap.parse_args()
    path = Path(args.path) if args.path else BASE_DIR / "episodes" / f"{args.episode}.json"
    ep = json.loads(path.read_text(encoding="utf-8"))
    cast = load_cast()
    if args.command == "plain":
        only = None
        if args.scenes:
            only = {int(x) if x.strip().isdigit() else x.strip() for x in args.scenes.split(",") if x.strip()}
        text = plain_text(ep, cast, only)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"✅ {args.out}（{len(text)}字）。初見レビューのサブエージェントには、このファイルのパスだけを渡す")
        else:
            sys.stdout.write(text)
        return
    if args.command == "review-pass":
        # STEP5.5 の合格を記録する（致命的ゼロ・直すを反映済み・もう一周して致命的なし、をメインが確かめた後）
        import datetime
        ep["beginner_review"] = {"passed_at": datetime.date.today().isoformat(), "rounds": args.rounds,
                                 "report": args.report or "", "lines_digest": lines_digest(ep)}
        if args.scenes:  # 合格後に変えたシーンだけを再チェックして記録し直した（2026-11-05）
            ep["beginner_review"]["rechecked_scenes"] = [x.strip() for x in args.scenes.split(",") if x.strip()]
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(ep, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        print("✅ 初見レビューの合格を記録しました: " + beginner_review_status(ep))
        return
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
    if st == STRUCTURE_V4:
        print("構成: rounds_v4（実現ラウンド。v2・v3 の規則＋下記）")
        print(f"  必須タグ: {', '.join(required_tags(ep))}（life_scene は不要）")
        print("  各論点: 最後の行が hope（残った手応え）・workaround（越え方）が1つ以上／skeptic_wish は沙織／"
              "沙織が譲る turn が1つ以上／next_step は verdict か closing")
        print("  判定: 画面の札は verdict（使い方への札）だけ。claim_verdict（発表の言い方の見立て）は記録用で、台詞では札の言葉を使わず一言で触れる")
    elif st == STRUCTURE_V3:
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
    if st in ROUND_STRUCTURES:
        gate = ("TTS・動画生成はこれが「済」でないと止まる" if beginner_review_required(ep, args.episode)
                else f"kl{BEGINNER_REVIEW_GATE_FROM:03d}より前の回なので、TTS・動画生成は止まらない")
        print("初見レビュー（STEP5.5）: " + beginner_review_status(ep) + f"　※{gate}")
    rw = readability_warnings(ep)
    if rw:
        print(f"── 読みやすさの手がかり（⚠ {len(rw)}件。不合格にはしない。STEP5.5 の初見レビューと、制作者に見せる前のセルフチェックの材料）")
        for w in rw:
            print("⚠ " + w)
    if errs:
        print(f"❌ {len(errs)}件の問題:")
        for e in errs:
            print("  - " + e)
        sys.exit(1)
    print("✅ 構造チェックOK（narration/narrator を同期しました）")


if __name__ == "__main__":
    main()
