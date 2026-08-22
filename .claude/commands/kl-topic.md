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
  `kl_venue_allowlist_update.py`（許可リスト更新・提案）→
  `kl_paper_hypecheck.py`（STAGE3）→ `kl_paper_interest_score.py`（STAGE4）
- 中間出力（すべて実行のたびに再生成される作業ファイル。`.gitignore`済み）:
  `stage1_pool.json` / `stage2_screened.json` / `stage3_hypecheck.json` / `stage4_ranked.json`
- 許可リスト: `reputable_venues.json`（gitで追跡。STAGE2のコスト最適化用）
- 確定キュー: `topics_queue.json`（gitで追跡）
- **最終選考候補リスト: `topics_shortlist.json`（gitで追跡、2026-08-21追加）。**
  `stage4_ranked.json`はSTAGE1〜4を再実行するたびに上書きされる作業ファイルの
  ため、STAGE4の上位20件（`stage5_candidates`）は毎回`topics_shortlist.json`に
  追記して恒久的に残す。今回不採用でも、別のストーリー（他の論文との組み合わせ等）
  で後日採用されうるため、`status: "available"`のまま蓄積する（採用されたら
  `status: "used"`・`used_in`にエピソードIDを記録）。既存エントリと
  `paperId`が重複する場合は追記しない（スコア等は初出時点のものを保持）。

---

## STEP 0 — 在庫（topics_shortlist.json）を先に確認する（2026-08-21追加）

STAGE1〜4のフル実行はSemantic Scholar検索・Gemini呼び出し（STAGE2〜4）を
伴うコストのかかる処理であり、かつ**検索条件（`query_vocabulary.json`の
クエリ・カテゴリweight）を変えずに再実行しても、上位には概ね同じ論文が
並ぶ**（母集団が短期間でそう変わらないため）。よって、まず
`topics_shortlist.json` の `status: "available"` 件数を確認する。

- **5件以上残っている場合:** STAGE1〜4のフル実行はスキップし、既存の
  `available` エントリをそのままSTEP2の「上位候補」として提示する
  （スコア・フック案・主人公案は生成済みのものを使う）。
- **5件未満の場合:** 在庫が尽きかけているため、STEP1（STAGE1〜4フル実行）
  に進む。その際、`kl_paper_search.py` の重複排除は `topics_queue.json`
  （採用済み）と `topics_shortlist.json`（採用・未採用問わず既出）の両方を
  見るため、既に見た論文が再スクリーニングされることはない
  （新規の論文のみがSTAGE2以降に回る）。

この閾値（5件）はSC/LWの「残り◯件以下で補充」に相当する目安で、運用実績を
見ながら調整してよい。

---

## STEP 1 — STAGE1・STAGE2を実行し、許可リストを更新する

```bash
python3 kl_paper_search.py
python3 kl_paper_screen.py
python3 kl_venue_allowlist_update.py
```

`kl_venue_allowlist_update.py` は提案のみ行う（`reputable_venues.json` は自動で
書き換えない）。提案された掲載誌をユーザーに見せ、追加してよいか確認してから
`--apply` で反映する（低品質誌を誤って許可リストに載せるリスクがあるため、
必ず人間確認を挟む。CLAUDE.md STAGE2の許可リスト方針参照）。

続けてSTAGE3・STAGE4を実行する:

```bash
python3 kl_paper_hypecheck.py
python3 kl_paper_interest_score.py
```

各STAGE完了後、簡潔な件数サマリのみ報告する（詳細な生データは画面に出さない）:

```
STAGE1: 収集{N}件 → プレフィルタ通過{N}件（うちプレプリント{N}件）
STAGE2: pass={N}（うち許可リスト自動pass{N}） flag={N} exclude={N}
許可リスト提案: {N}件（承認・適用したか）
STAGE3: ok={N} caution={N} high_risk={N}
STAGE4: 上位{N}件をランキング
```

STAGE1〜3は `--category` 指定で特定カテゴリのみの再実行も可能（前回除外理由が
偏っていた場合など、原因調査に使う）。

---

## STEP 2 — 上位候補を提示する

`stage4_ranked.json` の `stage5_candidates`（デフォルト上位20件）を、タイトル・
カテゴリ・総合スコア・スコア内訳・フック案・掲載誌とともに提示する。

