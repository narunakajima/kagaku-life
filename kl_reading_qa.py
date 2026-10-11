"""
kl_reading_qa.py — 台詞音声の「読み」照合QA（2026-10-11追加）

Gemini TTS がたまに起こす読み間違い（「同じ」→「おのじ」、「外骨格」→「がいこくかく」、
「脚」→「きゃく」、「45歳」→「54歳」など）を、行ごとに見つける。

なぜこの方式か（調査・試験の記録は kl-new.md STEP 8 の注記と、作成時の報告を参照）:
  Gemini（音声理解）や Whisper は文脈から「正しい語」へ補正して書き起こすため、1音の違いを
  見逃しやすい。そこで、言語モデルを持たない CTC の音素認識
  （prj-beatrice/japanese-hubert-base-phoneme-ctc-v4、Apache-2.0、約380MB）で
  「聞こえたとおりの音素」を出し、台本の期待する読み（LLM＝Gemini Pro がテキストだけを見て
  文脈込みで決めたカタカナ）と、行の中の局所的な差（ポケット）ごとに比べる。

  ・ポケットごとに、CTC の尤度で「期待する読み」と「認識された音」のどちらが音声に合うかを
    比べ（delta = 期待の損失 − 置き換えた列の損失、単位 nat）、差がしきい値を超えたものだけを
    不一致とする。認識のぶれ（どちらの読みでも大差なく説明できる）を誤検知しないため。
  ・長音・「おう/おー」「えい/えー」「いう/ゆう」・数字の促音便（イチテン/イッテン）は
    同じものとして扱う。無声化母音・ポーズの違いも吸収する。
  ・数字（算用数字・年齢・割合など）は、LLM が出した数字ごとの読みの範囲に差が重なれば、
    低いしきい値で「数字の不一致」として別枠で判定する。

限界（試験で確認したもの）:
  ・TTS が台本にない無意味な綴り（例「おのじ」）を渡されても正しい語に直して読むため、
    「1音違い」の人工試験は実在の語どうし（たいじゅう/たいじょう 等）でしか作れなかった。
  ・長音の脱落（どうして→どして）は、ゆれとして吸収するので検出しない。
  ・非常に速い発話（8モーラ/秒超）では音素認識が音を落とし、誤検知が出ることがある。
    認識した音素が期待の75%未満なら、音声を0.8倍速に伸ばして認識し直す。
  ・期待する読みは LLM が決めるので、LLM の読み自体が誤っていると誤検知になる
    （例: 推測→スイスク）。Gemini Pro を使い、別の読みも許容する（alt）ことで減らしている。
"""

import difflib
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

import numpy as np

# ── 設定 ─────────────────────────────────────────────
MODEL_ID = "prj-beatrice/japanese-hubert-base-phoneme-ctc-v4"
MODEL_REVISION = "f5fe07043bcb0b77a86faf72ac6d8fc1ae558f99"  # 2025-10-06版に固定
HF_HOME = Path(os.environ.get("KL_READING_QA_HF_HOME", Path.home() / ".cache" / "kl_reading_qa_hf"))
# transformers の一部の処理は cache_dir を渡しても既定の ~/.cache/huggingface を見に行くため、
# 取り込みより前に専用フォルダを指定しておく（kl_tts_gen.py は torch/transformers より先にこのモジュールを読む）
os.environ.setdefault("HF_HUB_CACHE", str(HF_HOME / "hub"))
READING_MODEL = "gemini-pro-latest"   # 期待する読み（テキストのみ）。flash は読み誤りが多かった
READING_CACHE = Path.home() / ".cache" / "kl_reading_qa" / "readings.json"
READING_BATCH = 30                    # 1回の LLM 呼び出しで読む台詞数
READING_WORKERS = 4                   # 並列に投げる呼び出し数
READING_TIMEOUT_MS = 600_000
DELTA_THRESHOLD = 4.5                 # ポケットの不一致判定（nat）。試験で実在の誤読（リバプール→リパブール）が4.8
NUMBER_DELTA_THRESHOLD = 2.0          # 数字の範囲に重なるポケット
SLOW_RETRY_RATIO = 0.75               # 認識音素数/期待音素数 がこれ未満なら 0.8 倍速で再認識
POCKET_MERGE_GAP = 3                  # 間の一致がこの数以下の差はまとめる（45→54 の入れ替わり対策）
PROMPT_VERSION = "2026-10-11-v1"

