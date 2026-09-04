"""
kl_confirmation_doc.py — くらしを変える科学 制作確認書生成スクリプト

episodes/kl{NNN}.json から人間向けの制作確認書（テキスト）を生成する。
SCの制作確認書と異なり、ナレーションは元から日本語のため英日翻訳は行わない。
ファクトチェックは自動化されていないため、人間が出典論文と照合したか
チェックする欄を用意するのみ（自己チェック結果はコミットメッセージ等に残す運用）。

使い方:
  python3 kl_confirmation_doc.py --episode kl001

出力先: ~/Desktop/kagaku-life/kl{NNN}_制作確認書.txt
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
DESKTOP_DIR = Path.home() / "Desktop" / "kagaku-life"

# CLAUDE.md「BGMパイプライン」2026-08-22確定のマッピング
# （intro=teaser/hook/context、main=citation/finding/data、outro=impact/closing）。
# kl_video_gen.py の BGM_ROLE_BY_TYPE と一致させること。
BGM_ROLE_BY_TYPE = {
    "teaser": "intro",
    "hook": "intro",
    "context": "intro",
    "citation": "main",
    "finding": "main",
    "data": "main",
    "impact": "outro",
    "closing": "outro",
}


def estimate_seconds(narration: str) -> float:
    # 日本語ナレーションの目安: 250〜300字/分（ゆったりめの物語調トーンを想定）
    return len(narration) / 275 * 60


def build_doc(ep: dict) -> str:
    lines = []
    add = lines.append

    add("=" * 64)
    add(f"  くらしを変える科学 {ep['episode_id']} 制作確認書")
    add(f"  生成日: {datetime.now().strftime('%Y-%m-%d')}")
    add("=" * 64)
    add("")
    add("【エピソード概要】")
    add("-" * 40)
    add(f"エピソードID  : {ep['episode_id']}")
    add(f"タイトル      : {ep['episode_title']}")
    add(f"YouTubeタイトル: {ep['youtube_title']}")
    add(f"総シーン数    : {len(ep['scenes'])}")
    total_chars = sum(len(s["narration"]) for s in ep["scenes"])
    est_min = estimate_seconds("".join(s["narration"] for s in ep["scenes"])) / 60
    add(f"ナレーション総文字数: {total_chars}字（推定尺 約{est_min:.1f}分・実尺はTTS生成後に確定）")
    protagonist = ep.get("protagonist") or {}
    p_gender = protagonist.get("gender", "—")
    r_gender = {"female": "male", "male": "female"}.get(p_gender, "—")
    add(f"主人公        : {protagonist.get('name', '—')}（{protagonist.get('age', '—')}歳・{protagonist.get('job', '—')}・{p_gender}）")
    add(f"ナレーター    : 生活者ボイス={p_gender} / 研究ボイス={r_gender}（2026-08〜2ナレーター制）")
    add("BGM           : ❌ 未選択")
    add("サムネイル    : ❌ 未生成")
    add("")

    add("=" * 64)
    add(f"【出典】（{len(ep.get('references', []))}本）")
    add("=" * 64)
    add("")
    preprint_count = 0
    for i, ref in enumerate(ep.get("references", [])):
        authors = ", ".join(ref.get("authors", []))
        is_pp = ref.get("is_preprint", False)
        if is_pp:
            preprint_count += 1
        status = "⚠️ プレプリント（査読前）" if is_pp else "✅ 査読済み"
        add(f"[{i}] {authors} ({ref.get('year')}). {ref.get('title')}.")
        add(f"    掲載誌: {ref.get('venue')} — {status}")
        if ref.get("institution"):
            add(f"    所属機関: {ref['institution']}")
        if ref.get("lead_researcher"):
            add(f"    中心研究者: {ref['lead_researcher']}")
        if ref.get("doi"):
            add(f"    DOI: {ref['doi']}")
        if ref.get("url"):
            add(f"    URL: {ref['url']}")
        add("")
    if preprint_count:
        add(f"⚠️ {preprint_count}本がプレプリント（査読前）。「査読」「プレプリント」は専門用語のため")
        add("   ナレーションでは使わず、概要欄の参考文献欄で開示する（CLAUDE.md STAGE2方針、2026-08-20改訂）。")
        add("")

    add("=" * 64)
    add("【ファクトチェック確認欄】")
    add("=" * 64)
    add("")
    add("□ 全シーンのナレーションを出典論文（上記URL/DOI）と1文ずつ突き合わせた")
    add("□ ナレーション内の所属機関・研究者名が出典の記載と一致している")
    add("□ 数値（成功率・人数・統計的有意差の有無等）が本文の記載と一致している")
    add("□ ヘッジ表現（研究段階である旨・限界の記載）が省略されていない")
    add("□ 二次報道由来の誇張表現が混入していない（STAGE3チェック結果と整合）")
    if preprint_count:
        add("□ 「査読」「プレプリント」の語がナレーションに残っていない（概要欄のみでの開示）")
        add("□ ナレーション内で研究段階・未実用化であることが一般的な表現で伝わっている")
    add("")

    add("=" * 64)
    add("【シーンタイプ・BGM役割の内訳】")
    add("=" * 64)
    add("")
    role_counts = {"intro": 0, "main": 0, "outro": 0}
    for s in ep["scenes"]:
        role_counts[BGM_ROLE_BY_TYPE.get(s["type"], "main")] += 1
    add(f"intro（序盤）: {role_counts['intro']}シーン / main（中盤）: {role_counts['main']}シーン / outro（終盤）: {role_counts['outro']}シーン")
    add("")

    add("=" * 64)
    add("【各シーンのナレーション・画像プロンプト】")
    add("=" * 64)
    add("")
    refs = ep.get("references", [])
    for s in ep["scenes"]:
        role = BGM_ROLE_BY_TYPE.get(s["type"], "main")
        est = estimate_seconds(s["narration"])
        narrator = s.get("narrator", "—")
        ref_note = ""
        if "reference_index" in s and 0 <= s["reference_index"] < len(refs):
            ref_note = f"  出典[{s['reference_index']}]: {refs[s['reference_index']].get('title', '')[:40]}"
        add(f"▶ S{s['scene_id']:02d}  [{s['type']} / BGM:{role} / narrator:{narrator}]  文字数: {len(s['narration'])}字（推定実尺: 約{est:.0f}秒）  ken_burns: {s['ken_burns']}{ref_note}")
        add("")
        add(f"  【ナレーション】")
        add(f"  {s['narration']}")
        add("")
        add(f"  【画像プロンプト】")
        add(f"  {s['image_prompt']}")
        add("")
        add("-" * 40)
        add("")

    add("=" * 64)
    add("【YouTube メタデータ】")
    add("=" * 64)
    add("")
    add("▼ 概要欄")
    add(ep.get("youtube_description", ""))
    add("")
    add("▼ タグ")
    add(", ".join(ep.get("youtube_tags", [])))
    add("")
    add("▼ サムネイルプロンプト")
    add(ep.get("thumbnail_prompt", ""))
    add("")

    add("=" * 64)
    add("【確認・承認】")
    add("-" * 40)
    add("□ 内容確認完了")
    add("□ ファクトチェック完了（上記チェック欄）")
    add("□ BGM選択完了")
    add("□ 素材生成GO")
    add("")
    add("備考:")
    add("")
    add("=" * 64)

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="制作確認書生成")
    parser.add_argument("--episode", required=True, help="エピソードID（例: kl001）")
    args = parser.parse_args()

    ep_path = BASE_DIR / "episodes" / f"{args.episode}.json"
    if not ep_path.exists():
        print(f"❌ {ep_path} がありません", file=sys.stderr)
        sys.exit(1)

    ep = json.loads(ep_path.read_text())
    doc = build_doc(ep)

    DESKTOP_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DESKTOP_DIR / f"{args.episode}_制作確認書.txt"
    out_path.write_text(doc)
    print(f"✅ 制作確認書を生成しました: {out_path}")


if __name__ == "__main__":
    main()
