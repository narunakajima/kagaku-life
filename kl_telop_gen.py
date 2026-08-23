"""
kl_telop_gen.py — くらしを変える科学 テロップ生成・焼き込みスクリプト

lamp-whisperの lw_video_gen.py のテロップ機能と同じ見た目（drawtext焼き込み）・
同じタイミング決定方法（Whisperによる音声解析）を踏襲する。

**2026-08-21改訂:** 当初「ナレーション文もTTS音声の長さも既知だからWhisperは
不要、文字数比例でタイミングを割り当てればよい」という設計にしたが、実際に
生成した動画で確認したところナレーションとテロップのタイミングが大きくズレて
いた。誤りは「テキストが分かっている＝いつ発話されるかも分かる」という前提
そのもので、実際の発話は句読点でのポーズ・数字の読み上げ等でペースが不均一
なため、文字数比例では実際の発話タイミングと一致しない。LWと同じくWhisperで
実際の音声を解析してタイミングを取得する方式に修正した。

LWとの違い: LWは自由形式の台本のため、Whisperの書き起こしと台本テキストが
食い違うことを前提にSequenceMatcherで頑健にマッチングする必要がある。
kagaku-lifeはTTS音声が「エピソードJSONのナレーション文をそのまま読み上げた
もの」であり、テキストと音声の対応が自明に近いため仕組みは流用しつつも
より単純なケースとして扱える（ただしWhisperの書き起こし精度・数字表記の
揺れは依然あるため、LWと同じSequenceMatcherによる頑健なマッチングは踏襲する）。

使い方:
  # 1. シーンごとの telop_cards（テキスト＋シーン内相対タイミング）を生成
  python3 kl_telop_gen.py --episode kl001 plan

  # 2. 動作確認用: 1シーンの画像+音声から静止画クリップを作り、テロップを焼き込む
  python3 kl_telop_gen.py --episode kl001 burn-test --scene 2

出力:
  plan: episodes/kl{NNN}.json の各シーンに telop_cards を書き込む
        （scene内相対時刻。動画全体でのオフセットは kl_video_gen.py 側で加算する想定）
  burn-test: ~/Desktop/kagaku-life/telop_test_S{NN}.mp4
  （Desktopは常に最新1エピソード分の確認用。エピソードIDのサブフォルダは作らない）
"""

import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
import wave

from janome.tokenizer import Tokenizer as JanomeTokenizer
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

BASE_DIR = Path(__file__).parent
DESKTOP_DIR = Path.home() / "Desktop" / "kagaku-life"

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FONT_SRC = Path("/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc")
FONT_TMP = Path("/tmp/kl_font.ttc")

MAX_LINE_CHARS = 20          # kagaku-lifeの物語調ナレーションはLWよりやや長めの文が多いため
TELOP_FONTSIZE = 50
TELOP_LINE_SPACING = 72
TELOP_CENTER_Y = 0.85        # 下部寄り（画面下15%付近）に表示
GAP = 0.15                   # カード間の最小間隔（秒）

# 半角?!や閉じ括弧（』」）も区切り候補に含める（2026-08-21追加。
# 半角の?!がBREAK_CHARSになく、強制分割が単語の途中にかかる問題が
# 実際の動画で発覚したため）。
BREAK_CHARS = "、。！？!?　 』」）"

# 句読点が無い長い文でも単語・複合語の途中で切らないよう、janome（形態素解析）で
# 実際の形態素境界を取得し、その境界以外では分割しない（2026-08-23改訂）。
# 従来は助詞の文字列マッチングによるヒューリスティックだったが、「変わらない」→
# 「変わ」/「らない」、「消える」→「消」/「える」、「もらう」→「しても」/「らう」等、
# 助詞マッチが見つからずmax_charsで強制分割される際に単語の途中で切れる事故が
# 実際の動画（kl002）で複数発覚した。形態素解析で得られる境界は常に単語の切れ目と
# 一致するため、この種の事故を構造的に防げる。


def get_wav_duration(wav_path: Path) -> float:
    with wave.open(str(wav_path)) as wf:
        return wf.getnframes() / wf.getframerate()


# janome（IPADIC）が誤って複合語の途中にトークン境界を置く既知の口語表現
# （例:「なんとかする」を「なんと」+「かする（掠する）」という稀な動詞に
# 誤analyze する）。形態素境界ベースの分割だけでは防げないため、数字連続と
# 同じ「保護区間」の仕組みで個別にブロックする（2026-08-23追加、kl002で発覚）。
PROTECTED_PHRASES = ["なんとか", "なんとなく", "どうにか", "どうにかして", "いつのまにか"]