# ── カナ → 音素（OpenJTalk 風。認識モデルの語彙と同じ）──────────────
_V = {"ア": "a", "イ": "i", "ウ": "u", "エ": "e", "オ": "o"}
_ROWS = {
    "カキクケコ": "k", "ガギグゲゴ": "g", "サシスセソ": "s", "ザジズゼゾ": "z",
    "タチツテト": "t", "ダヂヅデド": "d", "ナニヌネノ": "n", "ハヒフヘホ": "h",
    "バビブベボ": "b", "パピプペポ": "p", "マミムメモ": "m", "ラリルレロ": "r",
}
MORA = {k: [v] for k, v in _V.items()}
for _row, _c in _ROWS.items():
    for _ch, _v in zip(_row, "aiueo"):
        MORA[_ch] = [_c, _v]
MORA.update({
    "シ": ["sh", "i"], "ジ": ["j", "i"], "チ": ["ch", "i"], "ツ": ["ts", "u"], "ヂ": ["j", "i"],
    "ヅ": ["z", "u"], "フ": ["f", "u"], "ヤ": ["y", "a"], "ユ": ["y", "u"], "ヨ": ["y", "o"],
    "ワ": ["w", "a"], "ヲ": ["o"], "ヰ": ["i"], "ヱ": ["e"], "ン": ["N"], "ッ": ["cl"], "ヴ": ["v", "u"],
    "ァ": ["a"], "ィ": ["i"], "ゥ": ["u"], "ェ": ["e"], "ォ": ["o"], "ャ": ["y", "a"], "ュ": ["y", "u"],
    "ョ": ["y", "o"], "ヮ": ["w", "a"], "ヵ": ["k", "a"], "ヶ": ["k", "e"],
})
for _ch, _c in {"キ": "ky", "ギ": "gy", "シ": "sh", "ジ": "j", "チ": "ch", "ニ": "ny", "ヒ": "hy",
                "ビ": "by", "ピ": "py", "ミ": "my", "リ": "ry", "ヂ": "j"}.items():
    for _sm, _v in (("ャ", "a"), ("ュ", "u"), ("ョ", "o")):
        MORA[_ch + _sm] = [_c, _v]
for _ch, _c in (("シ", "sh"), ("ジ", "j"), ("チ", "ch")):
    MORA[_ch + "ェ"] = [_c, "e"]
MORA.update({
    "ティ": ["t", "i"], "ディ": ["d", "i"], "トゥ": ["t", "u"], "ドゥ": ["d", "u"],
    "テュ": ["ty", "u"], "デュ": ["dy", "u"], "ファ": ["f", "a"], "フィ": ["f", "i"],
    "フェ": ["f", "e"], "フォ": ["f", "o"], "フュ": ["fy", "u"], "ウィ": ["w", "i"],
    "ウェ": ["w", "e"], "ウォ": ["w", "o"], "ヴァ": ["v", "a"], "ヴィ": ["v", "i"],
    "ヴェ": ["v", "e"], "ヴォ": ["v", "o"], "ツァ": ["ts", "a"], "ツィ": ["ts", "i"],
    "ツェ": ["ts", "e"], "ツォ": ["ts", "o"], "クァ": ["kw", "a"], "グァ": ["gw", "a"],
    "イェ": ["y", "e"], "スィ": ["s", "i"], "ズィ": ["z", "i"],
})
VOWELS = set("aiueo")


def to_katakana(s: str) -> str:
    return "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in s)


def kana_to_phonemes(kana: str) -> list:
    """カタカナ（ひらがな可）→ 音素列。長音「ー」は直前の母音を繰り返す。カナ以外は捨てる。"""
    s = to_katakana(kana)
    out, i = [], 0
    while i < len(s):
        if s[i:i + 2] in MORA and len(s[i:i + 2]) == 2:
            out += MORA[s[i:i + 2]]
            i += 2
            continue
        ch = s[i]
        if ch == "ー":
            last = next((p for p in reversed(out) if p in VOWELS), None)
            if last:
                out.append(last)
        elif ch in MORA:
            out += MORA[ch]
        i += 1
    return out


