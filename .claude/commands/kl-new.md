# /kl-new — くらしを変える科学 新エピソード制作

論文選定（STAGE1〜5）からエピソードJSON生成・動画完成までの全工程を実行するコマンド
（2026-08-24、`/kl-topic`を統合。旧`/kl-topic`は廃止し、このコマンド1つに一本化した）。
各ステップは人間の確認を挟みながら進める（SCの`sc-new.md`と同じ設計思想: 重い創作ステップは
サブエージェントに委任し、オーケストレーター＝この会話はスクリプト実行と検証・進行管理に
専念する）。

> 論文選定（STEP1のSTAGE1〜5）は2026-08時点では軽量版。STAGE5の判断基準（「動画にしやすさ」
> 等の実務観点での選び直し）はまだパターン化できていないため、都度の会話に委ねる。何周か
> 運用して判断パターンが固まってきたら、このコマンドに反映していく。

---

## 定数（スクリプト一覧）

**論文選定（STEP1）:**

| 工程 | スクリプト |
|---|---|
| STAGE1収集・STAGE2信頼性チェック | `kl_paper_search.py` → `kl_paper_screen.py` |
| 許可リスト更新・提案 | `kl_venue_allowlist_update.py` |
| STAGE3誇張チェック | `kl_paper_hypecheck.py` |
| STAGE4面白さ判定 | `kl_paper_interest_score.py` |

中間出力（実行のたびに再生成される作業ファイル。`.gitignore`済み）:
`stage1_pool.json` / `stage2_screened.json` / `stage3_hypecheck.json` / `stage4_ranked.json`。
許可リスト: `reputable_venues.json`（gitで追跡）。確定キュー: `topics_queue.json`（gitで追跡）。
最終選考候補リスト: `topics_shortlist.json`（gitで追跡）。

**エピソード制作（STEP2以降）:**

| 工程 | スクリプト |
|---|---|
| 台本ファクトチェック | `kl_fact_check.py` |
| 制作確認書生成 | `kl_confirmation_doc.py` |
| 静止画生成（QA込み） | `kl_image_gen.py` |
| zoom_anchor判定 | `kl_zoom_anchor.py` |
| ナレーション音声生成 | `kl_tts_gen.py` |
| テロップ生成 | `kl_telop_gen.py` |
| BGM音声QA | `kl_bgm_qa.py` |
| BGM最終検証 | `kl_bgm_final_check.py` |
| BGMライブラリ登録 | `kl_bgm_library.py` |
| BGMクレジット注入 | `kl_inject_bgm_credit.py` |
| Google Drive格納 | `kl_finalize.py` |
| 動画生成 | `kl_video_gen.py` |
| Freesoundダウンロード（LW共有） | `$HOME/lamp-whisper/freesound_download.py` |

---

## STEP 1 — トピックを確定する

`topics_queue.json` の `queue` 配列に、先頭に `status: "confirmed"` のエントリがあるか確認する。

### ケースA — 既に確定済みトピックがある場合

そのエントリを次のエピソードとし、`episode_id`・`title`・`references`（複数可）・
`protagonist`・`notes`（ストーリーコンセプト）をユーザーに要約提示し、この内容で進めて
よいか確認する。OKが得られたらSTEP2へ進む。

### ケースB — 確定済みトピックがない場合（論文選定から開始）

以下のSTAGE0〜5を順に実行し、`topics_queue.json` に新規`confirmed`エントリを追記して
からケースAの手順（要約提示・確認）に進む。

#### STAGE 0 — 在庫（topics_shortlist.json）をカテゴリごとに確認する

**在庫管理・STAGE1以降の実行は6カテゴリ（`query_vocabulary.json`のキー:
`aging_care`/`home_robot`/`medical_support`/`mobility`/`work`/
`disaster_safety`）ごとに行う。** カテゴリを跨いだ全体件数だけを見ると、
特定カテゴリの在庫が尽きているのに他カテゴリの在庫に隠れて気づかない
ことがあるため（STAGE4の`--top`はデフォルトで全体横断の上位N件を返す
仕様であり、これが実際にkl001選定時にカテゴリの偏りとして表面化した
問題の根本原因でもある）。

STAGE1〜4のフル実行はSemantic Scholar検索・Gemini呼び出し（STAGE2〜4）を
伴うコストのかかる処理であり、かつ**検索条件を変えずに再実行しても、
上位には概ね同じ論文が並ぶ**（母集団が短期間でそう変わらないため）。

