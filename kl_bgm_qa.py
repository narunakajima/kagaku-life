"""
kl_bgm_qa.py — BGM候補の音声QA（ボーカル・台詞混入チェック）

samurai-chroniclesの sc_bgm_qa.py と同じ仕組み。Gemini のマルチモーダル音声理解を使い、
BGM候補にナレーションと競合する人の声（歌詞・台詞・ナレーション・ささやき等）が
含まれていないかを判定する。

使い方:
  python3 kl_bgm_qa.py --file <path.mp3>
  python3 kl_bgm_qa.py --dir <ディレクトリ>   # ディレクトリ内の *.mp3 を一括チェック
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from google import genai

import os

API_KEY = os.environ.get("GEMINI_API_KEY_KL") or os.environ.get("GEMINI_API_KEY", "")
QA_MODEL = "gemini-flash-latest"

# ボーカル混入は大抵冒頭〜中盤で判別できるため、全尺ではなく先頭 QA_CLIP_SECONDS 秒
# のみをQAに送る（Gemini音声入力トークンを大幅削減する）。sc_bgm_qa.pyと同じ仕組み。
QA_CLIP_SECONDS = 60

QA_PROMPT = (
    "Listen to this audio track. It will be used as instrumental background music (BGM) "
    "underneath a documentary narrator's voice, so any human voice in the track would "
    "clash with the narration.\n\n"
    "Determine whether the track contains ANY human vocals — sung lyrics, spoken dialogue, "
    "narration, whispering, chanting with words, or a vocal sample of any kind. "
    "Purely instrumental music (piano, strings, gentle percussion, wordless choir "
    "hums/oohs) should be marked has_vocals: false.\n\n"
    "Respond with ONLY a JSON object, no other text, in this exact format:\n"
    '{"has_vocals": true, "details": "brief description of the voice/lyrics heard"}\n'
    "or\n"
    '{"has_vocals": false, "details": "brief description of the instrumentation"}'
)


def _clip_audio_bytes(audio_path: Path, seconds: int = QA_CLIP_SECONDS) -> bytes:
    """先頭 seconds 秒だけを切り出したバイト列を返す。切り出しに失敗したら全尺を返す。"""
    suffix = audio_path.suffix or ".mp3"
    with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(audio_path), "-t", str(seconds), "-c", "copy", tmp.name],
            capture_output=True,
        )
        if result.returncode == 0:
            clipped = Path(tmp.name).read_bytes()
            if clipped:
                return clipped
    return audio_path.read_bytes()


def qa_audio_with_gemini(client, audio_path: Path) -> dict:
    """音声ファイルをGemini に渡し、ボーカル・台詞混入の有無を判定する。"""
    try:
        data = _clip_audio_bytes(audio_path)
        mime_type = "audio/mpeg" if audio_path.suffix.lower() == ".mp3" else "audio/wav"
        response = client.models.generate_content(
            model=QA_MODEL,
            contents=[
                QA_PROMPT,
                genai.types.Part.from_bytes(data=data, mime_type=mime_type),
            ],
        )
        text = response.text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        result = json.loads(text)
        return {
            "file": audio_path.name,
            "has_vocals": bool(result.get("has_vocals", False)),
            "details": result.get("details", ""),
        }
    except Exception as e:
        return {"file": audio_path.name, "has_vocals": None, "details": f"QA失敗: {e}"}


def run(paths: list) -> list:
    if not API_KEY:
        print("❌ GEMINI_API_KEY が設定されていません")
        sys.exit(1)
    client = genai.Client(api_key=API_KEY)

    results = []
    for p in paths:
        print(f"  {p.name} 判定中... ", end="", flush=True)
        result = qa_audio_with_gemini(client, p)
        results.append(result)
        if result["has_vocals"] is None:
            print(f"⚠️  {result['details']}")
        elif result["has_vocals"]:
            print(f"❌ ボーカル/台詞あり — {result['details']}")
        else:
            print(f"✓ インストゥルメンタル — {result['details']}")
    return results


def main():
    parser = argparse.ArgumentParser(description="BGM候補の音声QA（ボーカル混入チェック）")
    parser.add_argument("--file", help="単一ファイルをチェック")
    parser.add_argument("--dir", help="ディレクトリ内の *.mp3 を一括チェック")
    args = parser.parse_args()

    if args.file:
        paths = [Path(args.file)]
    elif args.dir:
        paths = sorted(Path(args.dir).glob("*.mp3"))
        if not paths:
            print(f"❌ *.mp3 が見つかりません: {args.dir}")
            sys.exit(1)
    else:
        parser.error("--file または --dir を指定してください")
        return

    results = run(paths)
    flagged = [r for r in results if r["has_vocals"]]
    if flagged:
        print(f"\n⚠️  ボーカル/台詞混入の疑いがある候補: {len(flagged)}件")
        for r in flagged:
            print(f"  - {r['file']}: {r['details']}")
        sys.exit(1)
    print("\n✓ 全候補インストゥルメンタル確認済み")


if __name__ == "__main__":
    main()