def tolerant(seq: list):
    """自然なゆれを吸収した列と、各要素の元の位置（seq の添字）を返す。
    同じ母音の連続（長音）→1つ、オウ→オ、エイ→エ、母音だけのイ＋ウ→ユウ（「いう/ゆう」）。"""
    out, idx = [], []
    vowel_end = False
    for j, t in enumerate(seq):
        if t in VOWELS and out and out[-1] in VOWELS and vowel_end:
            last = out[-1]
            if t == last or (last == "o" and t == "u") or (last == "e" and t == "i"):
                continue
            if last == "i" and t == "u" and (len(out) < 2 or out[-2] in VOWELS or out[-2] in ("N", "cl")):
                out[-1] = "y"
                out.append("u")
                idx.append(j)
                continue
        out.append(t)
        idx.append(j)
        vowel_end = t in VOWELS
    return out, idx


def find_pockets(exp: list, rec: list, gap: int = POCKET_MERGE_GAP):
    """行の中の局所的な差の塊 [(a0, a1, b0, b1)]。間の一致が gap 以下の差はまとめる。"""
    sm = difflib.SequenceMatcher(None, exp, rec, autojunk=False)
    merged = []
    for tag, a0, a1, b0, b1 in sm.get_opcodes():
        if tag == "equal":
            continue
        if merged and a0 - merged[-1][1] <= gap and b0 - merged[-1][3] <= gap:
            m = merged[-1]
            merged[-1] = (m[0], a1, m[2], b1)
        else:
            merged.append((a0, a1, b0, b1))
    return merged


def is_number_sokuon(exp, rec, p) -> bool:
    """数字の促音便（イチ→イッ、ハチ→ハッ、ロク→ロッ）。例: 1.1キロ イチテン／イッテン"""
    a0, a1, b0, b1 = p
    if rec[b0:b1] != ["cl"]:
        return False
    e, pre = exp[a0:a1], exp[max(0, a0 - 2):a0]
    return (e == ["ch", "i"] and (pre[-1:] == ["i"] or pre == ["h", "a"])) or (e == ["k", "u"] and pre == ["r", "o"])


def _find_sub(seq: list, sub: list, start: int = 0) -> int:
    n = len(sub)
    for i in range(start, len(seq) - n + 1):
        if seq[i:i + n] == sub:
            return i
    return -1


# ── 期待する読み（LLM、テキストのみ）────────────────────────
_PROMPT = """以下は日本語の台詞です。各台詞を、標準的なアナウンサーが文脈に沿って自然に読み上げたときの発音を、カタカナだけで書いてください。
規則:
- 助詞の「は」は「ワ」、「へ」は「エ」、「を」は「オ」と書く。長音は「ー」で書く（例: 東京→トーキョー、体重→タイジュー、先生→センセー）。
- 数字・記号・英字・単位もすべて読みに直す（例: 45歳→ヨンジューゴサイ、44.6%→ヨンジューヨンテンロクパーセント、WHO→ダブリューエイチオー、330ミリリットル→サンビャクサンジューミリリットル）。
- 漢字の読みは文脈で決める（例: 「脚」が人の足の意味ならアシ、「人気のない夜道」ならヒトケ）。
- 台詞の文字を飛ばさない。助詞も1文字ずつ必ず書く。句読点・記号・空白は書かない。
- 読み方が2通り以上ありうる語（例: 1日→イチニチ／ツイタチ、博士→ハカセ／ハクシ、人数→ニンズー／ニンスー、寝てる間→アイダ／マ、1.1→イッテンイチ／イチテンイチ）は、もっとも自然な読みを "kana" に、他にも正しいと言える読みがあれば、その読みにした台詞全体を "alt" に配列で入れる（最大3つ）。なければ "alt" は空配列。
- 台詞に算用数字・漢数字の数量（年齢・人数・割合・日付・金額など）があれば、"numbers" に [{"text": 台詞中の表記, "kana": その部分の読み, "alt": [別の正しい読み]}] を入れる。なければ空配列。
出力はJSON配列のみ: [{"id": "...", "kana": "...", "alt": [], "numbers": []}, ...]

台詞:
"""