各カテゴリについて、`topics_shortlist.json` の `category` が一致し
`status: "available"` のエントリ件数を数える。

- **3件以上残っているカテゴリ:** そのカテゴリはSTAGE1〜4のフル実行を
  スキップし、既存の `available` エントリをそのままSTAGE2の候補として使う。
- **3件未満のカテゴリ:** 在庫が尽きかけているため、STAGE1をそのカテゴリに
  限定して実行する（`--category {name}`）。重複排除は `topics_queue.json`
  （採用済み）と `topics_shortlist.json`（採用・未採用問わず既出、全カテゴリ横断）
  の両方を見るため、既に見た論文が再スクリーニングされることはない。

この閾値（カテゴリごとに3件）はSC/LWの「残り◯件以下で補充」に相当する
目安で、運用実績を見ながら調整してよい。

#### STAGE 1 — STAGE1・STAGE2を実行し、許可リストを更新する

STAGE0で在庫3件未満と判定された**カテゴリごとに**、`--category {name}` を
付けて実行する（全カテゴリ在庫十分ならこのSTAGEは全体をスキップしてよい）。

```bash
python3 kl_paper_search.py --category {name}
python3 kl_paper_screen.py --category {name}
python3 kl_venue_allowlist_update.py
```

`kl_venue_allowlist_update.py` は提案のみ行う（`reputable_venues.json` は自動で
書き換えない）。提案された掲載誌をユーザーに見せ、追加してよいか確認してから
`--apply` で反映する（低品質誌を誤って許可リストに載せるリスクがあるため、
必ず人間確認を挟む。CLAUDE.md STAGE2の許可リスト方針参照）。

続けてSTAGE3・STAGE4を実行する（STAGE4は`--top`を「そのカテゴリで欲しい
候補数」程度に絞る。デフォルトの全体横断20件のままだと他カテゴリの
候補で埋まってしまうため）:

```bash
python3 kl_paper_hypecheck.py --category {name}
python3 kl_paper_interest_score.py --category {name} --top 8
```

対象カテゴリごとに簡潔な件数サマリのみ報告する（詳細な生データは画面に出さない）:

```
[{カテゴリ名}]
STAGE1: 収集{N}件 → プレフィルタ通過{N}件（うちプレプリント{N}件）
STAGE2: pass={N}（うち許可リスト自動pass{N}） flag={N} exclude={N}
STAGE3: ok={N} caution={N} high_risk={N}
STAGE4: 上位{N}件をランキング
```

在庫が十分だったカテゴリも含め、STAGE2に進む前に `topics_shortlist.json` へ
新規候補を追記する（STAGE2の下で詳細を後述）。

#### STAGE 2 — 上位候補をカテゴリごとに提示する

`topics_shortlist.json` の `status: "available"` エントリを `category` ごとに
グループ化し、**6カテゴリそれぞれ**についてタイトル・総合スコア・スコア内訳・
フック案・掲載誌を提示する（全体を混ぜた単一の順位リストにはしない。
カテゴリを跨いだ横断ランキングは、STAGE4のスコアリング自体が主観的な
創作寄りの判断であることもあり、特定カテゴリの偏りを見えにくくするため）。

上位5〜20件程度を目安に提示する。STAGE4のスコアリング自体は主観的な創作寄りの
判断で、Geminiに単発プロンプトで大量処理させるより人間・Claudeの文脈判断の方が
精度が高い可能性がある。全件を人間が見るのは非現実的なため、一次選抜（大量処理・
低コスト）はGeminiに任せつつ、Claudeが確認する範囲を広げることでスコアだけを
鵜呑みにしない設計にした。

STAGE0で新たにSTAGE1〜4を実行したカテゴリについては、提示と同時にその
候補を `topics_shortlist.json` に追記する（`paperId` が既存エントリと
重複するものは追記しない）。すべて `status: "available"` として記録し、
STAGE5で実際に採用されたものだけ後から `"used"` に更新する。

#### STAGE 2.5 — カテゴリごとにストーリー案を1つ提案する

**カテゴリごとに**、そのカテゴリの候補を踏まえてClaudeが実際にどの論文
（複数可）を使ってどんなストーリーを組み立てるか、1案ずつ提案する
（6カテゴリ×1案=最大6案。単にスコア順に論文を並べるだけでなく、「動画として
面白くなるか」を先に一段階シミュレートすることで、STAGE4の人間判断を
やりやすくする）。

