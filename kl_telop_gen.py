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
  burn-test: ~/Desktop/kagaku-life/{episode}/telop_test_S{NN}.mp4
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

# 句読点が無い長い文でも複合語の途中で切らないよう、助詞の直後を安全な区切り候補にする
# （例:「取り組む」の途中で切れる事故を防ぐ。長い助詞から先にマッチさせる）
# 1文字の助詞は「やり遂げる」の「や」のように単語の先頭と偶然一致し、誤検出（本当は
# 単語の途中なのに区切ってしまう）のリスクが高い。実際に「や」で誤爆する事故が
# 発生したため、1文字候補は誤爆リスクの低いものだけに絞る
# （を/が/へ/のは単語の先頭に来ることが稀で比較的安全、は/に/で/と/も/し/やは
# 「早い」「匂い」「出る」「特に」「もの」「知る」「やり」等、単語の先頭と衝突しやすいため除外）。
PARTICLES = sorted(
    ["ながら", "けれど", "けども", "ばかり", "だけど", "ので", "のに", "から",
     "まで", "より", "だけ", "など", "しか", "こそ", "でも", "たら", "れば",
     "ても", "つつ", "を", "が", "へ", "の"],
    key=len, reverse=True,
)


def get_wav_duration(wav_path: Path) -> float:
    with wave.open(str(wav_path)) as wf:
        return wf.getnframes() / wf.getframerate()


def _in_number_run(text: str, pos: int) -> bool:
    """posが数字（%含む）の連続の途中にあるかどうか判定する。
    例: "92%" の "9"と"2"の間、"2"と"%"の間はどちらもTrue。
    """
    if pos <= 0 or pos >= len(text):
        return False
    before, after = text[pos - 1], text[pos]
    digit_or_pct = lambda c: c.isdigit() or c == "%"
    return digit_or_pct(before) and digit_or_pct(after)


def _nearest_safe_split(text: str, pos: int, floor: int = 1) -> int:
    """posが数字の途中なら、外側に安全な区切り位置を探す。"""
    if not _in_number_run(text, pos):
        return pos
    # 数字連続の先頭（前方）を探す（例: "92%"の直前まで戻る）
    back = pos
    while back > floor and _in_number_run(text, back):
        back -= 1
    if back > floor:
        return back
    # 戻れない場合は数字連続の直後まで進める
    fwd = pos
    while fwd < len(text) and _in_number_run(text, fwd):
        fwd += 1
    return fwd


def chunk_narration(text: str, max_chars: int = MAX_LINE_CHARS) -> list:
    """長いナレーション文を読みやすい長さのチャンクに分割する。
    句読点を優先して自然な位置で区切り、句読点が見つからない場合は文字数で強制分割する。
    どちらの場合も、数字（%等）の途中では絶対に分割しない。
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
            # 句読点が無い場合、助詞の直後を安全な区切りとして探す
            # （複合語の途中で切れるのを防ぐ。max_charsに近い位置を優先）
            best = None
            for i in range(max(0, max_chars - 8), min(len(window), max_chars + 5)):
                for p in PARTICLES:
                    if window[i - len(p):i] == p and i - len(p) >= 1:
                        if best is None or abs(i - max_chars) < abs(best - max_chars):
                            best = i
                        break
            split_pos = best
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

    known = sorted(s2w)
    if known:
        for i in range(known[0]):
            s2w[i] = max(0, s2w[known[0]] - (known[0] - i))
        for i in range(known[-1] + 1, len(script_full)):
            s2w[i] = min(len(char_times) - 1, s2w[known[-1]] + (i - known[-1]))
        for j in range(len(known) - 1):
            s1, s2 = known[j], known[j + 1]
            w1, w2 = s2w[s1], s2w[s2]
            for i in range(s1 + 1, s2):
                if i not in s2w:
                    frac = (i - s1) / (s2 - s1)
                    s2w[i] = round(w1 + frac * (w2 - w1))

    cards, s_pos = [], 0
    for chunk in chunks:
        norm_chunk = normalize(chunk)
        n = len(norm_chunk)
        if n == 0:
            continue
        w_s = min(s2w.get(s_pos, 0), len(char_times) - 1)
        w_e = min(s2w.get(s_pos + n - 1, len(char_times) - 1), len(char_times) - 1)
        start_t = round(char_times[w_s][0], 2)
        end_t = round(char_times[w_e][1], 2)
        cards.append({"lines": [chunk], "start": start_t, "end": end_t})
        s_pos += n

    # カード間に最小GAPを確保しつつ、各カードの最小表示時間も保証する
    # （startだけ後ろにずらしてendをそのままにすると、表示時間がほぼ0になり
    # 「一瞬で消える」カードが発生するため、ずらした分だけendも押す）
    MIN_CARD_DUR = 0.5
    for i in range(1, len(cards)):
        min_start = round(cards[i - 1]["end"] + GAP, 2)
        if cards[i]["start"] < min_start:
            shift = min_start - cards[i]["start"]
            cards[i]["start"] = min_start
            cards[i]["end"] = round(cards[i]["end"] + shift, 2)
        if cards[i]["end"] - cards[i]["start"] < MIN_CARD_DUR:
            cards[i]["end"] = round(cards[i]["start"] + MIN_CARD_DUR, 2)

    return cards


def cmd_plan(episode_id: str, scene_filter: list = None):
    ep_path = BASE_DIR / "episodes" / f"{episode_id}.json"
    ep = json.loads(ep_path.read_text())
    narration_dir = DESKTOP_DIR / episode_id / "narration"

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

    img_path = DESKTOP_DIR / episode_id / "images" / f"S{scene_id:02d}.png"
    wav_path = DESKTOP_DIR / episode_id / "narration" / f"S{scene_id:02d}.wav"
    if not img_path.exists() or not wav_path.exists():
        print(f"❌ 画像またはナレーション音声が見つかりません: {img_path} / {wav_path}", file=sys.stderr)
        sys.exit(1)

    out_dir = DESKTOP_DIR / episode_id
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