def _response_schema():
    from google.genai import types
    S, T = types.Schema, types.Type
    strs = S(type=T.ARRAY, items=S(type=T.STRING))
    num = S(type=T.OBJECT, properties={"text": S(type=T.STRING), "kana": S(type=T.STRING), "alt": strs},
            required=["text", "kana", "alt"])
    return S(type=T.ARRAY, items=S(type=T.OBJECT, properties={
        "id": S(type=T.STRING), "kana": S(type=T.STRING), "alt": strs,
        "numbers": S(type=T.ARRAY, items=num)}, required=["id", "kana", "alt", "numbers"]))


def _text_key(text: str) -> str:
    return hashlib.sha1(f"{PROMPT_VERSION}|{READING_MODEL}|{text}".encode("utf-8")).hexdigest()


class ReadingQA:
    """使い方:
        qa = ReadingQA(genai_client)
        qa.prefetch([台詞, ...])          # 期待する読みをまとめて取得（キャッシュ）
        res = qa.check(wav_bytes, 台詞)   # res["ok"], res["diffs"], res["numbers"] ...
    """

    def __init__(self, client, cache_path: Path = READING_CACHE, log=print):
        self.client = client
        self.cache_path = Path(cache_path)
        self.log = log
        self.llm_calls = 0
        try:
            self.cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except Exception:
            self.cache = {}
        self._model = None

    # 読み ---------------------------------------------------------
    def _save_cache(self):
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.cache_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.cache, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.cache_path)

    def _fetch_chunk(self, chunk):
        from google.genai import types
        items = [{"id": str(n), "text": t} for n, t in enumerate(chunk)]
        for attempt in range(3):
            try:
                r = self.client.models.generate_content(
                    model=READING_MODEL, contents=_PROMPT + json.dumps(items, ensure_ascii=False),
                    config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0,
                                                       response_schema=_response_schema(),
                                                       http_options=types.HttpOptions(timeout=READING_TIMEOUT_MS)))
                self.llm_calls += 1
                return {str(x.get("id")): x for x in json.loads(r.text)}
            except Exception as e:
                self.log(f"  ⚠️ 読みの取得に失敗（{type(e).__name__}: {e}）、{attempt + 1}回目")
        return {}

    def prefetch(self, texts):
        """期待する読みをまとめて取得してキャッシュする（台詞テキストのハッシュがキー）。"""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        todo = list(dict.fromkeys(t for t in texts if t and _text_key(t) not in self.cache))
        if not todo:
            return
        chunks = [todo[i:i + READING_BATCH] for i in range(0, len(todo), READING_BATCH)]
        self.log(f"  📖 台本の読みを取得中（{len(todo)}行、{READING_MODEL}、{len(chunks)}回）")
        with ThreadPoolExecutor(max_workers=READING_WORKERS) as ex:
            futs = {ex.submit(self._fetch_chunk, c): c for c in chunks}
            for fut in as_completed(futs):  # 届いた順にキャッシュへ（reading() が自分の行だけ待てるように）
                chunk, got = futs[fut], fut.result()
                for n, t in enumerate(chunk):
                    x = got.get(str(n))
                    if x and re.fullmatch(r"[ァ-ヴー]+", x.get("kana") or ""):
                        self.cache[_text_key(t)] = {
                            "text": t, "kana": x["kana"],
                            "alt": [a for a in (x.get("alt") or []) if re.fullmatch(r"[ァ-ヴー]+", a or "")][:3],
                            "numbers": [nm for nm in (x.get("numbers") or [])
                                        if isinstance(nm, dict) and nm.get("kana")],
                        }
                self._save_cache()

    def prefetch_async(self, texts):
        """prefetch を別スレッドで始める（音声生成と並行して読みを取る）。reading() が終わりを待つ。"""
        import threading
        texts = list(texts)
        self._thread = threading.Thread(target=self.prefetch, args=(texts,), daemon=True)
        self._thread.start()

    def reading(self, text: str):
        import time
        k = _text_key(text)
        th = getattr(self, "_thread", None)
        while th is not None and th.is_alive() and k not in self.cache:
            time.sleep(0.5)
        if k not in self.cache:
            self.prefetch([text])
        return self.cache.get(k)

    # 音素認識 -----------------------------------------------------
    def _load_model(self):
        if self._model is None:
            import torch
            from transformers import AutoModelForCTC, AutoProcessor
            dev = "mps" if torch.backends.mps.is_available() else "cpu"
            def load(local_only):
                kw = dict(revision=MODEL_REVISION, local_files_only=local_only, cache_dir=str(HF_HOME / "hub"))
                return (AutoProcessor.from_pretrained(MODEL_ID, **kw),
                        AutoModelForCTC.from_pretrained(MODEL_ID, use_safetensors=True, **kw))
            try:
                proc, model = load(True)
            except OSError:
                self.log(f"  ⏬ 音素認識モデル {MODEL_ID}（約380MB）を {HF_HOME} に取得します")
                proc, model = load(False)
            model = model.eval().to(dev)
            vocab = proc.tokenizer.get_vocab()
            self._model = (torch, model, vocab, {v: k for k, v in vocab.items()}, dev)
        return self._model

    @staticmethod
    def _decode_audio(wav_bytes: bytes, tempo: float = 1.0) -> np.ndarray:
        af = ["-af", f"atempo={tempo}"] if tempo != 1.0 else []
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", "pipe:0", *af, "-ac", "1", "-ar", "16000",
                              "-f", "s16le", "pipe:1"], input=wav_bytes, capture_output=True, check=True).stdout
        return np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0

    def _recognize(self, audio: np.ndarray):
        """→ (採点用の対数確率 [T,V]、貪欲復号の音素列)"""
        torch, model, vocab, inv, dev = self._load_model()
        a = np.pad(audio, 8000)
        with torch.inference_mode():
            lg = model(torch.from_numpy(a)[None].to(dev)).logits[0].float().cpu()
        lp = lg.log_softmax(-1)
        m = lp.clone()
        # 無声化母音（I/U）は i/u と同じ、ポーズ（pau/sil）は空白（blank）と同じに扱う
        m[:, vocab["i"]] = torch.logaddexp(lp[:, vocab["i"]], lp[:, vocab["I"]])
        m[:, vocab["u"]] = torch.logaddexp(lp[:, vocab["u"]], lp[:, vocab["U"]])
        bl = vocab["PAD"]
        m[:, bl] = torch.logsumexp(torch.stack([lp[:, bl], lp[:, vocab["pau"]], lp[:, vocab["sil"]]]), 0)
        skip = {bl, vocab["UNK"], vocab["SOS"], vocab["EOS"], vocab["pau"], vocab["sil"]}
        toks = [inv[int(i)] for i in torch.unique_consecutive(lg.argmax(-1)) if int(i) not in skip]
        return m, [t.lower() if t in ("I", "U") else t for t in toks]

    def _ctc_loss(self, m, seq: list) -> float:
        torch, _, vocab, _, _ = self._load_model()
        import torch.nn.functional as F
        bl = vocab["PAD"]
        if not seq:
            return float(-m[:, bl].sum())
        tgt = torch.tensor([vocab[t] for t in seq])
        return float(F.ctc_loss(m[:, None, :], tgt[None], torch.tensor([m.shape[0]]), torch.tensor([len(tgt)]),
                                blank=bl, reduction="sum", zero_infinity=True))

    # 照合 ---------------------------------------------------------
    def _compare(self, m, rec_raw: list, kana: str, numbers: list):
        exp_raw = kana_to_phonemes(kana)
        et, ei = tolerant(exp_raw)
        rt, ri = tolerant(rec_raw)
        base = self._ctc_loss(m, exp_raw)

        # 数字の範囲（期待列の添字）
        num_spans = []
        for nm in numbers or []:
            for k in [nm.get("kana")] + list(nm.get("alt") or []):
                sub = tolerant(kana_to_phonemes(k or ""))[0]
                pos = _find_sub(et, sub) if sub else -1
                if pos >= 0:
                    num_spans.append((pos, pos + len(sub), nm.get("text", "")))
                    break

        def raw_pos(idx, tol_i, n):
            return idx[tol_i] if tol_i < len(idx) else n

        diffs = []
        for p in find_pockets(et, rt):
            a0, a1, b0, b1 = p
            if is_number_sokuon(et, rt, p):
                continue
            alt = exp_raw[:raw_pos(ei, a0, len(exp_raw))] + rec_raw[raw_pos(ri, b0, len(rec_raw)):raw_pos(ri, b1, len(rec_raw))] \
                + exp_raw[raw_pos(ei, a1, len(exp_raw)):]
            delta = base - self._ctc_loss(m, alt)
            hit_nums = [t for s, e, t in num_spans if a0 < e and s < max(a1, a0 + 1)]
            th = NUMBER_DELTA_THRESHOLD if hit_nums else DELTA_THRESHOLD
            diffs.append({
                "expected": "".join(_kana_of(et[a0:a1])), "heard": "".join(_kana_of(rt[b0:b1])),
                "expected_phonemes": " ".join(et[a0:a1]), "heard_phonemes": " ".join(rt[b0:b1]),
                "context": " ".join(et[max(0, a0 - 4):a1 + 4]),
                "expected_around": _window_kana(et, a0, a1), "heard_around": _window_kana(rt, b0, b1),
                "delta": round(delta, 2), "number": hit_nums, "mismatch": delta > th,
            })
        return {
            "kana": kana, "expected_phonemes": " ".join(et), "heard_phonemes": " ".join(rt),
            "diffs": diffs, "score": sum(d["delta"] for d in diffs if d["mismatch"]),
            "coverage": len(rt) / max(1, len(et)),
        }

    def check(self, wav_bytes: bytes, text: str) -> dict:
        """1行の音声を台本と照合する。ok=False なら作り直し候補。"""
        r = self.reading(text)
        if not r:
            return {"ok": True, "skipped": "読みを取得できなかったため照合しませんでした", "text": text}
        audio = self._decode_audio(wav_bytes)
        m, rec = self._recognize(audio)
        best = None
        for tempo in (1.0, 0.8):
            if tempo != 1.0:
                if best["coverage"] >= SLOW_RETRY_RATIO:
                    break
                m, rec = self._recognize(self._decode_audio(wav_bytes, tempo))
            for kana in [r["kana"]] + list(r.get("alt") or []):
                c = self._compare(m, rec, kana, r.get("numbers"))
                c["tempo"] = tempo
                if best is None or c["score"] < best["score"]:
                    best = c
        # 非常に速い発話では音素認識がまとまった音を落とす（kl034 の締めの台詞で発生）。認識した音が
        # 全体に少なく、大きな「抜け」だけのポケットは、認識側の取りこぼしとみなして不一致にしない
        # （台詞の読み飛ばし自体は、前段の Gemini QA が SKIPPED として見ている）。
        for d in best["diffs"]:
            ne, nh = len(d["expected_phonemes"].split()), len(d["heard_phonemes"].split())
            if d["mismatch"] and not d["number"] and best["coverage"] < 0.9 and ne >= 8 and nh * 4 <= ne:
                d["mismatch"] = False
                d["uncertain"] = "速い発話で認識が音を落とした可能性（読み飛ばしは Gemini QA で確認）"
        mism = [d for d in best["diffs"] if d["mismatch"]]
        return {
            "ok": not mism, "text": text, "expected_kana": best["kana"],
            "expected_phonemes": best["expected_phonemes"], "heard_phonemes": best["heard_phonemes"],
            "tempo": best["tempo"], "mismatches": mism, "diffs": best["diffs"],
            "number_mismatch": any(d["number"] for d in mism),
        }


