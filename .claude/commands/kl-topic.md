# /kl-topic — くらしを変える科学 論文選定パイプライン

CLAUDE.md「論文選定ロジック（目利きプロセス）」のSTAGE1〜4を順に実行し、
上位候補を提示したうえで、人間の最終ゴーサイン（STAGE5）を経て
`topics_queue.json` に確定エピソードを追記するコマンド。

> 2026-08時点では軽量版。STAGE5の判断基準（「動画にしやすさ」等の実務観点での
> 選び直し）はまだパターン化できていないため、都度の会話に委ねる。何周か運用して
> 判断パターンが固まってきたら、このコマンドに反映していく。

---

## 定数

- スクリプト: `kl_paper_search.py`（STAGE1）→ `kl_paper_screen.py`（STAGE2）→
  `kl_paper_hypecheck.py`（STAGE3）→ `kl_paper_interest_score.py`（STAGE4）
- 中間出力（すべて実行のたびに再生成される作業ファイル。`.gitignore`済み）:
  `stage1_pool.json` / `stage2_screened.json` / `stage3_hypecheck.json` / `stage4_ranked.json`
- 確定キュー: `topics_queue.json`（gitで追跡）

---

## STEP 1 — STAGE1〜4を順に実行する

```bash
python3 kl_paper_search.py
python3 kl_paper_screen.py
python3 kl_paper_hypecheck.py
python3 kl_paper_interest_score.py
```

各STAGE完了後、簡潔な件数サマリのみ報告する（詳細な生データは画面に出さない）:

```
STAGE1: 収集{N}件 → プレフィルタ通過{N}件
STAGE2: pass={N} flag={N} exclude={N}
STAGE3: ok={N} caution={N} high_risk={N}
STAGE4: 上位{N}件をランキング
```

STAGE1〜3は `--category` 指定で特定カテゴリのみの再実行も可能（前回除外理由が
偏っていた場合など、原因調査に使う）。

---

## STEP 2 — 上位候補を提示する

`stage4_ranked.json` の `stage5_candidates`（デフォルト上位5件）を、タイトル・
カテゴリ・総合スコア・スコア内訳・フック案・掲載誌とともに提示する。

**カテゴリの偏りを確認する:** 上位候補が特定サブジャンルに集中している場合は、
その旨を指摘したうえで `all_scored` から他カテゴリの上位候補も参考として示す
（kl001選定時、上位5件中4件が同一カテゴリに偏っていたため、より幅広い視聴者層を
意識して家庭内ロボット・働き方カテゴリから比較検討した実例がある）。

---

## STEP 3 — 既知のパイプラインギャップを踏まえて補足する

CLAUDE.md STAGE2に記載の通り、Semantic Scholarがプレプリント版と正式出版版を
別レコードとして統合していない場合、優れた論文がSTAGE1の自動探索から漏れることが
ある（kl002 "Generative AI at Work" の実例）。

ユーザーが「他にこういうテーマはないか」と聞いてきた場合や、上位候補の質に
納得できない場合は、WebSearchで補助的に探してよい。査読済み掲載であることを
出版元の公式ページURLで人間が直接確認できれば、`pipeline_gap_flag: true` を付けて
候補に加えられる。

---

## STEP 4 — 人間の最終ゴーサイン（STAGE5）

どの候補を次エピソード（複数可）にするか、ユーザーに確認する。スコアだけでなく
「動画にしやすさ」（統計的ヘッジの複雑さ、絵作りのしやすさ、使い捨ての生活者
ストーリーの組み立てやすさ等の実務観点）も踏まえて一緒に検討してよい。

---

## STEP 5 — topics_queue.jsonに追記する

確定した候補を `topics_queue.json` の `queue` 配列末尾に追記する。

- `episode_id`: 既存の最大値+1から連番（`kl00N`）
- `status`: `"confirmed"`
- フィールド構成は既存エントリ（`kl001`/`kl002`）にならう（`title` / `category` /
  `category_label` / `venue` / `year` / `doi`または`url` / `semantic_scholar_id` /
  `authors` / `protagonist` / `hook_idea` / `notes`）
- `pipeline_gap_flag: true` の候補を採用した場合はその旨と根拠を `notes` に明記する

追記後 `total_topics` と `last_updated` を更新する。コミットメッセージには選定理由
（スコア・カテゴリバランス・「動画にしやすさ」等の判断根拠）を残す。pushは他の
作業と同様、通常のgit運用に従う。

---

## 実行タイミングの目安

`status: "confirmed"`（未着手）が少なくなってきたら実行する。SC/LWの
「残り◯件以下で補充」に相当する閾値は、今後の運用実績を見ながら決める
（2026-08時点では1周目のため未確定）。
