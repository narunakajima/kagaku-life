#!/usr/bin/env python3
"""Gemini テキスト／判定系 Flash モデル名の集約と、「モデル不存在」時の自動フォールバック（2026-11-09 指示024）。

方針:
- モデル名は候補リスト方式。-latest 系エイリアス・preview は入れない（ListModels で実在と generateContent 対応を
  確認できた固定IDだけを優先順に並べる）。無検証で最新名へ飛ぶ自動切替はしない。
- 呼び出しが「モデル不存在」（404 NOT_FOUND / is not found for API version）で失敗した場合に限り次の候補で再試行する。
  クォータ超過(429)・認証エラー(401/403)・その他のエラーでは切り替えない（そのまま例外を投げる）。
- 切り替えが起きたら、前後のモデル名を標準出力・gemini_model_fallback.log・model_fallback.txt に残す
  （nightly-news はこの model_fallback.txt を Slack に出す）。
- 全候補が不存在なら最後の例外をそのまま投げる（013の「対象があるのに0件なら非0終了＋Slack警告」が働く）。
- 対象外: TTS 専用モデル（*-tts）と画像生成モデル（nano-banana 等）。候補リストに無いモデル名の呼び出しは素通し。

使い方:
    import kl_gemini_model as gm
    MODEL = gm.primary()                       # 第一候補（環境変数 KL_GEMINI_MODEL で上書き可）
    client = gm.wrap_client(genai.Client(...)) # generate_content にフォールバックを仕込む
スクリプト個別の環境変数（KL_BGM_QA_MODEL 等）や --model は従来どおり使える。
"""
import os
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent

# ListModels（kl_list_models.py）で実在と generateContent 対応を確認した現行Flash系の固定ID。優先順。
# gemini-2.5-flash は「新規キーでは 404」（2026-11-09 実測）なので入れない。
DEFAULT_CANDIDATES = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
]

# 軽い工程（分類・整形レベル）用の Flash-Lite 系固定ID（2026-11-14 指示008。kl_list_models.py で gemini-3.5-flash-lite の実在を確認）。
# 事前承認済みはこの1件のみ。不存在時は他の Lite へ飛ばさず例外のまま（通常の Flash への自動復帰は未実装。フラグ有効化の前に要対応）。
LIGHT_CANDIDATES = [
    "gemini-3.5-flash-lite",
]

LOG_FILE = BASE_DIR / "gemini_model_fallback.log"      # 追記ログ（コミットしない）
NOTE_FILE = BASE_DIR / "model_fallback.txt"            # 今回の実行での切替メモ（Actions が Slack に出す。コミットしない）

EVENTS = []          # このプロセスで起きた切替 [(from, to, reason)]
_current = {}        # 元のモデル名 -> 現在使うモデル名（切替後は以降の呼び出しも新しい方から始める）


def _strip(name: str) -> str:
    return name[len("models/"):] if name.startswith("models/") else name


def candidates() -> list:
    """候補リスト。環境変数 KL_GEMINI_CANDIDATES（カンマ区切り）で上書き可（検証用）。"""
    env = os.environ.get("KL_GEMINI_CANDIDATES", "").strip()
    if env:
        return [_strip(x.strip()) for x in env.split(",") if x.strip()]
    first = os.environ.get("KL_GEMINI_MODEL", "").strip()
    cands = list(DEFAULT_CANDIDATES)
    if first:
        first = _strip(first)
        cands = [first] + [c for c in cands if c != first]
    return cands


def primary() -> str:
    return candidates()[0]


def light_candidates() -> list:
    """軽い工程用の候補。環境変数 KL_GEMINI_LIGHT_MODEL で第一候補を上書き可（検証用）。"""
    env = _strip(os.environ.get("KL_GEMINI_LIGHT_MODEL", "").strip())
    return [env] + [c for c in LIGHT_CANDIDATES if c != env] if env else list(LIGHT_CANDIDATES)


def light_model() -> str:
    """軽い工程用（分類・整形）の Flash-Lite 系モデル名。"""
    return light_candidates()[0]


def is_model_not_found(exc: Exception) -> bool:
    """「モデル不存在」の404だけを True にする。クォータ・認証・一時障害は False。"""
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    text = str(exc)
    low = text.lower()
    if code in (429, 401, 403) or "RESOURCE_EXHAUSTED" in text or "PERMISSION_DENIED" in text \
            or "UNAUTHENTICATED" in text:
        return False
    if code == 404 or "NOT_FOUND" in text or text.startswith("404"):
        # 404 のうちモデル名に関するものだけ
        return ("model" in low and ("not found" in low or "not_found" in low or "no longer available" in low
                                    or "is not supported" in low))
    return "is not found for api version" in low


def _record(src: str, dst: str, reason: str):
    EVENTS.append((src, dst, reason))
    msg = f"Gemini モデルを {src} から {dst} へ自動で切り替えました（理由: {reason[:120]}）"
    print(f"\n⚠️ {msg}", flush=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    script = Path(sys.argv[0]).name if sys.argv and sys.argv[0] else "?"
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(f"{stamp}\t{script}\t{src}\t{dst}\t{reason[:200]}\n")
        with NOTE_FILE.open("a", encoding="utf-8") as f:
            f.write(f"モデルを{dst}へ自動で切り替えました（{src} が見つかりません。{script}）\n")
    except OSError:
        pass


def generate_with_fallback(call, model: str, *args, **kwargs):
    """call(model=..., ...) を、不存在エラー時に限り次の候補で再試行して実行する。"""
    cands = candidates()
    base = _strip(model)
    if base in light_candidates():
        cands = light_candidates()       # 軽い工程用は Lite 候補の中だけで切り替える
    if base not in cands:
        return call(model=model, *args, **kwargs)        # 候補外（TTS・画像・pro 等）は素通し
    prefix = "models/" if model.startswith("models/") else ""
    cur = _current.get(base, base)
    start = cands.index(cur) if cur in cands else 0
    last = None
    for i in range(start, len(cands)):
        name = cands[i]
        try:
            res = call(model=prefix + name, *args, **kwargs)
        except Exception as e:  # noqa: BLE001
            if not is_model_not_found(e):
                raise
            last = e
            if i + 1 < len(cands):
                _record(name, cands[i + 1], str(e))
                _current[base] = cands[i + 1]
            continue
        _current[base] = name
        return res
    print(f"\n🚨 Gemini の全候補モデルが見つかりません: {', '.join(cands[start:])}", flush=True)
    raise last


def wrap_client(client):
    """genai.Client の models.generate_content にフォールバックを仕込んで同じ client を返す。"""
    models = client.models
    orig = models.generate_content
    if getattr(orig, "_kl_fallback", False):
        return client

    def generate_content(*args, **kwargs):
        model = kwargs.pop("model", None)
        if model is None and args:
            model, args = args[0], args[1:]
        return generate_with_fallback(orig, model, *args, **kwargs)

    generate_content._kl_fallback = True
    models.generate_content = generate_content
    return client