def _in_number_run(text: str, pos: int) -> bool:
    """posが数字（%含む）の連続の途中にあるかどうか判定する。
    例: "92%" の "9"と"2"の間、"2"と"%"の間はどちらもTrue。
    """
    if pos <= 0 or pos >= len(text):
        return False
    before, after = text[pos - 1], text[pos]
    digit_or_pct = lambda c: c.isdigit() or c == "%"
    return digit_or_pct(before) and digit_or_pct(after)


def _in_protected_phrase(text: str, pos: int) -> bool:
    """posがPROTECTED_PHRASESのいずれかの途中にあるかどうか判定する。"""
    if pos <= 0 or pos >= len(text):
        return False
    for phrase in PROTECTED_PHRASES:
        start = max(0, pos - len(phrase) + 1)
        idx = text.find(phrase, start, pos + len(phrase))
        while idx != -1 and idx <= pos - 1:
            if idx < pos < idx + len(phrase):
                return True
            idx = text.find(phrase, idx + 1, pos + len(phrase))
    return False


def _in_unsafe_run(text: str, pos: int) -> bool:
    return _in_number_run(text, pos) or _in_protected_phrase(text, pos)


def _nearest_safe_split(text: str, pos: int, floor: int = 1) -> int:
    """posが数字や保護フレーズの途中なら、外側に安全な区切り位置を探す。"""
    if not _in_unsafe_run(text, pos):
        return pos
    # 保護区間の先頭（前方）を探す
    back = pos
    while back > floor and _in_unsafe_run(text, back):
        back -= 1
    if back > floor:
        return back
    # 戻れない場合は保護区間の直後まで進める
    fwd = pos
    while fwd < len(text) and _in_unsafe_run(text, fwd):
        fwd += 1
    return fwd


_janome_tokenizer = None


def _load_janome() -> JanomeTokenizer:
    global _janome_tokenizer
    if _janome_tokenizer is None:
        _janome_tokenizer = JanomeTokenizer()
    return _janome_tokenizer


def _token_boundaries(text: str) -> list:
    """形態素解析で得られる各形態素の切れ目（文字オフセット）の一覧を返す
    （0とlen(text)を含む）。分割候補をこの一覧に限定すれば、単語・複合語の
    途中で切れることは構造的に起こらない。
    """
    boundaries = [0]
    pos = 0
    for tok in _load_janome().tokenize(text):
        pos += len(tok.surface)
        boundaries.append(pos)
    if boundaries[-1] != len(text):
        boundaries.append(len(text))
    return boundaries


def chunk_narration(text: str, max_chars: int = MAX_LINE_CHARS) -> list:
    """長いナレーション文を読みやすい長さのチャンクに分割する。
    句読点を優先して自然な位置で区切り、句読点が見つからない場合は形態素境界
    （janome）のうちmax_charsに最も近いものを使う。どちらの場合も、数字（%等）
    の途中では絶対に分割しない。
    """
    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break
        window = remaining[:max_chars + 5]
        split_pos = None
        # max_chars付近で句読点を後方から探す（自然な区切りを優先）
        for i in range(min(max_chars, len(window) - 1), max(0, max_chars - 8), -1):
            if window[i] in BREAK_CHARS:
                split_pos = i + 1
                break
        if split_pos is None:
            # 前方に句読点がないか少し先まで探す
            for i in range(max_chars, min(len(window), max_chars + 5)):
                if window[i] in BREAK_CHARS:
                    split_pos = i + 1
                    break
        if split_pos is None:
            # 句読点が無い場合、形態素境界のうちmax_charsに最も近いものを使う
            # （単語・複合語の途中で切れるのを構造的に防ぐ）
            boundaries = [
                b for b in _token_boundaries(remaining)
                if 1 <= b < len(remaining)
            ]
            if boundaries:
                split_pos = min(boundaries, key=lambda b: abs(b - max_chars))
        if split_pos is None:
            split_pos = max_chars
        split_pos = _nearest_safe_split(remaining, split_pos)
        split_pos = max(1, min(split_pos, len(remaining)))
        chunk = remaining[:split_pos].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[split_pos:]
    return chunks


def normalize(t: str) -> str:
    """句読点・記号・空白を除去して純粋な読み文字列にする（lw_video_gen.pyと同じ）。"""
    return "".join(
        ch for ch in t
        if unicodedata.category(ch) not in ("Po", "Ps", "Pe", "Pd", "Zs", "Cc")
    )


_whisper_model = None


def _load_whisper():
    global _whisper_model
    if _whisper_model is None:
        import whisper as _whisper
        print("  Whisperモデル読み込み中（初回はダウンロードあり）...")
        _whisper_model = _whisper.load_model("small")
    return _whisper_model


