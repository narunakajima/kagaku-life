"""
kl_sns_up.py — くらしを変える科学 YouTubeアップロード

使い方:
  python3 kl_sns_up.py --episode kl001              # 次の空き土曜19:00 JSTに自動予約
  python3 kl_sns_up.py --episode kl001 --now        # 即時公開
  python3 kl_sns_up.py --episode kl001 --publish-at "2026-06-06 19:00"  # 日時指定

デフォルト動作:
  毎週土曜 19:00 JST に1本公開。
  すでに予約済みのエピソードがある場合は翌週以降の空きスロットを自動割り当て。

認証: ~/.claude/secrets/yt_client_secrets.json（lamp-whisper / samurai-chronicles と共用）
      トークンは ~/.claude/secrets/yt_token_kl.json に保存（kagaku-life専用）。

（sc_sns_up.py をベースにkagaku-life向けに移植。プレイリスト機能なし・字幕アップロードなし・
 サイト再ビルドなし（別タスクで追加予定）。2026-08-23）
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

# kl001初回アップロード（2026-08-23）時に認証チャンネルとして確認済み: 幸せな未来のサイエンス
KAGAKU_LIFE_CHANNEL_ID: Optional[str] = "UCj5pDosl_4FiaZ_NdNg7IcA"

CHANNEL_HANDLE_URL = "https://www.youtube.com/@kagaku-life"

SECRETS_DIR = Path.home() / ".claude" / "secrets"
YT_CLIENT_SECRETS = SECRETS_DIR / "yt_client_secrets.json"
YT_TOKEN = SECRETS_DIR / "yt_token_kl.json"

BASE_DIR = Path(__file__).parent
GDRIVE_ROOT = (
    Path.home()
    / "Library"
    / "CloudStorage"
    / "GoogleDrive-naru.nakajima@gmail.com"
    / "マイドライブ"
    / "Kagaku-Life"
)


def get_youtube_client():
    creds = None
    if YT_TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(YT_TOKEN), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not YT_CLIENT_SECRETS.exists():
                print(f"❌ 認証ファイルが見つかりません: {YT_CLIENT_SECRETS}")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(str(YT_CLIENT_SECRETS), SCOPES)
            creds = flow.run_local_server(port=8082, prompt="select_account consent")
        YT_TOKEN.parent.mkdir(parents=True, exist_ok=True)
        YT_TOKEN.write_text(creds.to_json())
    youtube = build("youtube", "v3", credentials=creds)

    # チャンネル確認（誤チャンネルアップロード防止）
    ch_resp = youtube.channels().list(part="snippet", mine=True).execute()
    ch_items = ch_resp.get("items", [])
    if ch_items:
        ch_id = ch_items[0]["id"]
        ch_name = ch_items[0]["snippet"]["title"]
        print(f"  認証チャンネル: {ch_name} ({ch_id})")
        if KAGAKU_LIFE_CHANNEL_ID is None:
            print(f"  ⚠️  KAGAKU_LIFE_CHANNEL_ID が未設定です。上記のIDを"
                  f"kl_sns_up.pyのKAGAKU_LIFE_CHANNEL_IDに書き込むと、"
                  f"以降このチェックで誤チャンネルアップロードを防げます。")
        elif ch_id != KAGAKU_LIFE_CHANNEL_ID:
            print(f"  ❌ エラー: 幸せな未来のサイエンスチャンネルではありません！")
            print(f"  rm ~/.claude/secrets/yt_token_kl.json で再認証してください。")
            YT_TOKEN.unlink(missing_ok=True)
            sys.exit(1)
    else:
        print("  警告: チャンネル情報を取得できませんでした。")

    return youtube


JST = ZoneInfo("Asia/Tokyo")
PUBLISH_HOUR_JST = 19  # 毎週土曜 19:00 JST に公開
PUBLISH_WEEKDAY = 5  # 0=月 ... 5=土, 6=日


def find_next_publish_slot() -> str:
    """
    直近の「土曜 19:00 JST」スロットを返す（"YYYY-MM-DD HH:MM" JST 形式）。

    2026-08-23改訂: 従来は1週1本になるよう既に予約済みの土曜を避けて翌週以降に
    ずらしていたが、「次の土曜19:00までにアップロードされたエピソードは全て
    その土曜19:00にまとめて公開する」方式に変更した（ユーザー指定）。そのため
    scheduled_atが既に使われているかどうかは見ず、常に直近の次の土曜を返す
    （複数エピソードが同じ土曜のスロットを共有してよい）。

    - 今日が土曜かつ19:00 JSTがまだ未来 → 今日を候補に
    - それ以外 → 次の土曜を候補に
    """
    now_jst = datetime.now(JST)

    candidate = now_jst.replace(hour=PUBLISH_HOUR_JST, minute=0, second=0, microsecond=0)
    if candidate.weekday() != PUBLISH_WEEKDAY or candidate <= now_jst:
        days_ahead = (PUBLISH_WEEKDAY - candidate.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        candidate += timedelta(days=days_ahead)

    return candidate.strftime("%Y-%m-%d %H:%M")


def parse_publish_at(publish_at_str: str) -> str:
    """
    公開日時文字列を RFC 3339（UTC）に変換して返す。
    入力例:
      "2026-06-06 19:00"    → JST として解釈
      "2026-06-06 19:00 JST"
      "2026-06-06 10:00 UTC"
    """
    s = publish_at_str.strip()

    if s.upper().endswith("UTC"):
        tz = timezone.utc
        s = s[:-3].strip()
    else:
        if s.upper().endswith("JST"):
            s = s[:-3].strip()
        tz = ZoneInfo("Asia/Tokyo")

    for fmt in ("%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M", "%Y-%m-%dT%H:%M"):
        try:
            dt_naive = datetime.strptime(s, fmt)
            break
        except ValueError:
            continue
    else:
        raise ValueError(f"日時フォーマットが解析できません: {publish_at_str!r}\n"
                         "例: '2026-06-06 19:00' (JST) または '2026-06-06 10:00 UTC'")

    dt_aware = dt_naive.replace(tzinfo=tz)
    return dt_aware.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def upload_video(youtube, video_path: Path, title: str, description: str,
                 tags: list, publish_at: Optional[str] = None) -> str:
    if publish_at:
        publish_at_rfc = parse_publish_at(publish_at)
        status_body = {"privacyStatus": "private", "publishAt": publish_at_rfc}
        print(f"  アップロード中（予約公開: {publish_at}）: {video_path.name} ...")
    else:
        status_body = {"privacyStatus": "public"}
        print(f"  アップロード中: {video_path.name} ...")

    req = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": "28",  # Science & Technology
                "defaultLanguage": "ja",
            },
            "status": status_body,
        },
        media_body=MediaFileUpload(str(video_path), chunksize=-1, resumable=True),
    )
    response = None
    while response is None:
        status, response = req.next_chunk()
        if status:
            print(f"  {int(status.progress() * 100)}%", end="\r")
    video_id = response["id"]
    if publish_at:
        print(f"  ✓ 完了（予約公開: {publish_at}）: https://youtu.be/{video_id}")
    else:
        print(f"  ✓ 完了（即時公開）: https://youtu.be/{video_id}")
    return video_id


def upload_thumbnail(youtube, video_id: str, thumbnail_path: Path):
    print(f"  サムネイルアップロード中: {thumbnail_path.name} ...")
    youtube.thumbnails().set(
        videoId=video_id,
        media_body=MediaFileUpload(str(thumbnail_path), mimetype="image/png"),
    ).execute()
    print(f"  ✓ サムネイル完了")


def run(episode_id: str, publish_at: Optional[str] = None, publish_now: bool = False):
    ep_json = BASE_DIR / "episodes" / f"{episode_id}.json"
    if not ep_json.exists():
        print(f"❌ エピソードJSONが見つかりません: {ep_json}")
        sys.exit(1)

    with open(ep_json, encoding="utf-8") as f:
        ep = json.load(f)

    drive_ep_dir = GDRIVE_ROOT / episode_id.upper()
    main_video = drive_ep_dir / "output" / f"{episode_id}.mp4"
    shorts_video = drive_ep_dir / "output" / f"{episode_id}_shorts.mp4"
    thumbnail_file = drive_ep_dir / "images" / "thumbnail.png"

    title = ep["youtube_title"]
    description = ep["youtube_description"]
    tags = ep.get("youtube_tags", [])

    if publish_now:
        publish_at = None
        publish_label = "即時公開"
    elif publish_at:
        publish_label = f"予約公開: {publish_at} JST"
    else:
        publish_at = find_next_publish_slot()
        publish_label = f"予約公開: {publish_at} JST（自動）"

    print(f"\n{'━'*60}")
    print(f"  {episode_id} — YouTube アップロード（{publish_label}）")
    print(f"{'━'*60}\n")

    for path, label in [(main_video, "本編"), (shorts_video, "Shorts")]:
        if not path.exists():
            print(f"❌ {label}動画が見つかりません: {path}")
            sys.exit(1)

    youtube = get_youtube_client()

    # 本編
    print("【本編】")
    main_id = upload_video(youtube, main_video, title, description, tags, publish_at)
    if thumbnail_file.exists():
        try:
            upload_thumbnail(youtube, main_id, thumbnail_file)
        except Exception as e:
            print(f"  ⚠️  サムネイルスキップ（YouTube Studioで手動設定してください）: {e}")
    else:
        print(f"  ⚠️  サムネイルなし（スキップ）: {thumbnail_file.name}")

    time.sleep(2)

    # Shorts
    print("\n【Shorts】")
    shorts_list = ep.get("shorts") or []
    hook_lines = shorts_list[0].get("hook_lines", []) if shorts_list else []
    hook_text = "\n".join(hook_lines) if hook_lines else ep.get("episode_title", "")
    shorts_description = (
        f"{hook_text}\n\n"
        f"▶ 本編はこちら: https://youtu.be/{main_id}\n\n"
        f"毎週更新中！チャンネル登録はこちら:\n{CHANNEL_HANDLE_URL}"
    )
    shorts_id = upload_video(youtube, shorts_video,
                             f"{title} #Shorts", shorts_description, tags + ["shorts"],
                             publish_at)

    ep["youtube_url"] = f"https://youtu.be/{main_id}"
    ep["shorts_url"] = f"https://youtu.be/{shorts_id}"
    ep["scheduled_at"] = publish_at if publish_at else ""
    with open(ep_json, "w", encoding="utf-8") as f:
        json.dump(ep, f, ensure_ascii=False, indent=2)
    print(f"  ✓ {episode_id}.json に youtube_url / shorts_url / scheduled_at を保存しました")

    print(f"\n{'━'*60}")
    print(f"  ✓ アップロード完了（{publish_label}）")
    print(f"  本編:   https://youtu.be/{main_id}")
    print(f"  Shorts: https://youtu.be/{shorts_id}")
    print(f"{'━'*60}\n")

    print(f"{'━'*60}")
    print(f"  残りの変更をコミット")
    print(f"{'━'*60}")
    commit_remaining_changes(episode_id)


def commit_remaining_changes(episode_id: str):
    """
    アップロード完了は制作フローの区切りとなるため、episodes/kl{NNN}.json の書き戻し分を
    自動でコミット・プッシュする。差分がなければ何もしない。
    """
    status = subprocess.run(
        ["git", "-C", str(BASE_DIR), "status", "--porcelain"],
        capture_output=True, text=True,
    )
    if not status.stdout.strip():
        return

    subprocess.run(["git", "-C", str(BASE_DIR), "add", "-A"], capture_output=True, text=True)
    result = subprocess.run(
        ["git", "-C", str(BASE_DIR), "commit", "-m",
         f"data: {episode_id} YouTubeアップロード完了 → youtube_url/shorts_url/scheduled_at更新"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"  警告: git commit 失敗: {result.stderr.strip()}")
        return

    result = subprocess.run(
        ["git", "-C", str(BASE_DIR), "push"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print(f"  ✓ 残りの変更を git push しました")
    else:
        print(f"  警告: git push 失敗: {result.stderr.strip()}")


def cli():
    parser = argparse.ArgumentParser(description="くらしを変える科学 YouTubeアップロード")
    parser.add_argument("--episode", required=True, help="エピソードID（例: kl001）")
    parser.add_argument("--publish-at", metavar="DATETIME",
                        help="予約公開日時（JST）例: '2026-06-06 19:00' / 省略時は次の土曜19:00 JSTに自動予約")
    parser.add_argument("--now", action="store_true",
                        help="即時公開（土曜19:00 JST自動予約をスキップ）")
    args = parser.parse_args()

    run(args.episode, publish_at=args.publish_at, publish_now=args.now)


if __name__ == "__main__":
    cli()
