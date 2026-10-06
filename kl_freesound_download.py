#!/usr/bin/env python3
"""
kl_freesound_download.py — kagaku-life専用のFreesound BGM候補ダウンローダー（2026-10-06）

lamp-whisper / samurai-chronicles と共有している $HOME/lamp-whisper/freesound_download.py は
変更せず、掛け合い形式のBGM方針（CLAUDE.md「BGMパイプライン」）に合わせた検索をここで行う。
CLIは共有版と互換（クエリ1〜3個＋出力dir、--round、--start-slot、--library）。

共有版との違い（実測で分かった問題への対処）:
- Freesoundのクエリ語はすべて必須（AND）。3語以上は0件になりやすいので、2語を超えたら警告する
- filter に category:Music を加える（共有版は環境音・効果音も返し、「warm gentle」では上位30件の
  半分以上が Soundscapes / Sound effects だった）
- 名前・タグに環境音・声の語を含むものを手元で落とす。クエリに「-語」を付ける除外は既定では使わない
  （実測: "positive electronic"（90秒以上・Music）65件が、-voice で6件、-field-recording で5件、
  -ambient で3件に減った。説明文の「no vocals」などにも当たるうえ、語によって挙動が不安定なため。
  --query-exclude で有効にできる）
- 並び順は score（関連度）。共有版の rating_desc は、評価の高い同じ曲ばかりを上に出し、
  LW/SC と共有の既出リスト（~/.claude/scripts/.freesound_seen_ids、約800件）で消えて0件になっていた
- 既出リストは kagaku-life 専用（~/.claude/scripts/.kl_freesound_seen_ids）。共有リストは見ない
- 複数ページ（既定で1ページ30件×3ページ）を取って候補を集め、CC0を優先する（CC BYは警告つき）
- 長さの下限を役割別に持つ（intro 90秒・main 120秒・outro 45秒。区間の長さ×0.7が目安）。
  下限を満たす候補が1件も無いときは、30秒以上に緩めて探し直し「短い曲（ループで使う）」と表示する
  （kl_video_gen.py が短い曲をクロスフェードでつないでループするため。つなぎ目は人が聴いて確認する）

使い方:
  # 3クエリ＝intro/main/outro の順（--role を省略して3つ渡すと役割を順に割り当てる）
  python3 kl_freesound_download.py "upbeat synth" "lofi beat" "electric piano" \
      "$HOME/Desktop/kagaku-life/BGM/" --library "$HOME/kagaku-life/bgm_library.json"

  # 1役割だけ差し替え
  python3 kl_freesound_download.py "pizzicato playful" "$HOME/Desktop/kagaku-life/BGM/" \
      --role main --start-slot 2 --round 1 --library "$HOME/kagaku-life/bgm_library.json"

  # ダウンロードせず候補だけ見る（ヒット数・環境音の混入の確認用）
  python3 kl_freesound_download.py "lofi beat" /tmp/x --role main --list 10

オプション:
  --round n         次の候補を見る（n*ページ数 だけページを進める）。既定0
  --start-slot n    ファイル名のスロット番号の開始値。既定1
  --library path    bgm_library.json（重複除外用。source_id・曲名・クレジットの曲名で照合）
  --role r          intro / main / outro（全クエリに適用）。長さの下限を決める
  --min-duration s  長さの下限を直接指定（--role の既定より優先）
  --sort s          score（既定）/ created_desc / downloads_desc など
  --pages n         取得ページ数。既定3
  --no-exclude      手元の除外（名前・タグの環境音・声の語）を使わない（比較用）
  --query-exclude   クエリに「-vocal -vocals -singing -lyrics」を付ける（既定は付けない）
  --no-fallback     下限を満たす候補が無いとき30秒以上に緩めて探し直さない
  --list n          ダウンロードせず、条件を満たす上位n件を表示する
  --count n         1クエリあたりn曲ダウンロードする（既定1。score順の1位が良い曲とは限らないため、
                    役割ごとに2〜3曲取って kl_bgm_qa.py と耳で比べるのを推奨）

出力:
  BGM_candidate_{slot:02d}_{freesound_id}_{name}.mp3 を出力dirへ。
  CC BYの曲はクレジットを /tmp/kl_bgm_credits/{ファイル名stem}.credit.txt に書く
  （kl_bgm_library.py --add が拾う）。全曲について /tmp/kl_bgm_credits/{stem}.meta.json に
  Freesoundのid・曲名・投稿者・ライセンス・長さ・タグを書く（kl_bgm_library.py が source_id 等に記録する）。
  ファイル名を役割名にリネームしても拾えるよう、id_{freesound_id}.credit.txt / .meta.json も書く。
"""

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