同一カテゴリ内で複数論文を組み合わせるかどうかもここで判断する（kl001は
当初単一論文案だったが、home_robotカテゴリの候補にVLA基盤モデル論文が
複数集中していたことを踏まえ、複数論文を組み合わせた「潮流」ストーリーに
転換した実績があり、この転換はスコア表だけを見ていては気づきにくかった）。

各案には以下を含める:
- **カテゴリ**
- **使用する論文**（1本 or 複数本。複数本の場合は「独立した複数チームが同じ
  課題に別角度から挑んでいる」等、組み合わせる必然性を明記）
- **主人公（使い捨ての生活者）の簡単な設定**（職業・年齢・抱える課題）
- **一言ストーリーコンセプト**（課題→研究→未来の暮らし、の流れが一目で
  わかる程度）
- **なぜこの組み合わせが面白いか**（STAGE4の変革ポテンシャル・意外性等の
  観点との対応）

カテゴリ横断で6案並べて提示することで、STAGE4でユーザーが「どのストーリーが
良いか」だけでなく「直近のカテゴリローテーションとして何を選ぶべきか」も
一緒に判断できるようにする（CLAUDE.md STAGE1のカテゴリ重み・ローテーション
方針と対応。直近エピソードと同じカテゴリが続く場合はその旨を明示する）。
候補が薄いカテゴリ（在庫・スコアともに弱い）は無理に案を出さず、その旨を
報告するだけでよい。

#### STAGE 3 — 既知のパイプラインギャップを踏まえて補足する

CLAUDE.md STAGE2に記載の通り、Semantic Scholarがプレプリント版と正式出版版を
別レコードとして統合していない場合、優れた論文がSTAGE1の自動探索から漏れることが
ある（kl002 "Generative AI at Work" の実例）。

ユーザーが「他にこういうテーマはないか」と聞いてきた場合や、上位候補の質に
納得できない場合は、WebSearchで補助的に探してよい。査読済み掲載であることを
出版元の公式ページURLで人間が直接確認できれば、`pipeline_gap_flag: true` を付けて
候補に加えられる。

#### STAGE 4 — 人間の最終ゴーサイン

STAGE2.5でカテゴリごとに提示したストーリー案（または、それらを叩き台にした
修正案）のどれを次エピソード（複数可）にするか、ユーザーに確認する。スコアだけでなく
「動画にしやすさ」（統計的ヘッジの複雑さ、絵作りのしやすさ、使い捨ての生活者
ストーリーの組み立てやすさ等の実務観点）も踏まえて一緒に検討してよい。

**ユーザーが最終的にどのストーリー案で行くかを決定した時点でSTAGE4完了とする。**
論文単体ではなく「どのストーリーにするか」の決定がゴーサインの実体であり、
STAGE5ではその決定内容（使用論文・主人公・ストーリーコンセプト）をそのまま
`topics_queue.json` に記録する。

#### STAGE 5 — topics_queue.jsonに追記する

確定した候補を `topics_queue.json` の `queue` 配列末尾に追記する。

- `episode_id`: 既存の最大値+1から連番（`kl00N`）
- `status`: `"confirmed"`
- フィールド構成は既存エントリ（`kl001`/`kl002`）にならう（`title` / `format` /
  `category` / `category_label` / `references[]`（`title`/`authors`/`year`/`venue`/
  `url`または`doi`/`is_preprint`） / `protagonist` / `hook_idea` / `notes`）
- `pipeline_gap_flag: true` の候補を採用した場合はその旨と根拠を `notes` に明記する

採用した論文について、`topics_shortlist.json` 内の該当エントリ（`paperId` で
照合）を `status: "used"`・`used_in: "kl00N"` に更新する。不採用のまま残る
候補は `status: "available"` を維持し、削除しない。

追記後 `total_topics` と `last_updated` を更新する。コミットメッセージには選定理由
（スコア・カテゴリバランス・「動画にしやすさ」等の判断根拠）を残す。pushは他の
作業と同様、通常のgit運用に従う。

追記後、ケースAの手順（要約提示・確認）に進み、OKが得られたらSTEP2へ進む。

---

## STEP 2 — エピソードJSONを生成する（サブエージェントに委任）

このSTEPの生成（`episodes/kl{NNN}.json` 全体の作成）は `Agent` ツールで
**model指定なし（Sonnet相当）**のサブエージェントに委任する
（`run_in_background: false`、結果を待ってからSTEP3へ進む）。

サブエージェントは会話履歴を持たないため、Agentプロンプトには以下を
すべて明示的に含めること:

