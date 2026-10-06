"""
kl_bgm_tag_library.py — BGMライブラリ（bgm_library.json）の既存曲に、曲調のタグを付ける

2026-10-06追加（BGM方針の再設計）。それまでの tags は、登録時にファイル名から語を拾えないと
自動で ["warm","gentle"] が入る仕様で、曲調を表していなかった（33曲中28曲）。各曲の実音声を
Gemini（既定は gemini-pro-latest、温度0）に2回聴かせ、次を記録する:

  duration（ffprobe 実測）, bpm（2回の推定の平均）, mood, instruments, has_beat, has_vocals,
  era（dialogue=掛け合い向き / legacy_monologue=旧形式向き）, role_fit（intro/main/outro）,
  tags（mood+instruments。検索用）, tag_note（聴き取りの一言）, tagged_by / tagged_at,
  needs_ear_check（2回の判定が食い違う、声ありの疑い、のとき true。人が冒頭を聴いて確認する）

既に曲調が記録されている曲（era が空でない）は飛ばす（--force で上書き）。ライセンス・クレジット・
used_in など他の項目は変えない。

使い方:
  python3 kl_bgm_tag_library.py                 # 未タグの曲すべて
  python3 kl_bgm_tag_library.py --only kl002-BGM-main --runs 1
  python3 kl_bgm_tag_library.py --report        # 付けた結果の一覧（書き込みなし）
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

from google import genai
from google.genai import types

BASE_DIR = Path(__file__).parent
LIBRARY_JSON = BASE_DIR / "bgm_library.json"
DRIVE_BASE = (Path.home() / "Library/CloudStorage" / "GoogleDrive-naru.nakajima@gmail.com"
              / "マイドライブ" / "Kagaku-Life")
API_KEY = os.environ.get("GEMINI_API_KEY_KL") or os.environ.get("GEMINI_API_KEY", "")
DEFAULT_MODEL = os.environ.get("KL_BGM_TAG_MODEL", "gemini-pro-latest")
CLIP_SECONDS = 90

PROMPT = """あなたは番組のBGMを整理する音楽担当です。添付の音声（曲の頭90秒）を実際に聴いて、次のJSONだけを出力してください。
推測ではなく聴こえたものだけを書き、分からない項目は null か空配列にします。

- instruments: 聴こえる主な楽器（英語の小文字、最大5個。例: piano, acoustic-guitar, synth, electric-piano, strings, pizzicato, marimba, bells, drums, bass, lofi-beat, pads, flute, brass）
- has_beat: ドラム・パーカッション等の規則的なビートが鳴っているか（true/false）
- bpm: テンポ（整数。ビートが無い・不明なら null）
- mood: 次から1〜2個: bright, playful, curious, neutral, calm, emotional, sad, tense, dark, epic, dreamy
- has_vocals: 人の声（歌・ハミング・台詞・声のサンプル）が聴こえるか（true/false）
- loopable: 曲の頭と末尾を単純につないでも違和感が出にくい作りか（true/false/null）
- note: 聴いた印象を日本語で20字程度

