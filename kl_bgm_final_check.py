"""
kl_bgm_final_check.py — 選定済みBGM3曲（intro/main/outro）の最終検証

samurai-chroniclesの sc_bgm_final_check.py と同じ仕組み。テキストベースの候補絞り込みを
終えたあと、実際の音声3曲 + 制作確認書全文を Gemini に渡し、トーン適合・3曲の流れ・
音質面を実音声ベースで最終判定する。

使い方:
  python3 kl_bgm_final_check.py --episode kl002
  python3 kl_bgm_final_check.py --episode kl035 --runs 3   # 掛け合い形式（既定3回）

掛け合い形式（episode.format == "dialogue"）は2026-10-06に作り直した（CLAUDE.md「BGMパイプライン」）:
- 役割ごとに5項目（役割への適合・台詞とぶつからないか・テンポの範囲・ループのつなぎ目・ボーカルの有無）を
  1〜5点のJSONで出させ、温度0で --runs 回実行して項目ごとの中央値で判定する（同じ曲の組合せで
  「採用」と「差し替え推奨」が出るほど自由記述の判定がぶれていたため）
- 合格条件: 役割ごとに全項目3点以上、かつ5項目の平均3.5以上。3役割とも合格なら「合格」
- 2段階: (1) 狙いを伝えずに曲単体（頭30秒）を聴き取らせ、楽器・ビートの有無・声の有無・推定BPMを得る
  （狙いを先に伝えると、オルゴールを「シンセとビート」と書いて満点を付けることが実測で起きたため）。
  (2) 聴き取り結果＋ミックス＋つなぎ目で採点する。声あり→vocals=1、intro/main でビートなし→role_fit≦2、
  BPMはファイル名・メタ情報で分かればそれ、無ければ聴き取りの中央値でテンポを機械的に採点する
- 聴かせる音声: 役割ごとに「その区間の台詞（Drive の narration/S{id}.wav を並べた頭30秒）に、
  BGMを動画と同じ音量（kl_video_gen.BGM_VOLUME）で重ねた簡易ミックス」。曲が区間より短い場合は、
  kl_video_gen.make_seamless_bgm で作ったループのつなぎ目の前後12秒も聴かせる。
  台詞の音声が無い場合は曲単体（頭45秒）で判定する
- 最終行は「最終判定: 合格」か「最終判定: 要差し替え（main, outro）」
旧形式（format が無い回）は従来どおり制作確認書＋3曲の自由記述（PROMPT）。
"""
import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path
from google import genai

API_KEY = os.environ.get("GEMINI_API_KEY_KL") or os.environ.get("GEMINI_API_KEY", "")
MODEL = os.environ.get("KL_BGM_CHECK_MODEL", "gemini-flash-latest")  # --model でも切り替え可（2026-10-06）

DESKTOP_KL = Path(os.path.expanduser("~/Desktop/kagaku-life"))

PROMPT = """あなたは「幸せな未来のサイエンスチャンネル」（AI・ロボティクス研究解説×
使い捨ての生活者による物語演出、日本語YouTubeチャンネル）の音楽監督です。
以下に添付するのは、{episode}エピソードの完全な制作確認書と、このエピソードのBGMとして
選定された3曲の実音声です（intro→main→outroの順にクロスフェードでつながる3曲構成）。

【制作確認書】
{review_doc}

【添付音声】
1. intro（序盤 teaser〜citation 用）
2. main（中盤 context〜data、主人公の悩み〜研究紹介 用）
3. outro（終盤 impact〜closing、未来の暮らし〜締め 用）

以下を実際に聴いた上で判定してください：

1. 各曲は「温かく、希望が持てる、押し付けがましくない」というチャンネル方針に合致しているか
   （SF的に冷たい/大仰に壮大すぎる/悲壮すぎる曲は不適切）
2. 各曲のトーン・テンポ・感情が、対応するシーン群のナレーション内容に合っているか
   （introは好奇心・導入、mainは共感できる悩みから研究紹介への高まり、outroは
   温かい余韻・小さな幸せ）
3. intro→main→outroの3曲を通して聴いたとき、感情の流れに破綻がないか。
   特に3曲間の調性・音圧・テンポの落差が急激すぎないか
4. 音質面で気になる点（ループノイズ、フェードの唐突さ、ラウドネスの著しい差など）
5. 総合判定：このまま採用してよいか、どれか差し替えるべきか

日本語で、各曲ごとの評価→総合判定の順に、簡潔に（600字程度）回答してください。
"""


