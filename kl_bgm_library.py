"""
kl_bgm_library.py — BGM ライブラリ管理ユーティリティ

samurai-chroniclesの sc_bgm_library.py と同じ仕組み（KL用にパスを差し替え）。

使い方:
  # Freesound新規BGMをライブラリに追加（役割別: intro/main/outro）
  python3 kl_bgm_library.py --add --episode kl002 --role intro --file <path> --stem intro_candidate_01_xxx

  # ライブラリ既存BGMをエピソードに紐付け（bgm_sources[role] を episode JSON に記録）
  python3 kl_bgm_library.py --use-library --episode kl002 --role main --stem main_library_01_kl001-BGM
"""

import argparse
import json
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
LIBRARY_JSON = BASE_DIR / "bgm_library.json"
DRIVE_BASE = (
    Path.home()
    / "Library/CloudStorage"
    / "GoogleDrive-naru.nakajima@gmail.com"
    / "マイドライブ"
    / "Kagaku-Life"
)


def _load_library() -> list:
    if LIBRARY_JSON.exists():
        return json.loads(LIBRARY_JSON.read_text(encoding="utf-8"))
    return []


def _save_library(data: list):
    LIBRARY_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_ep(episode_id: str) -> tuple:
    """エピソードJSON を読み込んで (data, path) を返す。"""
    ep_json = BASE_DIR / "episodes" / f"{episode_id}.json"
    if not ep_json.exists():
        print(f"❌ エピソードJSONが見つかりません: {ep_json}")
        sys.exit(1)
    data = json.loads(ep_json.read_text(encoding="utf-8"))
    return data, ep_json


def _save_ep(ep_json: Path, data: dict):
    ep_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _tags_from_stem(stem: str) -> list:
    """Freesound ファイル名のキーワードからタグを推測する。
    例: intro_candidate_01_12345_gentle-piano → ["gentle", "piano"]
    """
    cleaned = re.sub(r'^(?:BGM|intro|main|outro)_candidate_\d+_\d+_', '', stem)
    words = re.split(r'[-_\s]+', cleaned.lower())
    known = {"warm", "gentle", "hopeful", "uplifting", "inspiring", "cozy",
             "heartfelt", "piano", "strings", "acoustic", "soft", "calm",
             "emotional", "tender", "optimistic", "light", "airy"}
    return [w for w in words if w in known] or ["warm", "gentle"]


def cmd_add(episode_id: str, bgm_file: Path, stem: str, role: str = None):
    """Freesound 新規BGMをライブラリに追加し、used_in を記録する。

    role 指定時（3曲構成）: BGM/{ep}-BGM-{role}.mp3 として保存し、
    episode JSON の bgm_sources[role] にパスを記録する。
    """
    library = _load_library()

    bgm_folder = DRIVE_BASE / "BGM"
    bgm_folder.mkdir(exist_ok=True)
    suffix = f"-{role}" if role else ""
    dst = bgm_folder / f"{episode_id}-BGM{suffix}.mp3"
    import shutil
    shutil.move(str(bgm_file), str(dst))
    rel_path = f"BGM/{episode_id}-BGM{suffix}.mp3"
    print(f"  ✓ Drive BGM/ に移動: {dst.name}")

    if role:
        ep_data, ep_json = _load_ep(episode_id)
        ep_data.setdefault("bgm_sources", {})[role] = rel_path
        _save_ep(ep_json, ep_data)
        print(f"  ✓ bgm_sources.{role} を設定: {rel_path}")

    existing = next((e for e in library if e["path"] == rel_path), None)
    if existing:
        if episode_id not in existing["used_in"]:
            existing["used_in"].append(episode_id)
            _save_library(library)
        print(f"  ✓ ライブラリ更新（既存エントリに {episode_id} を追加）")
        return

    tags = _tags_from_stem(stem)
    entry = {
        "id": f"{episode_id}-BGM{suffix}",
        "path": rel_path,
        "duration": 0,
        "license": "CC0",
        "credit": None,
        "tags": tags,
        "used_in": [episode_id],
    }

    credit_path = Path(f"/tmp/kl_bgm_credits/{stem}.credit.txt")
    if credit_path.exists():
        entry["license"] = "CC BY"
        entry["credit"] = credit_path.read_text(encoding="utf-8").strip()

    library.append(entry)
    _save_library(library)
    print(f"  ✓ ライブラリに追加: {rel_path}  tags={tags}")


def cmd_use_library(episode_id: str, stem: str, role: str = None):
    """ライブラリ既存BGMをエピソードに紐付ける（episode JSON に記録）。"""
    library = _load_library()
    ep_data, ep_json = _load_ep(episode_id)

    lib_id = re.sub(r'^(?:BGM|intro|main|outro)_library_\d+_', '', stem)
    entry = next((e for e in library if e["id"] == lib_id), None)

    if not entry:
        print(f"❌ ライブラリにエントリが見つかりません: id={lib_id}")
        sys.exit(1)

    if role:
        ep_data.setdefault("bgm_sources", {})[role] = entry["path"]
        print(f"  ✓ bgm_sources.{role} を設定: {entry['path']}")
    else:
        ep_data["bgm_source"] = entry["path"]
    _save_ep(ep_json, ep_data)

    if episode_id not in entry["used_in"]:
        entry["used_in"].append(episode_id)
        _save_library(library)

    if entry["license"] == "CC BY" and entry.get("credit"):
        credit_tmp = Path(f"/tmp/kl_bgm_credits/{stem}.credit.txt")
        credit_tmp.parent.mkdir(parents=True, exist_ok=True)
        credit_tmp.write_text(entry["credit"], encoding="utf-8")

    if not role:
        print(f"  ✓ bgm_source を設定: {entry['path']}")
    print(f"  ✓ ライブラリ used_in 更新: {entry['used_in']}")


def cli():
    parser = argparse.ArgumentParser(description="BGMライブラリ管理")
    parser.add_argument("--add", action="store_true", help="新規BGMをライブラリに追加")
    parser.add_argument("--use-library", action="store_true", help="ライブラリ曲をエピソードに紐付け")
    parser.add_argument("--episode", required=True)
    parser.add_argument("--file", help="BGMファイルパス（--add 時）")
    parser.add_argument("--stem", required=True, help="ファイル名（拡張子なし）")
    parser.add_argument("--role", choices=["intro", "main", "outro"],
                        help="3曲構成の役割（bgm_sources[role] に記録）")
    args = parser.parse_args()

    if args.add:
        if not args.file:
            parser.error("--add には --file が必要です")
        cmd_add(args.episode, Path(args.file), args.stem, role=args.role)
    elif args.use_library:
        cmd_use_library(args.episode, args.stem, role=args.role)
    else:
        parser.error("--add または --use-library を指定してください")


if __name__ == "__main__":
    cli()
