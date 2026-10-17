"""
kl_cast_video.py — 二人（大輔=dreamer、沙織=skeptic）の立ち絵を「待機ループの動画」にする

2026-10-17（パイロット）。samurai-chronicles の語り手 Tokio（narrator/clips/*.webm）と同じ発想で、
静止画の立ち絵（assets/cast/{role}_{expr}.png）を、息づかい・まばたき程度に動く背景透過のループ動画
（assets/cast/video/{role}_{expr}.webm）に置き換える。合成は kl_dialogue.build_sprite_tracks と
kl_video_gen.py が行う（webm が無い表情は静止画のまま。混在してよい）。

流れ:
  1. gen  : 生画像（assets/cast/raw/{role}_{expr}.png、マゼンタ背景、896x1200）を 720x960 に縮めて
            Veo 3.1 fast（image-to-video、6秒、720p、9:16）に渡し、素の動画を
            assets/cast/raw/video/{role}_{expr}_veo.mp4 に保存する。**課金される**（目安: 6秒で約$0.9、
            12表情で約$11。料金は Google の価格表で確認すること）。既にある分はスキップ（--force で作り直し）。
  2. post : 素の動画から、ポーズが保たれている区間（既定は前半。下の analyze で自動選定）を切り出し、
            静止画と同じ方法（kl_cast_gen.key_out と同じしきい値・にじみ取り・アルファの整え方）で
            背景を抜き、静止画と同じ 672x900 に縮めて、往復（前進＋逆再生）ループの webm（VP9 alpha）を
            assets/cast/video/{role}_{expr}.webm に書く。区間とフレーム数は assets/cast/video/loops.json に記録。
  3. analyze : 各クリップの動きの量を測り、使う区間（start〜end 秒）を提案する（post もこれを使う）。
  4. sheet : 確認用のコンタクトシート（各表情の start／中間／end のフレームを静止画と並べる）を出す。

Veo の制約（2026-10-17 の試作で分かったこと。SC の narrator/tokio.json の veo_notes も参照）:
  - 6秒の後半でポーズが崩れる（頭をかく手・上げた手・立てた指などが下がって素の姿勢に戻る）。
    前半の約3秒はポーズが保たれるので、前半だけを往復ループにする
  - 冒頭0.5〜1秒で手が大きく動き出す表情がある（大輔 excited・surprised）。往復の折り返しが速い動きの
    途中に来ると跳ね返って見えるので、analyze は動きの小さい瞬間を折り返し点に選ぶ
  - 笑顔の指示は笑い出しやすい。音声は安全フィルタにかかるので「No sound」と書かず
    "Ambient audio: soft distant wind only." と書き、音声は -an で捨てる
  - 9:16 の出力には上下に黒帯が付く（3:4 の入力 → 720x1280 の中央 y=160〜1120 が絵）
  - despill（色のにじみ取り）を全体にかけると服に色が付く（SC の記録）。ここでは静止画と同じ式
    （赤と青が緑より突出した分だけ削る）を使い、静止画と見た目をそろえる

使い方:
  python3 kl_cast_video.py gen --dry-run                    # 生成する予定の表情と費用の目安だけ表示
  python3 kl_cast_video.py gen                              # 未生成の表情だけ Veo で生成（課金）
  python3 kl_cast_video.py gen --role skeptic --expr amused --force   # 1本だけ作り直す（課金）
  python3 kl_cast_video.py analyze                          # 動きの量と、使う区間の提案
  python3 kl_cast_video.py post                             # 全表情のループ webm を作る（既存はスキップ）
  python3 kl_cast_video.py post --role dreamer --expr excited --force --start 0.9 --end 3.4
  python3 kl_cast_video.py sheet --out ~/Desktop/kl_cast_video_proto/sheet.png

口パク（話しているループ、2026-10-17）: どのサブコマンドも --kind talk で「話している間」のループを扱う。
  素の動画 assets/cast/raw/video/{role}_{expr}_talk.mp4 → assets/cast/video/{role}_{expr}_talk.webm
  （loops.json のキーは {role}_{expr}_talk）。kl_dialogue.build_sprite_tracks が台詞を話している間だけ使う。
  python3 kl_cast_video.py gen --kind talk --dry-run
  python3 kl_cast_video.py analyze --kind talk --verbose      # 口のあたりの動き（MOUTH_BOX）も表示
  python3 kl_cast_video.py post --kind talk
  python3 kl_cast_video.py sheet --kind talk --cols 8         # 手が下がる・記号・目閉じが無いか必ず目で確認する

APIキーは環境変数 GEMINI_API_KEY_KL（無ければ GEMINI_API_KEY）。
口パク（音声の大きさで口を切り替える）は未実装（kl_dialogue.build_sprite_tracks の docstring 参照）。
"""

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