# 掛け合い形式（2026-10-04〜）用。制作確認書の代わりに台本（シーンごとの役割と台詞）を渡す。
# main（ツッコミ・答え合わせ）は軽い緊張感を許可している（CLAUDE.md「掛け合い形式への転換」）。
# 掛け合い形式のBGM方針（CLAUDE.md「BGMパイプライン」2026-10-06）
ROLE_SPEC = {
    "intro": {"bpm": (105, 125), "desc": "冒頭の問い〜研究紹介〜夢語り。ニュースの引き・『何それ？』のワクワク。明るい長調、"
              "シンセのアルペジオ／プラック＋軽いビート。頭の2〜4小節で立ち上がる（長い前奏は不可）"},
    "main": {"bpm": (80, 100), "desc": "ツッコミ・答え合わせ。考える・確かめるときの軽い緊張と遊び。lo-fi／ヒップホップのビート、"
             "ピチカート、ミュートしたシンセベース。メロディは薄く、繰り返しが主役"},
    "outro": {"bpm": (85, 100), "desc": "判定〜締め。判定の決着感と、次回への軽い余韻。introと同系統の明るさを少し落ち着かせたもの"
              "（エレピ／ピアノ＋軽いビート）。泣きのストリングスや盛り上がりは不可"},
}
CRITERIA = ["role_fit", "dialogue_clash", "tempo", "loop_seam", "vocals"]
CRITERIA_JA = {"role_fit": "役割への適合", "dialogue_clash": "台詞とぶつからない", "tempo": "テンポの範囲",
               "loop_seam": "ループのつなぎ目", "vocals": "ボーカルなし"}
PASS_MIN_EACH = 3
PASS_MIN_AVG = 3.5
MIX_SECONDS = 30
SEAM_WINDOW = 6.0  # つなぎ目の前後それぞれの秒数
DEFAULT_RUNS = 3

DIALOGUE_PROMPT = """あなたは日本語の科学解説YouTubeチャンネル「幸せな未来のサイエンス」の音楽監督です。
番組は、夢語り担当（元エンジニアの男性）とツッコミ担当（統計に強い女性）の二人が、ニュースや論文を一次資料で確かめ、
最後に「もうすぐ来る／3年はかかる／まだ眉唾」を判定する掛け合い形式です。
BGMの方針: BGMは二人の会話のテンポを支えるリズム。感情を語るのは台詞。前向きで押し付けがましくないこと。
ジャンルや判定で曲調は変えない。不合格: ボーカル（ハミング・「オー」も不可）、壮大・オーケストラ、泣きのストリングス、
短調の悲しい曲、ホラー調、攻撃的なEDM、曲中の無音・テンポ変化・ドロップ、環境音の混入、オルゴールや遅いソロピアノ。

【{episode} の台本（シーンごとのBGMの役割と台詞）】
{review_doc}

【各役割の狙いと区間】
{role_specs}

【各曲の聴き取り結果】（狙いを伝えずに、曲単体の頭{mix_seconds}秒を別に聴いて書き取ったもの。曲調・楽器・ビートの有無は
これを正とする。上の「役割の狙い」は理想の説明であり、添付の曲がそうであるとは限らない）
{descriptions}

添付する音声（役割ごと）:
- 「ミックス」: その区間の台詞の頭{mix_seconds}秒に、BGMを実際の動画と同じ小さめの音量で重ねたもの（台詞とぶつかるかの判断用）
- 「つなぎ目」: 曲が区間より短くループさせる場合だけ。ループのつなぎ目を中央に置いた{seam_total:.0f}秒

role_fit は聴き取り結果と狙いを比べて付けること。狙いと違う楽器（例: オルゴール、ソロピアノ、ストリングス、
アコースティックギターの弾き語り風）やビートの無い曲は、role_fit を2以下にする。

各役割について、次の5項目を1〜5点（5=問題なし、3=許容、2以下=差し替えが必要）で採点してください。
- role_fit: 上記の役割の狙いに合っているか
- dialogue_clash: 台詞の聞き取りを邪魔しないか（台詞の帯域で鳴り続けるリード楽器・強い主旋律・派手な展開は減点）
- tempo: テンポが役割のBPM範囲に収まっているか（推定BPMも答える。範囲から10以上外れたら2以下）
- loop_seam: 「つなぎ目」の音声で、ループの継ぎ目が気にならないか（つなぎ目の音声が無い役割は5）
- vocals: 人の声（歌・語り・ハミング・声のサンプル）が無いか（聞こえたら1）

次のJSONだけを返してください（説明文やコードブロックは不要）:
{{"intro": {{"role_fit": n, "dialogue_clash": n, "tempo": n, "loop_seam": n, "vocals": n, "bpm_estimate": n, "comment": "日本語で1文"}},
 "main": {{...同じ形...}},
 "outro": {{...同じ形...}},
 "flow_comment": "3曲を続けて聴いたときの調性・音圧・テンポの落差について日本語で1〜2文"}}
"""


