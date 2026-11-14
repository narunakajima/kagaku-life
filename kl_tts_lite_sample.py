"""Flash-Lite TTS の試聴サンプル生成（削減プラン項目M、2026-11-14）。

指定エピソード・シーンの先頭 N 行を、現行モデル（gemini-3.8-flash-tts）と
Lite（gemini-3.8-flash-lite-tts）で同じ台詞・同じ声・同じ演技指導で読み上げ、
2本の WAV にして出力する。episodes/*.json は読むだけで書き換えない。
QA・読み照合は行わない（モデルの素の出来を聞き比べるため）。

使い方: python3 kl_tts_lite_sample.py --episode kl056 --scene 5 --lines 4
出力: ~/Desktop/kagaku-life/tts_lite_sample/{episode}_S{NN}_current.wav / _lite.wav
"""
import argparse
import json
import sys
import time
from pathlib import Path

import kl_dialogue as D
import kl_tts_gen as T

OUT_ROOT = T.DESKTOP_DIR / "tts_lite_sample"
DRIVE_DIR = (Path.home() / "Library/CloudStorage/GoogleDrive-naru.nakajima@gmail.com/マイドライブ"
             / "Kagaku-Life" / "検討用_TTS試聴")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episode", required=True)
    ap.add_argument("--scene", type=int, required=True)
    ap.add_argument("--lines", type=int, default=4, help="シーン先頭から何行使うか")
    ap.add_argument("--drive", action="store_true", help="生成した WAV を Drive の Kagaku-Life/検討用_TTS試聴 にもコピーする")
    args = ap.parse_args()
    if not T.API_KEY:
        sys.exit("❌ GEMINI_API_KEY が設定されていません")

    ep = json.loads((T.BASE_DIR / "episodes" / f"{args.episode}.json").read_text())
    scene = next(s for s in ep["scenes"] if s["scene_id"] == args.scene)
    lines = scene["lines"][: args.lines]
    cast = D.load_cast()
    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    for label, model in (("current", T.TTS_MODELS["flash"]), ("lite", T.TTS_MODELS["lite"])):
        wavs = []
        for k, line in enumerate(lines, start=1):
            c = cast[line["speaker"]]
            style = c["style"] + (f". For this line specifically: {line['tone']}" if line.get("tone") else "")
            data = None
            for attempt in range(1, T.MAX_RETRIES + 1):
                try:
                    data = T._tts_rest_call(line["text"], style, c["voice"], model=model)
                    break
                except Exception as e:
                    print(f"  ⚠️ {label} L{k}: {type(e).__name__}: {e}（{attempt}回目）")
                    time.sleep(2)
            if data is None:
                sys.exit(f"❌ {label} L{k} 生成失敗")
            p = OUT_ROOT / f"_{label}_L{k:02d}.wav"
            p.write_bytes(T._to_wav_bytes(data))
            wavs.append(p)
            print(f"✅ {label} L{k} {line['speaker']} voice={c['voice']} model={model}")
        out = OUT_ROOT / f"{args.episode}_S{args.scene:02d}_L01-{len(lines):02d}_{label}_{model}.wav"
        timings = D.concat_line_wavs(wavs, lines, out)
        print(f"   → {out.name}（{timings[-1][0] + timings[-1][1]:.1f}秒）")
        for p in wavs:
            p.unlink()
        if args.drive:
            import shutil
            DRIVE_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(out, DRIVE_DIR / out.name)
            same = (DRIVE_DIR / out.name).stat().st_size == out.stat().st_size
            print(f"   → Drive: {DRIVE_DIR / out.name}（サイズ一致={same}）")


if __name__ == "__main__":
    main()