sys.stdout.reconfigure(line_buffering=True)

BASE_DIR = Path(__file__).parent
CAST_JSON = BASE_DIR / "cast.json"
CAST_DIR = BASE_DIR / "assets" / "cast"
RAW_DIR = CAST_DIR / "raw"
RAW_VIDEO_DIR = RAW_DIR / "video"
VIDEO_DIR = CAST_DIR / "video"
LOOPS_JSON = VIDEO_DIR / "loops.json"

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FPS = 24

VEO_MODEL = "veo-3.1-fast-generate-preview"
VEO_SECONDS = 6
VEO_USD_PER_SEC = 0.15  # 目安（2026-10 時点の Veo 3.1 Fast）。実際の料金は価格表で確認
VEO_IN_W, VEO_IN_H = 720, 960       # Veo に渡す 3:4 のキャンバス
# 9:16 出力（720x1280）の中の絵の範囲 (w, h, x, y)。生画像 896x1200 を 720x960 に収めると 716x960 で
# 左右に2pxずつマゼンタの余白が付き、Veo はそれを上下の黒帯つきで 720x1280 の y=160〜1120 に置く。
# 静止画（896x1200 → 672x900）と位置をそろえるため、余白を除いた 716x960 を切り出す
CROP = (716, 960, 2, 160)

# 静止画（kl_cast_gen.py）と同じ大きさ・切り抜きのしきい値
SPRITE_H = 900
KEY_LO, KEY_HI = 90.0, 175.0

# 区間の自動選定（analyze）
WIN_MIN, WIN_MAX = 1.5, 3.6         # ループに使う区間の長さ（秒）
START_MAX = 1.5                     # 区間の開始はこの秒まで
END_MAX = 4.0                       # 区間の終わりはこの秒まで（これ以降はポーズが崩れやすい）
DEFAULT_WINDOW = (0.0, 3.2)
DRIFT_MAX = 8.0                     # 区間内で、開始フレームからのシルエットの変化がこの%を超えたら不可

WHO = {"dreamer": "a young Japanese man", "skeptic": "a Japanese woman with glasses"}


def load_cast() -> dict:
    return json.loads(CAST_JSON.read_text(encoding="utf-8"))


def all_jobs(cast: dict, role: str = None, expr: str = None) -> list:
    out = []
    for r in ("dreamer", "skeptic"):
        if role and r != role:
            continue
        for e in cast[r]["expressions"]:
            if expr and e != expr:
                continue
            out.append((r, e))
    return out


KINDS = ("idle", "talk")
PRONOUN = {"dreamer": "He", "skeptic": "She"}


def raw_video_path(role: str, expr: str, kind: str = "idle") -> Path:
    """素の動画。待機（idle）は {role}_{expr}_veo.mp4、話している（talk）は {role}_{expr}_talk.mp4"""
    return RAW_VIDEO_DIR / (f"{role}_{expr}_veo.mp4" if kind == "idle" else f"{role}_{expr}_talk.mp4")


def loop_key(role: str, expr: str, kind: str = "idle") -> str:
    return f"{role}_{expr}" if kind == "idle" else f"{role}_{expr}_talk"


def loop_path(role: str, expr: str, kind: str = "idle") -> Path:
    return VIDEO_DIR / f"{loop_key(role, expr, kind)}.webm"