def plan_telop_cards(narration: str, wav_path: Path, duration: float) -> list:
    """ナレーション文をチャンクに分割し、Whisperで実際の音声を解析してタイミングを割り当てる
    （lw_video_gen.py の generate_telop_from_whisper と同じ考え方: Whisperの書き起こしと
    既知のナレーション文をSequenceMatcherで対応付け、文字ごとのタイムスタンプを補間する）。
    """
    chunks = chunk_narration(narration)

    model = _load_whisper()
    result = model.transcribe(str(wav_path), language="ja", word_timestamps=True)

    all_chars, char_times = "", []
    for seg in result["segments"]:
        for w in seg.get("words", []):
            norm = normalize(w["word"])
            for ch in norm:
                all_chars += ch
                char_times.append((w["start"], w["end"]))

    if not char_times:
        # Whisperが単語タイムスタンプを取得できなかった場合のみ、文字数比例にフォールバックする
        print("  ⚠️ word_timestampsが取得できず、文字数比例にフォールバックします")
        total_chars = sum(len(c) for c in chunks) or 1
        cards, pos = [], 0.0
        usable = max(0.0, duration - GAP * (len(chunks) - 1))
        for chunk in chunks:
            share = len(chunk) / total_chars * usable
            start, end = round(pos, 2), round(pos + share, 2)
            cards.append({"lines": [chunk], "start": start, "end": end})
            pos = end + GAP
        return cards

    script_full = normalize(narration)
    matcher = difflib.SequenceMatcher(None, all_chars, script_full, autojunk=False)

    s2w: dict = {}
    for w_pos, s_pos, length in matcher.get_matching_blocks():
        for i in range(length):
            if s_pos + i not in s2w:
                s2w[s_pos + i] = w_pos + i

    # 各文字の開始・終了時刻を直接計算する（2026-08-23改訂）。
    # 従来はscript_full上の文字位置をchar_times配列のインデックスに変換してから
    # 時刻を引いていたが、Whisperの認識文字数が台本より少ない場合（数字の
    # 聞き取りミス等）、末尾の未マッチ文字がインデックスの上限にクランプされ、
    # 複数文字が同じ時刻を指してしまい、該当カードの表示時間がほぼ0秒になる
    # （＝一瞬で消える）事故が実際の動画（kl002）で発覚した。文字インデックスでは
    # なく時刻そのものを補間することで、この種のクランプを構造的に防ぐ。
    known = sorted(s2w)
    char_start = [None] * len(script_full)
    char_end = [None] * len(script_full)
    for i in known:
        ci = s2w[i]
        char_start[i] = char_times[ci][0]
        char_end[i] = char_times[ci][1]

    if known:
        span = char_end[known[-1]] - char_start[known[0]]
        n_known_chars = known[-1] - known[0] + 1
        avg_pace = span / n_known_chars if n_known_chars > 0 and span > 0 else 0.15

        # 先頭（最初のマッチより前）: 既知区間の先頭からペースを遡って外挿
        for i in range(known[0] - 1, -1, -1):
            steps_back = known[0] - i
            s = max(0.0, char_start[known[0]] - steps_back * avg_pace)
            char_start[i] = s
            char_end[i] = s + avg_pace

        # 末尾（最後のマッチより後）: 既知区間の末尾からペースで順に外挿
        # （インデックスクランプではなく時刻を積み上げるため、常に単調増加する）。
        # 音声の実際の長さ（duration）を超えないようクランプする（2026-08-23追加）。
        # クランプしないと、Whisperが台本末尾を認識できなかった場合に外挿が
        # 音声の終端を超えてしまい、テロップがクロスフェード先の次シーンの
        # テロップと同じ時間帯に重なって表示される事故が実際の動画（kl002、
        # S12→S13境界）で発覚した。
        for i in range(known[-1] + 1, len(script_full)):
            steps_fwd = i - known[-1]
            s = min(duration, char_end[known[-1]] + (steps_fwd - 1) * avg_pace)
            char_start[i] = s
            char_end[i] = min(duration, s + avg_pace)

        # 既知区間どうしの間（マッチが飛んでいる箇所）を時刻ベースで線形補間
        for j in range(len(known) - 1):
            s1, s2 = known[j], known[j + 1]
            gap_chars = s2 - s1 - 1
            if gap_chars <= 0:
                continue
            t1e, t2s = char_end[s1], char_start[s2]
            gap_span = t2s - t1e
            step = gap_span / (gap_chars + 1) if gap_span > 0 else avg_pace
            for k, i in enumerate(range(s1 + 1, s2), start=1):
                if char_start[i] is None:
                    char_start[i] = t1e + step * (k - 1)
                    char_end[i] = t1e + step * k

    cards, s_pos = [], 0
    for chunk in chunks:
        norm_chunk = normalize(chunk)
        n = len(norm_chunk)
        if n == 0:
            continue
        start_t = round(max(0.0, char_start[s_pos]), 2) if char_start[s_pos] is not None else 0.0
        end_idx = s_pos + n - 1
        end_t = round(char_end[end_idx], 2) if char_end[end_idx] is not None else start_t + 0.5
        cards.append({"lines": [chunk], "start": start_t, "end": end_t})
        s_pos += n

    # カード間に最小GAPを確保しつつ、各カードの最小表示時間も保証する
    # （startだけ後ろにずらしてendをそのままにすると、表示時間がほぼ0になり
    # 「一瞬で消える」カードが発生するため、ずらした分だけendも押す）。
    # 最小表示時間は固定0.5秒ではなく文字数に応じて決める（2026-08-23改訂。
    # 0.5秒固定だと6〜9文字程度のカードでも一瞬で消えてしまい、読み切れない
    # という指摘が実際にあったため）。また、従来はcards[0]（先頭カード）が
    # このチェックの対象外だったため、先頭カードにも同様に適用する。
    MIN_SEC_PER_CHAR = 0.15  # 上限おおよそ6.7文字/秒（読み取れる最低限の速さ）
    MIN_CARD_DUR_FLOOR = 0.6
    for i, card in enumerate(cards):
        if i > 0:
            min_start = round(cards[i - 1]["end"] + GAP, 2)
            if card["start"] < min_start:
                shift = min_start - card["start"]
                card["start"] = min_start
                card["end"] = round(card["end"] + shift, 2)
        text_len = len("".join(card["lines"]))
        min_dur = max(MIN_CARD_DUR_FLOOR, text_len * MIN_SEC_PER_CHAR)
        if card["end"] - card["start"] < min_dur:
            card["end"] = round(card["start"] + min_dur, 2)

    # 最終カードの終了時刻は、音声の実長を大きく超えないようにする
    # （kl_video_gen.py側のクリップはnarr_dur+NARR_DELAY+NARR_TAILの長さで
    # 作られ、その末尾-CROSSFADE_DURATION秒から次シーンとのクロスフェードが
    # 始まるため、実測ではdurationを0.2秒超える程度までが安全域）。
    # 上のMIN_CARD_DUR適用で最終カードが再び音声長を超えるケースがあるため、
    # 最後にもう一度クランプする。
    if cards:
        safe_end = round(duration + 0.2, 2)
        if cards[-1]["end"] > safe_end:
            cards[-1]["end"] = safe_end

    return cards