**2026-08〜: 上位5件→20件に拡大した。** STAGE4のスコアリング自体は主観的な創作寄りの
判断で、Geminiに単発プロンプトで大量処理させるより人間・Claudeの文脈判断の方が
精度が高い可能性がある。全件を人間が見るのは非現実的なため、一次選抜（大量処理・
低コスト）はGeminiに任せつつ、Claudeが確認する範囲を広げることでスコアだけを
鵜呑みにしない設計にした。

**カテゴリの偏りを確認する:** 上位候補が特定サブジャンルに集中している場合は、
その旨を指摘したうえで `all_scored` から他カテゴリの上位候補も参考として示す
（kl001選定時、上位5件中4件が同一カテゴリに偏っていたため、より幅広い視聴者層を
意識して家庭内ロボット・働き方カテゴリから比較検討した実例がある）。

提示と同時に、この20件を `topics_shortlist.json` に追記する（`paperId` が既存
エントリと重複するものは追記しない）。すべて `status: "available"` として記録し、
STEP5で実際に採用されたものだけ後から `"used"` に更新する。

---

## STEP 2.5 — ストーリー案を3つ提案する（2026-08-21追加）

上位20件（および参考として示した他カテゴリ候補）を踏まえ、**Claudeが実際に
どの論文（複数可）を使ってどんなストーリーを組み立てるか、3案ほど提案する。**
単にスコア順に論文を並べるだけでなく、「動画として面白くなるか」を先に一段階
シミュレートすることで、STEP4の人間判断をやりやすくする（kl001は当初単一論文
案だったが、上位候補にVLA基盤モデル論文が複数集中していたことを踏まえ、
複数論文を組み合わせた「潮流」ストーリーに転換した実績があり、この転換は
スコア表だけを見ていては気づきにくかった）。

各案には以下を含める:
- **使用する論文**（1本 or 複数本。複数本の場合は「独立した複数チームが同じ
  課題に別角度から挑んでいる」等、組み合わせる必然性を明記）
- **主人公（使い捨ての生活者）の簡単な設定**（職業・年齢・抱える課題）
- **一言ストーリーコンセプト**（課題→研究→未来の暮らし、の流れが一目で
  わかる程度）
- **なぜこの組み合わせが面白いか**（STAGE4の変革ポテンシャル・意外性等の
  観点との対応）

3案は互いに毛色を変える（例: 単一論文の深掘り案／複数論文の潮流案／
意外性重視で上位カテゴリと異なる分野を選ぶ案、など）ことで、STEP4での
人間の選択肢に幅を持たせる。

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

STEP2.5で提示した3つのストーリー案（または、それらを叩き台にした修正案）の
どれを次エピソード（複数可）にするか、ユーザーに確認する。スコアだけでなく
「動画にしやすさ」（統計的ヘッジの複雑さ、絵作りのしやすさ、使い捨ての生活者
ストーリーの組み立てやすさ等の実務観点）も踏まえて一緒に検討してよい。

**ユーザーが最終的にどのストーリー案で行くかを決定した時点でSTAGE5完了とする。**
論文単体ではなく「どのストーリーにするか」の決定がゴーサインの実体であり、
STEP5ではその決定内容（使用論文・主人公・ストーリーコンセプト）をそのまま
`topics_queue.json` に記録する。

---

## STEP 5 — topics_queue.jsonに追記する

確定した候補を `topics_queue.json` の `queue` 配列末尾に追記する。

- `episode_id`: 既存の最大値+1から連番（`kl00N`）
- `status`: `"confirmed"`
- フィールド構成は既存エントリ（`kl001`/`kl002`）にならう（`title` / `category` /
  `category_label` / `venue` / `year` / `doi`または`url` / `semantic_scholar_id` /
  `authors` / `protagonist` / `hook_idea` / `notes`）
- `pipeline_gap_flag: true` の候補を採用した場合はその旨と根拠を `notes` に明記する

採用した論文について、`topics_shortlist.json` 内の該当エントリ（`paperId` で
照合）を `status: "used"`・`used_in: "kl00N"` に更新する（不採用のまま残る
候補は `status: "available"` を維持し、削除しない）。

追記後 `total_topics` と `last_updated` を更新する。コミットメッセージには選定理由
（スコア・カテゴリバランス・「動画にしやすさ」等の判断根拠）を残す。pushは他の
作業と同様、通常のgit運用に従う。

---

## 実行タイミングの目安

`status: "confirmed"`（未着手）が少なくなってきたら実行する。SC/LWの
「残り◯件以下で補充」に相当する閾値は、今後の運用実績を見ながら決める
（2026-08時点では1周目のため未確定）。
