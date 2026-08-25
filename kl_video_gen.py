"""
kl_video_gen.py — くらしを変える科学 動画生成スクリプト

samurai-chroniclesの sc_video_gen.py と同じ設計思想（Ken Burns + クロスフェード +
BGM3曲ミックス + テロップ焼き込み）を踏襲する。kl_image_gen.py / kl_tts_gen.py /
kl_zoom_anchor.py / kl_telop_gen.py / kl_bgm_library.py で用意した素材を1本の動画に
組み立てる最終工程。

構成: [ティザー(scenes 1-N, teaser type)] → [ロゴイントロ] →
      [本編(残りのscenes)] → [ロゴアウトロ]
（CLAUDE.md「動画全体構成」参照。SCと違い、ティザーは独立した特別枠ではなく
scenes配列内のteaserタイプシーンとして扱う）

使い方:
  python3 kl_video_gen.py --episode kl001
  python3 kl_video_gen.py --episode kl001 --out ~/Desktop/kagaku-life/kl001/output

前提: kl_image_gen.py / kl_tts_gen.py / kl_zoom_anchor.py / kl_telop_gen.py plan /
kl_bgm_library.py --add がすべて完了していること（Google Driveに画像・音声・BGMが
格納済み、episode JSONにzoom_anchor・telop_cardsが書き込み済み）。
"""

import argparse
import json
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import ImageFont

sys.stdout.reconfigure(line_buffering=True)

BASE_DIR = Path(__file__).parent
DRIVE_BASE = (
    Path.home()
    / "Library/CloudStorage"
    / "GoogleDrive-naru.nakajima@gmail.com"
    / "マイドライブ"
    / "Kagaku-Life"
)
DESKTOP_DIR = Path.home() / "Desktop" / "kagaku-life"

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"

OUTPUT_W = 1408
OUTPUT_H = 768
FPS = 24

NARR_DELAY = 0.5
NARR_TAIL = 1.0
MIN_CLIP_FLOOR = 3.0
CROSSFADE_DURATION = 0.8

KB_ZOOM_FACTOR = 1.40
KB_ZOOM_SPEED = 0.0006
STATIC_ZOOM_FACTOR = 1.06  # "static"は完全静止ではなく、クリップ全長にわたる
                            # ごく控えめな連続ズームにする（下記make_ken_burns参照）

# 研究ボイス（Orus）が生活者ボイス（Leda）より聞き取りづらいという指摘のため、
# ナレーター別に音量を補正する（2026-08-21追加）。
NARRATOR_VOLUME = {"persona": 1.0, "research": 1.5}

BGM_VOLUME = 0.12
BGM_FADE_IN = 5
BGM_FADE_OUT = 6
BGM_CROSSFADE = 4.0
BGM_ROLES = ["intro", "main", "outro"]

INTRO_DURATION = 4.0
OUTRO_DURATION = 7.0
LOGO_PATH = DRIVE_BASE / "LOGO.PNG"
FONT_BOLD = Path("/System/Library/Fonts/ヒラギノ角ゴシック W8.ttc")
FONT_REGULAR = Path("/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc")
FONT_TMP_BOLD = Path("/tmp/kl_font_bold.ttc")
FONT_TMP_REGULAR = Path("/tmp/kl_font_regular.ttc")

CHANNEL_NAME = "幸せな未来のサイエンス"
OFFICIAL_SITE = "kagaku-life.com"
OUTRO_LINE1 = OFFICIAL_SITE
OUTRO_LINE2 = "毎週更新・チャンネル登録お願いします"

TELOP_FONTSIZE = 44
TELOP_CENTER_Y = 0.88
TELOP_LINE_SPACING = 64
TEASER_TELOP_FONTSIZE = 84  # SCのキネティック字幕（110pt@1920幅）を1408幅に換算

# Shorts（縦動画）用
SHORTS_W = 768
SHORTS_H = 1376
SHORTS_XFADE = 0.4
SHORTS_TELOP_FONTSIZE = 48
SHORTS_TELOP_CENTER_Y = 0.82
# 冒頭フックテキスト（SCのshorts_hook_text_filterを1408x768→768x1376比で換算）
SHORTS_HOOK_CONFIGS = [(114, "h*0.07"), (89, "h*0.16")]