- STEP1で確定した `references` / `protagonist` / `notes`（ストーリーコンセプト）
- 下記「生成ルール」節の全文
- 出力先パス `$HOME/kagaku-life/episodes/kl{NNN}.json` に直接JSONファイルを
  書き込むよう指示する（オーケストレーター側では保存しない。画面にJSON全体を
  出力させない）

完了後、オーケストレーターは保存されたJSONのシーン数・スキーマ妥当性のみを
検証してSTEP3へ進む（内容の細部レビューはSTEP5の制作確認書で行う）。

### 生成ルール

**動画尺・シーン数:** 目標7〜9分、10〜15シーンの可変レンジ（複数論文回は
15シーン程度まで許容）。クリップ尺は実際のナレーション音声長から決まるため、
`duration_seconds` はフォールバック専用（目安値でよい）。

**シーンタイプとBGM役割:**

| type | 内容 | BGM役割 | 画風 | ナレーター |
|---|---|---|---|---|
| `teaser` | 冒頭の離脱回避ティザー（`impact`の一部を数秒先出し） | intro | 物語調 | persona |
| `hook` | 主人公の自己紹介（3〜5秒） | intro | 物語調 | persona |
| `citation` | 出典明示（大学名・発表年等、人名は含めない） | intro | 物語調 | research |
| `context` | 主人公が抱える課題の説明 | main | 物語調 | persona |
| `finding` | 研究の紹介（内容・手法・結果） | main | 物語調 | research |
| `data` | グラフ・比較図 | main | チャート調 | research |
| `impact` | 実現した未来の暮らし（主人公視点） | outro | 物語調 | persona |
| `closing` | 締め | outro | 物語調 | research |

境界計算: 境界1(intro→main)=最初の`context`/`finding`開始、
境界2(main→outro)=最初の`impact`開始。

**`teaser`（4シーン・各2秒前後）:** `impact`シーンの内容を先出しする複数カットの
高速フラッシュ構成（1カットのみにしない）。各カットのナレーションは10〜15字程度の
短いフレーズ。最後のカットだけ問いかけで締める、やや長め（3〜4秒）でもよい。
ナレーターはpersona。

**2ナレーターボイス制・語り口:**
- persona（生活者パート: `teaser`/`hook`/`context`/`impact`）は**一人称の独白調**
  （三人称の説明調にしない）。主語の「私」は必要な箇所以外省略。
- research（`citation`/`finding`/`data`/`closing`）は客観的な説明調。
- `impact`は「もし実現したら」を1シーン目（最初のimpactシーン）で示せば十分。
  以降のシーンでヘッジ表現（〜かもしれません、想像しています等）を連呼せず、
  没入感のある感情表現を優先する。
- `closing`は必ずresearchボイスで締める（citationと対になる客観的な語り）。
- **全エピソード共通のオチ:** 科学の本当の価値は主人公の暮らしにもたらす
  小さな幸せである、という着地で終える。技術のすごさ自体を感情的な締めに
  しない。`impact`は朝・夕方・休日等の複数の具体的瞬間に分けて描く。

**研究紹介の書き方:**
- 実際の所属機関名（大学・企業名）は明記する。研究者個人の人名（特に外国人名）
  はナレーションに含めない（日本語TTSでの発音が不自然になりやすいため）。
  人名は `references[].lead_researcher` に記録するのみ。
- 成功率等の具体的な数値をできるだけ盛り込む（研究の説得力になる）。
- 「査読」「プレプリント」の語はナレーションで使わない（概要欄で開示）。
  代わりに「まだ研究段階のプロトタイプ」等の一般的な表現でヘッジする。

**画像プロンプト（`image_prompt`）:**
- **シーン内容のみを書く。スタイルキーワード（palette/lighting/no anime等）は
  書かない**（`kl_image_gen.py`がシーンtypeに応じてBASE_CONTEXT/CHART_CONTEXTを
  自動付与するため、二重指定・スタイル相反を避ける）。
- 登場人物の性別・年齢を明記する（特に子供。性別未指定だと誤った性別で
  生成されるバグが実際に起きた）。
- 時間帯は視覚的に明示する（例: "soft morning daylight, not night"、
  "evening, dusk sky visible through window"）。時間帯を言葉だけで示すと
  夜空を誤生成することがある。