API_KEY = os.environ.get("FREESOUND_API_KEY", "")
BASE_URL = "https://freesound.org/apiv2"
SEEN_IDS_FILE = os.path.expanduser("~/.claude/scripts/.kl_freesound_seen_ids")
DEFAULT_LIBRARY_JSON = os.path.expanduser("~/kagaku-life/bgm_library.json")
CREDITS_DIR = "/tmp/kl_bgm_credits"

MAX_DURATION = 300
ROLE_MIN_DURATION = {"intro": 90, "main": 120, "outro": 45}
DEFAULT_MIN_DURATION = 30
DEFAULT_ROLES_FOR_3 = ["intro", "main", "outro"]

PAGE_SIZE = 30
DEFAULT_PAGES = 3
CC0_PREFERENCE_WINDOW = 10  # 条件を満たす上位この件数の中にCC0があればそれを優先する

# クエリに付ける除外語（Freesoundの「-語」はその語を含む音を除外する）
EXCLUDE_TERMS = ["vocal", "vocals", "singing", "lyrics"]  # --query-exclude 時のみ
# 名前・タグにこれらを含むものは手元でも落とす（タグの表記ゆれ対策）
REJECT_WORDS = {
    "vocal", "vocals", "voice", "voices", "singing", "singer", "sing", "lyrics", "rap", "speech",
    "spoken", "choir", "acapella", "a-cappella",
    "ambience", "ambiance", "atmosphere", "soundscape", "field-recording", "fieldrecording",
    "field", "nature", "birds", "bird", "rain", "wind", "insects", "insect", "cicada", "cicadas", "frog",
    "frogs", "crickets", "water", "river", "ocean", "waves", "forest", "street", "traffic", "car",
    "alarm", "siren", "crowd", "room-tone", "sfx", "foley", "drone", "noise", "horror", "epic",
    "battle", "war", "dark", "dubstep", "meditation", "sleep",
}
# 3語以上は0件になりやすい（すべて必須のため）
MAX_QUERY_WORDS = 2


def load_seen_ids() -> set:
    if not os.path.exists(SEEN_IDS_FILE):
        return set()
    with open(SEEN_IDS_FILE) as f:
        return set(line.strip() for line in f if line.strip())


def save_seen_ids(ids: set):
    os.makedirs(os.path.dirname(SEEN_IDS_FILE), exist_ok=True)
    with open(SEEN_IDS_FILE, "w") as f:
        f.write("\n".join(sorted(ids)))


def _normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def load_library_fingerprints(library_json: str) -> tuple:
    ids, names = set(), set()
    if not library_json or not os.path.exists(library_json):
        return ids, names
    try:
        with open(library_json, encoding="utf-8") as f:
            library = json.load(f)
    except (OSError, json.JSONDecodeError):
        return ids, names
    for entry in library:
        if entry.get("source_id"):
            ids.add(str(entry["source_id"]))
        if entry.get("source_name"):
            names.add(_normalize_name(entry["source_name"]))
        m = re.search(r"Music:\s*(.+?)\s+by\s+", entry.get("credit") or "")
        if m:
            names.add(_normalize_name(m.group(1)))
    return ids, names


def license_kind(url: str) -> str:
    u = (url or "").lower()
    if "publicdomain/zero" in u:
        return "CC0"
    if "/by/" in u and "nc" not in u and "nd" not in u and "sa" not in u:
        return "CC BY"
    return "OTHER"


def license_label(url: str) -> str:
    short = (url or "").split("/licenses/")[-1].rstrip("/")
    version = short.split("/")[-1] if "/" in short else ""
    return f"CC BY {version}" if version else "CC BY"


def reject_reason(sound: dict) -> str:
    words = set(re.split(r"[^a-z0-9\-]+", (sound.get("name") or "").lower()))
    words |= {t.lower() for t in sound.get("tags") or []}
    hit = sorted(words & REJECT_WORDS)
    if hit:
        return "除外語: " + ",".join(hit[:3])
    if sound.get("category") and sound["category"] != "Music":
        return f"category={sound['category']}"
    return ""


def build_query(query: str, use_exclude: bool) -> str:
    if not use_exclude:
        return query
    present = set(query.lower().split())
    return query + " " + " ".join(f"-{t}" for t in EXCLUDE_TERMS if t not in present)


def search(query: str, min_dur: float, sort: str, start_page: int, pages: int, use_exclude: bool) -> tuple:
    """条件を満たす候補を集める。戻り値: (総ヒット数, 取得した結果のリスト)"""
    filt = (f"duration:[{min_dur} TO {MAX_DURATION}] "
            'license:("Creative Commons 0" OR "Attribution") category:Music')
    total, results = None, []
    for p in range(start_page, start_page + pages):
        params = urllib.parse.urlencode({
            "query": build_query(query, use_exclude),
            "filter": filt,
            "fields": "id,name,duration,previews,license,username,tags,category,subcategory",
            "page_size": PAGE_SIZE,
            "page": p,
            "sort": sort,
            "token": API_KEY,
        })
        try:
            with urllib.request.urlopen(f"{BASE_URL}/search/text/?{params}", timeout=30) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                break
            raise
        if total is None:
            total = data.get("count", 0)
        page_results = data.get("results", [])
        results += page_results
        if not data.get("next") or not page_results:
            break
    return total or 0, results


