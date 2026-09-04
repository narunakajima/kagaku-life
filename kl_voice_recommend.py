"""
kl_voice_recommend.py — ナレーターボイス選定の一次推薦（実音声をGeminiに聴かせる）

kl_bgm_final_check.py と同じ仕組み: テキストラベルによる絞り込み（Claudeが事前に
5候補→3候補に narrowing 済みという前提）で選んだ候補の実音声を生成し、実際の
音声ファイル + 主人公の設定・ストーリーコンセプトをGeminiに渡して、キャラクターに
最も合う声を推薦させる。

2026-09-01改訂: 当初は人間が実際に聴いて最終判断する運用だったが、判断基準が
主人公の年齢・性格・状況との相性という定型的な照合作業であるため、Geminiの
推薦をそのまま採用する方式に変更した（ユーザー確認は不要）。

使い方:
  python3 kl_voice_recommend.py --episode kl003 --role persona \
    --voices Achird,Rasalgethi,Charon \
    --text "ウェブサイトを作る仕事をしていました。佐藤健太、42歳。"
"""

import argparse
import json
import os
import sys
import wave
from pathlib import Path

from google import genai
from google.genai import types

API_KEY = os.environ.get("GEMINI_API_KEY", "")
TTS_MODEL = "gemini-3.1-flash-tts-preview"
RECOMMEND_MODEL = "gemini-3.7-flash"

BASE_DIR = Path(__file__).parent
DESKTOP_DIR = Path.home() / "Desktop" / "kagaku-life"

PROMPT_TEMPLATE = """あなたは「幸せな未来のサイエンスチャンネル」（AI・ロボティクス研究解説×
使い捨ての生活者による物語演出、日本語YouTubeチャンネル）の音響ディレクターです。

このエピソード（{episode}）の主人公は以下の設定です:
{protagonist}

ストーリーコンセプト:
{notes}

これから3つの音声を聴かせます。いずれも同じ短いセリフ「{text}」を、異なる声
（Gemini TTSのプリセットボイス）で読み上げたものです。このうち、上記の主人公の
年齢・性格・状況に最も自然に合う声はどれか、実際に聴いた声質・話し方の印象を
踏まえて1つ選んでください。

添付順序: {voice_order}

日本語で、以下の形式で簡潔に回答してください（各声の講評は1〜2文、全体で
300字程度）:
1. 各声の聴いた印象（声質・話し方）
2. 推薦: {{voice名}}（理由）
"""


def synth(client, text: str, voice_name: str, out_path: Path):
    config = types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
            )
        ),
    )
    resp = client.models.generate_content(model=TTS_MODEL, contents=text, config=config)
    data = resp.candidates[0].content.parts[0].inline_data.data
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(data)


def main():
    parser = argparse.ArgumentParser(description="ナレーターボイスの一次推薦（実音声をGeminiに聴かせる）")
    parser.add_argument("--episode", required=True, help="エピソードID（例: kl003）")
    parser.add_argument("--role", required=True, choices=["persona", "research"], help="ボイスの役割")
    parser.add_argument("--voices", required=True, help="候補ボイス名（カンマ区切り、Claudeが3件程度に絞り込み済みのもの）")
    parser.add_argument("--text", required=True, help="読み上げるサンプルナレーション文")
    args = parser.parse_args()

    if not API_KEY:
        print("❌ GEMINI_API_KEY が設定されていません", file=sys.stderr)
        sys.exit(1)

    ep_path = BASE_DIR / "episodes" / f"{args.episode}.json"
    if not ep_path.exists():
        print(f"❌ {ep_path} がありません", file=sys.stderr)
        sys.exit(1)
    ep = json.loads(ep_path.read_text())

    voices = [v.strip() for v in args.voices.split(",") if v.strip()]
    out_dir = DESKTOP_DIR / "voice_test"
    out_dir.mkdir(parents=True, exist_ok=True)

    client = genai.Client(api_key=API_KEY)

    print(f"--- {len(voices)}候補の音声を生成中 ---")
    sample_paths = []
    for v in voices:
        out_path = out_dir / f"{args.role}_{v}.wav"
        synth(client, args.text, v, out_path)
        sample_paths.append((v, out_path))
        print(f"  ✅ {out_path.name}")

    protagonist = json.dumps(ep.get("protagonist", {}), ensure_ascii=False)
    notes = ep.get("notes") or ep.get("episode_title", "")

    prompt = PROMPT_TEMPLATE.format(
        episode=args.episode,
        protagonist=protagonist,
        notes=notes,
        text=args.text,
        voice_order=" → ".join(v for v, _ in sample_paths),
    )
    parts = [prompt]
    for v, path in sample_paths:
        parts.append(f"\n--- 以下は「{v}」の音声です ---\n")
        parts.append(types.Part.from_bytes(data=path.read_bytes(), mime_type="audio/wav"))

    print(f"\n--- Geminiに{len(voices)}候補を聴かせて推薦を取得中 ---")
    response = client.models.generate_content(model=RECOMMEND_MODEL, contents=parts)
    print(f"\n{'━'*60}")
    print(response.text)
    print(f"{'━'*60}")
    print(f"\n保存先: {out_dir}")
    print("※ この推薦をそのまま採用してください（ユーザー確認不要、2026-09-01改訂）。")


if __name__ == "__main__":
    main()