- `finding`シーンは研究室での実験風景にする（家庭内シーンにしない）。
  研究者は**分野を問わず白衣を着せる**（経済学・社会科学系の研究でも、視認性・
  「この人は研究者」という一目での伝わりやすさを優先する。kl002で経済学研究
  という理由で白衣を外した結果ユーザーから指摘があり、分野に関わらず白衣を
  着せる方針に統一した、2026-08-23）。論文の実施国に応じた人種で描写する
  （世界各地で独立した研究が進んでいることを視覚的に示す）。データはコーナーの
  小さなフラットグラフィック（全体の1/8以下、no text/numerals）でさりげなく
  示してよい。
- `data`タイプは物語シーンと別トーン（`kl_image_gen.py`が自動適用）。
  内容は棒グラフとは限らない（壁+矢印+トレンド線等、内容に応じて自由に
  構図を指定してよい）。
- 未来パートの統合ロボットは全シーンで同一デザインを保つこと（説明文を
  使い回す）。ヒューマノイド的な人体プロポーション（頭・首・胴・腕・脚が
  人間らしい比率）を明記し、トイっぽい/マスコット的な見た目にならないよう
  指定する。フレンドリーだが機械的な顔（人間の顔に見えない）にする。
- 抽象的なアイコン（意味の伝わらない手のアイコン等）は避け、人物の様子・
  構図で伝える。
- 文字は一切入れない（"no text"を必ず含める）。
- 職業・学歴等の属性による比較を扱う回では、当該属性を必要以上に貶める
  表現にならないよう注意する（例: 「〜卒だから」という表現を、客観的な事実
  としてではなく本人の劣等感・コンプレックスとして描く。kl002で実際に
  指摘・修正した、2026-08-23。STEP2.5の配慮チェックとも対応）。

