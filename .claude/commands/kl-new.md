# /kl-new — くらしを変える科学 新エピソード制作

`/kl-topic`のSTAGE5で確定したストーリー（`topics_queue.json`の
`status: "confirmed"`エントリ）をもとに、エピソードJSON生成から動画完成
までの全工程を実行するコマンド。各ステップは人間の確認を挟みながら進める
（SCの`sc-new.md`と同じ設計思想: 重い創作ステップはサブエージェントに委任し、
オーケストレーター＝この会話はスクリプト実行と検証・進行管理に専念する）。

---

## 定数（スクリプト一覧）

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

## STEP 1 — 次のトピックを確認する

`topics_queue.json` の `queue` 配列から、先頭にある `status: "confirmed"` の
エントリを次のエピソードとする（見つからなければ `/kl-topic` を先に実行するよう
案内して終了）。

`episode_id`・`title`・`references`（複数可）・`protagonist`・`notes`
（ストーリーコンセプト）をユーザーに要約提示し、この内容で進めてよいか確認する。

---

## STEP 2 — エピソードJSONを生成する（サブエージェントに委任）

このSTEPの生成（`episodes/kl{NNN}.json` 全体の作成）は `Agent` ツールで
**model指定なし（Sonnet相当）**のサブエージェントに委任する
（`run_in_background: false`、結果を待ってからSTEP3へ進む）。

サブエージェントは会話履歴を持たないため、Agentプロンプトには以下を
すべて明示的に含めること:

- STEP1で確認した `references` / `protagonist` / `notes`（ストーリーコンセプト）
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
  研究者は白衣を着せ、論文の実施国に応じた人種で描写する（世界各地で
  独立した研究が進んでいることを視覚的に示す）。データはコーナーの
  小さなフラットグラフィック（全体の1/8以下、no text/numerals）で
  さりげなく示してよい。
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

