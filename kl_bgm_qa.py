"""
kl_bgm_qa.py — BGM候補の音声QA（ボーカル・台詞混入チェック）

samurai-chroniclesの sc_bgm_qa.py と同じ仕組み。Gemini のマルチモーダル音声理解を使い、
BGM候補にナレーションと競合する人の声（歌詞・台詞・ナレーション・ささやき等）が
含まれていないかを判定する。

使い方:
  python3 kl_bgm_qa.py --file <path.mp3>
  python3 kl_bgm_qa.py --dir <ディレクトリ>   # ディレクトリ内の *.mp3 を一括チェック

2026-10-06: 温度0で3回判定して多数決にした（1回でも「あり」なら不合格＝安全側）。
「あり」の場合は声が聞こえる時刻（秒）も出すので、人はその前後だけ聴いて確認する。
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
# 2026-10-06: --model / 環境変数 KL_BGM_QA_MODEL で切り替えられる。実測で gemini-pro-latest は6曲×3回の
# 判定がすべて一致した一方、flash は3曲で判定が割れた（ソロピアノに「男性ボーカル」など）。費用は pro の方が高い
QA_MODEL = os.environ.get("KL_BGM_QA_MODEL", "gemini-flash-latest")

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
    "\n\nIf has_vocals is true, also add \"vocal_times\": a list of start times in seconds "
    "(numbers, measured from the start of this clip) where the voice is heard, e.g. "
    '{"has_vocals": true, "vocal_times": [12, 41], "details": "..."}'
)

# 判定のぶれ対策（2026-10-06）: 同じ曲で3回中2回だけボーカルと判定されたことがあったため、
# 温度0で QA_RUNS 回判定して多数決にする。1回でも判定が割れたら安全側（不合格）に倒す。
QA_RUNS = 3


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


def _qa_once(client, audio_path: Path, data: bytes, retries: int = 2) -> dict:
    """1回分の判定。空の応答・JSONの読み取り失敗は retries 回まで取り直す
    （実測で3回に1回ほど空の応答が返り、判定できた回が1回だけになることがあった）。"""
    r = _qa_once_raw(client, audio_path, data)
    while r["has_vocals"] is None and retries > 0:
        retries -= 1
        r = _qa_once_raw(client, audio_path, data)
    return r


def _qa_once_raw(client, audio_path: Path, data: bytes) -> dict:
    try:
        mime_type = "audio/mpeg" if audio_path.suffix.lower() == ".mp3" else "audio/wav"
        response = client.models.generate_content(
            model=QA_MODEL,
            contents=[
                QA_PROMPT,
                genai.types.Part.from_bytes(data=data, mime_type=mime_type),
            ],
            config=genai.types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                **({"thinking_config": genai.types.ThinkingConfig(thinking_budget=0)} if "flash" in QA_MODEL else {}),
            ),
        )
        text = response.text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        # 応答の前に英語の考え書きが付き、その後ろにJSONが来ることがある（実測）。最後の {...} を読む
        m = re.search(r"\{[^{}]*\}\s*$", text, re.S) or re.search(r"\{.*\}", text, re.S)
        result = json.loads(m.group(0) if m else text)
        return {
            "file": audio_path.name,
            "has_vocals": bool(result.get("has_vocals", False)),
            "vocal_times": [t for t in (result.get("vocal_times") or []) if isinstance(t, (int, float))],
            "details": result.get("details", ""),
        }
    except Exception as e:
        return {"file": audio_path.name, "has_vocals": None, "vocal_times": [], "details": f"QA失敗: {e}"}


def _ranges(secs: list) -> list:
    """[0,1,2,3,10,11] → ["0〜3秒", "10〜11秒"]（連続する秒をまとめる）"""
    out, start, prev = [], None, None
    for t in secs:
        if start is None:
            start = prev = t
        elif t <= prev + 2:
            prev = t
        else:
            out.append(f"{start}秒" if start == prev else f"{start}〜{prev}秒")
            start = prev = t
    if start is not None:
        out.append(f"{start}秒" if start == prev else f"{start}〜{prev}秒")
    return out


def qa_audio_with_gemini(client, audio_path: Path, runs: int = None) -> dict:
    """音声ファイルをGeminiに runs 回渡し、ボーカル・台詞混入の有無を多数決で判定する。

    - 全回「なし」→ has_vocals False
    - 1回でも「あり」→ has_vocals True（割れた場合も安全側に倒して不合格。split=True）
    - 判定できた回が1回も無い → has_vocals None
    vocal_times は「あり」と答えた回の時刻（秒）をまとめたもの。人はその前後5秒だけ聴けばよい。
    """
    runs = runs or QA_RUNS
    data = _clip_audio_bytes(audio_path)
    votes = [_qa_once(client, audio_path, data) for _ in range(runs)]
    valid = [v for v in votes if v["has_vocals"] is not None]
    yes = [v for v in valid if v["has_vocals"]]
    if not valid:
        return {"file": audio_path.name, "has_vocals": None, "split": False, "votes": "0/0",
                "vocal_times": [], "details": votes[0]["details"]}
    times = _ranges(sorted({round(float(t)) for v in yes for t in v["vocal_times"]}))
    split = 0 < len(yes) < len(valid)
    detail_src = yes[0] if yes else valid[0]
    return {
        "file": audio_path.name,
        "has_vocals": bool(yes),
        "split": split,
        "votes": f"{len(yes)}/{len(valid)}",
        "vocal_times": times,
        "details": detail_src["details"],
    }


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
            label = "判定が割れた（安全側で不合格）" if result.get("split") else "ボーカル/台詞あり"
            at = f" 時刻: {', '.join(result['vocal_times'])}（前後5秒を人が聴いて確認）" \
                if result.get("vocal_times") else ""
            print(f"❌ {label} [{result['votes']}] — {result['details']}{at}")
        else:
            print(f"✓ インストゥルメンタル [{result['votes']}] — {result['details']}")
    return results


def main():
    global QA_MODEL, QA_RUNS
    parser = argparse.ArgumentParser(description="BGM候補の音声QA（ボーカル混入チェック）")
    parser.add_argument("--file", help="単一ファイルをチェック")
    parser.add_argument("--dir", help="ディレクトリ内の *.mp3 を一括チェック")
    parser.add_argument("--model", help=f"判定に使うモデル（既定 {QA_MODEL}。gemini-pro-latest の方がぶれにくい）")
    parser.add_argument("--runs", type=int, default=QA_RUNS, help=f"判定回数（既定 {QA_RUNS}、多数決）")
    args = parser.parse_args()
    if args.model:
        QA_MODEL = args.model
    QA_RUNS = max(1, args.runs)

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
            at = f"（{', '.join(r['vocal_times'])}）" if r.get("vocal_times") else ""
            print(f"  - {r['file']} [{r['votes']}]{at}: {r['details']}")
        sys.exit(1)
    print("\n✓ 全候補インストゥルメンタル確認済み")


if __name__ == "__main__":
    main()
