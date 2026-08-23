"""
kl_finalize.py — くらしを変える科学 確認済み素材のGoogle Drive格納スクリプト

~/Desktop/kagaku-life/ に生成済みの画像・ナレーション（確認・採用済み）を、
Google Driveのローカル同期フォルダ Kagaku-Life/KL{NNN}/ へコピーする
（SC・LWと同じ「Desktopは確認用、Google Driveはコンテンツ格納用」の運用）。
Desktopは常に最新1エピソード分の確認用でエピソードIDのサブフォルダを
持たないが、Google Drive側はエピソードごとの永続格納先のためKL{NNN}/の
ままとする。本編シーン・サムネイルに加え、shortsフィールド
（shorts{M}_S{NN}.png/.wav）も格納する。

この環境ではディレクトリ一覧（ls/iterdir）がmacOSの権限制約で失敗することがあるため、
episodes/kl{NNN}.jsonのscene_idから期待されるファイル名を直接組み立てて処理する
（存在しないファイルはスキップし、警告を出す）。

使い方:
  python3 kl_finalize.py --episode kl001
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
DESKTOP_DIR = Path.home() / "Desktop" / "kagaku-life"
GDRIVE_ROOT = (
    Path.home()
    / "Library"
    / "CloudStorage"
    / "GoogleDrive-naru.nakajima@gmail.com"
    / "マイドライブ"
    / "Kagaku-Life"
)


def copy_if_exists(src: Path, dst: Path) -> bool:
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"✅ {src.name} → {dst}")
    return True


def main():
    parser = argparse.ArgumentParser(description="確認済み素材をGoogle Driveへ格納")
    parser.add_argument("--episode", required=True, help="エピソードID（例: kl001）")
    args = parser.parse_args()

    ep_path = BASE_DIR / "episodes" / f"{args.episode}.json"
    if not ep_path.exists():
        print(f"❌ {ep_path} がありません", file=sys.stderr)
        sys.exit(1)
    ep = json.loads(ep_path.read_text())

    drive_ep_name = args.episode.upper()  # kl001 -> KL001（SC/LWの命名規則に合わせる）
    drive_ep_dir = GDRIVE_ROOT / drive_ep_name

    desktop_images = DESKTOP_DIR / "images"
    desktop_narration = DESKTOP_DIR / "narration"

    copied = 0
    missing = []

    for scene in ep["scenes"]:
        sid = scene["scene_id"]
        fname = f"S{sid:02d}.png"
        if copy_if_exists(desktop_images / fname, drive_ep_dir / "images" / fname):
            copied += 1
        else:
            missing.append(f"images/{fname}")

        wname = f"S{sid:02d}.wav"
        if copy_if_exists(desktop_narration / wname, drive_ep_dir / "narration" / wname):
            copied += 1
        else:
            missing.append(f"narration/{wname}")

    if copy_if_exists(desktop_images / "thumbnail.png", drive_ep_dir / "images" / "thumbnail.png"):
        copied += 1
    else:
        missing.append("images/thumbnail.png")

    for shorts in ep.get("shorts", []):
        mid = shorts["shorts_id"]
        for i in range(1, len(shorts["scenes"]) + 1):
            fname = f"shorts{mid}_S{i:02d}.png"
            if copy_if_exists(desktop_images / fname, drive_ep_dir / "images" / fname):
                copied += 1
            else:
                missing.append(f"images/{fname}")

            wname = f"shorts{mid}_S{i:02d}.wav"
            if copy_if_exists(desktop_narration / wname, drive_ep_dir / "narration" / wname):
                copied += 1
            else:
                missing.append(f"narration/{wname}")

    desktop_output = DESKTOP_DIR / "output"
    vname = f"{args.episode}.mp4"
    if copy_if_exists(desktop_output / vname, drive_ep_dir / "output" / vname):
        copied += 1
    else:
        missing.append(f"output/{vname}")

    shorts_vname = f"{args.episode}_shorts.mp4"
    if copy_if_exists(desktop_output / shorts_vname, drive_ep_dir / "output" / shorts_vname):
        copied += 1
    else:
        missing.append(f"output/{shorts_vname}")

    print(f"\n{copied}件をGoogle Driveに格納しました: {drive_ep_dir}")
    if missing:
        print(f"\n⚠️ 見つからなかったファイル（未生成または未確認の可能性）: {len(missing)}件")
        for m in missing:
            print(f"  - {m}")


if __name__ == "__main__":
    main()