def cmd_plan(episode_id: str, scene_filter: list = None):
    ep_path = BASE_DIR / "episodes" / f"{episode_id}.json"
    ep = json.loads(ep_path.read_text())
    narration_dir = DESKTOP_DIR / "narration"

    updated = 0
    for scene in ep["scenes"]:
        sid = scene["scene_id"]
        if scene_filter and sid not in scene_filter:
            continue
        wav_path = narration_dir / f"S{sid:02d}.wav"
        if not wav_path.exists():
            print(f"  ⚠️  S{sid:02d}: 音声ファイルが見つかりません（スキップ）")
            continue
        duration = get_wav_duration(wav_path)
        print(f"  S{sid:02d}: Whisperで解析中...")
        cards = plan_telop_cards(scene["narration"], wav_path, duration)
        scene["telop_cards"] = cards
        updated += 1
        print(f"  S{sid:02d}: {len(cards)}枚のカード（音声長 {duration:.2f}s）")
        for c in cards:
            print(f"      {c['start']:.2f}〜{c['end']:.2f}  {c['lines'][0]}")

    ep_path.write_text(json.dumps(ep, ensure_ascii=False, indent=2))
    print(f"\n完了: {updated}シーンに telop_cards を書き込みました")


def burn_telop(video: Path, cards: list, dst: Path, tmp: Path):
    """cards（{"lines":[...], "start":, "end":}）を drawtext で焼き込む。
    lw_video_gen.py の burn_telop と同じ仕組み（textfile方式でエスケープ回避）。
    """
    shutil.copy(str(FONT_SRC), str(FONT_TMP))
    font = str(FONT_TMP)
    cy = TELOP_CENTER_Y

    filter_parts = []
    prev = "0:v"
    idx = 0
    for ci, card in enumerate(cards):
        lines = card["lines"]
        t_start, t_end = card["start"], card["end"]
        enable = f"between(t\\,{t_start:.2f}\\,{t_end:.2f})"
        n = len(lines)
        for li, line in enumerate(lines[:2]):
            tf = tmp / f"telop_{ci}_{li}.txt"
            tf.write_text(line.replace("\r", ""), encoding="utf-8")
            if n == 1:
                y_expr = f"h*{cy}-text_h/2"
            else:
                half_gap = TELOP_LINE_SPACING / 2
                offset = -half_gap if li == 0 else half_gap
                y_expr = f"h*{cy}-text_h/2+{offset}"
            out = f"dv{idx}"
            filter_parts.append(
                f"[{prev}]drawtext="
                f"fontfile={font}"
                f":textfile={tf}"
                f":expansion=none"
                f":fontcolor=white:fontsize={TELOP_FONTSIZE}"
                f":borderw=7:bordercolor=black@1.0"
                f":shadowx=2:shadowy=2:shadowcolor=black@0.75"
                f":x=(w-text_w)/2"
                f":y=({y_expr})"
                f":enable={enable}"
                f"[{out}]"
            )
            prev = out
            idx += 1

    if not filter_parts:
        subprocess.run([FFMPEG, "-y", "-i", str(video), "-c", "copy", str(dst)], check=True)
        return

    subprocess.run(
        [
            FFMPEG, "-y", "-i", str(video),
            "-filter_complex", ";".join(filter_parts),
            "-map", f"[{prev}]",
            "-map", "0:a" if _has_audio(video) else "0:v",
            "-c:v", "libx264", "-crf", "18", "-preset", "slow",
        ] + (["-c:a", "copy"] if _has_audio(video) else [])
        + [str(dst)],
        check=True,
    )


