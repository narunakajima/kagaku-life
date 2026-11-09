#!/usr/bin/env python3
"""現在のキーで generateContent に使える Gemini モデルの一覧を表示する（モデル名の404調査用）。
使い方: python3 kl_list_models.py [絞り込み語]
"""
import os
import sys

from google import genai

key = os.environ.get("GEMINI_API_KEY_KL") or os.environ.get("GEMINI_API_KEY", "")
if not key:
    sys.exit("APIキーが環境変数にありません")
flt = sys.argv[1] if len(sys.argv) > 1 else ""
client = genai.Client(api_key=key)
for m in client.models.list():
    acts = getattr(m, "supported_actions", None) or []
    if "generateContent" in acts and flt in m.name:
        print(m.name)
