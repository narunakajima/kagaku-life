"""
kl_tts_gen.py — くらしを変える科学 ナレーション音声生成スクリプト

episodes/kl{NNN}.json の各シーンのnarration文を、scene.narrator（persona/research）
に応じて narration_voices（エピソードごとに選定済みのボイス名）で読み分け、
gemini-2.5-pro-preview-ttsで音声を生成する（CLAUDE.md「ストーリー構成と
2ナレーターボイス制」参照）。

narration_voicesが未設定のエピソードは、先にボイス選定（聴き比べ）を行ってから
episodes/kl{NNN}.jsonに記録すること。

使い方:
  python3 kl_tts_gen.py --episode kl001                 # 全シーン+Shorts生成
  python3 kl_tts_gen.py --episode kl001 --scenes 5,6,9   # 指定シーンのみ再生成
  python3 kl_tts_gen.py --episode kl001 --shorts-only    # Shortsのみ

出力: ~/Desktop/kagaku-life/narration/S{NN}.wav,
      shorts{M}_S{NN}.wav
      （Desktopは常に最新1エピソード分の確認用。エピソードIDのサブフォルダは作らない）
"""

import argparse
import io
import json
import os
import re
import shutil
import sys
import time
import wave
from pathlib import Path

from google import genai
from google.genai import types

sys.stdout.reconfigure(line_buffering=True)

BASE_DIR = Path(__file__).parent
DESKTOP_DIR = Path.home() / "Desktop" / "kagaku-life"

API_KEY = os.environ.get("GEMINI_API_KEY_KL") or os.environ.get("GEMINI_API_KEY", "")
QA_MODEL = "gemini-flash-latest"  # ナレーション音声が台本通りか判定する用（sc_tts_gen.pyと同じ考え方）
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
# personaは主人公ごとに毎回声・年齢・性格が変わるため、STYLE_PREFIXのような
# 固定辞書ではなく episodes/kl{NNN}.json の narration_voices.persona_style
# （任意フィールド）にエピソードごとの演技指導を記録し、synth()のstyle_overrideで
# 上書きする方式にする（2026-08-25追加、kl004で高齢者演技指導が必要になったため）。


def _to_wav_bytes(pcm_data: bytes, sample_rate: int = 24000) -> bytes:
    """PCM バイト列を QA 用に WAV バイト列へ変換する。"""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)
    return buf.getvalue()


def qa_narration_with_gemini(client: genai.Client, audio_data: bytes, script_text: str) -> dict:
    """生成されたナレーション音声が台本通りに発話されているかをGeminiに判定させる。
    samurai-chroniclesのsc_tts_gen.pyと同じ考え方（2026-09-04導入）。"""
    try:
        wav_bytes = _to_wav_bytes(audio_data)
        qa_prompt = (
            "Listen to this narration audio and compare it against the intended script below.\n\n"
            "Check for these issues:\n"
            "- SKIPPED: one or more sentences or phrases from the script are missing from the audio\n"
            "- ALTERED: the spoken words deviate significantly from the script — not just natural "
            "reading variation (pauses, emphasis), but substituted, garbled, or materially different wording\n"
            "- REPEATED: any part of the script is spoken more than once\n"
            "- CUTOFF: the audio ends abruptly mid-sentence or mid-word instead of completing the script\n\n"
            f"Script:\n{script_text}\n\n"
            "Respond with ONLY a JSON object, no other text, in this exact format:\n"
            '{"ok": true, "issues": []}\n'
            "or\n"
            '{"ok": false, "issues": ["ISSUE_TYPE: brief description", ...]}'
        )
        response = client.models.generate_content(
            model=QA_MODEL,
            contents=[
                qa_prompt,
                types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"),
            ],
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=0)
            ),
        )
        text_resp = response.text.strip()
        if text_resp.startswith("```"):
            text_resp = re.sub(r"^```(?:json)?\s*", "", text_resp)
            text_resp = re.sub(r"\s*```$", "", text_resp)
        result = json.loads(text_resp)
        return {"ok": bool(result.get("ok", True)), "issues": result.get("issues", [])}
    except Exception as e:
        # QA自体が失敗した場合はサイレントにOK扱いせず、issueとして扱い
        # 既存のリトライ機構に乗せる（API障害等を「問題なし」と誤認しないため）。
        return {"ok": False, "issues": [f"QA_ERROR: {e}"]}


def synth(client: genai.Client, text: str, voice_name: str, out_path: Path, narrator: str = None, style_override: str = None) -> bool:
    prefix = style_override if style_override is not None else STYLE_PREFIX.get(narrator, "")
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
                candidate_data = parts[0].inline_data.data
                qa = qa_narration_with_gemini(client, candidate_data, text)
                if qa["ok"]:
                    data = candidate_data
                    break
                reason = f"台本不一致の疑い（{'; '.join(qa['issues'])}）"
            else:
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
    parser.add_argument("--shorts-scenes", help="Shorts内の生成する番号をカンマ区切りで指定（例: 4）。指定時は自動的に--shorts-only扱い")
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

    out_dir = DESKTOP_DIR / "narration"
    out_dir.mkdir(parents=True, exist_ok=True)
    DESKTOP_DIR.mkdir(parents=True, exist_ok=True)
    (DESKTOP_DIR / ".current_episode").write_text(args.episode, encoding="utf-8")

    client = genai.Client(api_key=API_KEY, http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))

    target_ids = None
    if args.scenes:
        target_ids = {int(s) for s in args.scenes.split(",")}

    shorts_only = args.shorts_only or bool(args.shorts_scenes)

    persona_style = voices.get("persona_style")

    if not shorts_only:
        for scene in ep["scenes"]:
            sid = scene["scene_id"]
            if target_ids is not None and sid not in target_ids:
                continue
            narrator = scene["narrator"]
            voice_name = voices[narrator]
            out_path = out_dir / f"S{sid:02d}.wav"
            style_override = persona_style if narrator == "persona" else None
            synth(client, scene["narration"], voice_name, out_path, narrator=narrator, style_override=style_override)

    if shorts_only or args.scenes is None:
        # 本編シーンと一言一句同じナレーションなら、別々に生成し直さず本編の
        # 確認済み音声をそのまま流用する（同じテキストでも生成のたびに
        # 声の質が変わりうるため、二重生成は無駄なだけでなく品質のばらつきの
        # 原因にもなる。2026-08-22追加）。
        main_wav_by_text = {scene["narration"]: out_dir / f"S{scene['scene_id']:02d}.wav" for scene in ep["scenes"]}
        shorts_target_ids = None
        if args.shorts_scenes:
            shorts_target_ids = {int(s) for s in args.shorts_scenes.split(",")}
        for shorts in ep.get("shorts", []):
            mid = shorts["shorts_id"]
            for i, s in enumerate(shorts["scenes"], start=1):
                if shorts_target_ids is not None and i not in shorts_target_ids:
                    continue
                out_path = out_dir / f"shorts{mid}_S{i:02d}.wav"
                reuse_path = main_wav_by_text.get(s["narration"])
                if reuse_path and reuse_path.exists():
                    shutil.copy(reuse_path, out_path)
                    print(f"✅ {out_path.name}（本編{reuse_path.name}を流用）")
                    continue
                voice_name = voices[s["narrator"]]
                style_override = persona_style if s["narrator"] == "persona" else None
                synth(client, s["narration"], voice_name, out_path, narrator=s["narrator"], style_override=style_override)

    print(f"\n完了。保存先: {out_dir}")


if __name__ == "__main__":
    main()
