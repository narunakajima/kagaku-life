#!/usr/bin/env python3
"""幸せな未来のサイエンスの未返信コメントを取得／返信投稿する（/kl-upload STEP 3.6）。

  python3 kl_comment_reply.py list            # 未返信コメントをJSONで出力（投稿しない）
  python3 kl_comment_reply.py post FILE.json  # {"スレッドID": "返信文", ...} を投稿

返信文は Claude が内容に合わせて書く。スクリプトは取得と投稿のみ。
返信済みスレッドIDは data/comment_replies.json に記録（二重返信防止）。
自分のコメントや、すでに自分の返信があるスレッドは対象外。
"""
import json
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

CHANNEL_ID = "UCj5pDosl_4FiaZ_NdNg7IcA"
TOKEN = Path.home() / ".claude/secrets/yt_token_kl.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.force-ssl"]
LOG = Path(__file__).parent / "data/comment_replies.json"


def youtube():
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if not creds.valid:
        creds.refresh(Request())
        TOKEN.write_text(creds.to_json())
    yt = build("youtube", "v3", credentials=creds)
    ch = yt.channels().list(part="id", mine=True).execute().get("items", [])
    if not ch or ch[0]["id"] != CHANNEL_ID:
        sys.exit("認証チャンネルが幸せな未来のサイエンスではありません。中止します。")
    return yt


def mine(sn):
    return sn.get("authorChannelId", {}).get("value") == CHANNEL_ID


def load_done():
    return set(json.loads(LOG.read_text())["replied"]) if LOG.exists() else set()


def unreplied(yt, max_pages=5):
    done, token, out = load_done(), None, []
    titles = {}
    for _ in range(max_pages):
        r = yt.commentThreads().list(
            part="snippet,replies", allThreadsRelatedToChannelId=CHANNEL_ID,
            maxResults=100, order="time", textFormat="plainText", pageToken=token).execute()
        for th in r.get("items", []):
            sn = th["snippet"]["topLevelComment"]["snippet"]
            replies = th.get("replies", {}).get("comments", [])
            if (mine(sn) or th["id"] in done
                    or th["snippet"]["totalReplyCount"] > len(replies)
                    or any(mine(x["snippet"]) for x in replies)):
                continue
            vid = sn["videoId"]
            if vid not in titles:
                v = yt.videos().list(part="snippet", id=vid).execute().get("items", [])
                titles[vid] = v[0]["snippet"]["title"] if v else ""
            out.append({"thread_id": th["id"], "video_id": vid, "video_title": titles[vid],
                        "author": sn["authorDisplayName"], "text": sn["textDisplay"],
                        "likes": sn.get("likeCount", 0), "published": sn["publishedAt"]})
        token = r.get("nextPageToken")
        if not token:
            break
    return out


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("list", "post"):
        sys.exit(__doc__)
    yt = youtube()
    if sys.argv[1] == "list":
        print(json.dumps(unreplied(yt), ensure_ascii=False, indent=1))
        return
    replies = json.loads(Path(sys.argv[2]).read_text())
    done = load_done()
    for tid, text in replies.items():
        if tid in done or not text.strip():
            continue
        try:
            yt.comments().insert(part="snippet", body={
                "snippet": {"parentId": tid, "textOriginal": text}}).execute()
            done.add(tid)
            print(f"  ✓ {tid}: {text}")
        except Exception as e:
            print(f"  ⚠ {tid}: 失敗 {e}")
    LOG.parent.mkdir(exist_ok=True)
    LOG.write_text(json.dumps({"replied": sorted(done)}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
