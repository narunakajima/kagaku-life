#!/usr/bin/env python3
"""
kl_title_check.py — YouTube 上の本編タイトルが episodes/kl*.json の youtube_title と食い違っていないかを確かめ、
食い違いを #cc-reports（Slack）に通知する（2026-11-11、kl055 の関連動画タイマー無限再試行の再発防止）

背景: YouTube Studio で手動でタイトルを変えると JSON と食い違い、JSON を元に動く処理（関連動画タイマーなど）が
失敗し続ける。この確認で、食い違いを最大15分で知る。

仕様:
  - 対象 = youtube_url のある回の本編（Shorts は対象外。タイトルを JSON に持っていないため）。
  - YouTube Data API の videos.list（snippet）を50本ずつ。1ユニット。認証は kl_sns_up.py と同じ yt_token_kl.json。
  - 食い違いは「同じ回・同じ食い違い」を1回だけ Slack に通知する。解消したら記録を消す。
  - JSON は書き換えない（YouTube 側が正しいとは限らないため）。YouTube 側に合わせるときは `apply` を人が実行する。
  - 取得に失敗しても何も壊さない（次回に再試行）。

使い方:
  python3 kl_title_check.py check   # 食い違いを表示し、新しいものだけ Slack に通知（kl_related_auto.py の run の冒頭からも呼ぶ）
  python3 kl_title_check.py list    # 表示だけ（通知・記録なし）
  python3 kl_title_check.py apply kl055 [kl056 ...]   # JSON の youtube_title を YouTube 側に合わせる

状態: ~/Library/Logs/claude-team/kagaku-life-title-check-state.json（リポジトリの外）
"""
import glob
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG_DIR = Path.home() / "Library" / "Logs" / "claude-team"
STATE = LOG_DIR / "kagaku-life-title-check-state.json"
YT_TOKEN = Path.home() / ".claude" / "secrets" / "yt_token_kl.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.force-ssl"]


def video_id(url):
    m = re.search(r"(?:youtu\.be/|v=|shorts/)([A-Za-z0-9_-]{11})", url or "")
    return m.group(1) if m else ""


def episodes():
    for f in sorted(glob.glob(str(ROOT / "episodes" / "kl*.json"))):
        p = Path(f)
        ep = json.loads(p.read_text(encoding="utf-8"))
        vid = video_id(ep.get("youtube_url"))
        if vid and ep.get("youtube_title"):
            yield p, ep, vid


def fetch_titles(ids):
    """{動画ID: 実際のタイトル}。失敗したら例外。"""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials.from_authorized_user_file(str(YT_TOKEN), SCOPES)
    if not creds.valid:
        creds.refresh(Request())
        YT_TOKEN.write_text(creds.to_json())
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    out = {}
    ids = list(ids)
    for i in range(0, len(ids), 50):
        r = yt.videos().list(part="snippet", id=",".join(ids[i:i + 50])).execute()
        for it in r.get("items", []):
            out[it["id"]] = it["snippet"]["title"]
    return out


def mismatches():
    rows = [(p, ep, vid) for p, ep, vid in episodes()]
    actual = fetch_titles(v for _, _, v in rows)
    res = []
    for p, ep, vid in rows:
        a = actual.get(vid)
        if a is None:   # 削除済み・非公開で取れない等は対象外（食い違いとは別の問題）
            continue
        if a.strip() != ep["youtube_title"].strip():
            res.append({"episode_id": ep["episode_id"], "video_id": vid, "json": ep["youtube_title"], "youtube": a, "path": p})
    return res


def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"notified": {}}


def save_state(st):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def check(notify=True):
    """食い違い一覧を返す。notify=True なら新しいものだけ Slack に通知する。API 失敗時は None。"""
    try:
        rows = mismatches()
    except Exception as e:  # noqa: BLE001 — 取得失敗でタイマーを止めない
        print(f"タイトル確認をスキップ（取得失敗: {type(e).__name__}）", file=sys.stderr)
        return None
    if not notify:
        return rows
    import kl_related_auto as ra   # post() を共用（#cc-reports）
    st = load_state()
    now_keys = set()
    for r in rows:
        key = r["episode_id"]
        sig = r["youtube"]
        now_keys.add(key)
        if st["notified"].get(key) == sig:
            continue
        if ra.post(f"🔀 *KL タイトルの食い違い*: {r['episode_id']} の本編（{r['video_id']}）\n"
                   f"• JSON: {r['json']}\n• YouTube: {r['youtube']}\n"
                   f"YouTube 側に合わせるなら `python3 kl_title_check.py apply {r['episode_id']}`。"
                   "JSON を元に動く処理（関連動画タイマー等）が失敗する原因になります（同じ食い違いの通知は1回だけ）。"):
            st["notified"][key] = sig
    for key in list(st["notified"]):
        if key not in now_keys:   # 解消した
            del st["notified"][key]
    save_state(st)
    return rows


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd in ("check", "list"):
        rows = check(notify=(cmd == "check"))
        if rows is None:
            sys.exit(1)
        if not rows:
            print("食い違いなし")
        for r in rows:
            print(f"{r['episode_id']}\n  JSON   : {r['json']}\n  YouTube: {r['youtube']}")
    elif cmd == "apply" and len(sys.argv) > 2:
        want = set(sys.argv[2:])
        rows = mismatches()
        for r in rows:
            if r["episode_id"] not in want:
                continue
            p = r["path"]
            text = p.read_text(encoding="utf-8")
            old = json.dumps(r["json"], ensure_ascii=False)
            new = json.dumps(r["youtube"], ensure_ascii=False)
            if f'"youtube_title": {old}' not in text:
                print(f"{r['episode_id']}: 書き換え箇所が見つからない（手で直してください）")
                continue
            p.write_text(text.replace(f'"youtube_title": {old}', f'"youtube_title": {new}', 1), encoding="utf-8")
            print(f"✓ {r['episode_id']}: youtube_title を YouTube 側に合わせた")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