def run_cmd(cmd: list, label: str = ""):
    print(f"  ▶ {label}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-4000:], file=sys.stderr)
        raise RuntimeError(f"ffmpeg失敗: {label}")


def probe_audio_duration(path: Path) -> float:
    r = subprocess.run(
        [FFPROBE, "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
        capture_output=True, text=True,
    )
    return float(json.loads(r.stdout)["format"]["duration"])


def make_ken_burns(src: Path, dst: Path, duration: float, effect: str, anchor: tuple = (0.5, 0.5),
                   w: int = OUTPUT_W, h: int = OUTPUT_H):
    """画像にKen Burnsエフェクトを適用して動画クリップを生成する（SCのmake_ken_burnsと同じ仕組み）。"""
    if effect == "pan_zoom_out":
        # 2人構図用の汎用値。左右どちら向きにパンするかはSCと同じくランダムに
        # 決める（JSON側では方向を固定せず、kl_zoom_anchor.pyが「2人構図」と
        # 判定したシーンに一律"pan_zoom_out"を書き込む設計）。
        effect = random.choice(["pan_zoom_out_lr", "pan_zoom_out_rl"])
    total_frames = max(1, int(duration * FPS))
    z = KB_ZOOM_FACTOR
    buf_w, buf_h = w * 2, h * 2
    prescale = f"scale={buf_w}:{buf_h}:flags=lanczos"
    px, py = anchor

    # zoom_inは固定速度(KB_ZOOM_SPEED)だと、クリップが約28秒を超える長さの場合
    # （kagaku-lifeは1シーンのナレーションが長く、context/findingシーンで
    # 30〜45秒のクリップになることが多い）最大倍率(KB_ZOOM_FACTOR)に途中で
    # 到達してしまい、残り時間ずっとズームが完全静止する。これが「カクッと
    # 止まる」体感の原因だった（2026-08-25発見・修正）。zoom_out は元々
    # クリップ全長に応じた可変速度（z_step_dn）で最後まで動き続ける設計に
    # なっていたため、zoom_inも同様に「固定速度」と「クリップ全長で割った
    # 可変速度」の遅い方を採用するようにし、短いクリップ（ティザー等）は
    # 従来通りの控えめな速度、長いクリップは最後まで途切れず動き続けるように
    # 統一した。
    zoom_step = min(KB_ZOOM_SPEED, (z - 1.0) / max(total_frames, 1))
    z_end = round(1.0 + zoom_step * total_frames, 6)
    z_step_dn = round((z - 1.0) / max(total_frames, 1), 8)

    if effect == "zoom_in":
        vf = (
            f"{prescale},"
            f"zoompan=z='min(1+{zoom_step}*on,{z_end})'"
            f":x='{px}*(iw-iw/zoom)':y='{py}*(ih-ih/zoom)'"
            f":d={total_frames}:s={w}x{h}:fps={FPS},setsar=1,format=yuv420p"
        )
    elif effect == "zoom_out":
        vf = (
            f"{prescale},"
            f"zoompan=z='max({z}-{z_step_dn}*on,1)'"
            f":x='{px}*(iw-iw/zoom)':y='{py}*(ih-ih/zoom)'"
            f":d={total_frames}:s={w}x{h}:fps={FPS},setsar=1,format=yuv420p"
        )
    elif effect == "pan_right":
        vf = (
            f"{prescale},"
            f"zoompan=z='{z}'"
            f":x='iw/2-(iw/zoom/2)+({buf_w}-{buf_w}/{z})/2*on/{total_frames}'"
            f":y='ih/2-(ih/zoom/2)'"
            f":d={total_frames}:s={w}x{h}:fps={FPS},setsar=1,format=yuv420p"
        )
    elif effect == "pan_left":
        vf = (
            f"{prescale},"
            f"zoompan=z='{z}'"
            f":x='iw/2-(iw/zoom/2)+({buf_w}-{buf_w}/{z})/2*(1-on/{total_frames})'"
            f":y='ih/2-(ih/zoom/2)'"
            f":d={total_frames}:s={w}x{h}:fps={FPS},setsar=1,format=yuv420p"
        )
    elif effect in ("pan_zoom_out_lr", "pan_zoom_out_rl"):
        # 2人構図用: フェーズ1（60%）で片側→反対側へパン、フェーズ2（40%）で
        # パン先の位置からズームアウトして全体を見せる（SCのpan_zoom_out_lr/rlと同じ仕組み）。
        pf = int(total_frames * 0.6)
        zf = max(total_frames - pf, 1)
        z_step_dn2 = round((z - 1.0) / zf, 6)
        pan_range = round(buf_w * (1 - 1 / z), 4)
        z_expr = (f"if(lt(on\\,{pf})\\,"
                  f"{z}\\,"
                  f"max({z}-{z_step_dn2}*(on-{pf})\\,1))")
        if effect == "pan_zoom_out_lr":
            x_expr = f"if(lt(on\\,{pf})\\,{pan_range}*on/{pf}\\,iw-iw/zoom)"
        else:
            x_expr = f"if(lt(on\\,{pf})\\,{pan_range}*(1-on/{pf})\\,0)"
        vf = (
            f"{prescale},"
            f"zoompan=z='{z_expr}'"
            f":x='{x_expr}':y='ih/2-(ih/zoom/2)'"
            f":d={total_frames}:s={w}x{h}:fps={FPS},setsar=1,format=yuv420p"
        )
    else:  # static
        # 従来は完全に静止したフレーム（zが定数）だったが、kagaku-lifeは
        # 1シーンのナレーションが長く"static"クリップが30秒を超えることも
        # あるため、完全に動かない画面が長時間続いて不自然だという指摘が
        # あった（2026-08-25）。KB_ZOOM_FACTORよりずっと控えめな
        # STATIC_ZOOM_FACTORまで、クリップ全長をかけてごくゆっくり
        # ズームインする「呼吸するような静止」に変更した（完全に動かないの
        # ではなく、常にクリップ全体を通して緩やかに動き続ける）。
        static_step = (STATIC_ZOOM_FACTOR - 1.0) / max(total_frames, 1)
        static_end = round(1.0 + static_step * total_frames, 6)
        vf = (
            f"{prescale},"
            f"zoompan=z='min(1+{static_step}*on,{static_end})'"
            f":x='{px}*(iw-iw/zoom)':y='{py}*(ih-ih/zoom)'"
            f":d={total_frames}:s={w}x{h}:fps={FPS},setsar=1,format=yuv420p"
        )

    run_cmd(
        [
            FFMPEG, "-y", "-loop", "1", "-i", str(src),
            "-vf", vf, "-t", str(duration), "-r", str(FPS),
            "-c:v", "libx264", "-crf", "18", "-preset", "slow",
            "-pix_fmt", "yuv420p", str(dst),
        ],
        f"KB {effect} {src.stem} ({duration:.1f}s)",
    )


def crossfade_concat_n(clips: list, durations: list, dst: Path, xfade_dur: float = CROSSFADE_DURATION):
    n = len(clips)
    if n == 1:
        run_cmd([FFMPEG, "-y", "-i", str(clips[0]), "-c", "copy", str(dst)], "copy (1 clip)")
        return

    offsets, cumulative = [], 0.0
    for i in range(n - 1):
        cumulative += durations[i] - xfade_dur
        offsets.append(round(cumulative, 3))

    inputs = []
    for c in clips:
        inputs += ["-i", str(c)]

    fc_parts, prev = [], "0:v"
    for i in range(1, n):
        out_label = f"v{i}"
        fc_parts.append(f"[{prev}][{i}:v]xfade=transition=fade:duration={xfade_dur}:offset={offsets[i-1]}[{out_label}]")
        prev = out_label

    run_cmd(
        [FFMPEG, "-y"] + inputs + [
            "-filter_complex", ";".join(fc_parts),
            "-map", f"[{prev}]",
            "-c:v", "libx264", "-crf", "18", "-preset", "slow",
            str(dst),
        ],
        f"crossfade concat ({n}クリップ)",
    )


def concat_video_clips(clips: list, dst: Path):
    """複数の動画クリップをハードカットで結合する（logo等、クロスフェード不要な結合用）。"""
    list_file = dst.parent / "_concat_list.txt"
    list_file.write_text("\n".join(f"file '{c}'" for c in clips), encoding="utf-8")
    run_cmd(
        [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
         "-c:v", "libx264", "-crf", "18", "-preset", "slow", str(dst)],
        "concat clips",
    )


def make_logo_clip(dst: Path, duration: float, lines: list, tmp: Path):
    """静止画ロゴから、暗い背景+ロゴ+テキスト+フェードのバンパークリップを生成する
    （SCのmake_intro_clip/make_outro_clipと同じ仕組み。別途動画ファイルは不要）。
    """
    shutil.copy(str(FONT_BOLD), str(FONT_TMP_BOLD))
    shutil.copy(str(FONT_REGULAR), str(FONT_TMP_REGULAR))

    logo_w = 320
    logo_y = f"(H-h)/2-90"

    drawtexts = []
    y_positions = [f"h/2+{110 + i*50}" for i in range(len(lines))]
    for i, (text, font, size, color) in enumerate(lines):
        tf = tmp / f"logo_text_{dst.stem}_{i}.txt"
        tf.write_text(text, encoding="utf-8")
        drawtexts.append(
            f"drawtext=fontfile={font}:textfile={tf}:expansion=none"
            f":fontsize={size}:fontcolor={color}"
            f":x=(w-text_w)/2:y={y_positions[i]}"
            f":shadowx=1:shadowy=1:shadowcolor=black@0.6"
        )

    text_chain = ",".join(drawtexts)
    fade_out_start = max(0.0, duration - 1.0)

    vf = (
        f"[1:v]scale={logo_w}:-1,format=rgba[logo];"
        f"[0:v][logo]overlay=(W-w)/2:{logo_y},"
        f"{text_chain},"
        f"fade=t=in:st=0:d=0.8,"
        f"fade=t=out:st={fade_out_start:.2f}:d=1.0"
    )

    run_cmd(
        [
            FFMPEG, "-y",
            "-f", "lavfi", "-i", f"color=c=0x0a1626:size={OUTPUT_W}x{OUTPUT_H}:rate={FPS}:d={duration}",
            "-i", str(LOGO_PATH),
            "-filter_complex", vf,
            "-t", str(duration),
            "-c:v", "libx264", "-crf", "18", "-preset", "slow",
            "-pix_fmt", "yuv420p", str(dst),
        ],
        f"logo clip ({dst.stem}, {duration:.1f}s)",
    )


def resolve_bgm_paths(ep: dict) -> dict:
    sources = ep.get("bgm_sources") or {}
    if all(sources.get(r) for r in BGM_ROLES):
        paths = {r: DRIVE_BASE / sources[r] for r in BGM_ROLES}
        if all(p.exists() for p in paths.values()):
            return paths
        missing = [r for r, p in paths.items() if not p.exists()]
        raise FileNotFoundError(f"bgm_sourcesのファイルが見つかりません: {missing}")
    raise FileNotFoundError("bgm_sourcesが3役割とも設定されていません（kl_bgm_library.py --add で登録してください）")


# CLAUDE.md「シーンタイプ体系とBGM3曲構成の対応」の役割表そのもの。
# 境界計算はこの役割マッピングに基づいて行う（type名を個別にハードコード
# しない）。
# 2026-08-22改訂: 「自己紹介＋課題の紹介（〜context）」と「研究の紹介
# （citation〜）」で区切る方が物語上自然、というユーザーの判断により、
# contextをintro側に、citationをmain側に変更した（旧: context=main,
# citation=intro）。
BGM_ROLE_BY_TYPE = {
    "teaser": "intro", "hook": "intro", "context": "intro",
    "citation": "main", "finding": "main", "data": "main",
    "impact": "outro", "closing": "outro",
}


def compute_bgm_segments(bgm_paths: dict, main_scenes: list, main_offsets: list,
                         intro_block_dur: float, total_dur: float) -> list:
    """CLAUDE.md「境界計算ルール」: 境界1=最初のmain役割シーン開始、
    境界2=最初のoutro役割シーン開始（いずれも本編=main_scenes内でのオフセット、
    intro_block_dur=ティザー+ロゴイントロの尺を加算してグローバル時刻にする）。
    """
    roles = [BGM_ROLE_BY_TYPE.get(s.get("type", ""), "main") for s in main_scenes]
    n = len(main_scenes)
    b1_idx = next((i for i, r in enumerate(roles) if r != "intro"), n // 3)
    b2_idx = next((i for i, r in enumerate(roles) if r == "outro"), n * 2 // 3)
    if b2_idx <= b1_idx:
        b2_idx = min(max(b1_idx + 1, n * 2 // 3), n - 1)

    b1 = intro_block_dur + main_offsets[b1_idx]
    b2 = intro_block_dur + main_offsets[b2_idx]
    print(f"  BGM切替: intro→main {b1:.1f}s (S{main_scenes[b1_idx]['scene_id']:02d})"
          f" / main→outro {b2:.1f}s (S{main_scenes[b2_idx]['scene_id']:02d})")

    half_xf = BGM_CROSSFADE / 2
    return [
        (bgm_paths["intro"], 0.0, min(b1 + half_xf, total_dur)),
        (bgm_paths["main"], max(0.0, b1 - half_xf), min(b2 + half_xf, total_dur)),
        (bgm_paths["outro"], max(0.0, b2 - half_xf), total_dur),
    ]


def _bgm_segment_filter(in_idx: int, start: float, end: float, is_first: bool, is_last: bool, out_label: str) -> str:
    seg_dur = end - start
    fade_in = BGM_FADE_IN if is_first else BGM_CROSSFADE
    fade_out = BGM_FADE_OUT if is_last else BGM_CROSSFADE
    fade_out_start = max(0.0, seg_dur - fade_out)
    delay_ms = int(start * 1000)
    return (
        f"[{in_idx}:a]aloop=loop=-1:size=2000000000,"
        f"atrim=duration={seg_dur:.3f},"
        f"volume={BGM_VOLUME},"
        f"afade=t=in:st=0:d={fade_in},"
        f"afade=t=out:st={fade_out_start:.3f}:d={fade_out},"
        f"adelay={delay_ms}:all=1[{out_label}]"
    )


def build_audio_track(all_scenes: list, all_offsets: list, narration_dir: Path,
                      total_dur: float, bgm_segments: list, dst: Path):
    """全シーンのナレーション（テイザー+本編、グローバルオフセット）とBGM3曲をミックスする。"""
    narr_inputs, narr_filters, all_labels = [], [], []

    for i, scene in enumerate(all_scenes):
        sid = scene["scene_id"]
        wav = narration_dir / f"S{sid:02d}.wav"
        if not wav.exists():
            continue
        offset_ms = int(all_offsets[i] * 1000 + NARR_DELAY * 1000)
        idx = len(narr_inputs)
        narr_inputs.append(wav)
        lbl = f"n{i}"
        vol = NARRATOR_VOLUME.get(scene.get("narrator"), 1.0)
        narr_filters.append(f"[{idx}:a]volume={vol},adelay={offset_ms}:all=1[{lbl}]")
        all_labels.append(f"[{lbl}]")

    n_narr = len(narr_inputs)
    n_bgm = len(bgm_segments)
    bgm_labels = []
    for si, (bgm_path, start, end) in enumerate(bgm_segments):
        lbl = f"bgm{si}"
        narr_filters.append(_bgm_segment_filter(n_narr + si, start, end, si == 0, si == n_bgm - 1, lbl))
        bgm_labels.append(f"[{lbl}]")

    narr_filters.append(f"{''.join(all_labels)}amix=inputs={n_narr}:duration=longest:normalize=0[narr_mix]")
    narr_filters.append(f"[narr_mix]apad=whole_dur={total_dur}[narr_padded]")
    narr_filters.append(
        f"[narr_padded]{''.join(bgm_labels)}amix=inputs={1 + n_bgm}:duration=first:normalize=0[mix]"
    )
    narr_filters.append(f"[mix]atrim=duration={total_dur:.3f},asetpts=N/SR/TB[aout]")

    inputs_flat = []
    for wav in narr_inputs:
        inputs_flat += ["-i", str(wav)]
    for bgm_path, _, _ in bgm_segments:
        inputs_flat += ["-i", str(bgm_path)]

    run_cmd(
        [FFMPEG, "-y"] + inputs_flat + [
            "-filter_complex", ";".join(narr_filters),
            "-map", "[aout]", "-c:a", "aac", "-b:a", "192k", str(dst),
        ],
        "音声ミックス",
    )


def _fit_font_size(text: str, font_path: Path, max_size: int, max_width: int, min_size: int = 32) -> int:
    """指定した最大幅に収まるまでフォントサイズを縮小する（2026-08-22追加。
    ティザーの大型テロップが長い文で画面端からはみ出す問題への対処）。
    """
    size = max_size
    while size > min_size:
        font = ImageFont.truetype(str(font_path), size)
        w = font.getbbox(text)[2]
        if w <= max_width:
            return size
        size -= 4
    return min_size


def burn_telop_global(video: Path, all_scenes: list, all_offsets: list, dst: Path, tmp: Path):
    """全シーンのtelop_cards（シーン内相対時刻）にシーンのグローバルオフセットを加算し、
    動画全体にdrawtextで焼き込む（kl_telop_gen.pyのburn_telopと同じ仕組み）。
    """
    shutil.copy(str(FONT_BOLD), str(FONT_TMP_BOLD))
    shutil.copy(str(FONT_REGULAR), str(FONT_TMP_REGULAR))
    font = str(FONT_TMP_REGULAR)
    font_bold = str(FONT_TMP_BOLD)
    cy = TELOP_CENTER_Y

    filter_parts, prev, idx = [], "0:v", 0
    for scene, offset in zip(all_scenes, all_offsets):
        is_teaser = scene["type"] == "teaser"
        for card in scene.get("telop_cards", []):
            t_start = offset + NARR_DELAY + card["start"]
            t_end = offset + NARR_DELAY + card["end"]
            line = card["lines"][0]
            tf = tmp / f"telop_{idx}.txt"
            tf.write_text(line.replace("\r", ""), encoding="utf-8")
            enable = f"between(t\\,{t_start:.2f}\\,{t_end:.2f})"
            out = f"dv{idx}"
            if is_teaser:
                # ティザーはSCのキネティック字幕（画面中央・大型フォント）を踏襲し、
                # 通常の下部テロップと差別化してフックの強さを出す（2026-08-22追加）。
                # 長い文で画面端からはみ出さないよう、幅に応じてフォントサイズを縮小する
                # （2026-08-22追加。S04のような長めのフレーズではみ出す事故が実際に発生）。
                fs = _fit_font_size(line, FONT_BOLD, TEASER_TELOP_FONTSIZE, int(OUTPUT_W * 0.92))
                filter_parts.append(
                    f"[{prev}]drawtext=fontfile={font_bold}:textfile={tf}:expansion=none"
                    f":fontcolor=white:fontsize={fs}"
                    f":borderw=9:bordercolor=black@1.0"
                    f":x=(w-text_w)/2:y=(h*0.5-text_h/2):enable={enable}[{out}]"
                )
            else:
                filter_parts.append(
                    f"[{prev}]drawtext=fontfile={font}:textfile={tf}:expansion=none"
                    f":fontcolor=white:fontsize={TELOP_FONTSIZE}"
                    f":borderw=7:bordercolor=black@1.0"
                    f":shadowx=2:shadowy=2:shadowcolor=black@0.75"
                    f":x=(w-text_w)/2:y=(h*{cy}-text_h/2):enable={enable}[{out}]"
                )
            prev = out
            idx += 1

    if not filter_parts:
        run_cmd([FFMPEG, "-y", "-i", str(video), "-c", "copy", str(dst)], "copy (no telop)")
        return

    run_cmd(
        [
            FFMPEG, "-y", "-i", str(video),
            "-filter_complex", ";".join(filter_parts),
            "-map", f"[{prev}]", "-map", "0:a",
            "-c:v", "libx264", "-crf", "18", "-preset", "slow", "-c:a", "copy",
            str(dst),
        ],
        f"テロップ焼き込み（{idx}枚）",
    )


def gen_video(episode_id: str, out_dir: Path = None):
    ep_path = BASE_DIR / "episodes" / f"{episode_id}.json"
    ep = json.loads(ep_path.read_text())

    img_dir = DRIVE_BASE / episode_id / "images"
    narration_dir = DRIVE_BASE / episode_id / "narration"
    bgm_paths = resolve_bgm_paths(ep)

    if out_dir is None:
        out_dir = DESKTOP_DIR / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    scenes = ep["scenes"]
    teaser_scenes = [s for s in scenes if s["type"] == "teaser"]
    main_scenes = [s for s in scenes if s["type"] != "teaser"]

    print(f"\n{'━'*60}\n  {episode_id} — 動画生成開始\n"
          f"  ティザー{len(teaser_scenes)}シーン + 本編{len(main_scenes)}シーン\n{'━'*60}\n")

    def scene_durations_and_offsets(group: list) -> tuple:
        durations = []
        for scene in group:
            wav = narration_dir / f"S{scene['scene_id']:02d}.wav"
            narr_dur = probe_audio_duration(wav) if wav.exists() else 3.0
            durations.append(round(max(MIN_CLIP_FLOOR, narr_dur + NARR_DELAY + NARR_TAIL), 2))
        offsets = [0.0]
        for i in range(1, len(group)):
            offsets.append(round(offsets[-1] + durations[i - 1] - CROSSFADE_DURATION, 3))
        return durations, offsets

    teaser_durs, teaser_offsets = scene_durations_and_offsets(teaser_scenes)
    main_durs, main_offsets = scene_durations_and_offsets(main_scenes)
    teaser_block_dur = (teaser_offsets[-1] + teaser_durs[-1]) if teaser_scenes else 0.0
    main_block_dur = main_offsets[-1] + main_durs[-1]

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)

        def make_group_clips(group: list, durations: list) -> list:
            paths = []
            for scene, dur in zip(group, durations):
                sid = scene["scene_id"]
                img = img_dir / f"S{sid:02d}.png"
                clip = tmp / f"kb_S{sid:02d}.mp4"
                anchor = (scene.get("zoom_anchor") or {"x": 0.5, "y": 0.5})
                make_ken_burns(img, clip, dur, scene.get("ken_burns", "static"), (anchor["x"], anchor["y"]))
                paths.append(clip)
            return paths

        print("--- Ken Burnsクリップ生成 ---")
        teaser_clips = make_group_clips(teaser_scenes, teaser_durs)
        main_clips = make_group_clips(main_scenes, main_durs)

        print("\n--- クロスフェード結合 ---")
        teaser_video = tmp / "teaser_video.mp4"
        main_video = tmp / "main_video.mp4"
        if teaser_clips:
            crossfade_concat_n(teaser_clips, teaser_durs, teaser_video)
        crossfade_concat_n(main_clips, main_durs, main_video)

        print("\n--- ロゴクリップ生成 ---")
        intro_logo = tmp / "intro_logo.mp4"
        outro_logo = tmp / "outro_logo.mp4"
        make_logo_clip(intro_logo, INTRO_DURATION,
                        [(CHANNEL_NAME, str(FONT_TMP_BOLD), 44, "white")], tmp)
        make_logo_clip(outro_logo, OUTRO_DURATION,
                        [(OUTRO_LINE1, str(FONT_TMP_BOLD), 40, "0xf0a868"),
                         (OUTRO_LINE2, str(FONT_TMP_REGULAR), 26, "white")], tmp)

        print("\n--- 映像全結合 ---")
        video_parts = ([teaser_video] if teaser_scenes else []) + [intro_logo, main_video, outro_logo]
        full_video = tmp / "full_video.mp4"
        concat_video_clips(video_parts, full_video)

        intro_block_dur = teaser_block_dur + INTRO_DURATION
        total_dur = intro_block_dur + main_block_dur + OUTRO_DURATION
        print(f"\n  合計尺: {total_dur:.1f}s ({total_dur/60:.1f}分)"
              f"（ティザー{teaser_block_dur:.1f}s + ロゴ{INTRO_DURATION:.0f}s"
              f" + 本編{main_block_dur:.1f}s + ロゴ{OUTRO_DURATION:.0f}s）")

        all_scenes = teaser_scenes + main_scenes
        all_offsets = teaser_offsets + [o + intro_block_dur for o in main_offsets]

        print("\n--- 音声ミックス ---")
        bgm_segments = compute_bgm_segments(bgm_paths, main_scenes, main_offsets, intro_block_dur, total_dur)
        audio_track = tmp / "audio_track.aac"
        build_audio_track(all_scenes, all_offsets, narration_dir, total_dur, bgm_segments, audio_track)

        print("\n--- テロップ焼き込み ---")
        video_with_audio = tmp / "video_with_audio.mp4"
        run_cmd(
            [FFMPEG, "-y", "-i", str(full_video), "-i", str(audio_track),
             "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "copy", "-shortest",
             str(video_with_audio)],
            "映像+音声結合",
        )
        output_file = out_dir / f"{episode_id}.mp4"
        burn_telop_global(video_with_audio, all_scenes, all_offsets, output_file, tmp)

    print(f"\n{'━'*60}\n  ✓ 完成: {output_file}\n"
          f"  合計尺: {total_dur:.1f}s ({total_dur/60:.1f}分)\n{'━'*60}")


def gen_shorts_video(episode_id: str, out_dir: Path = None):
    """Shorts（9:16縦動画）を1本組み立てる。本編と違いロゴイントロ/アウトロは
    付けず（短尺のため）、シンプルにシーンをクロスフェード結合するのみ。
    BGMはbgm_sources.mainを全編通して1トラックのみ使う。
    """
    ep_path = BASE_DIR / "episodes" / f"{episode_id}.json"
    ep = json.loads(ep_path.read_text())
    shorts_list = ep.get("shorts") or []
    if not shorts_list:
        print("⚠️ shortsフィールドがありません。スキップします。")
        return

    img_dir = DRIVE_BASE / episode_id / "images"
    narration_dir = DRIVE_BASE / episode_id / "narration"

    if out_dir is None:
        out_dir = DESKTOP_DIR / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    mid = shorts_list[0]["shorts_id"]
    scenes = shorts_list[0]["scenes"]
    print(f"\n{'━'*60}\n  {episode_id} — Shorts動画生成開始（{len(scenes)}シーン）\n{'━'*60}\n")

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)

        durations = []
        for i, scene in enumerate(scenes, start=1):
            wav = narration_dir / f"shorts{mid}_S{i:02d}.wav"
            narr_dur = probe_audio_duration(wav) if wav.exists() else 2.0
            durations.append(max(1.5, narr_dur + NARR_DELAY + 0.3))

        offsets = [0.0]
        for i in range(1, len(scenes)):
            offsets.append(offsets[-1] + durations[i - 1] - SHORTS_XFADE)
        total_dur = offsets[-1] + durations[-1]
        print(f"  合計尺: {total_dur:.1f}s")

        print("\n--- Ken Burnsクリップ生成 ---")
        clips = []
        for i, scene in enumerate(scenes, start=1):
            img = img_dir / f"shorts{mid}_S{i:02d}.png"
            dst = tmp / f"kb_shorts_S{i:02d}.mp4"
            make_ken_burns(img, dst, durations[i - 1], "zoom_in", w=SHORTS_W, h=SHORTS_H)
            clips.append(dst)

        print("\n--- クロスフェード結合 ---")
        scenes_video = tmp / "shorts_video.mp4"
        crossfade_concat_n(clips, durations, scenes_video, xfade_dur=SHORTS_XFADE)

        print("\n--- 音声ミックス ---")
        narr_inputs, narr_filters, all_labels = [], [], []
        for i, scene in enumerate(scenes, start=1):
            wav = narration_dir / f"shorts{mid}_S{i:02d}.wav"
            if not wav.exists():
                continue
            offset_ms = int(offsets[i - 1] * 1000 + NARR_DELAY * 1000)
            idx = len(narr_inputs)
            narr_inputs.append(wav)
            lbl = f"n{i}"
            vol = NARRATOR_VOLUME.get(scene.get("narrator"), 1.0)
            narr_filters.append(f"[{idx}:a]volume={vol},adelay={offset_ms}:all=1[{lbl}]")
            all_labels.append(f"[{lbl}]")

        n_narr = len(narr_inputs)
        try:
            bgm_paths = resolve_bgm_paths(ep)
            bgm_input = bgm_paths["main"]
            narr_filters.append(_bgm_segment_filter(n_narr, 0.0, total_dur, True, True, "bgm0"))
            has_bgm = True
        except FileNotFoundError:
            print("  ⚠️ BGM未設定のためナレーションのみでミックスします")
            has_bgm = False

        narr_filters.append(f"{''.join(all_labels)}amix=inputs={n_narr}:duration=longest:normalize=0[narr_mix]")
        narr_filters.append(f"[narr_mix]apad=whole_dur={total_dur}[narr_padded]")
        if has_bgm:
            narr_filters.append(f"[narr_padded][bgm0]amix=inputs=2:duration=first:normalize=0[mix]")
        else:
            narr_filters.append(f"[narr_padded]anull[mix]")
        narr_filters.append(f"[mix]atrim=duration={total_dur:.3f},asetpts=N/SR/TB[aout]")

        inputs_flat = []
        for wav in narr_inputs:
            inputs_flat += ["-i", str(wav)]
        if has_bgm:
            inputs_flat += ["-i", str(bgm_input)]
        audio_track = tmp / "audio.aac"
        run_cmd(
            [FFMPEG, "-y"] + inputs_flat + [
                "-filter_complex", ";".join(narr_filters),
                "-map", "[aout]", "-c:a", "aac", "-b:a", "192k", str(audio_track),
            ],
            "音声ミックス",
        )

        video_with_audio = tmp / "video_with_audio.mp4"
        run_cmd(
            [FFMPEG, "-y", "-i", str(scenes_video), "-i", str(audio_track),
             "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "copy", "-shortest",
             str(video_with_audio)],
            "映像+音声結合",
        )

        print("\n--- テロップ焼き込み ---")
        shutil.copy(str(FONT_REGULAR), str(FONT_TMP_REGULAR))
        shutil.copy(str(FONT_BOLD), str(FONT_TMP_BOLD))
        font = str(FONT_TMP_REGULAR)
        font_bold = str(FONT_TMP_BOLD)
        filter_parts, prev, idx = [], "0:v", 0

        hook_lines = shorts_list[0].get("hook_lines") or []
        if hook_lines:
            # 冒頭クリップの間だけ表示する大型フックテキスト（SCのshorts_hook_text_filter踏襲）
            hook_end = durations[0]
            for i, text in enumerate(hook_lines[:2]):
                fs, y = SHORTS_HOOK_CONFIGS[i]
                fs = _fit_font_size(text, FONT_BOLD, fs, int(SHORTS_W * 0.92))
                tf = tmp / f"hook_{i}.txt"
                tf.write_text(text.replace("\r", ""), encoding="utf-8")
                bw = 9 if i == 0 else 7
                out = f"hook{i}"
                filter_parts.append(
                    f"[{prev}]drawtext=fontfile={font_bold}:textfile={tf}:expansion=none"
                    f":fontcolor=white:fontsize={fs}:borderw={bw}:bordercolor=black@1.0"
                    f":shadowx=4:shadowy=4:shadowcolor=black@0.75"
                    f":x=(w-text_w)/2:y={y}:enable=between(t\\,0\\,{hook_end:.2f})[{out}]"
                )
                prev = out
                idx += 1

        for i, (scene, offset, dur) in enumerate(zip(scenes, offsets, durations)):
            t_start = offset + NARR_DELAY
            t_end = offset + dur
            tf = tmp / f"telop_{idx}.txt"
            tf.write_text(scene["narration"].replace("\r", ""), encoding="utf-8")
            enable = f"between(t\\,{t_start:.2f}\\,{t_end:.2f})"
            out = f"dv{idx}"
            fs = _fit_font_size(scene["narration"], FONT_REGULAR, SHORTS_TELOP_FONTSIZE, int(SHORTS_W * 0.92))
            filter_parts.append(
                f"[{prev}]drawtext=fontfile={font}:textfile={tf}:expansion=none"
                f":fontcolor=white:fontsize={fs}"
                f":borderw=7:bordercolor=black@1.0"
                f":shadowx=2:shadowy=2:shadowcolor=black@0.75"
                f":x=(w-text_w)/2:y=(h*{SHORTS_TELOP_CENTER_Y}-text_h/2):enable={enable}[{out}]"
            )
            prev = out
            idx += 1

        output_file = out_dir / f"{episode_id}_shorts.mp4"
        run_cmd(
            [
                FFMPEG, "-y", "-i", str(video_with_audio),
                "-filter_complex", ";".join(filter_parts),
                "-map", f"[{prev}]", "-map", "0:a",
                "-c:v", "libx264", "-crf", "18", "-preset", "slow", "-c:a", "copy",
                str(output_file),
            ],
            f"テロップ焼き込み（{idx}枚）",
        )

    print(f"\n{'━'*60}\n  ✓ Shorts完成: {output_file}\n"
          f"  合計尺: {total_dur:.1f}s\n{'━'*60}")


def main():
    parser = argparse.ArgumentParser(description="くらしを変える科学 動画生成")
    parser.add_argument("--episode", required=True, help="エピソードID（例: kl001）")
    parser.add_argument("--out", help="出力先ディレクトリ（省略時: ~/Desktop/kagaku-life/output）")
    parser.add_argument("--shorts-only", action="store_true", help="Shorts動画のみ生成（本編はスキップ）")
    parser.add_argument("--no-shorts", action="store_true", help="Shorts動画を生成しない（本編のみ）")
    args = parser.parse_args()
    out_dir = Path(args.out).expanduser() if args.out else None
    if not args.shorts_only:
        gen_video(args.episode, out_dir)
    if not args.no_shorts:
        gen_shorts_video(args.episode, out_dir)


if __name__ == "__main__":
    main()