_MORA_END = VOWELS | {"N", "cl"}


def _window_kana(seq: list, i0: int, i1: int, pad: int = 6) -> str:
    """差の前後を、モーラの切れ目にそろえてカタカナで返す（表示用）。"""
    s, e = max(0, i0 - pad), min(len(seq), i1 + pad)
    while s > 0 and seq[s - 1] not in _MORA_END:
        s -= 1
    while e < len(seq) and e > 0 and seq[e - 1] not in _MORA_END:
        e += 1
    return "".join(_kana_of(seq[s:e]))


_PH2KANA = None


def _kana_of(phonemes: list) -> list:
    """音素列 → 表示用のカタカナ（近似）。"""
    global _PH2KANA
    if _PH2KANA is None:
        _PH2KANA = {}
        for k, v in MORA.items():
            _PH2KANA.setdefault(tuple(v), k)
    out, i = [], 0
    while i < len(phonemes):
        for n in (2, 1):
            t = tuple(phonemes[i:i + n])
            if len(t) == n and t in _PH2KANA:
                out.append(_PH2KANA[t])
                i += n
                break
        else:
            out.append(phonemes[i])
            i += 1
    return out


# ── 既存の音声をまとめて照合する（作り直しはしない）────────────────
def _cut_line(scene_wav: Path, t0: float, dur: float) -> bytes:
    return subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t0), "-t", str(dur), "-i", str(scene_wav),
                           "-f", "wav", "pipe:1"], capture_output=True, check=True).stdout


