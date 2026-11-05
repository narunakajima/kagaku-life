"""
kl_tts_gen.py — くらしを変える科学 ナレーション音声生成スクリプト

episodes/kl{NNN}.json の各シーンのnarration文を、scene.narrator（persona/research）
に応じて narration_voices（エピソードごとに選定済みのボイス名）で読み分け、
gemini-3.8-flash-ttsで音声を生成する（CLAUDE.md「ストーリー構成と
2ナレーターボイス制」参照）。

narration_voicesが未設定のエピソードは、先にボイス選定（聴き比べ）を行ってから
episodes/kl{NNN}.jsonに記録すること。

使い方:
  python3 kl_tts_gen.py --episode kl001                 # 全シーン+Shorts生成
  python3 kl_tts_gen.py --episode kl001 --scenes 5,6,9   # 指定シーンのみ再生成
  python3 kl_tts_gen.py --episode kl001 --shorts-only    # Shortsのみ
  python3 kl_tts_gen.py --episode kl001 --force          # 既存ファイルも含め全シーン再生成
  python3 kl_tts_gen.py --episode kl035 --no-reading-qa  # 読み照合QA（掛け合い形式のみ）を使わない

出力: ~/Desktop/kagaku-life/narration/S{NN}.wav,
      shorts{M}_S{NN}.wav
      （Desktopは常に最新1エピソード分の確認用。エピソードIDのサブフォルダは作らない）

読み照合QA（掛け合い形式、2026-10-11〜。kl_reading_qa.py）:
  Gemini QA を通った台詞を、音素認識（言語モデルなしの CTC）で「聞こえたとおりの音」にして、
  台本の期待する読み（Gemini Pro がテキストから決めたカタカナ）と行内の局所的な差で照合する。
  不一致の行だけ作り直し（最大 READING_QA_MAX_REGEN 回）、残ったら一番ましな音声で続行して
  narration/reading_qa.json に記録し、最後にまとめて表示する。

生成済みならスキップ（2026-09-04〜、sc_tts_gen.pyと同じ考え方）:
  --scenes未指定のフル実行では、既に音声が存在するシーンは再生成しない。
  全シーンを強制的に作り直したい場合は --force。
"""

import argparse
import base64
import io
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

from google import genai
from google.genai import types

sys.stdout.reconfigure(line_buffering=True)

BASE_DIR = Path(__file__).parent
DESKTOP_DIR = Path.home() / "Desktop" / "kagaku-life"

API_KEY = os.environ.get("GEMINI_API_KEY_KL") or os.environ.get("GEMINI_API_KEY", "")
QA_MODEL = "gemini-flash-latest"  # ナレーション音声が台本通りか判定する用（sc_tts_gen.pyと同じ考え方）
# 2026-09-28: gemini-3.1-flash-tts-preview → gemini-3.8-flash-tts（正式版）に移行。
# 3.8は入力テキストを「読み上げ原稿そのもの」として扱うため、演技指導（STYLE_PREFIX・
# persona_style）をテキスト先頭に付けると指示文まで読み上げられてしまう。演技指導は
# speech_metadata.style で本文と分けて渡す（_tts_rest_call参照）。また出力が
# ヘッダーなしPCMからヘッダー付きWAVに変わったため、RIFF判定でどちらにも対応する。
# （経緯: 2026-08-21に3.1で演技指導付きだとfinish_reason=OTHERになる不具合があり
# 一時gemini-2.5-pro-preview-ttsに切り替え、2026-09-05に解消を確認して3.1に戻していた。
# MAX_RETRIESによるリトライは引き続き安全網として残す。）
#
# ⚠️ speech_metadata は2026-09-28時点のgoogle-genai最新版（PyPI 1.47.0）の
# types.Part にまだ型定義されておらず、SDK経由で呼ぶとPydanticに拒否される
# （samurai-chronicles側の実機検証で確認済み。同じgoogle-genaiパッケージを
# 使っているためKL側でも同様に失敗する）。そのためTTS生成のみ生のREST APIを
# 直接叩く（_tts_rest_call）。QA用の音声読み込み（qa_narration_with_gemini）は
# speech_metadataを使わないためSDKのままでよい。SDKがspeech_metadataに
# 対応したら synth() 内の _tts_rest_call 呼び出しを
# client.models.generate_content に戻してよい。
MODEL = "gemini-3.8-flash-tts"
MODEL_REST_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
REQUEST_TIMEOUT_MS = 60_000
MAX_RETRIES = 5
READING_QA_MAX_REGEN = 3  # 読みの不一致で作り直す上限（Gemini QA・API失敗の MAX_RETRIES とは別に数える）

