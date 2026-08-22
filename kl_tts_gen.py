"""
kl_tts_gen.py — くらしを変える科学 ナレーション音声生成スクリプト

episodes/kl{NNN}.json の各シーンのnarration文を、scene.narrator（persona/research）
に応じて narration_voices（エピソードごとに選定済みのボイス名）で読み分け、
gemini-3.1-flash-tts-previewで音声を生成する（CLAUDE.md「ストーリー構成と
2ナレーターボイス制」参照）。

narration_voicesが未設定のエピソードは、先にボイス選定（聴き比べ）を行ってから
episodes/kl{NNN}.jsonに記録すること。

使い方:
  python3 kl_tts_gen.py --episode kl001                 # 全シーン+Shorts生成
  python3 kl_tts_gen.py --episode kl001 --scenes 5,6,9   # 指定シーンのみ再生成
  python3 kl_tts_gen.py --episode kl001 --shorts-only    # Shortsのみ

出力: ~/Desktop/kagaku-life/{episode}/narration/S{NN}.wav,
      shorts{M}_S{NN}.wav
"""

import argparse
import json
import os
import sys
import time
import wave
from pathlib import Path

from google import genai
from google.genai import types

sys.stdout.reconfigure(line_buffering=True)

BASE_DIR = Path(__file__).parent
DESKTOP_DIR = Path.home() / "Desktop" / "kagaku-life"

API_KEY = os.environ.get("GEMINI_API_KEY", "")
# gemini-3.1-flash-tts-preview はテキスト先頭に演技指導（スタイル指示）を付けると
# finish_reason=OTHER で空データが返る不具合がある（lamp-whisperのlw_tts_gen.pyで
# 発覚・対処済み）。gemini-2.5-pro-preview-ttsに切り替える（2026-08-21）。
# 2026-08-22追記: gemini-2.5-pro-preview-ttsでも演技指導の有無に関わらず
# finish_reason=OTHERで空データが返ることが稀にある（一過性の不具合で、
# 演技指導固有の問題ではない）。lw_tts_gen.pyと同じくリトライで対処する。
MODEL = "gemini-2.5-pro-preview-tts"
REQUEST_TIMEOUT_MS = 60_000
MAX_RETRIES = 5

# 研究ボイス（Orus）は稀に音程が高く裏返ることがあり、また短いフレーズ
# （Shorts等）では雰囲気が暗く/硬く聞こえがちなため、落ち着いた低めの音程を
# 保ちつつ、チャンネルの温かいトーンに合う明るさを明示的に指示する。
STYLE_PREFIX = {
    "research": (
        "Say in an energetic, warm, upbeat documentary-narrator voice, at a "
        "brisk and lively speaking pace — enthusiastic and engaging, never "
        "flat, cold, heavy, or somber. Keep a stable, moderate-to-low pitch "
        "and do not let it rise or break upward at any point: "
    ),
}


def synth(client: genai.Client, text: str, voice_name: str, out_path: Path, narrator: str = None) -> bool:
    prefix = STYLE_PREFIX.get(narrator, "")
    prompt = f"{prefix}{text}" if prefix else text
    config = types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
            )
        ),
    )
    data = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = client.models.generate_content(model=MODEL, contents=prompt, config=config)
            candidate = resp.candidates[0] if resp.candidates else None
            parts = candidate.content.parts if (candidate and candidate.content) else None
            if parts:
                data = parts[0].inline_data.data
                break
            reason = f"空データ（finish_reason={getattr(candidate, 'finish_reason', '?')}）"
        except Exception as e:
            reason = f"{type(e).__name__}: {e}"
        if attempt < MAX_RETRIES:
            print(f"  ⚠️ {out_path.name}: {reason}（{attempt}回目）、リトライ")
            time.sleep(2)
    if data is None:
        print(f"❌ {out_path.name}: {MAX_RETRIES}回試行して失敗", file=sys.stderr)
        return False
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(data)
    print(f"✅ {out_path.name} ({voice_name})")
    return True


def main():
    parser = argparse.ArgumentParser(description="くらしを変える科学 ナレーション音声生成")
    parser.add_argument("--episode", required=True, help="エピソードID（例: kl001）")
    parser.add_argument("--scenes", help="生成するscene_idをカンマ区切りで指定（省略時は全シーン）")
    parser.add_argument("--shorts-only", action="store_true", help="Shortsのみ生成")
    args = parser.parse_args()

    if not API_KEY:
        print("❌ GEMINI_API_KEY が設定されていません", file=sys.stderr)
        sys.exit(1)

    ep_path = BASE_DIR / "episodes" / f"{args.episode}.json"
    if not ep_path.exists():
        print(f"❌ {ep_path} がありません", file=sys.stderr)
        sys.exit(1)
    ep = json.loads(ep_path.read_text())

    voices = ep.get("narration_voices")
    if not voices or "persona" not in voices or "research" not in voices:
        print(
            "❌ narration_voicesが未設定です。先にボイスを選定し、"
            f'episodes/{args.episode}.json に "narration_voices": '
            '{"persona": "...", "research": "..."} を記録してください。',
            file=sys.stderr,
        )
        sys.exit(1)

    out_dir = DESKTOP_DIR / args.episode / "narration"
    out_dir.mkdir(parents=True, exist_ok=True)

    client = genai.Client(api_key=API_KEY, http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))

    target_ids = None
    if args.scenes:
        target_ids = {int(s) for s in args.scenes.split(",")}

    if not args.shorts_only:
        for scene in ep["scenes"]:
            sid = scene["scene_id"]
            if target_ids is not None and sid not in target_ids:
                continue
            narrator = scene["narrator"]
            voice_name = voices[narrator]
            out_path = out_dir / f"S{sid:02d}.wav"
            synth(client, scene["narration"], voice_name, out_path, narrator=narrator)

    if args.shorts_only or args.scenes is None:
        for shorts in ep.get("shorts", []):
            mid = shorts["shorts_id"]
            for i, s in enumerate(shorts["scenes"], start=1):
                voice_name = voices[s["narrator"]]
                out_path = out_dir / f"shorts{mid}_S{i:02d}.wav"
                synth(client, s["narration"], voice_name, out_path, narrator=s["narrator"])

    print(f"\n完了。保存先: {out_dir}")


if __name__ == "__main__":
    main()