JSONのみ:
{"instruments": [], "has_beat": false, "bpm": null, "mood": [], "has_vocals": false, "loopable": null, "note": ""}
"""


def load_library() -> list:
    return json.loads(LIBRARY_JSON.read_text(encoding="utf-8"))


def save_library(lib: list) -> None:
    tmp = LIBRARY_JSON.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(lib, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(LIBRARY_JSON)


def probe_duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                        str(path)], capture_output=True, text=True)
    try:
        return round(float(r.stdout.strip()), 1)
    except ValueError:
        return 0.0


def clip(path: Path, out: Path) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(path), "-t", str(CLIP_SECONDS), "-ac", "1",
                    "-ar", "22050", "-b:a", "64k", str(out)], check=True)


def parse_json(text: str) -> dict:
    s = text.strip()
    a, b = s.find("{"), s.rfind("}")
    return json.loads(s[a:b + 1])


def listen(client, model: str, audio: bytes) -> dict:
    last = None
    for attempt in range(4):
        try:
            resp = client.models.generate_content(
                model=model,
                contents=[PROMPT, types.Part.from_bytes(data=audio, mime_type="audio/mpeg")],
                config=types.GenerateContentConfig(temperature=0))
            return parse_json(resp.text)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 ** (attempt + 1))
    raise RuntimeError(f"聴き取りに失敗: {last}")


MIN_LEN = {"intro": 90, "main": 120, "outro": 45}   # 役割別の曲の長さの下限（秒）。足りなければ short_for_role に入れる
PLUCKED = {"pizzicato", "marimba", "kalimba", "xylophone", "bells"}


def decide_era_and_roles(duration: float, d: dict) -> tuple:
    """新方針（CLAUDE.md「BGMパイプライン」）の基準で、掛け合い向きか・どの役割に合うかを決める。
    role_fit は音楽的な適合だけで決める（長さが足りない役割は short_for_role に別に記録する）。
    掛け合い向き(dialogue): 声なし・暗い/泣き/壮大でない、かつビートがある、またはビートは無くても
      弾むピチカート系の遊び心のある曲（kl031・kl032 の main のような曲）。
    旧形式向き(legacy_monologue): それ以外（ビートなしの静かなピアノ、泣きの曲など）。"""
    moods = set(d.get("mood") or [])
    heavy = moods & {"sad", "dark", "epic", "emotional", "dreamy", "tense"}
    beat = bool(d.get("has_beat"))
    bpm = d.get("bpm")
    if d.get("has_vocals"):
        return "", []
    plucked_playful = bool(set(d.get("instruments") or []) & PLUCKED) and bool(moods & {"playful", "curious", "bright"})
    dialogue_ok = not heavy and ((beat and (bpm is None or bpm >= 65)) or plucked_playful)
    if not dialogue_ok:
        return "legacy_monologue", []
    roles = []
    if beat and bpm and 100 <= bpm <= 130:
        roles.append("intro")
    if (beat and bpm and 70 <= bpm <= 105) or (not beat and plucked_playful):
        roles.append("main")
    if beat and bpm and 80 <= bpm <= 105:
        roles.append("outro")
    return "dialogue", roles


def derive_flags(entry: dict) -> dict:
    """保存済みの項目から era / role_fit / short_for_role / needs_ear_check を再計算する（聴き直さない）。"""
    era, roles = decide_era_and_roles(entry.get("duration") or 0, entry)
    short = [r for r in roles if (entry.get("duration") or 0) < MIN_LEN[r]]
    why = [w for w in (entry.get("ear_check_reason") or "").split("、") if w and not w.startswith("mood")]
    if set(entry.get("mood") or []) & {"dark", "tense"}:
        why.append("mood が dark/tense（温かい曲として使われてきた曲は判定を疑う）")
    return {"era": era, "role_fit": roles, "short_for_role": short,
            "needs_ear_check": bool(why), "ear_check_reason": "、".join(why)}


def tag_entry(client, model: str, entry: dict, runs: int) -> dict:
    src = DRIVE_BASE / entry["path"]
    if not src.exists():
        raise FileNotFoundError(src)
    duration = probe_duration(src)
    with tempfile.TemporaryDirectory() as td:
        small = Path(td) / "clip.mp3"
        clip(src, small)
        audio = small.read_bytes()
    results = [listen(client, model, audio) for _ in range(runs)]
    bpms = [r.get("bpm") for r in results if isinstance(r.get("bpm"), (int, float))]
    bpm = round(statistics.mean(bpms)) if bpms else None
    beats = [bool(r.get("has_beat")) for r in results]
    vocals = [bool(r.get("has_vocals")) for r in results]
    merged = {
        "instruments": sorted({i for r in results for i in (r.get("instruments") or [])})[:6],
        "has_beat": sum(beats) * 2 > len(beats),
        "bpm": bpm,
        "mood": sorted({m for r in results for m in (r.get("mood") or [])})[:3],
        "has_vocals": any(vocals),
        "note": (results[0].get("note") or "")[:40],
    }
    ear = False
    why = []
    if len(set(vocals)) > 1 or merged["has_vocals"]:
        ear, why = True, why + ["声の判定"]
    if len(set(beats)) > 1:
        ear, why = True, why + ["ビート有無が割れた"]
    if len(bpms) >= 2 and max(bpms) > min(bpms) * 1.15:
        ear, why = True, why + [f"BPM推定が割れた({min(bpms)}〜{max(bpms)})"]
    out = {
        "duration": duration, "bpm": bpm, "mood": merged["mood"], "instruments": merged["instruments"],
        "has_beat": merged["has_beat"], "has_vocals": merged["has_vocals"],
        "tags": sorted(set(merged["mood"]) | set(merged["instruments"])),
        "tag_note": merged["note"], "tagged_by": f"{model} x{runs}", "tagged_at": date.today().isoformat(),
        "ear_check_reason": "、".join(why),
    }
    out.update(derive_flags(out))
    return out


def report(lib: list) -> None:
    print(f"{'id':<20}{'長さ':>6}{'BPM':>5} ビート 声  era               role_fit            mood／楽器")
    for e in lib:
        if not e.get("tagged_at"):
            print(f"{e['id']:<20}  （未タグ）")
            continue
        print(f"{e['id']:<20}{e['duration']:>6.0f}{(e.get('bpm') or 0):>5} {'有' if e.get('has_beat') else '無':^4} "
              f"{'有' if e.get('has_vocals') else '-':^2} {e.get('era') or '-':<17} {','.join(e.get('role_fit') or []) or '-':<12}"
              f"{('短:' + ','.join(e.get('short_for_role') or [])) if e.get('short_for_role') else '':<10}"
              f"{','.join(e.get('mood') or [])}／{','.join(e.get('instruments') or [])}"
              + ("  ★耳で確認: " + e.get("ear_check_reason", "") if e.get("needs_ear_check") else ""))


def main():
    ap = argparse.ArgumentParser(description="BGMライブラリの既存曲に曲調のタグを付ける")
    ap.add_argument("--only", help="この id だけ（例: kl002-BGM-main）")
    ap.add_argument("--runs", type=int, default=2, help="聴かせる回数（既定2。食い違えば要確認の印）")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--force", action="store_true", help="タグ付け済みの曲も付け直す")
    ap.add_argument("--report", action="store_true", help="結果の一覧を表示するだけ")
    ap.add_argument("--rederive", action="store_true", help="聴き直さず、保存済みの項目から era/role_fit 等を再計算する")
    args = ap.parse_args()
    lib = load_library()
    if args.report:
        report(lib)
        return
    if args.rederive:
        for e in lib:
            if e.get("tagged_at"):
                e.update(derive_flags(e))
        save_library(lib)
        report(lib)
        return
    if not API_KEY:
        print("❌ GEMINI_API_KEY が設定されていません", file=sys.stderr)
        sys.exit(1)
    client = genai.Client(api_key=API_KEY, http_options=types.HttpOptions(timeout=180_000))
    todo = [e for e in lib if (args.only == e["id"] if args.only else (args.force or not e.get("tagged_at")))]
    print(f"タグ付け対象: {len(todo)}曲（モデル {args.model}、{args.runs}回ずつ）")
    for n, e in enumerate(todo, 1):
        try:
            tags = tag_entry(client, args.model, e, args.runs)
        except Exception as ex:  # noqa: BLE001
            print(f"  [{n}/{len(todo)}] ⚠️ {e['id']}: {ex}")
            continue
        e.update(tags)
        save_library(lib)  # 1曲ごとに保存（途中で止まっても失われない）
        flag = "  ★耳で確認: " + tags["ear_check_reason"] if tags["needs_ear_check"] else ""
        print(f"  [{n}/{len(todo)}] ✓ {e['id']}: {tags['duration']:.0f}秒 BPM{tags['bpm']} "
              f"beat={'有' if tags['has_beat'] else '無'} {tags['era'] or '-'} {tags['role_fit']}{flag}")
    print("\n完了。`python3 kl_bgm_tag_library.py --report` で一覧を見られます")


if __name__ == "__main__":
    main()
