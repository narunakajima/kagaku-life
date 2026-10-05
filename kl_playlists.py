"""
kl_playlists.py — YouTubeの再生リストを5ジャンル（genres.json）に同期する

2026-10-06追加。関心ごとの4領域（再生リストは1つも未作成だった）から、世間の関心が高い5ジャンルに変えた際に、
再生リストを作って既存の動画を入れるために作成。以後は /kl-upload（kl_sns_up.py）がアップロード直後に
add_episode_to_playlist() を呼び、新しい回を該当ジャンルの再生リストに入れる。

- ジャンルの正は topics_queue.json の genre。再生リストIDは theme_playlists.json（ジャンルキー → playlist_id）
- 入れるのは本編動画のみ（Shortsは入れない）。publish_hold の回（公開予約を取り消した回）は入れない
- 予約公開待ち（YouTube上は非公開）の動画も入れてよい。公開されるまで視聴者には見えない
- 既に入っている動画は重複して入れない。再生リストの並びは古い回→新しい回

使い方:
  python3 kl_playlists.py --dry-run   # 何を作り何を入れるかだけ表示
  python3 kl_playlists.py             # 再生リストを作成（未作成のもの）し、足りない動画を追加
"""
import argparse
import json
import re
import time
from pathlib import Path

BASE_DIR = Path(__file__).parent
GENRES_JSON = BASE_DIR / "genres.json"
THEME_PLAYLISTS_JSON = BASE_DIR / "theme_playlists.json"
TOPICS_QUEUE_JSON = BASE_DIR / "topics_queue.json"
EPISODES_DIR = BASE_DIR / "episodes"


def _video_id(url: str) -> str:
    m = re.search(r"(?:youtu\.be/|v=)([A-Za-z0-9_-]{11})", url or "")
    return m.group(1) if m else ""


def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def genre_of(episode_id: str):
    for e in _load(TOPICS_QUEUE_JSON)["queue"]:
        if e.get("episode_id") == episode_id:
            return e.get("genre")
    return None


def _playlist_items(youtube, playlist_id: str) -> set:
    from googleapiclient.errors import HttpError
    ids, token = set(), None
    while True:
        for attempt in range(4):  # 作成直後は 404 になることがある（反映待ち）
            try:
                r = youtube.playlistItems().list(part="contentDetails", playlistId=playlist_id,
                                                 maxResults=50, pageToken=token).execute()
                break
            except HttpError as e:
                if e.resp.status != 404 or attempt == 3:
                    raise
                time.sleep(3 * (attempt + 1))
        ids |= {i["contentDetails"]["videoId"] for i in r.get("items", [])}
        token = r.get("nextPageToken")
        if not token:
            return ids


def ensure_playlist(youtube, genre: str, dry_run: bool = False):
    """ジャンルの再生リストIDを返す。theme_playlists.json に無ければ作成して書き戻す。"""
    genres = _load(GENRES_JSON)["genres"]
    tp = _load(THEME_PLAYLISTS_JSON)
    pid = (tp.get(genre) or {}).get("playlist_id")
    if pid:
        return pid
    g = genres[genre]
    if dry_run:
        print(f"  [作成予定] 再生リスト「{g['label']}」（公開）")
        return None
    r = youtube.playlists().insert(
        part="snippet,status",
        body={"snippet": {"title": g["label"], "description": g["youtube_description"], "defaultLanguage": "ja"},
              "status": {"privacyStatus": "public"}}).execute()
    pid = r["id"]
    tp[genre] = {"display_name": g["label"], "playlist_id": pid}
    THEME_PLAYLISTS_JSON.write_text(json.dumps(tp, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✓ 再生リスト作成: {g['label']} → {pid}")
    return pid


def add_episode_to_playlist(youtube, episode_id: str, dry_run: bool = False) -> bool:
    genre = genre_of(episode_id)
    ep = _load(EPISODES_DIR / f"{episode_id}.json")
    vid = _video_id(ep.get("youtube_url", ""))
    if not genre or not vid or ep.get("publish_hold"):
        print(f"  - {episode_id}: スキップ（genre={genre} video={bool(vid)} hold={bool(ep.get('publish_hold'))}）")
        return False
    pid = ensure_playlist(youtube, genre, dry_run)
    if dry_run or not pid:
        print(f"  [追加予定] {episode_id} → {genre}")
        return True
    if vid in _playlist_items(youtube, pid):
        print(f"  = {episode_id}: 既に {genre} に入っています")
        return False
    youtube.playlistItems().insert(part="snippet", body={"snippet": {
        "playlistId": pid, "resourceId": {"kind": "youtube#video", "videoId": vid}}}).execute()
    print(f"  ✓ {episode_id} → {genre}")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--episode", help="この回だけ追加する")
    args = ap.parse_args()
    from kl_sns_up import get_youtube_client
    youtube = get_youtube_client()
    mine = youtube.playlists().list(part="snippet", mine=True, maxResults=50).execute().get("items", [])
    print("既存の再生リスト:", [(p["id"], p["snippet"]["title"]) for p in mine] or "なし")
    eids = [args.episode] if args.episode else sorted(
        e["episode_id"] for e in _load(TOPICS_QUEUE_JSON)["queue"]
        if (EPISODES_DIR / f"{e['episode_id']}.json").exists())
    for eid in eids:
        add_episode_to_playlist(youtube, eid, args.dry_run)


if __name__ == "__main__":
    main()
