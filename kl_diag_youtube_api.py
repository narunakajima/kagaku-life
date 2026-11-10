"""診断（指示 2026-11-10-016）: YouTube Data API v3 が使えるか（どのキーの環境変数があるか、search.list が通るか）を確かめる。
キーの値は表示しない。"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

names = ["YOUTUBE_API_KEY_KL", "YOUTUBE_API_KEY", "GEMINI_API_KEY_KL", "GEMINI_API_KEY", "GOOGLE_API_KEY"]
print("環境変数の有無:", {n: bool(os.environ.get(n)) for n in names})
for n in names:
    k = os.environ.get(n)
    if not k:
        continue
    url = "https://www.googleapis.com/youtube/v3/search?" + urllib.parse.urlencode(
        {"part": "snippet", "q": "humanoid robot", "type": "video", "maxResults": 1, "key": k})
    try:
        r = json.loads(urllib.request.urlopen(url, timeout=20).read())
        print(n, "→ 成功 totalResults=", r.get("pageInfo", {}).get("totalResults"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            msg = json.loads(body)["error"]
            print(n, "→ HTTP", e.code, msg.get("status"), (msg.get("message") or "")[:140])
        except Exception:
            print(n, "→ HTTP", e.code, body[:140])
    except Exception as e:
        print(n, "→ 失敗", type(e).__name__, str(e)[:100])
