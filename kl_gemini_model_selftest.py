#!/usr/bin/env python3
"""kl_gemini_model のフォールバック検証（小さく実行）。
使い方: KL_GEMINI_CANDIDATES="gemini-bogus-9.9-flash,gemini-3.8-flash,gemini-3.7-flash" python3 kl_gemini_model_selftest.py
  - 第一候補が存在しない名前でも、次の候補へ切り替えて応答が返る
  - 切替の記録（標準出力・gemini_model_fallback.log・model_fallback.txt）が出る
  - 全候補が不存在のときは例外になる（--all-bogus）
  - 判定関数が 429/403 では切り替えない
"""
import os
import sys

if "--all-bogus" in sys.argv:
    os.environ["KL_GEMINI_CANDIDATES"] = "gemini-bogus-9.9-flash,gemini-bogus-9.8-flash"
elif "--primary-bogus" in sys.argv:
    os.environ["KL_GEMINI_CANDIDATES"] = "gemini-bogus-9.9-flash,gemini-3.8-flash,gemini-3.7-flash"

from google import genai

import kl_gemini_model as gm

key = os.environ.get("GEMINI_API_KEY_KL") or os.environ.get("GEMINI_API_KEY", "")
if not key:
    sys.exit("APIキーが環境変数にありません")


class E(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


assert gm.is_model_not_found(E(404, "404 NOT_FOUND. models/x is not found for API version v1beta"))
assert not gm.is_model_not_found(E(429, "429 RESOURCE_EXHAUSTED. quota"))
assert not gm.is_model_not_found(E(403, "403 PERMISSION_DENIED"))
assert not gm.is_model_not_found(E(500, "500 INTERNAL"))
print("判定関数 OK（404モデル不存在のみ True）")

if "--probe" in sys.argv:   # 既定候補が全て実在し generateContent で応答するかを1件ずつ確認
    raw = genai.Client(api_key=key)
    for c in gm.DEFAULT_CANDIDATES:
        try:
            t = raw.models.generate_content(model=c, contents="1+1は？数字だけ答えて").text
            print("OK ", c, (t or "").strip()[:20])
        except Exception as e:  # noqa: BLE001
            print("NG ", c, str(e)[:120])
    sys.exit(0)

client = gm.wrap_client(genai.Client(api_key=key))
cands = gm.candidates()
print("候補:", cands)
if "--all-bogus" in sys.argv:
    try:
        client.models.generate_content(model=cands[0], contents="1+1=?")
    except Exception as e:  # noqa: BLE001
        print("全候補失敗で例外になった（検知が働く）:", str(e)[:100])
        sys.exit(3)
    sys.exit("例外にならなかった")
r = client.models.generate_content(model=cands[0], contents="1+1は？数字だけ答えて")
print("応答:", (r.text or "").strip()[:50])
print("切替イベント:", gm.EVENTS)
assert gm.EVENTS or cands[0] in ("gemini-3.8-flash",), "切替が記録されていない"