# 研究ボイス（Orus）は稀に音程が高く裏返ることがあり、また短いフレーズ
# （Shorts等）では雰囲気が暗く/硬く聞こえがちなため、落ち着いた低めの音程を
# 保ちつつ、チャンネルの温かいトーンに合う明るさを明示的に指示する。
# 2026-09-06改訂（1回目）: 当初の「energetic/brisk and lively/enthusiastic」
# という強い指示が、kl015で「異様にテンションが高い」との指摘を受けるほど
# ハイテンションな読み上げになっていたため、テンポと熱量を落とし、
# 「落ち着いているが温かい」トーンに寄せた。
# 2026-09-06改訂（2回目）: 落ち着かせすぎた反動で「もう少しテンポアップして
# ほしい」との指摘を受けたため、熱量（energetic/enthusiastic等の煽り表現）は
# 追加せず、テンポ（brisk/efficient）だけを穏やかに戻した。「熱量を上げずに
# テンポだけ上げる」という組み合わせが今回の狙い。
STYLE_PREFIX = {
    "research": (
        "Say in a warm, clear, calmly confident documentary-narrator voice, "
        "at a brisk, efficient speaking pace that keeps the explanation "
        "moving along without ever feeling rushed — engaged and thoughtful, "
        "never flat, cold, heavy, or somber, and never overly excited, "
        "breathless, or hyped-up. Keep a stable, moderate-to-low pitch and "
        "do not let it rise or break upward at any point: "
    ),
}
# personaは主人公ごとに毎回声・年齢・性格が変わるため、STYLE_PREFIXのような
# 固定辞書ではなく episodes/kl{NNN}.json の narration_voices.persona_style
# （任意フィールド）にエピソードごとの演技指導を記録し、synth()のstyle_overrideで
# 上書きする方式にする（2026-08-25追加、kl004で高齢者演技指導が必要になったため）。


def _to_wav_bytes(audio_data: bytes, sample_rate: int = 24000) -> bytes:
    """WAV/PCMいずれのバイト列でも WAV バイト列へ正規化する（3.8はWAVで返す）。"""
    if audio_data[:4] == b"RIFF":
        return audio_data
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_data)
    return buf.getvalue()


def _tts_rest_call(text: str, style: str, voice_name: str) -> bytes:
    """gemini-3.8-flash-tts を speech_metadata.style 付きで呼び出す（生REST）。
    google-genai SDK（PyPI最新1.47.0時点）が speech_metadata を型定義しておらず
    Pydanticに拒否されるための回避策（ファイル冒頭のコメント参照）。
    既存のSTYLE_PREFIX/persona_styleは「〜: 」で本文に続ける前提の書式のため、
    末尾のコロン・空白を落としてから渡す。"""
    style = style.strip().rstrip(":").strip()
    part = {"text": text}
    if style:
        part["speech_metadata"] = {"style": style}
    url = MODEL_REST_URL.format(model=MODEL, key=API_KEY)
    body = {
        "contents": [{"role": "user", "parts": [part]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": voice_name}
                }
            },
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_MS / 1000) as resp:
        data = json.loads(resp.read())
    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"レスポンスにcandidatesがありません: {data}")
    parts = candidates[0].get("content", {}).get("parts") or []
    for p in parts:
        inline = p.get("inlineData")
        if inline and inline.get("data"):
            return base64.b64decode(inline["data"])
    finish_reason = candidates[0].get("finishReason", "?")
    raise RuntimeError(f"空データ（finish_reason={finish_reason}）")


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


