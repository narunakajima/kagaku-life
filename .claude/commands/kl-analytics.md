# /kl-analytics — くらしを変える科学 YouTubeアナリティクス分析

蓄積されたYouTube Analyticsデータから相対的な強弱パターンを把握し、
制作ルール（`query_vocabulary.json`のカテゴリweight・`.claude/commands/kl-new.md`の
選定基準等）に反映するコマンド。samurai-chroniclesの`/sc-analytics`と同じ構成を
踏襲しているが、KLはSCよりチャンネル規模・データ量が小さく、`combined_a3`レポートの
`subscribed_status`列が常に`unknown`で使い物にならない等の違いがあるため、
そのまま移植せず、以下の各所で意図的に差分を入れている（理由は該当箇所に記載）。

月1回程度の低頻度想定（毎エピソードではない）。CLAUDE.mdの
「カテゴリ重み（weight）とアナリティクス連動」に定めるとおり、**公開エピソードが
最低12話に達するまではweightを全カテゴリ均等のまま固定する**運用のため、
12話未満のうちにこのコマンドを実行してもweight見直しの判断材料にはしない
（トレンド把握・異常検知の目的でなら実行しても構わない）。

---

## STEP 1 — データ最新化

```bash
/usr/bin/python3 kl_yt_download_reports.py
```

**このプロジェクトのgoogle-authライブラリは`/usr/bin/python3`（Python 3.9系、
`~/Library/Python/3.9/site-packages`）にのみインストールされている。** デフォルトの
`python3`（Homebrew、`/opt/homebrew/bin/python3`）では`ModuleNotFoundError: No module
named 'google'`になる。`kl_sns_up.py`・`kl_yt_download_reports.py`・
`kl_analytics_report.py`（Google API呼び出しはしないが一貫性のため）はいずれも
`/usr/bin/python3`で実行すること。

**注意:** `analytics/raw/`は`.gitignore`対象のため、他端末（MacBook/iMac）からの
`git pull`後はローカルのCSVが消えていることがある。分析前は必ず実行して最新化すること。

## STEP 2 — 基本集計

```bash
/usr/bin/python3 kl_analytics_report.py
```

出力される内容:
- **チャンネル全体の月次露出トレンド**（インプレッション・再生数、`--after`/`--before`の
  期間指定の影響を受けず常に全期間で表示。カテゴリ別の優劣を論じる前に、それが
  チャンネル全体の構造的な増減でないかを切り分けるため）
- 全動画（本編・Shorts）の一覧（再生数・視聴分・平均維持率・完了率・インプレッション・CTR）
- 視聴維持率トップ5・ワースト5
- **カテゴリ別ロールアップ（本編のみ、公開後14日間のage-adjusted集計）。**
  測定窓（14日）が完了していない直近公開分は自動的に除外される。該当カテゴリの
  該当話数`n`が`MIN_CATEGORY_N`（現在3）未満の場合は「n不足のため参考程度」の
  注記が付く