def choose(results: list, seen_ids: set, lib_ids: set, lib_names: set, use_exclude: bool) -> tuple:
    """(採用候補リスト（並び順＝score順）, 除外の内訳dict)"""
    eligible, skipped = [], {"既出": 0, "ライブラリ重複": 0, "環境音・声など": 0, "ライセンス": 0}
    for s in results:
        sid = str(s["id"])
        if sid in seen_ids:
            skipped["既出"] += 1
            continue
        if sid in lib_ids or _normalize_name(s["name"]) in lib_names:
            skipped["ライブラリ重複"] += 1
            continue
        if license_kind(s.get("license")) == "OTHER":
            skipped["ライセンス"] += 1
            continue
        if use_exclude:
            why = reject_reason(s)
            if why:
                s["_reject"] = why
                skipped["環境音・声など"] += 1
                continue
        eligible.append(s)
    return eligible, skipped


def pick(eligible: list):
    window = eligible[:CC0_PREFERENCE_WINDOW]
    for s in window:
        if license_kind(s.get("license")) == "CC0":
            return s
    return eligible[0] if eligible else None


def download_sound(sound: dict, output_dir: str, slot: int) -> str:
    preview_url = sound["previews"].get("preview-hq-mp3") or sound["previews"].get("preview-lq-mp3")
    if not preview_url:
        raise ValueError(f"No preview URL for sound {sound['id']}")
    safe_name = re.sub(r"[^\w\-]", "_", sound["name"])[:40]
    filepath = os.path.join(output_dir, f"BGM_candidate_{slot:02d}_{sound['id']}_{safe_name}.mp3")
    req = urllib.request.Request(preview_url, headers={"User-Agent": "kagaku-life-bgm/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(filepath, "wb") as f:
        f.write(resp.read())
    return filepath


def write_sidecars(sound: dict, filepath: str, role: str):
    os.makedirs(CREDITS_DIR, exist_ok=True)
    stem = os.path.splitext(os.path.basename(filepath))[0]
    kind = license_kind(sound.get("license"))
    meta = {
        "source": "freesound",
        "source_id": str(sound["id"]),
        "source_name": sound["name"],
        "username": sound.get("username"),
        "license": kind,
        "license_url": sound.get("license"),
        "duration": round(float(sound.get("duration") or 0), 2),
        "tags": sound.get("tags") or [],
        "subcategory": sound.get("subcategory"),
        "searched_role": role,
        "url": f"https://freesound.org/s/{sound['id']}/",
    }
    credit_line = None
    if kind == "CC BY":
        credit_line = (f'🎵 Music: {sound["name"]} by {sound.get("username", "unknown")} '
                       f'(freesound.org) — {license_label(sound.get("license"))}')
        meta["credit"] = credit_line
    for key in (stem, f"id_{sound['id']}"):
        with open(os.path.join(CREDITS_DIR, f"{key}.meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        if credit_line:
            with open(os.path.join(CREDITS_DIR, f"{key}.credit.txt"), "w", encoding="utf-8") as f:
                f.write(credit_line)
    return credit_line


def parse_args(argv: list) -> dict:
    flags_with_value = {"--round", "--start-slot", "--library", "--role", "--min-duration",
                        "--sort", "--pages", "--list", "--count"}
    opts = {"--no-exclude": False, "--query-exclude": False, "--no-fallback": False}
    positional, i = [], 1
    while i < len(argv):
        a = argv[i]
        if a in flags_with_value:
            if i + 1 >= len(argv):
                sys.exit(f"Error: {a} には値が必要です")
            opts[a] = argv[i + 1]
            i += 2
        elif a in ("--no-exclude", "--query-exclude", "--no-fallback"):
            opts[a] = True
            i += 1
        elif a in ("-h", "--help"):
            print(__doc__)
            sys.exit(0)
        else:
            positional.append(a)
            i += 1
    if len(positional) < 2 or len(positional) > 4:
        sys.exit("Usage: kl_freesound_download.py <q1> [q2] [q3] <output_dir> [--role r] [--round n] "
                 "[--start-slot n] [--library path] [--min-duration s] [--sort s] [--pages n] [--list n]")
    opts["queries"] = positional[:-1]
    opts["output_dir"] = positional[-1]
    return opts


def main():
    if not API_KEY:
        print("Error: FREESOUND_API_KEY is not set.")
        sys.exit(1)
    o = parse_args(sys.argv)
    queries = o["queries"]
    role_opt = o.get("--role")
    if role_opt and role_opt not in ROLE_MIN_DURATION:
        sys.exit(f"Error: --role は intro/main/outro のいずれか（指定: {role_opt}）")
    if role_opt:
        roles = [role_opt] * len(queries)
    elif len(queries) == 3:
        roles = DEFAULT_ROLES_FOR_3
    else:
        roles = [None] * len(queries)
    round_n = int(o.get("--round", 0))
    start_slot = int(o.get("--start-slot", 1))
    pages = int(o.get("--pages", DEFAULT_PAGES))
    sort = o.get("--sort", "score")
    use_exclude = not o["--no-exclude"]
    query_exclude = o["--query-exclude"]
    list_n = int(o["--list"]) if "--list" in o else 0
    count = max(1, int(o.get("--count", 1)))
    library_json = os.path.expanduser(o.get("--library", DEFAULT_LIBRARY_JSON))
    output_dir = o["output_dir"]

    seen_ids = load_seen_ids()
    lib_ids, lib_names = load_library_fingerprints(library_json)
    print(f"Library fingerprints: {len(lib_ids)} ids, {len(lib_names)} names / kl既出: {len(seen_ids)}件")
    if not list_n:
        os.makedirs(output_dir, exist_ok=True)

    downloaded = []
    for i, query in enumerate(queries):
        slot = start_slot + i
        role = roles[i]
        min_dur = float(o["--min-duration"]) if "--min-duration" in o else \
            ROLE_MIN_DURATION.get(role, DEFAULT_MIN_DURATION)
        n_words = len(query.split())
        if n_words > MAX_QUERY_WORDS:
            print(f"    ⚠️  クエリが{n_words}語です。Freesoundは全語必須のため0件になりやすい（2語まで推奨）")
        start_page = 1 + round_n * pages
        print(f"[{slot}] {role or '-'}: '{query}'（{min_dur:.0f}〜{MAX_DURATION}秒, sort={sort}, "
              f"page {start_page}〜{start_page + pages - 1}）")
        total, results = search(query, min_dur, sort, start_page, pages, query_exclude)
        eligible, skipped = choose(results, seen_ids, lib_ids, lib_names, use_exclude)
        short_fallback = False
        if not eligible and min_dur > DEFAULT_MIN_DURATION and not o["--no-fallback"]:
            print(f"    {min_dur:.0f}秒以上の候補なし（総ヒット{total}件）→ {DEFAULT_MIN_DURATION}秒以上に緩めて探し直します")
            total, results = search(query, DEFAULT_MIN_DURATION, sort, start_page, pages, query_exclude)
            eligible, skipped = choose(results, seen_ids, lib_ids, lib_names, use_exclude)
            short_fallback = True
        n_cc0 = sum(license_kind(s.get("license")) == "CC0" for s in eligible)
        print(f"    総ヒット {total}件 / 取得 {len(results)}件 → 候補 {len(eligible)}件（CC0 {n_cc0}）"
              f" / 除外 {', '.join(f'{k}{v}' for k, v in skipped.items() if v) or 'なし'}")

        if list_n:
            for s in eligible[:list_n]:
                print(f"      - [{license_kind(s.get('license'))}] {s['name'][:50]} ({s['duration']:.0f}s) "
                      f"id={s['id']} {s.get('subcategory') or ''}")
            continue

        chosen = []
        for _ in range(count):
            s_ = pick([e for e in eligible if e not in chosen])
            if s_:
                chosen.append(s_)
        if not chosen:
            print(f"    No new results for '{query}'（--round を上げるか、語を変えてください）")
            continue
        for sound in chosen:
            filepath = download_sound(sound, output_dir, slot)
            seen_ids.add(str(sound["id"]))
            kind = license_kind(sound.get("license"))
            print(f"    {sound['name']} ({sound['duration']:.1f}s) [{kind}] {sound.get('subcategory') or ''}")
            if short_fallback or sound["duration"] < min_dur:
                print(f"    ⚠️  短い曲（{min_dur:.0f}秒未満）。動画ではループして使うので、つなぎ目を聴いて確認してください")
            print(f"    Saved: {os.path.basename(filepath)}")
            credit_line = write_sidecars(sound, filepath, role)
            if credit_line:
                print("    ⚠️  CC BY — 概要欄へのクレジットが必要です（kl_bgm_library.py --add が自動で拾います）:")
                print(f"    {credit_line}")
        downloaded.append(query)

    if list_n:
        return
    save_seen_ids(seen_ids)
    print(f"\n{len(downloaded)}/{len(queries)} queries downloaded to: {output_dir}")
    if len(downloaded) < len(queries):
        print("Warning: fewer tracks than expected. Try different queries or --round.")
        sys.exit(1)


if __name__ == "__main__":
    main()