def synth(client: genai.Client, text: str, voice_name: str, out_path: Path, narrator: str = None,
          style_override: str = None, reading_qa=None, reading_log: dict = None) -> bool:
    """1本の音声を生成し、Gemini QA（台本どおりか）を通ったら保存する。
    reading_qa（kl_reading_qa.ReadingQA）を渡すと、さらに読み照合を行い、不一致なら作り直す
    （最大 READING_QA_MAX_REGEN 回。上限後は不一致が一番小さい音声を採用して警告する）。
    結果は reading_log[out_path.name] に入れる。"""
    style = style_override if style_override is not None else STYLE_PREFIX.get(narrator, "")
    data = None
    fails = 0
    regen = 0
    best = None  # (不一致の大きさ, 音声, 照合結果)
    final_rq = None
    while True:
        try:
            candidate_data = _tts_rest_call(text, style, voice_name)
            qa = qa_narration_with_gemini(client, candidate_data, text)
            reason = f"台本不一致の疑い（{'; '.join(qa['issues'])}）"
        except Exception as e:
            qa = None
            reason = f"{type(e).__name__}: {e}"
        if qa and qa["ok"]:
            if reading_qa is None:
                data = candidate_data
                break
            try:
                rq = reading_qa.check(candidate_data, text)
            except Exception as e:
                print(f"  ⚠️ {out_path.name}: 読み照合を実行できませんでした（{type(e).__name__}: {e}）。照合なしで採用します")
                data, final_rq = candidate_data, {"ok": True, "skipped": f"照合エラー: {e}", "text": text}
                break
            rq["attempt"] = regen + 1
            if rq["ok"]:
                data, final_rq = candidate_data, rq
                break
            size = sum(d["delta"] for d in rq["mismatches"])
            if best is None or size < best[0]:
                best = (size, candidate_data, rq)
            desc = "; ".join(f"{d['expected']}→{d['heard'] or '（なし）'}" for d in rq["mismatches"])
            regen += 1
            if regen > READING_QA_MAX_REGEN:
                data, final_rq = best[1], best[2]
                print(f"  ⚠️ {out_path.name}: 読みの不一致が{READING_QA_MAX_REGEN}回作り直しても解消しないため、"
                      f"不一致が一番小さい音声（{final_rq['attempt']}回目）を採用します")
                break
            print(f"  ⚠️ {out_path.name}: 読みの不一致の疑い（{desc}）、作り直し（{regen}/{READING_QA_MAX_REGEN}）")
            continue
        fails += 1
        if fails >= MAX_RETRIES:
            break
        print(f"  ⚠️ {out_path.name}: {reason}（{fails}回目）、リトライ")
        time.sleep(2)
    if data is None and best is not None:
        # 読み照合で作り直している途中に API・Gemini QA の失敗が上限に達した場合
        data, final_rq = best[1], best[2]
    if data is None:
        print(f"❌ {out_path.name}: {MAX_RETRIES}回試行して失敗", file=sys.stderr)
        return False
    out_path.write_bytes(_to_wav_bytes(data))
    if reading_log is not None and final_rq is not None:
        final_rq["regenerated"] = regen
        reading_log[out_path.name] = final_rq
    print(f"✅ {out_path.name} ({voice_name})" + ("" if final_rq is None or final_rq.get("ok") else " ⚠️読みの不一致あり"))
    return True


def guard_desktop_episode(desktop_dir: Path, episode: str) -> None:
    """Desktopに別エピソードの素材が残っているまま生成を始めると、.current_episode が新しいエピソードに
    書き換わり、kl_finalize.py の取り違え防止（マーカー照合）をすり抜けて、残っていた素材が新しい
    エピソードのDriveフォルダへ上書きコピーされる（2026-10-05、kl032の素材がKL031へ上書きされた事故）。
    マーカーと違うエピソードの素材（images/narration）が残っていたら、生成を止める。"""
    marker = desktop_dir / ".current_episode"
    current = marker.read_text(encoding="utf-8").strip() if marker.exists() else None
    if current is None or current == episode:
        return
    leftovers = [d for d in ("images", "narration", "output") if (desktop_dir / d).exists()
                 and any((desktop_dir / d).iterdir())]
    if leftovers:
        print(f"❌ Desktopには {current} の素材（{', '.join(leftovers)}）が残っています。{episode} の生成を始めると "
              f"kl_finalize.py の取り違え防止をすり抜けて上書きされるため止めます。\n"
              f"   {current} がDriveへ同期済みなら、{desktop_dir}/{{images,narration,output}} を片付けてから実行してください。",
              file=sys.stderr)
        sys.exit(1)