- トラフィックソース別視聴数（`traffic_source_type`。コードのまま表示される
  ものがある場合は
  [公式ドキュメント](https://developers.google.com/youtube/reporting/v1/reports/dimensions#traffic_source_type)
  でコードの意味を確認すること）

期間を絞る場合:
```bash
/usr/bin/python3 kl_analytics_report.py --after kl010 --before kl020
```

**SCの`/sc-analytics`との既知の差分（意図的に移植しなかった項目）:**
- **新規視聴者獲得比率（非登録者視聴%、`subscribed_status`ベース）は実装しない。**
  KLの`combined_a3`データを確認したところ、この列は全行が`unknown`で埋まっており
  分析に使えない状態だった（SCと違いこの次元がAPI側で有効になっていない可能性が
  高い。原因調査は別タスク）。無理に実装すると常に無意味な数値を出すことになるため
  見送った。
- **`--min-impressions`/`--min-views`のような足切り閾値は導入していない。** SCは
  1500imp/50viewsを既定にしているが、KLは公開話数・再生数の絶対値がSCよりずっと
  小さく（本稿執筆時点で最大インプレッションの動画でも数千件程度）、SCと同じ閾値を
  適用するとほぼ全動画が「測定不能」になり分析自体が成立しない。代わりにカテゴリ
  ロールアップの`MIN_CATEGORY_N`（該当話数）でのみ低信頼の注記を出す設計とした。
  STEP4のOpus解釈時は、個々の動画のimpressions/views実数を必ず併記して人間・Opus
  自身が判断する
- **タイトル型別・登場人物数別の集計はない。** KLのエピソードJSONにSCの
  `character_ref`・タイトル型に相当する構造化フィールドが無いため、KL固有の
  比較軸は現状カテゴリ（`category_label`）のみ

## STEP 3 — 追加分析（必要に応じて）

STEP2の出力だけで判断がつかない場合、以下を人手で深掘りする:

- **カテゴリ単位のシグナル**（同一カテゴリの複数話が揃って強い/弱いか）。
  `topics_queue.json`の`queue`配列でカテゴリごとにepisode_idを拾い、STEP2の
  per-episode表と突き合わせる
- **`analytics/raw/`の生CSVを直接読む。** `kl_analytics_report.py`の集計に
  疑問がある場合（外れ値1本に引っ張られていないか等）は生データで検算する

## STEP 4 — 解釈・提言をOpusサブエージェントに委任

**理由:** STEP1-3（集計の実行自体）はスクリプトでモデル非依存。Opusが効くのは
「その結果をどう解釈し、次のアクションにどうつなげるか」の部分のみ。本コマンドは
月1回程度の低頻度なのでOpus利用によるコスト増もほぼ無視できる。

STEP1-3で得た**集計結果**（生CSVではなく集計済みの数値・比較表）を`Agent`ツールで
`model: "opus"`のサブエージェントに渡す。サブエージェントは会話履歴を持たないため、
以下を明示的に含めること:

- STEP2-3で得た集計結果（数値・比較表）全文
- 過去の分析結果・意思決定の記録（project memoryのYouTubeアナリティクス関連メモの要約）
- 現在の`topics_queue.json`の`queue`配列のうち直近数話分の構成
  （**配列の並び順どおり**のcategory構成。同一カテゴリの連続がないか等、
  順序自体も判断材料にするため）

**KLは`topics_queue.json`に`hypotheses`セクションを持たない**（SCとの構造的な
差分）。仮説の検証・ステータス更新はこのコマンドの対象外とする。仮説レジストリを
KLにも導入するかどうかは別途検討する。

Agentプロンプト:
```
以下はくらしを変える科学（kagaku-life）のYouTubeアナリティクス集計結果です。

{集計結果}

過去の分析結果・意思決定の記録:
{project memoryの要約}

現在のトピックキュー（直近数話分の**配列並び順どおり**のcategory構成）:
{サマリ}

以下を行ってください（日本語で）：
1. 各指標について、サンプルサイズ・外れ値の影響を踏まえて統計的に妥当な解釈かを
   検証する（小さいnでの早合点、外れ値1本への依存がないか。必要ならこの集計結果
   だけでなく`analytics/raw/`の生CSVを直接読んで検算してよい）
2. 複数指標を横断した傾向を統合的に解釈する
3. 具体的なアクション提言（優先度つき）— `query_vocabulary.json`のカテゴリweight・
   `.claude/commands/kl-new.md`の選定基準・BGMトーン等、制作ルールに反映すべき変更
4. まだ判断を保留すべき（データ不足の）項目があれば明記する
5. キューの投入順序自体（同一カテゴリ・弱いトピックの連続がないか）に問題があれば
   指摘する

**以下は必ず守ること（過去にsamurai-chroniclesの監査で発覚した誤りの再発防止）:**
- 公開後14日の期間集計で、**測定窓（14日）が完了していない動画をコホート比較に
  含めない**（`kl_analytics_report.py`のage-adjusted集計は既に窓未完了を除外
  済みだが、生CSVを直接集計し直す場合は自分で同様の除外を行うこと）
- コホート間比較を行う場合、**各動画のクリック数・インプレッション数を併記**する
  （KLはSCの`--min-impressions`のような足切りをしていないため、実数が小さい
  比較を「有意」と呼ばないこと）
- コホートの境界（例:「9月公開分」）は**公開月で固定**し、都合の良い結果が出る
  ように事後的に境界を動かさない
- 複数のカテゴリ・期間を横断的に走査して「最良の結果」を報告する場合は、
  **走査した候補数と多重比較の影響**を明記する
```

`run_in_background: false`で結果を待つ。

## STEP 5 — ユーザーへ提示・承認

Opusの提言をそのままユーザーに提示し、`query_vocabulary.json`のweight・
`.claude/commands/kl-new.md`等への反映可否を確認する。ここで自動確定はしない。

## STEP 6 — 承認内容の反映

承認が得られた項目について:
- `query_vocabulary.json`の該当カテゴリの`weight`を更新
- 必要なら`.claude/commands/kl-new.md`の該当ルールを更新
- 分析結果と意思決定の経緯をproject memoryに記録（数値・根拠・Why・How to applyを含める）
