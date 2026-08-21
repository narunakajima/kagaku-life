"""
kl_inject_bgm_credit.py — BGM CC BY クレジットを episodes/kl{NNN}.json の youtube_description に注入する

使い方（kl_bgm_library.py --add でのBGM登録後に呼び出す）:
  python3 kl_inject_bgm_credit.py --episode kl002 --credit-file /tmp/kl_bgm_credits/intro_candidate_01_xxx.credit.txt

credit.txt が存在しない（CC0 曲）場合は何もしない。
すでにクレジットが含まれている場合も重複追加しない。
"""

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent


def run(episode_id: str, credit_file: Path):
    if not credit_file.exists():
        print(f"  クレジットファイルなし（CC0曲）: スキップ")
        return

    credit_line = credit_file.read_text(encoding="utf-8").strip()
    if not credit_line:
        print(f"  クレジットファイルが空: スキップ")
        return

    ep_json = BASE_DIR / "episodes" / f"{episode_id}.json"
    if not ep_json.exists():
        print(f"❌ エピソードJSONが見つかりません: {ep_json}")
        sys.exit(1)

    with open(ep_json, encoding="utf-8") as f:
        ep = json.load(f)

    desc = ep.get("youtube_description", "")

    if credit_line in desc:
        print(f"  クレジット既に存在: スキップ")
        return

    hashtag_idx = desc.find("\n#")
    if hashtag_idx != -1:
        desc = desc[:hashtag_idx] + f"\n\n{credit_line}" + desc[hashtag_idx:]
    else:
        desc = desc.rstrip() + f"\n\n{credit_line}"

    ep["youtube_description"] = desc

    with open(ep_json, "w", encoding="utf-8") as f:
        json.dump(ep, f, ensure_ascii=False, indent=2)

    print(f"  ✓ クレジットを ep.json に追記しました:")
    print(f"    {credit_line}")


def cli():
    parser = argparse.ArgumentParser(description="BGM CC BY クレジット注入")
    parser.add_argument("--episode", required=True, help="エピソードID（例: kl002）")
    parser.add_argument("--credit-file", required=True, type=Path,
                        help="BGM の .credit.txt ファイルパス")
    args = parser.parse_args()
    run(args.episode, args.credit_file)


if __name__ == "__main__":
    cli()
