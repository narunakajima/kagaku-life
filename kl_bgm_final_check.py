"""
kl_bgm_final_check.py — 選定済みBGM3曲（intro/main/outro）の最終検証

samurai-chroniclesの sc_bgm_final_check.py と同じ仕組み。テキストベースの候補絞り込みを
終えたあと、実際の音声3曲 + 制作確認書全文を Gemini に渡し、トーン適合・3曲の流れ・
音質面を実音声ベースで最終判定する。

使い方:
  python3 kl_bgm_final_check.py --episode kl002
"""
import argparse
import os
import sys
from pathlib import Path
from google import genai

API_KEY = os.environ.get("GEMINI_API_KEY_KL") or os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-flash-latest"

DESKTOP_KL = Path(os.path.expanduser("~/Desktop/kagaku-life"))

PROMPT = """あなたは「幸せな未来のサイエンスチャンネル」（AI・ロボティクス研究解説×
使い捨ての生活者による物語演出、日本語YouTubeチャンネル）の音楽監督です。
以下に添付するのは、{episode}エピソードの完全な制作確認書と、このエピソードのBGMとして
選定された3曲の実音声です（intro→main→outroの順にクロスフェードでつながる3曲構成）。

【制作確認書】
{review_doc}

【添付音声】
1. intro（序盤 teaser〜citation 用）
2. main（中盤 context〜data、主人公の悩み〜研究紹介 用）
3. outro（終盤 impact〜closing、未来の暮らし〜締め 用）

以下を実際に聴いた上で判定してください：

1. 各曲は「温かく、希望が持てる、押し付けがましくない」というチャンネル方針に合致しているか
   （SF的に冷たい/大仰に壮大すぎる/悲壮すぎる曲は不適切）
2. 各曲のトーン・テンポ・感情が、対応するシーン群のナレーション内容に合っているか
   （introは好奇心・導入、mainは共感できる悩みから研究紹介への高まり、outroは
   温かい余韻・小さな幸せ）
3. intro→main→outroの3曲を通して聴いたとき、感情の流れに破綻がないか。
   特に3曲間の調性・音圧・テンポの落差が急激すぎないか
4. 音質面で気になる点（ループノイズ、フェードの唐突さ、ラウドネスの著しい差など）
5. 総合判定：このまま採用してよいか、どれか差し替えるべきか

日本語で、各曲ごとの評価→総合判定の順に、簡潔に（600字程度）回答してください。
"""


# 掛け合い形式（2026-10-04〜）用。制作確認書の代わりに台本（シーンごとの役割と台詞）を渡す。
# main（ツッコミ・答え合わせ）は軽い緊張感を許可している（CLAUDE.md「掛け合い形式への転換」）。
DIALOGUE_PROMPT = """あなたは日本語の科学解説YouTubeチャンネル「幸せな未来のサイエンス」の音楽監督です。
番組は、夢語り担当（元エンジニアの男性）とツッコミ担当（統計に強い女性）の二人が、論文を持ち寄って
「それは本当に暮らしに来るのか」を掛け合いで確かめ、最後に「もうすぐ来る／10年はかかる／まだ眉唾」を判定する形式です。
以下は{episode}の台本（シーンごとのBGMの役割と台詞）と、選んだBGM3曲の実音声です（intro→main→outroの順に
クロスフェードでつながります）。

【台本】
{review_doc}

【各曲の役割】
1. intro: 冒頭の問い〜研究紹介〜夢語り（好奇心・期待・少しワクワク）
2. main: ツッコミ・答え合わせ（軽い緊張感や遊び心があってよい。考えごとをしているような、
   少しとぼけた、ピチカートなど。重い・暗い・攻撃的・ホラー調は不可）
3. outro: 判定〜締め（余韻。判定が割れる・厳しい回もあるので、甘すぎず落ち着いたもの）

以下を実際に聴いた上で判定してください：
1. 各曲が役割に合っているか。台詞（二人の会話）の邪魔にならないか（ボーカル・強い主旋律・派手な展開は不可）
2. 3曲を通したときの流れに破綻がないか（調性・音圧・テンポの急な落差）
3. 音質面（ループノイズ、フェードの唐突さ、ラウドネスの差）
4. 総合判定: このまま採用してよいか、どれを差し替えるべきか

日本語で、各曲ごとの評価→総合判定の順に、簡潔に（600字程度）回答してください。
"""


def find_role_file(bgm_dir: Path, role: str) -> Path:
    matches = sorted(bgm_dir.glob(f"{role}_*.mp3"))
    if not matches:
        print(f"❌ {role} の音声ファイルが見つかりません: {bgm_dir}", file=sys.stderr)
        sys.exit(1)
    if len(matches) > 1:
        print(f"⚠️  {role} に複数ファイルがあります。最初の1件を使用: {matches[0].name}", file=sys.stderr)
    return matches[0]


def main():
    parser = argparse.ArgumentParser(description="選定済みBGM3曲の最終検証（実音声+制作確認書をGeminiに渡す）")
    parser.add_argument("--episode", required=True, help="エピソードID（例: kl002）")
    args = parser.parse_args()

    if not API_KEY:
        print("❌ GEMINI_API_KEY が設定されていません", file=sys.stderr)
        sys.exit(1)

    import json
    ep_path = Path(__file__).parent / "episodes" / f"{args.episode}.json"
    ep = json.loads(ep_path.read_text(encoding="utf-8")) if ep_path.exists() else {}
    prompt_template = PROMPT
    review_path = DESKTOP_KL / f"{args.episode}_制作確認書.txt"
    if ep.get("format") == "dialogue":
        import kl_dialogue as D
        cast = D.load_cast()
        review_text = "\n\n".join(
            f"S{s['scene_id']:02d} [{s['type']} / BGM:{D.scene_bgm_role(s)}]\n{D.scene_text(s, cast)}"
            for s in ep["scenes"])
        prompt_template = DIALOGUE_PROMPT
    elif not review_path.exists():
        print(f"❌ 制作確認書が見つかりません: {review_path}", file=sys.stderr)
        print("  先に kl_confirmation_doc.py --episode {args.episode} を実行してください", file=sys.stderr)
        sys.exit(1)
    else:
        review_text = review_path.read_text(encoding="utf-8")

    bgm_dir = DESKTOP_KL / "BGM"
    tracks = {
        "intro": find_role_file(bgm_dir, "intro"),
        "main": find_role_file(bgm_dir, "main"),
        "outro": find_role_file(bgm_dir, "outro"),
    }

    client = genai.Client(api_key=API_KEY)

    parts = [prompt_template.format(episode=args.episode, review_doc=review_text)]
    for role, path in tracks.items():
        data = path.read_bytes()
        parts.append(f"\n--- 以下は「{role}」用の音声（{path.name}）です ---\n")
        parts.append(genai.types.Part.from_bytes(data=data, mime_type="audio/mpeg"))

    response = client.models.generate_content(
        model=MODEL,
        contents=parts,
    )
    print(response.text)


if __name__ == "__main__":
    main()
