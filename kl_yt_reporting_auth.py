#!/usr/bin/env python3
"""
kl_yt_reporting_auth.py — YouTube Reporting API 用のスコープで認証する

既存の kl_sns_up.py が使う認証（yt_token_kl.json）には
youtube.upload / youtube.force-ssl スコープしか含まれておらず、
Reporting API（チャンネルの分析レポート定期生成）を使うには
yt-analytics.readonly のスコープを追加した状態で再度ブラウザ認可フローを通す必要がある。

このスクリプトを実行すると:
  1. ブラウザが自動で開き、Google アカウントでのログイン・許可画面が表示される
  2. 許可すると、新しいスコープを含むトークンが
     ~/.claude/secrets/yt_token_kl_reporting.json に保存される
  3. 保存後、認証チャンネルが幸せな未来のサイエンス（kagaku-life）であることを確認して表示する

※ 既存の yt_token_kl.json（アップロード用）は上書きしない。
   Reporting API 用は別ファイルとして分離管理する。

使い方:
  python3 kl_yt_reporting_auth.py
  python3 kl_yt_reporting_auth.py --monetary   # 収益レポートも使う場合
"""

import argparse
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

KAGAKU_LIFE_CHANNEL_ID = "UCj5pDosl_4FiaZ_NdNg7IcA"  # 幸せな未来のサイエンス チャンネルID

SECRETS_DIR = Path.home() / ".claude" / "secrets"
YT_CLIENT_SECRETS = SECRETS_DIR / "yt_client_secrets.json"
YT_TOKEN_REPORTING = SECRETS_DIR / "yt_token_kl_reporting.json"

BASE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
MONETARY_SCOPE = "https://www.googleapis.com/auth/yt-analytics-monetary.readonly"


def main():
    parser = argparse.ArgumentParser(description="YouTube Reporting API 用スコープで再認証する")
    parser.add_argument("--monetary", action="store_true", help="収益レポート用スコープも追加する")
    args = parser.parse_args()

    scopes = list(BASE_SCOPES)
    if args.monetary:
        scopes.append(MONETARY_SCOPE)

    if not YT_CLIENT_SECRETS.exists():
        print(f"❌ 認証ファイルが見つかりません: {YT_CLIENT_SECRETS}")
        sys.exit(1)

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  YouTube Reporting API 用スコープで再認証します")
    print("  追加スコープ: yt-analytics.readonly" + ("（+ yt-analytics-monetary.readonly）" if args.monetary else ""))
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()
    print("  ブラウザが開きます。幸せな未来のサイエンス のチャンネルに紐づく")
    print("  Google アカウントでログインし、すべての権限を許可してください。")
    print()

    creds = None
    if YT_TOKEN_REPORTING.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(YT_TOKEN_REPORTING), scopes)
        except Exception:
            creds = None

    if creds and creds.valid:
        print("  ✓ 既存トークンが有効です（再認証は不要でした）")
    else:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None

        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file(str(YT_CLIENT_SECRETS), scopes)
            creds = flow.run_local_server(port=8084, prompt="select_account consent")

        YT_TOKEN_REPORTING.parent.mkdir(parents=True, exist_ok=True)
        YT_TOKEN_REPORTING.write_text(creds.to_json())
        print(f"  ✓ トークンを保存しました: {YT_TOKEN_REPORTING}")

    # チャンネル確認（誤チャンネル認証防止）
    youtube = build("youtube", "v3", credentials=creds)
    ch_resp = youtube.channels().list(part="snippet", mine=True).execute()
    ch_items = ch_resp.get("items", [])
    if ch_items:
        ch_id = ch_items[0]["id"]
        ch_name = ch_items[0]["snippet"]["title"]
        print(f"  認証チャンネル: {ch_name} ({ch_id})")
        if ch_id != KAGAKU_LIFE_CHANNEL_ID:
            print("  ❌ エラー: 幸せな未来のサイエンス チャンネルではありません！")
            print(f"  rm {YT_TOKEN_REPORTING} で再認証してください。")
            YT_TOKEN_REPORTING.unlink(missing_ok=True)
            sys.exit(1)
    else:
        print("  警告: チャンネル情報を取得できませんでした。")

    print()
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  ✓ 完了 — これで kl_yt_reporting_job.py からジョブ登録が行えます")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


if __name__ == "__main__":
    main()
