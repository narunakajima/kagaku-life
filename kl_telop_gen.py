"""
kl_telop_gen.py — くらしを変える科学 テロップ生成・焼き込みスクリプト

lamp-whisperの lw_video_gen.py のテロップ機能と同じ見た目（drawtext焼き込み）を
踏襲するが、タイミング決定方法は異なる。

LWとの違い: LWは1本の連続音声＋自由形式の台本のため、Whisperで音声を解析して
セリフの発話タイミングを推定する必要がある。kagaku-lifeはシーンごとに個別の
TTS音声ファイルがあり、ナレーション文もエピソードJSONに正確な文字列として
存在するため、**Whisperは不要**——各シーンのナレーション文を読みやすい長さの
カード（テロップ表示単位）に分割し、実際のTTS音声の長さに対して文字数比例で
タイミングを割り当てる。

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
import json
import os
import shutil
import subprocess
import sys
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

BREAK_CHARS = "、。！？　 "


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
            split_pos = max_chars
        split_pos = _nearest_safe_split(remaining, split_pos)
        split_pos = max(1, min(split_pos, len(remaining)))
        chunk = remaining[:split_pos].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[split_pos:]
    return chunks


def plan_telop_cards(narration: str, duration: float) -> list:
    """ナレーション文をチャンクに分割し、文字数比例でシーン内相対タイミングを割り当てる。"""
    chunks = chunk_narration(narration)
    total_chars = sum(len(c) for c in chunks) or 1
    cards = []
    pos = 0.0
    usable = max(0.0, duration - GAP * (len(chunks) - 1))
    for chunk in chunks:
        share = len(chunk) / total_chars * usable
        start = round(pos, 2)
        end = round(pos + share, 2)
        cards.append({"lines": [chunk], "start": start, "end": end})
        pos = end + GAP
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
        cards = plan_telop_cards(scene["narration"], duration)
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
                f":borderw=1:bordercolor=white@1.0"
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