**`references`/`reference_index`:** `finding`/`dataシーンには`reference_index`
（`references`配列のインデックス、0始まり）を付与する。単一論文回は0固定。

**thumbnail_prompt:** 16:9、統合ロボットの説明を含める（本編と同一デザイン）。

**shorts（1本、5〜6シーン）:** 各カット2〜3秒の短いフレーズに区切る。
「フック→本編ダイジェスト→CTA」の短い展開。`image_prompt`はShorts専用に
縦構図を意識して新規に書く。チャート系のカットには `"style": "chart"` を
付与する。narrator/narration_voicesは本編と共通。

**JSONスキーマ:** `episode_id` / `episode_title` / `youtube_title` /
`youtube_description`（参考文献・査読前開示を含む） / `youtube_tags` /
`references[]` / `protagonist` / `thumbnail_prompt` / `scenes[]`
（`scene_id`/`type`/`narrator`/`reference_index`/`duration_seconds`/
`narration`/`image_prompt`/`ken_burns`） / `shorts[]`。
`narration_voices`はSTEP3で決まるため、この時点では省略してよい。

---

## STEP 3 — ナレーターボイス選定

`protagonist.gender` を確認する。

- **persona（生活者ボイス）: 必ず新規選定する。** 女性候補5種
  （Kore/Leda/Autonoe/Despina/Sulafat）または男性候補5種（Charon/Orus/
  Iapetus/Rasalgethi/Achird）から、性別に応じて主人公の実ナレーション文
  （`hook`シーン等）で読み上げ比較のサンプルを`gemini-3.1-flash-tts-preview`で
  生成し、ユーザーに聴き比べてもらって決定する。
- **research（研究ボイス）: 性別ごとに固定。** 男性=`Orus`（確定済み、
  そのまま使う）。女性研究ボイスがまだ未選定な場合（主人公が男性の初回）は、
  同様に候補5種を比較して決定し、以降固定として使う（CLAUDE.mdに記録する）。

決定したボイス名を `episodes/kl{NNN}.json` の `narration_voices` に書き込む。

---

## STEP 4 — 台本ファクトチェック

```bash
python3 kl_fact_check.py --episode kl{NNN}
```

`ok`以外の判定が出た場合、該当シーンのナレーションを修正して再実行する。

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

---

## STEP 10 — BGM選定

CLAUDE.md「BGMパイプライン」の手順に従う（トーンは必ず温かく・希望が持てる・
押し付けがましくない。禁止語: epic/battle/war/dark/aggressive/horror）。

1. Freesoundから役割別（intro/main/outro）に候補をダウンロード:
   ```bash
   mkdir -p "$HOME/Desktop/kagaku-life/kl{NNN}/BGM"
   FREESOUND_API_KEY=$FREESOUND_API_KEY python3 "$HOME/lamp-whisper/freesound_download.py" \
     "<Q_intro>" "<Q_main>" "<Q_outro>" \
     "$HOME/Desktop/kagaku-life/kl{NNN}/BGM/" \
     --round 0 --start-slot 1 \
     --library "$HOME/kagaku-life/bgm_library.json"
   ```
2. `kl_bgm_qa.py --dir` でボーカル混入チェック
3. 役割ごとに複数候補がある場合、Claudeがテキスト情報（曲名・タグ・QAの音の
   説明）だけで1曲に絞り込む
4. `kl_bgm_final_check.py --episode kl{NNN}` で実音声+制作確認書をGeminiに渡し、
   最終検証（テキストだけでは質感を見誤ることがあるため省略しない）
5. 条件付き採用・差し替えが出た場合は該当役割だけ差し替えて再検証する
6. 承認が得られたら `kl_bgm_library.py --add --episode kl{NNN} --role {role} --file {path} --stem {name}`
   で本登録（Google Driveへ移動・`bgm_sources`に記録）
7. CC BYライセンス曲があれば `kl_inject_bgm_credit.py --episode kl{NNN} --credit-file {path}`
   でクレジットを概要欄に注入

---

## STEP 11 — Google Driveへ格納

```bash
python3 kl_finalize.py --episode kl{NNN}
```

画像・ナレーション・Shortsを確認済みとしてGoogle Driveへコピーする。

---

## STEP 12 — 動画生成

```bash
python3 kl_video_gen.py --episode kl{NNN}
```

引数なしで本編（`kl{NNN}.mp4`）とShorts（`kl{NNN}_shorts.mp4`）の両方が
生成される（Shortsのみ再生成したい場合は `--shorts-only`、本編のみは
`--no-shorts`）。

完成後、複数箇所（本編: ティザー・ロゴイントロ・本編冒頭・本編中盤・
ロゴアウトロ、Shorts: 冒頭・中盤・末尾）をフレーム抽出して目視確認し、
`SendUserFile` でユーザーに送る。フィードバックがあれば該当工程（画像/音声/
テロップ/動画生成）に戻って修正し、**修正後は必ず `kl_finalize.py` で
Google Driveへ同期してから `kl_video_gen.py` を再実行する**（`kl_video_gen.py`
はGoogle Drive側の素材を読むため、Desktop側の修正だけでは反映されない。
kl001制作時に実際にこれが原因で修正が反映されない事故が起きている）。

**テロップの描画設定（フォント・縁取り太さ・色等）は `kl_telop_gen.py` と
`kl_video_gen.py` の両方に別々の実装があり、片方だけ直すと反映漏れが起きる
（kl001制作時に実際に発生）。テロップの見た目を変更する際は両ファイルを
同時に修正すること。**

---

## STEP 13 — topics_queue.json / topics_shortlist.json を更新する

- `topics_queue.json` の該当エントリの `status` を `"confirmed"` から
  `"in_production"` または `"published"`（アップロード状況に応じて）に更新する
- `topics_shortlist.json` の採用論文エントリを `status: "used"`・
  `used_in: "kl{NNN}"` に更新する（`/kl-topic` STEP5と同じ運用）

更新をコミット・push する。