def load_loops() -> dict:
    try:
        return json.loads(LOOPS_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ── gen: Veo で素の動画を作る ─────────────────────────────────────────

def veo_prompt(cast: dict, role: str, expr: str, kind: str = "idle") -> str:
    desc = cast[role]["expressions"][expr]
    if kind == "talk":
        # 2026-10-17: 話している間だけ使うループ（口パク）。大輔 neutral の試作で、口の開閉が自然で画風も保たれた
        # プロンプトに、表情・手のポーズを保つ指示と、待機ループで出た不具合（記号の描き込み・笑い出す・手が下がる）の禁止を足した
        pr = PRONOUN[role]
        return (
            f"A 2D flat-colour anime-style illustration of {WHO[role]}, waist-up, on a solid magenta (#FF00FF) background. "
            f"The pose and expression: {desc}. "
            f"{pr} is TALKING in a relaxed, friendly conversational way throughout the whole clip: the mouth opens and "
            "closes naturally in clear speech movements, with small natural nods and slight head movement, a natural "
            "blink once or twice, gentle breathing. "
            "Keep this exact facial expression and this exact pose for the whole clip: no big smile, does NOT laugh, "
            "does NOT change expression, does not keep the eyes closed (unless the expression above says so), and the "
            "arms and hands stay exactly where they are — do not lower them or move them away. "
            "Do NOT draw any symbols, question marks, exclamation marks, text, speech bubbles, sparkles or effect lines. "
            "The camera is fixed, no zoom, no pan. The background stays solid magenta. "
            "Keep the exact art style and line quality of the input image. Ambient audio: soft distant wind only."
        )
    return (
        f"A 2D flat-colour anime-style illustration of {WHO[role]}, waist-up, on a solid magenta (#FF00FF) background. "
        f"The pose and expression: {desc}. "
        "Subtle idle loop: the character HOLDS this exact pose and expression. Only gentle breathing (shoulders rise "
        "and fall slightly) and a natural slow blink once or twice, plus a very slight head movement. The character "
        "does NOT speak, does NOT laugh out loud, does NOT change expression, and does not lower or move the arms and "
        "hands away from their position. The camera is fixed, no zoom, no pan. The background stays solid magenta. "
        "Keep the exact art style and line quality of the input image. Ambient audio: soft distant wind only."
    )


def veo_input_png(role: str, expr: str) -> bytes:
    im = Image.open(RAW_DIR / f"{role}_{expr}.png").convert("RGB")
    bg = Image.new("RGB", (VEO_IN_W, VEO_IN_H), (255, 0, 255))
    r = min(VEO_IN_W / im.width, VEO_IN_H / im.height)
    sz = (int(im.width * r), int(im.height * r))
    bg.paste(im.resize(sz, Image.LANCZOS), ((VEO_IN_W - sz[0]) // 2, VEO_IN_H - sz[1]))
    buf = io.BytesIO()
    bg.save(buf, "PNG")
    return buf.getvalue()


def cmd_gen(args):
    cast = load_cast()
    kind = args.kind
    jobs = all_jobs(cast, args.role, args.expr)
    todo = [(r, e) for r, e in jobs if args.force or not raw_video_path(r, e, kind).exists()]
    skip = [(r, e) for r, e in jobs if (r, e) not in todo]
    for r, e in skip:
        print(f"  スキップ（生成済み）: {raw_video_path(r, e, kind).name}")
    cost = len(todo) * VEO_SECONDS * VEO_USD_PER_SEC
    print(f"  [{kind}] 生成予定: {len(todo)}本（{', '.join(f'{r}_{e}' for r, e in todo) or 'なし'}）"
          f" — 費用の目安 約${cost:.1f}（{VEO_SECONDS}秒 × ${VEO_USD_PER_SEC}/秒）")
    if args.dry_run or not todo:
        return
    api_key = os.environ.get("GEMINI_API_KEY_KL") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("❌ 環境変数 GEMINI_API_KEY_KL がありません")
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=api_key)
    RAW_VIDEO_DIR.mkdir(parents=True, exist_ok=True)

    def one(job):
        role, expr = job
        out = raw_video_path(role, expr, kind)
        err = ""
        for _ in range(2):  # APIエラー（動画が返らない）のときだけ1回取り直す
            try:
                op = client.models.generate_videos(
                    model=VEO_MODEL, prompt=veo_prompt(cast, role, expr, kind),
                    image=types.Image(image_bytes=veo_input_png(role, expr), mime_type="image/png"),
                    config=types.GenerateVideosConfig(aspect_ratio="9:16", duration_seconds=VEO_SECONDS,
                                                      number_of_videos=1, resolution="720p"))
                while not op.done:
                    time.sleep(10)
                    op = client.operations.get(op)
                if getattr(op, "error", None):
                    raise RuntimeError(str(op.error))
                vid = op.response.generated_videos[0].video
                client.files.download(file=vid)
                vid.save(str(out))
                return role, expr, "✅"
            except Exception as e:  # 1回だけ取り直す
                err = str(e)[:200]
        return role, expr, "❌ " + err

    with ThreadPoolExecutor(4) as ex:
        for role, expr, st in ex.map(one, todo):
            print(f"  {st} {role}_{expr}")
    print("  次: python3 kl_cast_video.py post（背景抜き・ループ化）")


# ── 素の動画の読み込み・動きの測定 ───────────────────────────────────

def read_frames(path: Path, w: int = None, h: int = None) -> np.ndarray:
    """素の動画を絵の範囲（CROP）だけ RGB の配列 (n, h, w, 3) で読む。w/h を渡すと縮小する。"""
    cw, ch, cx, cy = CROP
    vf = f"crop={cw}:{ch}:{cx}:{cy}"
    if w:
        vf += f",scale={w}:{h}"
    else:
        w, h = cw, ch
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", str(path), "-vf", vf, "-an",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3)


# 口のあたりの範囲（180x240 に縮めた絵の中の座標 (x0, y0, x1, y1)）。二人とも全表情で頭の位置はほぼ同じ
# （kl_cast_gen.py が同じ構図で差分を作っているため）。頭の傾き・うなずきでずれても入るよう広めに取る
MOUTH_BOX = {"dreamer": (90, 82, 128, 108), "skeptic": (58, 74, 96, 100)}
# 話しているループで、口のあたりの動き（隣のフレームとの差の平均）がこれ未満なら「口があまり動いていない」と警告
TALK_MOUTH_MIN = 2.0


def mouth_activity(fr: np.ndarray, role: str) -> np.ndarray:
    """口のあたりの、隣のフレームとの差（フレームごと）。fr は 180x240 に縮めた (n, h, w, 3)。"""
    x0, y0, x1, y1 = MOUTH_BOX[role]
    m = fr[:, y0:y1, x0:x1].astype(np.float32)
    out = np.zeros(len(fr))
    out[1:] = np.abs(m[1:] - m[:-1]).mean(axis=(1, 2, 3))
    out[0] = out[1]
    return out


def analyze_clip(path: Path, role: str = None, kind: str = "idle") -> dict:
    """動きの量（隣のフレームとの差）とシルエットの変化を測り、往復ループに使う区間を選ぶ。
    折り返し点（区間の始まりと終わり）は動きの小さい瞬間にし、区間内でポーズが崩れない（シルエットの
    変化が DRIFT_MAX% 以下）ものの中で、長く・早く始まるものを選ぶ。
    kind="talk" では、口のあたりの動き（mouth_activity）が大きい区間を加点し、その平均も返す。"""
    fr = read_frames(path, 180, 240).astype(np.float32)
    n = len(fr)
    motion = np.zeros(n)
    motion[1:] = np.abs(fr[1:] - fr[:-1]).mean(axis=(1, 2, 3))
    motion[0] = motion[1]
    k = np.ones(5) / 5
    sm = np.convolve(np.pad(motion, 2, mode="edge"), k, mode="valid")
    mask = np.sqrt(((fr - np.array([255, 40, 250])) ** 2).sum(-1)) > 130
    mouth = mouth_activity(fr, role) if role else np.zeros(n)
    best = None
    for s in range(0, min(n, int(START_MAX * FPS) + 1)):
        for e in range(s + int(WIN_MIN * FPS), min(n - 1, s + int(WIN_MAX * FPS), int(END_MAX * FPS)) + 1):
            drift = max((mask[i] ^ mask[s]).mean() * 100 for i in range(s, e + 1, 3))
            if drift > DRIFT_MAX:
                break  # これより長い区間はさらに崩れる
            score = (e - s) / FPS - 1.5 * (sm[s] + sm[e]) - 0.4 * s / FPS
            if kind == "talk":
                # 話しているループは口の動きが主役なので、折り返しの動きは軽めに見て、口がよく動く区間を選ぶ
                score = (e - s) / FPS - 0.5 * (sm[s] + sm[e]) - 0.4 * s / FPS + 0.3 * float(mouth[s:e + 1].mean())
            if best is None or score > best[0]:
                best = (score, s, e, drift)
    if best is None:
        s, e, drift = int(DEFAULT_WINDOW[0] * FPS), int(DEFAULT_WINDOW[1] * FPS), None
    else:
        _, s, e, drift = best
    return {"start": round(s / FPS, 3), "end": round(e / FPS, 3), "turn_motion": [round(float(sm[s]), 2), round(float(sm[e]), 2)],
            "drift_pct": None if drift is None else round(float(drift), 1),
            "mouth_activity": round(float(mouth[s:e + 1].mean()), 2),
            "profile": [round(float(x), 1) for x in sm[::3]],
            "mouth_profile": [round(float(x), 1) for x in mouth[::3]]}


def cmd_analyze(args):
    cast = load_cast()
    for role, expr in all_jobs(cast, args.role, args.expr):
        p = raw_video_path(role, expr, args.kind)
        if not p.exists():
            print(f"  {loop_key(role, expr, args.kind)}: 素の動画がありません")
            continue
        a = analyze_clip(p, role, args.kind)
        warn = "  ⚠️ 口があまり動いていない" if args.kind == "talk" and a["mouth_activity"] < TALK_MOUTH_MIN else ""
        print(f"  {loop_key(role, expr, args.kind):24s} 区間 {a['start']:.2f}〜{a['end']:.2f}秒  折り返しの動き {a['turn_motion']}"
              f"  シルエット変化 {a['drift_pct']}%  口の動き {a['mouth_activity']}{warn}")
        if args.verbose:
            print("     動き(0.125秒ごと):   " + " ".join(f"{x:4.1f}" for x in a["profile"]))
            print("     口の動き(0.125秒ごと): " + " ".join(f"{x:4.1f}" for x in a["mouth_profile"]))


# ── post: 背景抜き・往復ループ化 ─────────────────────────────────────

def key_frame(rgb: np.ndarray, bg) -> Image.Image:
    """kl_cast_gen.key_out と同じ式でマゼンタを抜いた RGBA（元の大きさ）を返す。
    透明な画素の色は近くの絵の色で埋める（縮小・VP9 の色の間引きで縁に暗い色やピンクが混ざらないように）。"""
    f = rgb.astype(np.float32)
    d = np.sqrt(((f - np.asarray(bg, np.float32)) ** 2).sum(-1))
    a = np.clip((d - KEY_LO) / (KEY_HI - KEY_LO), 0, 1) * 255
    a = np.where(d <= KEY_LO, 0, np.where(d >= KEY_HI, 255, a.astype(np.int32))).astype(np.uint8)
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    spill = np.minimum(r, b) - g
    k = np.where(a < 255, 0.9, 0.5)
    cut = np.where(spill > 0, np.floor(spill * k), 0)
    r2, b2 = r - cut, b - cut
    out_rgb = np.stack([r2, g, b2], -1)
    alpha = Image.fromarray(a)
    ac = alpha.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))
    ac = ac.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.7))
    an = np.asarray(ac, np.float32) / 255.0
    # 透明部分の色を、近くの絵の色（アルファで重みをつけてぼかした色）で埋める
    pm = Image.fromarray(np.clip(out_rgb * an[..., None], 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(6))
    ab = np.asarray(Image.fromarray((an * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(6)), np.float32) / 255.0
    fill = np.asarray(pm, np.float32) / np.maximum(ab, 1e-3)[..., None]
    final = np.where(an[..., None] > 0.02, out_rgb, fill)
    rgba = np.dstack([np.clip(final, 0, 255).astype(np.uint8), np.asarray(ac)])
    return Image.fromarray(rgba)


def build_loop(role: str, expr: str, start: float, end: float, out: Path, kind: str = "idle") -> dict:
    src = raw_video_path(role, expr, kind)
    fr = read_frames(src)
    h, w = fr.shape[1:3]
    first = fr[0]
    border = np.concatenate([first[0, ::7], first[::7, 0], first[::7, w - 1]])
    bg = tuple(int(x) for x in np.median(border, axis=0))
    s, e = int(round(start * FPS)), min(len(fr) - 1, int(round(end * FPS)))
    idx = list(range(s, e + 1)) + list(range(e - 1, s, -1))  # 往復（前進＋逆再生、端のフレームは重ねない）
    keyed = {}
    st_png = CAST_DIR / f"{role}_{expr}.png"
    # 静止画と同じ大きさ（672x900）にそろえる（716x960 からだと 671.25 になるため、静止画の幅を使う）
    sw = Image.open(st_png).width if st_png.exists() else int(w * SPRITE_H / h)
    for i in sorted(set(idx)):
        keyed[i] = key_frame(fr[i], bg).resize((sw, SPRITE_H), Image.LANCZOS)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{sw}x{SPRITE_H}",
           "-r", str(FPS), "-i", "-", "-an", "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
           "-b:v", "0", "-crf", "24", "-auto-alt-ref", "0", "-row-mt", "1", str(out)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in idx:
        p.stdin.write(keyed[i].tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError(f"webm の書き出しに失敗: {out}")
    # 静止画との位置合わせの確認（1フレーム目のシルエットと静止画のシルエットの重なり）
    iou = None
    st = CAST_DIR / f"{role}_{expr}.png"
    if st.exists():
        sa = np.asarray(Image.open(st).convert("RGBA").getchannel("A")) > 128
        va = np.asarray(keyed[s].getchannel("A")) > 128
        if sa.shape == va.shape:
            iou = round(float((sa & va).sum() / max(1, (sa | va).sum())), 3)
    small = np.stack([np.asarray(Image.fromarray(fr[i]).resize((180, 240), Image.BILINEAR)) for i in range(s, e + 1)])
    return {"kind": kind, "start": round(s / FPS, 3), "end": round(e / FPS, 3), "frames": len(idx),
            "seconds": round(len(idx) / FPS, 3), "size": [sw, SPRITE_H], "bg": list(bg),
            "iou_vs_static_first_frame": iou,
            "mouth_activity": round(float(mouth_activity(small, role)[1:].mean()), 2),
            "source": src.name}


def cmd_post(args):
    cast = load_cast()
    loops = load_loops()
    kind = args.kind
    for role, expr in all_jobs(cast, args.role, args.expr):
        key = loop_key(role, expr, kind)
        src = raw_video_path(role, expr, kind)
        out = loop_path(role, expr, kind)
        if not src.exists():
            print(f"  {key}: 素の動画がありません（gen を先に）")
            continue
        if out.exists() and not args.force:
            print(f"  スキップ（作成済み）: {out.relative_to(BASE_DIR)}")
            continue
        if args.start is not None and args.end is not None:
            start, end, how = args.start, args.end, "指定"
        elif key in loops and loops[key].get("manual"):
            start, end, how = loops[key]["start"], loops[key]["end"], "loops.json の手動指定"
        else:
            a = analyze_clip(src, role, kind)
            start, end, how = a["start"], a["end"], "自動選定"
        info = build_loop(role, expr, start, end, out, kind)
        if how != "自動選定":
            info["manual"] = True
        loops[key] = info
        print(f"  ✅ {key}: {info['start']:.2f}〜{info['end']:.2f}秒（{how}）→ 往復 {info['seconds']:.2f}秒"
              f" / 静止画との重なり {info['iou_vs_static_first_frame']} / 口の動き {info['mouth_activity']}")
        LOOPS_JSON.write_text(json.dumps(loops, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ── sheet: 確認用のコンタクトシート ───────────────────────────────────

def decode_webm_frames(path: Path, times: list) -> list:
    """VP9 alpha の webm から指定秒のフレームを RGBA で取り出す（libvpx-vp9 デコーダでないとアルファが落ちる）。"""
    out = []
    for t in times:
        raw = subprocess.run([FFMPEG, "-v", "error", "-c:v", "libvpx-vp9", "-ss", f"{t:.3f}", "-i", str(path),
                              "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"],
                             capture_output=True, check=True).stdout
        out.append(Image.open(io.BytesIO(raw)).convert("RGBA"))
    return out


def cmd_sheet(args):
    cast = load_cast()
    loops = load_loops()
    kind = args.kind
    jobs = [j for j in all_jobs(cast, args.role, args.expr) if loop_path(*j, kind).exists()]
    if not jobs:
        sys.exit("ループの webm がありません（post を先に）")
    th = 300
    cell_w = int(672 * th / 900)
    n_cols = args.cols  # 静止画 + ループの前進側を等間隔に
    sheet = Image.new("RGB", (cell_w * (n_cols + 1), th * len(jobs)), (40, 60, 80))
    for row, (role, expr) in enumerate(jobs):
        n = loops.get(loop_key(role, expr, kind), {}).get("seconds", 6.0)
        ims = [Image.open(CAST_DIR / f"{role}_{expr}.png").convert("RGBA")]
        ims += decode_webm_frames(loop_path(role, expr, kind), [(n / 2 - 0.05) * i / max(1, n_cols - 1) for i in range(n_cols)])
        for c, im in enumerate(ims):
            im = im.resize((cell_w, th), Image.LANCZOS)
            cell = Image.new("RGBA", (cell_w, th), (60, 90, 110, 255))
            cell.alpha_composite(im)
            sheet.paste(cell.convert("RGB"), (c * cell_w, row * th))
    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    print(f"  シート: {out}（列: 静止画／ループの前進側を始まりから折り返しまで等間隔に{n_cols}枚）")


def main():
    ap = argparse.ArgumentParser(description="二人の立ち絵の待機ループ動画（Veo）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("gen", "analyze", "post", "sheet"):
        p = sub.add_parser(name)
        p.add_argument("--role", choices=["dreamer", "skeptic"])
        p.add_argument("--expr")
        if name in ("gen", "post"):
            p.add_argument("--force", action="store_true", help="既存を作り直す")
        if name == "gen":
            p.add_argument("--dry-run", action="store_true", help="生成せず、予定と費用の目安だけ表示")
        p.add_argument("--kind", choices=KINDS, default="idle",
                       help="idle: 待機ループ（既定）／ talk: 話している間のループ（口パク）")
        if name == "post":
            p.add_argument("--start", type=float, help="使う区間の始まり（秒）。--end と一緒に指定すると自動選定より優先")
            p.add_argument("--end", type=float)
        if name == "analyze":
            p.add_argument("--verbose", action="store_true")
        if name == "sheet":
            p.add_argument("--out", default=str(Path.home() / "Desktop" / "kl_cast_video_proto" / "cast_loop_sheet.png"))
            p.add_argument("--cols", type=int, default=6, help="ループから取り出す枚数")
    args = ap.parse_args()
    {"gen": cmd_gen, "analyze": cmd_analyze, "post": cmd_post, "sheet": cmd_sheet}[args.cmd](args)


if __name__ == "__main__":
    main()