# 1段目: 狙いを伝えずに曲単体を聴き取らせる（2026-10-06）。狙い（「明るいシンセ＋軽いビート」）を
# 先に伝えると、オルゴールの曲を「シンセプラックと軽快なビート」と書き、全項目5点を付けることが実測で起きた
# （狙いを伝えずに同じ曲を聴かせると「オルゴールのみ、ドラムなし」と正しく答える）。
DESCRIBE_PROMPT = (
    "Listen to this music clip carefully. Describe only what you actually hear. "
    "Respond with ONLY a JSON object: "
    '{"instruments": "楽器と曲調を日本語で1文", "has_beat": true/false (is there a drum/percussion beat?), '
    '"has_vocals": true/false (any human voice: singing, speech, humming, vocal samples), '
    '"bpm_estimate": number or null}'
)


def describe_track(client, solo_bytes: bytes) -> dict:
    resp = client.models.generate_content(
        model=MODEL,
        contents=[DESCRIBE_PROMPT, genai.types.Part.from_bytes(data=solo_bytes, mime_type="audio/mpeg")],
        config=genai.types.GenerateContentConfig(temperature=0, response_mime_type="application/json"))
    return _parse_json(resp.text)


def _probe(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _ffmpeg(args: list) -> bool:
    return subprocess.run(["ffmpeg", "-y", "-v", "error"] + args, capture_output=True).returncode == 0


def section_info(ep: dict) -> dict:
    """役割ごとの (シーンIDのリスト, おおよその区間の長さ秒)。台詞の dur の合計＋シーンの前後の余白。"""
    import kl_dialogue as D
    out = {r: {"scene_ids": [], "dur": 0.0} for r in ROLE_SPEC}
    for s in ep.get("scenes", []):
        r = D.scene_bgm_role(s)
        if r not in out:
            continue
        out[r]["scene_ids"].append(s["scene_id"])
        out[r]["dur"] += sum(float(l.get("dur") or 0) for l in s.get("lines", [])) + 1.5
    return out


def find_narration_dir(episode: str) -> Path:
    try:
        import kl_video_gen as V
        cands = [V.DRIVE_BASE / episode / "narration", V.DESKTOP_DIR / "narration"]
    except Exception:
        cands = [DESKTOP_KL / "narration"]
    for c in cands:
        try:
            if (c / "S01.wav").exists():
                return c
        except OSError:
            continue
    return None


def build_role_audio(role: str, track: Path, scene_ids: list, narr_dir: Path, section_dur: float, work: Path) -> list:
    """(曲単体のmp3バイト列, [(ラベル, mp3バイト列)]) 。後者はミックスと（必要なら）つなぎ目。"""
    import kl_video_gen as V
    parts = []
    solo = work / f"{role}_solo.mp3"
    _ffmpeg(["-i", str(track), "-t", str(MIX_SECONDS), "-b:a", "128k", str(solo)])
    solo_bytes = solo.read_bytes() if solo.exists() else track.read_bytes()
    wavs = [narr_dir / f"S{sid:02d}.wav" for sid in scene_ids] if narr_dir else []
    wavs = [w for w in wavs if w.exists()]
    mix = work / f"{role}_mix.mp3"
    ok = False
    if wavs:
        inputs = []
        for w in wavs:
            inputs += ["-i", str(w)]
        n = len(wavs)
        concat = "".join(f"[{i}:a]aresample=44100,aformat=channel_layouts=stereo[a{i}];" for i in range(n)) + \
            "".join(f"[a{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[narr]"
        fc = (f"{concat};[narr]atrim=duration={MIX_SECONDS}[n2];"
              f"[{n}:a]aloop=loop=-1:size=2000000000,atrim=duration={MIX_SECONDS},aresample=44100,"
              f"aformat=channel_layouts=stereo,volume={V.BGM_VOLUME}[b];"
              f"[n2][b]amix=inputs=2:duration=longest:normalize=0[out]")
        ok = _ffmpeg(inputs + ["-i", str(track), "-filter_complex", fc, "-map", "[out]",
                               "-t", str(MIX_SECONDS), "-b:a", "128k", str(mix)])
    if ok:
        parts.append((f"「{role}」のミックス（台詞＋BGM、頭{MIX_SECONDS}秒）", mix.read_bytes()))

    track_dur = _probe(track)
    if track_dur and track_dur < section_dur:
        looped = V.make_seamless_bgm(track, track_dur * 2, work / "loops", role)
        if looped != track:
            seam = _probe(work / "loops" / f"{role}_trimmed.wav") - min(V.BGM_LOOP_XFADE, track_dur / 4) / 2
            clip = work / f"{role}_seam.mp3"
            if _ffmpeg(["-ss", f"{max(0.0, seam - SEAM_WINDOW):.2f}", "-t", f"{SEAM_WINDOW * 2:.2f}",
                        "-i", str(looped), "-b:a", "128k", str(clip)]):
                parts.append((f"「{role}」のループのつなぎ目（中央がつなぎ目）", clip.read_bytes()))
    return solo_bytes, parts


def known_bpm(track: Path) -> float:
    """機械的に分かるBPM（ファイル名・Freesoundのメタ情報・ライブラリの bpm）。分からなければ None。

    モデルの推定BPMは当てにならない（kl034 main の「Lofi Beat C Major 70bpm」を88と推定した）ため、
    分かる場合はテンポの採点をこちらで置き換える。
    """
    texts = [track.stem]
    m = re.search(r"_candidate_\d+_(\d+)_", track.stem)
    for key in ([track.stem] + ([f"id_{m.group(1)}"] if m else [])):
        meta = Path(f"/tmp/kl_bgm_credits/{key}.meta.json")
        if meta.exists():
            try:
                d = json.loads(meta.read_text(encoding="utf-8"))
                texts += [d.get("source_name") or ""] + list(d.get("tags") or [])
            except (OSError, json.JSONDecodeError):
                pass
    lib = Path(__file__).parent / "bgm_library.json"
    lm = re.search(r"(kl\d{3}-BGM-(?:intro|main|outro))", track.stem)
    if lm and lib.exists():
        entry = next((e for e in json.loads(lib.read_text(encoding="utf-8")) if e["id"] == lm.group(1)), None)
        if entry and entry.get("bpm"):
            return float(entry["bpm"])
        if entry:
            texts += [entry.get("source_name") or "", entry.get("credit") or ""]
    for t in texts:
        mm = re.search(r"(\d{2,3})\s*-?\s*bpm", str(t).lower())
        if mm and 40 <= int(mm.group(1)) <= 200:
            return float(mm.group(1))
    return None


def tempo_score(bpm: float, lo: int, hi: int) -> float:
    if lo <= bpm <= hi:
        return 5.0
    gap = lo - bpm if bpm < lo else bpm - hi
    return 3.0 if gap <= 5 else (2.0 if gap <= 10 else 1.0)


def _parse_json(text: str) -> dict:
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    m = re.search(r"\{.*\}", t, re.S)
    return json.loads(m.group(0) if m else t)


def run_dialogue_check(client, episode: str, ep: dict, tracks: dict, runs: int) -> int:
    import kl_dialogue as D
    cast = D.load_cast()
    review_text = "\n\n".join(
        f"S{s['scene_id']:02d} [{s['type']} / BGM:{D.scene_bgm_role(s)}]\n{D.scene_text(s, cast)}"
        for s in ep["scenes"])
    sections = section_info(ep)
    narr_dir = find_narration_dir(episode)
    if not narr_dir:
        print("⚠️  台詞の音声（narration/S01.wav）が見つからないため、曲単体で判定します")

    track_durs = {r: _probe(p) for r, p in tracks.items()}
    spec_lines = []
    for r, spec in ROLE_SPEC.items():
        lo, hi = spec["bpm"]
        sd, td = sections[r]["dur"], track_durs[r]
        loop_note = f"曲{td:.0f}秒 < 区間 → 約{sd / td:.1f}回ループ" if td and td < sd else f"曲{td:.0f}秒（ループなし）"
        spec_lines.append(f"- {r}: {spec['desc']}。目安 {lo}〜{hi} BPM。区間の長さ 約{sd:.0f}秒、{loop_note}")
        print(f"  {r}: {tracks[r].name}  区間 約{sd:.0f}秒 / {loop_note}")

    with tempfile.TemporaryDirectory() as tmp_str:
        work = Path(tmp_str)
        solos, audio_parts = {}, []
        for r in ROLE_SPEC:
            solos[r], role_parts = build_role_audio(r, tracks[r], sections[r]["scene_ids"], narr_dir,
                                                    sections[r]["dur"], work)
            for label, data in role_parts:
                audio_parts.append(f"\n--- 以下は{label} ---\n")
                audio_parts.append(genai.types.Part.from_bytes(data=data, mime_type="audio/mpeg"))

        results, descs = [], {r: [] for r in ROLE_SPEC}
        for i in range(runs):
            try:
                run_desc = {r: describe_track(client, solos[r]) for r in ROLE_SPEC}
                for r in ROLE_SPEC:
                    descs[r].append(run_desc[r])
                desc_text = "\n".join(
                    f"- {r}: {d.get('instruments')}／ビート{'あり' if d.get('has_beat') else 'なし'}／"
                    f"声{'あり' if d.get('has_vocals') else 'なし'}／推定BPM {d.get('bpm_estimate')}"
                    for r, d in run_desc.items())
                prompt = DIALOGUE_PROMPT.format(
                    episode=episode, review_doc=review_text, role_specs="\n".join(spec_lines),
                    descriptions=desc_text, mix_seconds=MIX_SECONDS, seam_total=SEAM_WINDOW * 2)
                resp = client.models.generate_content(
                    model=MODEL, contents=[prompt] + audio_parts,
                    config=genai.types.GenerateContentConfig(temperature=0, response_mime_type="application/json"))
                res = _parse_json(resp.text)
                # 聴き取り結果からの機械的な上限（プロンプトの指示だけに頼らない）
                for r, d in run_desc.items():
                    sc = res.setdefault(r, {})
                    if d.get("has_vocals") is True:
                        sc["vocals"] = 1
                    if d.get("has_beat") is False and r in ("intro", "main") \
                            and isinstance(sc.get("role_fit"), (int, float)):
                        sc["role_fit"] = min(sc["role_fit"], 2)
                    if isinstance(d.get("bpm_estimate"), (int, float)):
                        sc["bpm_estimate"] = d["bpm_estimate"]
                    sc["heard"] = d.get("instruments")
                results.append(res)
                print(f"  判定 {i + 1}/{runs} 完了")
            except Exception as e:
                print(f"  ⚠️ 判定 {i + 1}/{runs} 失敗: {e}")
    if not results:
        print("❌ 判定を1回も取得できませんでした")
        print("最終判定: 判定不能")
        return 2

    failed = []
    print(f"\n{'━' * 60}\n  BGM最終検証（{episode}、{len(results)}回の中央値）\n{'━' * 60}")
    for r in ROLE_SPEC:
        med = {}
        for c in CRITERIA:
            vals = [float(x.get(r, {}).get(c)) for x in results
                    if isinstance(x.get(r, {}).get(c), (int, float))]
            med[c] = statistics.median(vals) if vals else 0.0
        bpms = [x.get(r, {}).get("bpm_estimate") for x in results
                if isinstance(x.get(r, {}).get("bpm_estimate"), (int, float))]
        kb = known_bpm(tracks[r])
        if kb:
            med["tempo"] = tempo_score(kb, *ROLE_SPEC[r]["bpm"])
            bpms = [kb]
        if kb is None and bpms:
            # 聴き取りの推定BPMの中央値でテンポを機械的に採点する（モデルの自己採点より一貫する）
            med["tempo"] = min(med["tempo"], tempo_score(statistics.median(bpms), *ROLE_SPEC[r]["bpm"]))
        avg = sum(med.values()) / len(CRITERIA)
        ok = all(v >= PASS_MIN_EACH for v in med.values()) and avg >= PASS_MIN_AVG
        if not ok:
            failed.append(r)
        spread = {c: sorted(float(x.get(r, {}).get(c, 0) or 0) for x in results) for c in CRITERIA}
        print(f"\n[{r}] {tracks[r].name} — {'合格' if ok else '要差し替え'}（平均 {avg:.2f}）"
              f"  {'BPM（ファイル名・メタ情報）' if kb else '推定BPM（モデル）'} {statistics.median(bpms):.0f}"
              f"（目安 {ROLE_SPEC[r]['bpm'][0]}〜{ROLE_SPEC[r]['bpm'][1]}）" if bpms else
              f"\n[{r}] {tracks[r].name} — {'合格' if ok else '要差し替え'}（平均 {avg:.2f}）")
        for c in CRITERIA:
            mark = "  " if med[c] >= PASS_MIN_EACH else "✗ "
            print(f"   {mark}{CRITERIA_JA[c]}: {med[c]:.1f}  （各回 {spread[c]}）")
        heard = [x.get(r, {}).get("heard") for x in results if x.get(r, {}).get("heard")]
        if heard:
            print(f"   聞こえた音: {heard[0]}")
        comments = [x.get(r, {}).get("comment") for x in results if x.get(r, {}).get("comment")]
        if comments:
            print(f"   コメント: {comments[0]}")
    flows = [x.get("flow_comment") for x in results if x.get("flow_comment")]
    if flows:
        print(f"\n3曲の流れ: {flows[0]}")
    print("\n人が聴いて確かめる箇所: 各区間の頭15秒、mainのループのつなぎ目、introからmainへの切り替わり")
    print(f"\n最終判定: {'合格' if not failed else '要差し替え（' + ', '.join(failed) + '）'}")
    return 0 if not failed else 1


def find_role_file(bgm_dir: Path, role: str) -> Path:
    matches = sorted(bgm_dir.glob(f"{role}_*.mp3"))
    if not matches:
        print(f"❌ {role} の音声ファイルが見つかりません: {bgm_dir}", file=sys.stderr)
        sys.exit(1)
    if len(matches) > 1:
        print(f"⚠️  {role} に複数ファイルがあります。最初の1件を使用: {matches[0].name}", file=sys.stderr)
    return matches[0]


def main():
    global MODEL
    parser = argparse.ArgumentParser(description="選定済みBGM3曲の最終検証（実音声+台本をGeminiに渡す）")
    parser.add_argument("--episode", required=True, help="エピソードID（例: kl002）")
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS, help="掛け合い形式の判定回数（中央値を取る）")
    parser.add_argument("--model", help=f"判定に使うモデル（既定 {MODEL}）")
    parser.add_argument("--bgm-dir", help="intro_*.mp3 / main_*.mp3 / outro_*.mp3 を置いたフォルダ（既定 ~/Desktop/kagaku-life/BGM）")
    args = parser.parse_args()

    if not API_KEY:
        print("❌ GEMINI_API_KEY が設定されていません", file=sys.stderr)
        sys.exit(1)

    if args.model:
        MODEL = args.model
    ep_path = Path(__file__).parent / "episodes" / f"{args.episode}.json"
    ep = json.loads(ep_path.read_text(encoding="utf-8")) if ep_path.exists() else {}

    bgm_dir = Path(os.path.expanduser(args.bgm_dir)) if args.bgm_dir else DESKTOP_KL / "BGM"
    tracks = {
        "intro": find_role_file(bgm_dir, "intro"),
        "main": find_role_file(bgm_dir, "main"),
        "outro": find_role_file(bgm_dir, "outro"),
    }
    client = genai.Client(api_key=API_KEY)

    if ep.get("format") == "dialogue":
        sys.exit(run_dialogue_check(client, args.episode, ep, tracks, max(1, args.runs)))

    # 旧形式（kl001〜kl030）: 制作確認書＋3曲の自由記述
    review_path = DESKTOP_KL / f"{args.episode}_制作確認書.txt"
    if not review_path.exists():
        print(f"❌ 制作確認書が見つかりません: {review_path}", file=sys.stderr)
        print(f"  先に kl_confirmation_doc.py --episode {args.episode} を実行してください", file=sys.stderr)
        sys.exit(1)
    review_text = review_path.read_text(encoding="utf-8")
    parts = [PROMPT.format(episode=args.episode, review_doc=review_text)]
    for role, path in tracks.items():
        parts.append(f"\n--- 以下は「{role}」用の音声（{path.name}）です ---\n")
        parts.append(genai.types.Part.from_bytes(data=path.read_bytes(), mime_type="audio/mpeg"))
    response = client.models.generate_content(model=MODEL, contents=parts)
    print(response.text)


if __name__ == "__main__":
    main()