def _has_audio(video: Path) -> bool:
    r = subprocess.run(
        [shutil.which("ffprobe") or "ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=index", "-of", "csv=p=0", str(video)],
        capture_output=True, text=True,
    )
    return bool(r.stdout.strip())


def cmd_burn_test(episode_id: str, scene_id: int):
    ep_path = BASE_DIR / "episodes" / f"{episode_id}.json"
    ep = json.loads(ep_path.read_text())
    scene = next(s for s in ep["scenes"] if s["scene_id"] == scene_id)
    if "telop_cards" not in scene:
        print("❌ telop_cards がありません。先に `plan` を実行してください", file=sys.stderr)
        sys.exit(1)

    img_path = DESKTOP_DIR / "images" / f"S{scene_id:02d}.png"
    wav_path = DESKTOP_DIR / "narration" / f"S{scene_id:02d}.wav"
    if not img_path.exists() or not wav_path.exists():
        print(f"❌ 画像またはナレーション音声が見つかりません: {img_path} / {wav_path}", file=sys.stderr)
        sys.exit(1)

    out_dir = DESKTOP_DIR
    tmp_dir = out_dir / "_telop_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    duration = get_wav_duration(wav_path)
    silent_clip = tmp_dir / "base.mp4"
    subprocess.run(
        [
            FFMPEG, "-y", "-loop", "1", "-i", str(img_path), "-i", str(wav_path),
            "-t", str(duration), "-vf", "scale=1408:768",
            "-c:v", "libx264", "-crf", "18", "-preset", "fast",
            "-c:a", "aac", "-b:a", "192k", "-shortest",
            str(silent_clip),
        ],
        check=True,
    )

    out_path = out_dir / f"telop_test_S{scene_id:02d}.mp4"
    burn_telop(silent_clip, scene["telop_cards"], out_path, tmp_dir)
    shutil.rmtree(tmp_dir, ignore_errors=True)
    print(f"✅ テスト動画を保存しました: {out_path}")


def main():
    parser = argparse.ArgumentParser(description="くらしを変える科学 テロップ生成・焼き込み")
    parser.add_argument("--episode", required=True, help="エピソードID（例: kl001）")
    parser.add_argument("command", choices=["plan", "burn-test"])
    parser.add_argument("--scenes", help="対象scene_idをカンマ区切りで指定（plan用、省略時は全シーン）")
    parser.add_argument("--scene", type=int, help="対象scene_id（burn-test用）")
    args = parser.parse_args()

    if args.command == "plan":
        scene_filter = [int(s) for s in args.scenes.split(",")] if args.scenes else None
        cmd_plan(args.episode, scene_filter)
    elif args.command == "burn-test":
        if not args.scene:
            parser.error("burn-test には --scene が必要です")
        cmd_burn_test(args.episode, args.scene)


if __name__ == "__main__":
    main()