def _atomic_write_json(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def run_dialogue(args, ep: dict, ep_path: Path, client) -> None:
    """掛け合い形式（format: dialogue、2026-10-04〜）の音声生成。
    台詞を1行ずつ、話者の声（cast.json の voice）と演技指導（cast.json の style＋行ごとの tone）で
    生成し、話者に応じた間を入れて連結してシーン音声 S{NN}.wav にする。各行のシーン内の開始時刻と
    長さを lines[].t0 / dur に書き込む（kl_telop_gen.py と kl_video_gen.py が使う）。

    行ごとの音声は narration/S{NN}_L{KK}.wav に残し、同じ台詞・同じ演技指導なら再生成しない
    （台詞を直した行だけが作り直される。L{KK}.txt に生成時の台詞と指導を記録して比較する）。"""
    import kl_dialogue as D

    cast = D.load_cast()
    out_dir = DESKTOP_DIR / "narration"
    target_ids = {int(s) for s in args.scenes.split(",")} if args.scenes else None
    shorts_only = args.shorts_only or bool(args.shorts_scenes)
    shorts_target_ids = {int(s) for s in args.shorts_scenes.split(",")} if args.shorts_scenes else None

    def style_for_line(line: dict) -> str:
        base = cast[line["speaker"]]["style"]
        if line.get("tone"):
            base += f". For this line specifically: {line['tone']}"
        return base

    def line_sig(text: str, speaker: str, style: str) -> str:
        return json.dumps({"text": text, "speaker": speaker, "style": style,
                           "voice": cast[speaker]["voice"]}, ensure_ascii=False)

    def is_cached(text: str, speaker: str, style: str, out_path: Path) -> bool:
        stamp = out_path.with_suffix(".txt")
        return (not args.force and out_path.exists() and stamp.exists()
                and stamp.read_text(encoding="utf-8") == line_sig(text, speaker, style))

    # 読み照合QA（kl_reading_qa.py）。今回生成する行の「期待する読み」を、音声生成と並行して取得しておく。
    # 結果は narration/reading_qa.json に行ごとに残す（作り直さなかった行は前回の結果を引き継ぐ）。
    reading_qa = None
    reading_log_path = out_dir / "reading_qa.json"
    try:
        reading_log = json.loads(reading_log_path.read_text(encoding="utf-8"))
    except Exception:
        reading_log = {}
    if not args.no_reading_qa:
        todo = []
        if not shorts_only:
            for scene in ep["scenes"]:
                if target_ids is not None and scene["scene_id"] not in target_ids:
                    continue
                for k, line in enumerate(scene["lines"], start=1):
                    p = out_dir / f"S{scene['scene_id']:02d}_L{k:02d}.wav"
                    if not is_cached(line["text"], line["speaker"], style_for_line(line), p):
                        todo.append(line["text"])
        if shorts_only or args.scenes is None:
            main_texts = {(l["speaker"], l["text"]) for sc in ep["scenes"] for l in sc["lines"]}
            for shorts in ep.get("shorts", []):
                for i, s in enumerate(shorts["scenes"], start=1):
                    if shorts_target_ids is not None and i not in shorts_target_ids:
                        continue
                    if (s["narrator"], s["narration"]) in main_texts:
                        continue  # 本編の行を流用する
                    todo.append(s["narration"])
        if todo:
            try:
                import kl_reading_qa
                import torch  # noqa: F401（音素認識に必要。無ければ ImportError で照合なしに切り替える）
                import transformers  # noqa: F401
                reading_qa = kl_reading_qa.ReadingQA(genai.Client(api_key=API_KEY))
                reading_qa.prefetch_async(todo)
            except ImportError as e:
                print(f"⚠️ 読み照合QAを使えません（{e}）。pip3 install --user transformers で入ります。"
                      "今回は照合なしで続行します（--no-reading-qa で、この警告を消せます）")

    def save_reading_log():
        if reading_qa is not None:
            _atomic_write_json(reading_log_path, reading_log)

    def synth_line(text: str, speaker: str, style: str, out_path: Path) -> bool:
        if is_cached(text, speaker, style, out_path):
            return True
        ok = synth(client, text, cast[speaker]["voice"], out_path, style_override=style,
                   reading_qa=reading_qa, reading_log=reading_log)
        if ok:
            out_path.with_suffix(".txt").write_text(line_sig(text, speaker, style), encoding="utf-8")
            save_reading_log()
        return ok

    failed = []
    if not shorts_only:
        for scene in ep["scenes"]:
            sid = scene["scene_id"]
            if target_ids is not None and sid not in target_ids:
                continue
            wavs = []
            for k, line in enumerate(scene["lines"], start=1):
                p = out_dir / f"S{sid:02d}_L{k:02d}.wav"
                if not synth_line(line["text"], line["speaker"], style_for_line(line), p):
                    failed.append(p.name)
                wavs.append(p)
            if any(not p.exists() for p in wavs):
                print(f"❌ S{sid:02d}: 失敗した行があるためシーン音声を作れません", file=sys.stderr)
                continue
            timings = D.concat_line_wavs(wavs, scene["lines"], out_dir / f"S{sid:02d}.wav")
            for line, (t0, dur) in zip(scene["lines"], timings):
                line["t0"], line["dur"] = t0, dur
            scene["lines_hash"] = D.lines_hash(scene)
            print(f"   → S{sid:02d}.wav（{len(wavs)}行、{timings[-1][0] + timings[-1][1]:.1f}秒）")
            _atomic_write_json(ep_path, ep)

    if shorts_only or args.scenes is None:
        main_line_wav = {}
        for scene in ep["scenes"]:
            for k, line in enumerate(scene["lines"], start=1):
                main_line_wav[(line["speaker"], line["text"])] = out_dir / f"S{scene['scene_id']:02d}_L{k:02d}.wav"
        for shorts in ep.get("shorts", []):
            mid = shorts["shorts_id"]
            for i, s in enumerate(shorts["scenes"], start=1):
                if shorts_target_ids is not None and i not in shorts_target_ids:
                    continue
                out_path = out_dir / f"shorts{mid}_S{i:02d}.wav"
                reuse = main_line_wav.get((s["narrator"], s["narration"]))
                if reuse and reuse.exists():
                    shutil.copy(reuse, out_path)
                    if reuse.name in reading_log:
                        reading_log[out_path.name] = dict(reading_log[reuse.name], copied_from=reuse.name)
                    print(f"✅ {out_path.name}（本編{reuse.name}を流用）")
                    continue
                style = cast[s["narrator"]]["style"] + (f". For this line specifically: {s['tone']}" if s.get("tone") else "")
                if not synth_line(s["narration"], s["narrator"], style, out_path):
                    failed.append(out_path.name)
    if failed:
        print(f"\n⚠️ 失敗: {', '.join(failed)}", file=sys.stderr)
    if reading_qa is not None:
        save_reading_log()
        import kl_reading_qa
        n = kl_reading_qa.print_summary(reading_log, header="読みの不一致が残った行（作り直し上限後に採用）")
        print(f"\n読み照合QA: {len(reading_log)}行の記録 → {reading_log_path}"
              + (f"（不一致が残った行 {n}）" if n else "（不一致なし）")
              + f"、読みの取得 {reading_qa.llm_calls}回")
    print(f"\n完了。保存先: {out_dir}")


def main():
    parser = argparse.ArgumentParser(description="くらしを変える科学 ナレーション音声生成")
    parser.add_argument("--episode", required=True, help="エピソードID（例: kl001）")
    parser.add_argument("--scenes", help="生成するscene_idをカンマ区切りで指定（省略時は全シーン）")
    parser.add_argument("--shorts-only", action="store_true", help="Shortsのみ生成")
    parser.add_argument("--shorts-scenes", help="Shorts内の生成する番号をカンマ区切りで指定（例: 4）。指定時は自動的に--shorts-only扱い")
    parser.add_argument("--force", action="store_true",
                         help="--scenes未指定のフル実行で、既存ファイルがあっても全シーン再生成する（デフォルトは既存ファイルをスキップ）")
    parser.add_argument("--no-reading-qa", action="store_true",
                         help="読み照合QA（音素認識で台本の読みと照合し、不一致の行を作り直す。掛け合い形式のみ）を使わない")
    parser.add_argument("--skip-beginner-review", action="store_true",
                         help="初見レビュー（kl-new STEP5.5）が「済」でなくても続行する。rounds_v3・rounds_v4 の kl046 以降は、しばらくは必須"
                              "（なるさんの指示、2026-10-19）。制作者の了承なしに使わない。KL_SKIP_BEGINNER_REVIEW=1 でも同じ")
    args = parser.parse_args()

    # 初見レビューの確認は、APIキーの確認・ファイルの書き込み・API呼び出しより先に行う（2026-10-19）
    _ep_path = BASE_DIR / "episodes" / f"{args.episode}.json"
    if _ep_path.exists():
        import kl_dialogue as _D
        _D.enforce_beginner_review(json.loads(_ep_path.read_text()), args.episode,
                                   skip=args.skip_beginner_review, tool="kl_tts_gen.py")

    if not API_KEY:
        print("❌ GEMINI_API_KEY が設定されていません", file=sys.stderr)
        sys.exit(1)

    ep_path = BASE_DIR / "episodes" / f"{args.episode}.json"
    if not ep_path.exists():
        print(f"❌ {ep_path} がありません", file=sys.stderr)
        sys.exit(1)
    ep = json.loads(ep_path.read_text())

    if ep.get("format") == "dialogue":
        out_dir = DESKTOP_DIR / "narration"
        DESKTOP_DIR.mkdir(parents=True, exist_ok=True)
        guard_desktop_episode(DESKTOP_DIR, args.episode)
        out_dir.mkdir(parents=True, exist_ok=True)
        (DESKTOP_DIR / ".current_episode").write_text(args.episode, encoding="utf-8")
        client = genai.Client(api_key=API_KEY, http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))
        run_dialogue(args, ep, ep_path, client)
        return

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
    DESKTOP_DIR.mkdir(parents=True, exist_ok=True)
    guard_desktop_episode(DESKTOP_DIR, args.episode)
    out_dir.mkdir(parents=True, exist_ok=True)
    (DESKTOP_DIR / ".current_episode").write_text(args.episode, encoding="utf-8")

    client = genai.Client(api_key=API_KEY, http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))

    target_ids = None
    if args.scenes:
        target_ids = {int(s) for s in args.scenes.split(",")}

    shorts_only = args.shorts_only or bool(args.shorts_scenes)

    persona_style = voices.get("persona_style")

    # 「生成済みならスキップ」（2026-09-04〜、sc_tts_gen.pyと同じ考え方）:
    # --scenes未指定のフル実行では、既に音声が存在するシーンは再生成しない。
    skip_existing = target_ids is None and not args.force

    if not shorts_only:
        for scene in ep["scenes"]:
            sid = scene["scene_id"]
            if target_ids is not None and sid not in target_ids:
                continue
            out_path = out_dir / f"S{sid:02d}.wav"
            if skip_existing and out_path.exists():
                print(f"✅ {out_path.name}（既存ファイルをスキップ）")
                continue
            narrator = scene["narrator"]
            voice_name = voices[narrator]
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
                if skip_existing and not args.shorts_scenes and out_path.exists():
                    print(f"✅ {out_path.name}（既存ファイルをスキップ）")
                    continue
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