**`references`/`reference_index`:** `finding`/`dataシーンには`reference_index`
（`references`配列のインデックス、0始まり）を付与する。単一論文回は0固定。

**thumbnail_prompt:** 16:9、統合ロボットの説明を含める（本編と同一デザイン）。
`thumbnail_headline`/`thumbnail_subcopy`も忘れずに設定する（未設定だとテキスト
合成がスキップされ、文字なしサムネイルになる事故が実際に起きた。STEP6参照）。

**shorts（1本、5〜6シーン）:** 各カット2〜3秒の短いフレーズに区切る。
「フック→本編ダイジェスト→CTA」の短い展開。`image_prompt`はShorts専用に
縦構図を意識して新規に書く。チャート系のカットには `"style": "chart"` を
付与する。narrator/narration_voicesは本編と共通。

**JSONスキーマ:** `episode_id` / `episode_title` / `youtube_title` /
`youtube_description`（参考文献・査読前開示を含む） / `youtube_tags` /
`references[]` / `protagonist` / `thumbnail_prompt` / `thumbnail_headline` /
`thumbnail_subcopy` / `scenes[]`（`scene_id`/`type`/`narrator`/`reference_index`/
`duration_seconds`/`narration`/`image_prompt`/`ken_burns`） / `shorts[]`。
`narration_voices`はSTEP3で決まるため、この時点では省略してよい。

**想定尺の見積もり（2026-08-23追加）:** シーンJSON生成直後、`scenes`（teaser除く
本編シーンのみ）の`narration`文字数合計を250〜300字/分（`kl_confirmation_doc.py`
の`estimate_seconds`と同じ目安）で秒数換算し、7〜9分の目標に対して大きく
不足していないか確認する。目安として400秒（7分弱）を下回りそうな場合は、
STEP6（画像生成、最初の実コスト工程）に進む前にユーザーへ尺を伸ばすか確認する
（シーン追加 or ナレーション加筆）。生成後に動画を作ってから尺不足が発覚すると、
シーン挿入に伴うシーン番号のずれ・ファイル名リネーム・zoom_anchor/telop再生成
など手戻りが大きい（kl002で実際に発生した）。

---

## STEP 2.5 — 台本の品質・配慮チェック（Opusサブエージェントに委任）

STEP2で生成した `episodes/kl{NNN}.json` を、`Agent` ツールで `model: "opus"` の
サブエージェントにレビューさせる（`run_in_background: false`、結果を待ってから
STEP3へ進む）。

**なぜここだけOpusを使うか:** STAGE2/3や`kl_fact_check.py`が「Opusを使わない」
方針なのは、それらが検索グラウンディングで裏取りできる照合タスク（論文の数値と
一致しているか等）だからである。一方このSTEPは、文章のトーン・含意が特定の
読者層（学歴・職業等）を不必要に貶めていないか、生活実感に寄り添っているかを
読み取る、より繊細な判断力を要するタスクであり、**台本を生成したモデル自身
では気づけないことがkl001・kl002で複数回確認されている**（Sonnet生成→人間との
複数往復のやり取りでようやく修正できたケースが実際にあった）。SCのSTEP3A
（史実知識チェック、Opus使用）と同じ理由でここだけ強いモデルを使う。

Agentプロンプトには `episodes/kl{NNN}.json` のパスと、以下のチェック観点を
含める:

**チェック観点:**
1. **特定の属性への配慮**（学歴・職業・年齢・家族構成等）: 比較対象となる属性を
   不必要に見下す・卑下する表現になっていないか（例: 「専門学校卒」を必要以上に
   劣ったものとして描いていないか。実際に事実の記述ではなく本人のコンプレックス
   として描くよう修正した実例がkl002である）。研究内容の紹介として正確な範囲を
   超えて、特定の読者層を傷つける書き方になっていないか。
2. **生活実感との整合性**: 主人公の設定・状況描写に論理矛盾がないか（例:
   kl001で実際に発覚した「まだ存在しない製品への不安」のような、ストーリー
   自体の一貫性を壊す記述）。「もし実現したら」を待つ未来ではなく「今すぐ
   始められる一歩」として描くべき技術（既に実用化されている生成AI等）を、
   不必要に遠い未来のことのように書いていないか（kl002で実際に指摘された
   論点）。
3. **一人称/客観の語り口の一貫性**: persona/researchボイスの語り口ルール
   （本ファイル「生成ルール」節・CLAUDE.md参照）を守れているか。
4. **その他の台本品質**: 不自然な日本語、唐突な感情の飛躍、冗長な繰り返し等。

**問題が見つかった場合は、ユーザー確認なしに即座に `episodes/kl{NNN}.json` の
該当シーンを直接修正させる**（SCのSTEP3Aと同じ運用）。オーケストレーターは
完了報告を受け取り、修正内容の要約のみユーザーに提示する（画面にJSON全体は
出力させない）。

---

## STEP 3 — ナレーターボイス選定

`protagonist.gender` を確認する。

- **persona（生活者ボイス）: 必ず新規選定する。2段階の推薦プロセスで絞り込む
  （2026-08-24確定）:**
  1. **Claudeによる一次絞り込み（ラベル判定）:** 女性候補5種（Kore/Leda/
     Autonoe/Despina/Sulafat）または男性候補5種（Charon/Orus/Iapetus/
     Rasalgethi/Achird）のうち、各ボイスに割り当てられている公式の性格ラベル
     （例: Charon=Informative、Orus=Firm、Iapetus=Clear、Rasalgethi=
     Informative、Achird=Friendly、Kore=Firm、Leda=Youthful、Autonoe=
     Bright、Despina=Smooth、Sulafat=Warm等）と、今回の主人公の年齢・性格・
     状況を照らし合わせて3件程度に絞り込む。
  2. **Geminiによる実音声ベースの推薦:** 絞り込んだ3候補を`kl_voice_recommend.py`
     で実際に生成し、その音声を`gemini-3.6-flash`に聴かせて、主人公の設定
     （`episodes/kl{NNN}.json`の`protagonist`/`notes`）に最も合う声を推薦させる
     （`kl_bgm_final_check.py`と同じ「実音声+設定文をGeminiに渡す」方式）:
     ```bash
     python3 kl_voice_recommend.py --episode kl{NNN} --role persona \
       --voices {候補1},{候補2},{候補3} \
       --text "{hookシーン等の主人公の実ナレーション文}"
     ```
     音声は`~/Desktop/kagaku-life/voice_test/`に保存される（スクラッチパッド
     ではなくFinderで確認できる場所に置く）。
  3. Geminiの推薦とその理由をユーザーに提示し、**最終判断は必ずユーザーが
     実際に聴いて決める**（Claudeのラベル判定・Geminiの推薦はどちらも一次
     選定の参考情報であり、人間の最終確認を省略しない）。
- **research（研究ボイス）: 性別ごとに固定。** 男性=`Orus`（確定済み、
  そのまま使う）。女性=`Autonoe`（確定済み、そのまま使う）。両方確定済みの
  ため、新規選定が必要になるのは今後3人目以降の性別区分が生まれた場合のみ。

決定したボイス名を `episodes/kl{NNN}.json` の `narration_voices` に書き込む。

---

## STEP 4 — 台本ファクトチェック

```bash
python3 kl_fact_check.py --episode kl{NNN}
```

`ok`以外の判定が出た場合、該当シーンのナレーションを修正して再実行する。
数値・固有名詞が絡む場合、必要に応じてWebSearch/WebFetchで論文原文（NBER working
paper等）を直接確認し、ナレーションを具体的かつ正確な内容に書き直す（kl002 S9で
実施した実例: タスク内容を「ビジネス課題」という曖昧な表現から、論文本文にある
「上司からのメールに返信する形で問題を診断・提案する」という具体的な内容に修正）。

---

## STEP 5 — 制作確認書生成・内容確認

```bash
python3 kl_confirmation_doc.py --episode kl{NNN}
```

生成された `~/Desktop/kagaku-life/kl{NNN}_制作確認書.txt` の内容（ナレーション・
画像プロンプト・出典・チェックリスト）をユーザーに確認してもらう。修正依頼が
あればSTEP2の内容に戻って直接編集し、STEP4・STEP5を再実行する。

**この確認を経てから初めてSTEP6以降（実際の生成コスト）に進む。**

---

## STEP 6 — 静止画生成

```bash
python3 kl_image_gen.py --episode kl{NNN}
```

自動画像QA込みで全シーン+サムネイル+Shortsを生成する。QAで解決しなかった
シーンや、目視で気になる点があれば個別に `--scenes` で再生成する。

`thumbnail_headline`/`thumbnail_subcopy`が未設定だとサムネイルへのテキスト
合成がスキップされる（STEP2の生成ルール参照）。生成後のサムネイルに文字が
入っていない場合は、この2フィールドをkl{NNN}.jsonに追記し、
`composite_thumbnail_text()`（`kl_image_gen.py`内の関数）を直接呼び出して
既存の生成済みサムネイル画像にテキストのみ合成し直す（画像自体の再生成は不要）。

---

## STEP 7 — zoom_anchor判定

```bash
python3 kl_zoom_anchor.py --episode kl{NNN}
```

---

## STEP 8 — ナレーション音声生成

```bash
python3 kl_tts_gen.py --episode kl{NNN}
```

---

## STEP 9 — テロップ生成

```bash
python3 kl_telop_gen.py --episode kl{NNN} plan
```

生成後、目視またはスクリプトで以下を確認する（kl002で実際に発生した不具合の
再発防止）:
- テロップが単語・複合語の途中で切れていないか
- 各カードの表示時間が短すぎないか（一瞬で消えるカードがないか）
- シーン境界（クロスフェード区間）で前後のテロップが重なって表示されていないか

上記は`kl_telop_gen.py`側で構造的に対処済み（janome形態素解析による分割位置の
適正化、前方+後方2パスによる表示時間・音声長超過の防止）だが、新しいエピソードの
内容（専門用語・数字の多さ等）によっては別種の問題が起こり得るため、本編動画
生成後（STEP12）に複数箇所をフレーム抽出して確認する。

---

## STEP 10 — BGM選定

CLAUDE.md「BGMパイプライン」の手順に従う（トーンは必ず温かく・希望が持てる・
押し付けがましくない。禁止語: epic/battle/war/dark/aggressive/horror）。

**SC/LWと同じく、候補は「Freesound新規ダウンロード」だけでなく「`bgm_library.json`
の既存曲」も含めて役割ごとに揃える。** 過去エピソードで確認済みの曲は品質・
トーンの信頼度が高く、新規ダウンロードだけに頼ると同じ探索を毎回繰り返すことになる。

1. `bgm_library.json` を読み、役割のトーン（intro=好奇心・静かな導入、
   main=研究紹介への高まり、outro=温かい余韻）に近い`tags`を持つ既存曲を
   役割ごとに1〜2曲ピックアップする（同一エピソードでの重複使用は避ける）。
2. Freesoundから役割別（intro/main/outro）に新規候補を1曲ずつダウンロード:
   ```bash
   mkdir -p "$HOME/Desktop/kagaku-life/BGM"
   FREESOUND_API_KEY=$FREESOUND_API_KEY python3 "$HOME/lamp-whisper/freesound_download.py" \
     "<Q_intro>" "<Q_main>" "<Q_outro>" \
     "$HOME/Desktop/kagaku-life/BGM/" \
     --round 0 --start-slot 1 \
     --library "$HOME/kagaku-life/bgm_library.json"
   ```
3. 新規ダウンロード分のみ `kl_bgm_qa.py --dir` でボーカル混入チェック
   （ライブラリ曲は過去のQA実績があるため再チェック不要）
4. 役割ごとに複数候補（ライブラリ+新規）がある場合、Claudeがテキスト情報
   （曲名・タグ・QAの音の説明）だけで1曲に絞り込む
5. `kl_bgm_final_check.py --episode kl{NNN}` で実音声+制作確認書をGeminiに渡し、
   最終検証（テキストだけでは質感を見誤ることがあるため省略しない）
6. 条件付き採用・差し替えが出た場合は該当役割だけ差し替えて再検証する
7. 承認が得られたら本登録する:
   - 新規曲の場合: `kl_bgm_library.py --add --episode kl{NNN} --role {role} --file {path} --stem {name}`
     （Google Driveへ移動・`bgm_sources`に記録・ライブラリに新規追加）
   - 既存ライブラリ曲を採用した場合: `kl_bgm_library.py --use-library --episode kl{NNN} --role {role} --stem {library_id}`
     （ダウンロード・移動不要、`bgm_sources`に既存パスを記録・`used_in`を更新）
8. CC BYライセンス曲があれば `kl_inject_bgm_credit.py --episode kl{NNN} --credit-file {path}`
   でクレジットを概要欄に注入

---

## STEP 11 — 静止画・ナレーションのユーザー確認 → Google Driveへ格納

**Drive反映前に必ずユーザーの確認を得る。** STEP6〜9で生成した本編静止画・
Shorts静止画・ナレーション音声を`SendUserFile`で送り、OKが出るまではDesktop
ローカルのみに留める（Driveへは同期しない）。修正が入った場合は該当工程を
やり直し、再度確認を得る（kl002で実際にこの順番を求められた運用）。

OKが得られたら:

```bash
python3 kl_finalize.py --episode kl{NNN}
```

画像・ナレーション・Shortsを確認済みとしてGoogle Driveへコピーする。

---

## STEP 12 — 動画生成

**動画生成前に、想定尺（STEP2で見積もった値、または実際のナレーション音声長
合計）が7分を大きく下回りそうな場合は、尺を伸ばすかどうかユーザーに確認する**
（STEP2の「想定尺の見積もり」参照）。

```bash
python3 kl_video_gen.py --episode kl{NNN}
```

引数なしで本編（`kl{NNN}.mp4`）とShorts（`kl{NNN}_shorts.mp4`）の両方が
生成される（Shortsのみ再生成したい場合は `--shorts-only`、本編のみは
`--no-shorts`）。

完成後、複数箇所（本編: ティザー・ロゴイントロ・本編冒頭・本編中盤・
ロゴアウトロ、Shorts: 冒頭・中盤・末尾）をフレーム抽出して目視確認し、
STEP9に記載のテロップ不具合（単語途中分割・一瞬で消えるカード・シーン境界の
重複）がないかも合わせて確認する。`SendUserFile` でユーザーに送る。
フィードバックがあれば該当工程（画像/音声/テロップ/動画生成）に戻って修正し、
**修正後は必ず `kl_finalize.py` でGoogle Driveへ同期してから
`kl_video_gen.py` を再実行する**（`kl_video_gen.py`はGoogle Drive側の素材を
読むため、Desktop側の修正だけでは反映されない。kl001制作時に実際にこれが
原因で修正が反映されない事故が起きている）。

**テロップの描画設定（フォント・縁取り太さ・色等）は `kl_telop_gen.py` と
`kl_video_gen.py` の両方に別々の実装があり、片方だけ直すと反映漏れが起きる
（kl001制作時に実際に発生）。テロップの見た目を変更する際は両ファイルを
同時に修正すること。**

---

## STEP 13 — topics_queue.json / topics_shortlist.json を更新する

- `topics_queue.json` の該当エントリの `status` を `"confirmed"` から
  `"produced"`（画像・音声・動画すべて完成、公開待ち）に更新する
  （YouTube公開時は`/kl-upload`が`"published"`へさらに更新する）
- `topics_shortlist.json` の採用論文エントリを `status: "used"`・
  `used_in: "kl{NNN}"` に更新する（STEP1 STAGE5と同じ運用。まだ未更新の
  場合のみ）

更新をコミット・push する。

---

## 完了後: YouTubeアップロード

制作が完了（`status: "produced"`）したら `/kl-upload` でYouTubeへアップロードする
（詳細は `.claude/commands/kl-upload.md` 参照）。
