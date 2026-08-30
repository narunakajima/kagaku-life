#!/usr/bin/env python3
"""
kl_yt_reporting_job.py — YouTube Reporting API のジョブ管理

事前に kl_yt_reporting_auth.py で yt-analytics.readonly スコープを含む
トークン（~/.claude/secrets/yt_token_kl_reporting.json）を発行しておくこと。

使い方:
  python3 kl_yt_reporting_job.py --list-types          # 利用可能なレポートタイプ一覧
  python3 kl_yt_reporting_job.py --create channel_basic_a2 [--name 任意の名前]
  python3 kl_yt_reporting_job.py --list-jobs           # 登録済みジョブ一覧
  python3 kl_yt_reporting_job.py --list-reports <job_id>   # 生成済みレポート一覧
  python3 kl_yt_reporting_job.py --download <job_id> <report_id> <output_path>
"""

import argparse
import sys
from pathlib import Path

import google_auth_httplib2
import httplib2
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SECRETS_DIR = Path.home() / ".claude" / "secrets"
YT_TOKEN_REPORTING = SECRETS_DIR / "yt_token_kl_reporting.json"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def get_reporting_client():
    if not YT_TOKEN_REPORTING.exists():
        print(f"❌ トークンが見つかりません: {YT_TOKEN_REPORTING}")
        print("   先に `python3 kl_yt_reporting_auth.py` を実行して認証してください。")
        sys.exit(1)

    creds = Credentials.from_authorized_user_file(str(YT_TOKEN_REPORTING), SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            YT_TOKEN_REPORTING.write_text(creds.to_json())
        else:
            print("❌ トークンが無効です。kl_yt_reporting_auth.py で再認証してください。")
            sys.exit(1)

    return build("youtubereporting", "v1", credentials=creds)


def list_report_types(yt):
    resp = yt.reportTypes().list().execute()
    print("━━━ 利用可能なレポートタイプ ━━━")
    for rt in resp.get("reportTypes", []):
        print(f"  {rt['id']:35s} {rt.get('name', '')}")


def create_job(yt, report_type_id, name):
    body = {"reportTypeId": report_type_id, "name": name or f"kl-{report_type_id}"}
    resp = yt.jobs().create(body=body).execute()
    print("✓ ジョブを作成しました")
    print(f"  job_id : {resp['id']}")
    print(f"  name   : {resp['name']}")
    print(f"  type   : {resp['reportTypeId']}")
    print("  ※ レポートはこの後、Google 側で自動的に毎日生成されます（最大180日分）")


def list_jobs(yt):
    resp = yt.jobs().list().execute()
    print("━━━ 登録済みジョブ ━━━")
    for job in resp.get("jobs", []):
        print(f"  {job['id']}  {job['reportTypeId']:30s} {job['name']}")


def list_reports(yt, job_id):
    resp = yt.jobs().reports().list(jobId=job_id).execute()
    print(f"━━━ ジョブ {job_id} のレポート一覧 ━━━")
    for rep in resp.get("reports", []):
        print(f"  {rep['id']}  期間:{rep['startTime']}〜{rep['endTime']}  作成:{rep['createTime']}")


def download_report(yt, job_id, report_id, output_path):
    rep = yt.jobs().reports().get(jobId=job_id, reportId=report_id).execute()
    url = rep["downloadUrl"]

    creds = Credentials.from_authorized_user_file(str(YT_TOKEN_REPORTING), SCOPES)
    authed_http = google_auth_httplib2.AuthorizedHttp(creds, http=httplib2.Http())
    resp, content = authed_http.request(url)
    if resp.status != 200:
        print(f"❌ ダウンロード失敗: status={resp.status}")
        sys.exit(1)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(content)
    print(f"✓ 保存しました: {out}")


def main():
    parser = argparse.ArgumentParser(description="YouTube Reporting API ジョブ管理")
    parser.add_argument("--list-types", action="store_true")
    parser.add_argument("--create", metavar="REPORT_TYPE_ID")
    parser.add_argument("--name", metavar="NAME")
    parser.add_argument("--list-jobs", action="store_true")
    parser.add_argument("--list-reports", metavar="JOB_ID")
    parser.add_argument("--download", nargs=3, metavar=("JOB_ID", "REPORT_ID", "OUTPUT_PATH"))
    args = parser.parse_args()

    yt = get_reporting_client()

    if args.list_types:
        list_report_types(yt)
    elif args.create:
        create_job(yt, args.create, args.name)
    elif args.list_jobs:
        list_jobs(yt)
    elif args.list_reports:
        list_reports(yt, args.list_reports)
    elif args.download:
        job_id, report_id, output_path = args.download
        download_report(yt, job_id, report_id, output_path)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