def main():
    """使い方:
      python3 kl_reading_qa.py --episode kl035 --narration-dir <S{NN}.wav のあるフォルダ> [--out 結果.json]
    episodes/kl{NNN}.json の lines[].t0/dur でシーン音声を行に切り出し、読みを照合して表示する。
    行ごとの音声（S{NN}_L{KK}.wav）があればそちらを使う。音声もエピソードJSONも書き換えない。"""
    import argparse
    import sys
    from google import genai

    ap = argparse.ArgumentParser(description="台詞音声の読み照合（既存の音声を確認するだけ）")
    ap.add_argument("--episode", required=True)
    ap.add_argument("--narration-dir", required=True)
    ap.add_argument("--scenes", help="scene_id をカンマ区切り")
    ap.add_argument("--out", help="結果JSONの保存先（省略時は表示のみ）")
    args = ap.parse_args()
    key = os.environ.get("GEMINI_API_KEY_KL") or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        sys.exit("❌ GEMINI_API_KEY が設定されていません")
    ep = json.loads((Path(__file__).parent / "episodes" / f"{args.episode}.json").read_text(encoding="utf-8"))
    nd = Path(args.narration_dir)
    targets = {int(x) for x in args.scenes.split(",")} if args.scenes else None
    qa = ReadingQA(genai.Client(api_key=key))
    scenes = [s for s in ep["scenes"] if targets is None or s["scene_id"] in targets]
    qa.prefetch([l["text"] for s in scenes for l in s.get("lines", [])])
    results, bad = {}, []
    for s in scenes:
        sid = s["scene_id"]
        for k, line in enumerate(s.get("lines", []), start=1):
            name = f"S{sid:02d}_L{k:02d}"
            lw = nd / f"{name}.wav"
            if lw.exists():
                wav = lw.read_bytes()
            elif "t0" in line and (nd / f"S{sid:02d}.wav").exists():
                wav = _cut_line(nd / f"S{sid:02d}.wav", line["t0"], line["dur"])
            else:
                print(f"  - {name}: 音声がありません")
                continue
            r = qa.check(wav, line["text"])
            results[name] = r
            if not r["ok"]:
                bad.append(name)
    print_summary(results)
    if args.out:
        Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{len(results)}行を照合、不一致の疑い {len(bad)}行（LLM呼び出し {qa.llm_calls}回）")


def print_summary(results: dict, header: str = "読みの不一致の疑いがある行") -> int:
    bad = {k: v for k, v in results.items() if not v.get("ok", True)}
    if not bad:
        return 0
    print(f"\n⚠️ {header}（{len(bad)}行。耳で確認し、必要なら台本の語を言い換える）:")
    for name, r in bad.items():
        print(f"  {name}: {r.get('text', '')}")
        for d in r.get("mismatches", []):
            tag = "【数字】" if d.get("number") else ""
            print(f"      {tag}台本「…{d.get('expected_around', d['expected'])}…」→ 聞こえた音「…{d.get('heard_around', d['heard'])}…」"
                  f"（差の部分: {d['expected'] or '－'}→{d['heard'] or '（なし）'}、大きさ {d['delta']}）")
    return len(bad)


if __name__ == "__main__":
    main()
