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

    2026-10-06: 該当語が無いときに ["warm", "gentle"] を入れる既定値をやめた（33曲中28曲が
    この既定値で warm/gentle になり、tags が曲調を表していなかった）。該当語が無ければ空。
    曲調は --bpm / --mood / --instruments / --has-beat / --era / --role-fit で明示的に記録する。
    """
    cleaned = re.sub(r'^(?:BGM|intro|main|outro)_candidate_\d+_\d+_', '', stem)
    words = re.split(r'[-_\s]+', cleaned.lower())
    known = {"warm", "gentle", "hopeful", "uplifting", "inspiring", "cozy",
             "heartfelt", "piano", "strings", "acoustic", "soft", "calm",
             "emotional", "tender", "optimistic", "light", "airy",
             "upbeat", "synth", "lofi", "beat", "pizzicato", "playful", "pop",
             "electronic", "chill", "corporate", "rhodes", "guitar", "hiphop"}
    return [w for w in words if w in known]


def _probe_duration(path: Path) -> float:
    """ffprobe で実測した長さ（秒）。測れなければ0。"""
    import subprocess
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "csv=p=0", str(path)], capture_output=True, text=True, timeout=60)
        return round(float(r.stdout.strip()), 2)
    except Exception:
        return 0.0


def _find_sidecar(stem: str, bgm_file: Path, ext: str) -> Path:
    """kl_freesound_download.py / 共有版 freesound_download.py が書いたクレジット・メタ情報を探す。

    探す順: /tmp/kl_bgm_credits/{stem}, /tmp/kl_bgm_credits/{元のbasename},
    /tmp/kl_bgm_credits/id_{ファイル名中のFreesound id}, /tmp/lw_bgm_credits/{元のbasename}
    """
    cands = [Path(f"/tmp/kl_bgm_credits/{stem}{ext}"),
             Path(f"/tmp/kl_bgm_credits/{bgm_file.stem}{ext}")]
    m = re.search(r'_candidate_\d+_(\d+)_', f"{stem} {bgm_file.stem}")
    if m:
        cands.append(Path(f"/tmp/kl_bgm_credits/id_{m.group(1)}{ext}"))
    if ext == ".credit.txt":
        cands.append(Path(f"/tmp/lw_bgm_credits/{bgm_file.stem}{ext}"))
    return next((c for c in cands if c.exists()), None)


def cmd_add(episode_id: str, bgm_file: Path, stem: str, role: str = None, meta: dict = None):
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

    tags = _tags_from_stem(stem)

    # freesound_download.py（lamp-whisper由来の共有スクリプト、そのまま流用のため
    # 変更しない）はクレジットを /tmp/kl_bgm_credits/ ではなく /tmp/lw_bgm_credits/
    # に、ダウンロード直後のファイル名（stemではなく元のbasename）で書き出す。
    # このディレクトリ名の不一致により、CC BY曲のクレジットが自動で拾われず
    # license/creditが常にCC0/Noneのままになる不具合があった（kl005で発覚）。
    # kl_bgm_credits/{stem} を優先しつつ、lw_bgm_credits/{元のbasename} も
    # フォールバックとして見る。
    # 2026-10-06: kl_freesound_download.py は /tmp/kl_bgm_credits/{ダウンロード時のstem} と
    # id_{Freesound id} の両方に書くので、役割名にリネームした後でも id から拾える。
    credit_path = _find_sidecar(stem, bgm_file, ".credit.txt")
    license_, credit = ("CC BY", credit_path.read_text(encoding="utf-8").strip()) \
        if credit_path else ("CC0", None)
    if not credit_path:
        print("  ⚠️ クレジットファイルが見つからないため CC0 として登録します。CC BY の曲なら"
              " --source-id を付けるか、ダウンロード時のファイル名のまま --file に渡してください")

    # 曲調のメタデータ（2026-10-06）。未指定の項目は空のまま記録する。
    meta = dict(meta or {})
    meta_path = _find_sidecar(stem, bgm_file, ".meta.json")
    fs_meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path else {}
    extra = {
        "duration": _probe_duration(dst),
        "source_id": fs_meta.get("source_id") or meta.pop("source_id", None),
        "source_name": fs_meta.get("source_name"),
        "source_url": fs_meta.get("url"),
        "bpm": meta.get("bpm"),
        "mood": meta.get("mood") or [],
        "instruments": meta.get("instruments") or [],
        "has_beat": meta.get("has_beat"),
        "era": meta.get("era") or "",
        "role_fit": meta.get("role_fit") or ([role] if role else []),
    }

    existing = next((e for e in library if e["path"] == rel_path), None)
    if existing:
        # dst（Drive上のファイル名）は episode_id+role だけで決まるため、
        # 同じ役割を同じエピソード内で差し替えると同じpathに新しい曲が
        # 上書きされる。以前は「既存path＝同一曲」とみなしてtags/license/
        # creditの更新をスキップしていたため、差し替え後もライブラリの
        # メタデータが古い曲のまま残る不具合があった（kl005で発覚。この時は
        # 偶然どちらもCC0だったため実害は出なかったが、CC BY曲を差し替える
        # ケースでは誤ったクレジット表示につながりかねない）。
        # --add は常に新しいダウンロード内容を表すため、実体ファイル同様に
        # メタデータも常に上書きする。
        existing["tags"] = tags
        existing["license"] = license_
        existing["credit"] = credit
        existing.update(extra)
        if episode_id not in existing["used_in"]:
            existing["used_in"].append(episode_id)
        _save_library(library)
        print(f"  ✓ ライブラリ更新（既存エントリのメタデータを新曲の内容で上書き）")
        return

    entry = {
        "id": f"{episode_id}-BGM{suffix}",
        "path": rel_path,
        "license": license_,
        "credit": credit,
        "tags": tags,
        "used_in": [episode_id],
    }
    entry.update(extra)

    library.append(entry)
    _save_library(library)
    print(f"  ✓ ライブラリに追加: {rel_path}  duration={extra['duration']}s bpm={extra['bpm']}"
          f" mood={extra['mood']} instruments={extra['instruments']} era={extra['era'] or '-'}")


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
    # 曲調のメタデータ（--add 時のみ、すべて任意。2026-10-06追加）
    def _csv(v):
        return [x.strip() for x in v.split(",") if x.strip()] if v else []
    parser.add_argument("--bpm", type=float, help="テンポ（例: 92）")
    parser.add_argument("--mood", help="カンマ区切り（例: bright,playful / neutral / emotional）")
    parser.add_argument("--instruments", help="カンマ区切り（例: synth,lofi-beat,piano,pizzicato）")
    parser.add_argument("--has-beat", choices=["yes", "no"], help="ビート（ドラム）の有無")
    parser.add_argument("--era", choices=["dialogue", "legacy_monologue"],
                        help="掛け合い形式向き（dialogue）か、旧形式向き（legacy_monologue）か")
    parser.add_argument("--role-fit", help="合う役割をカンマ区切り（例: intro,outro）。省略時は --role")
    parser.add_argument("--source-id", help="FreesoundのID（ファイル名から分からないときのクレジット・重複除外用）")
    args = parser.parse_args()

    if args.add:
        if not args.file:
            parser.error("--add には --file が必要です")
        meta = {
            "bpm": args.bpm,
            "mood": _csv(args.mood),
            "instruments": _csv(args.instruments),
            "has_beat": {"yes": True, "no": False}.get(args.has_beat),
            "era": args.era,
            "role_fit": _csv(args.role_fit),
            "source_id": args.source_id,
        }
        if args.source_id:
            for ext in (".credit.txt", ".meta.json"):
                src = Path(f"/tmp/kl_bgm_credits/id_{args.source_id}{ext}")
                if src.exists():
                    dst = Path(f"/tmp/kl_bgm_credits/{args.stem}{ext}")
                    if not dst.exists():
                        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        cmd_add(args.episode, Path(args.file), args.stem, role=args.role, meta=meta)
    elif args.use_library:
        cmd_use_library(args.episode, args.stem, role=args.role)
    else:
        parser.error("--add または --use-library を指定してください")


if __name__ == "__main__":
    cli()
