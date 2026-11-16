# KL 画像の Muse 代替 ― 1話試行の仕様書

作成: 2026-11-15（指示 2026-11-15-005、Muse → Claude Code）。**この文書は試行の仕様だけ。制作フロー（`kl-new.md`）・制作コードは変更しない。** 試行は kl057 の制作セッションが、この文書を読んで実施する。

## 目的

KL の残りのコストで最大の画像生成（約 ¥195/話、Gemini）を、Muse の画像生成で代替できるか、1話だけ試す。判断材料は「品質が現行に届くか」「手間と時間が見合うか」「いくら回避できるか」。

## 対象と範囲

- 対象: 次回制作の1話（kl057 想定。変わったら、その話。結果ファイルに実際の話数を書く）。
- **Muse 生成に切り替えるもの = 通常なら `kl_image_gen.py` が Gemini で生成する画像すべて**。全点を切り替える（一部だけ Gemini に残さない）。
  | 種類 | ファイル名 | サイズ（幅×高さ） | 備考 |
  |---|---|---|---|
  | 本編シーン（`image_prompt` を持つシーン。`type` が data/check の図表調も含む。図表調は指定した日本語ラベル・数値だけを描かせ、それ以外の文字・数字は足さない） | `S{NN}.png` | 1376×768（16:9） | `image_asset`・`reuse_scene_id`・カード類のシーンは対象外（下記） |
  | サムネイル背景 | `thumbnail_bg.png` | 1376×768 | **文字・立ち絵は載せない背景のみ**。見出し・立ち絵・判定ラベルは `kl_dialogue.composite_thumbnail_dialogue` が合成し直す（`kl_image_gen.py --recomposite-thumbnail`。これはコード実行のみで Gemini 不使用）。`thumbnail_b`（B案）があれば、**`thumbnail_bg.png` を `thumbnail_b.png` に複製し、`composite_thumbnail_keyword` で文字を載せる**（A案の文字を載せる前の背景から作る。`--recomposite-thumbnail` はB案を作らない。合成後の `thumbnail.png` から作ると A案の文字が重なる）。A案は `python3 kl_image_gen.py --episode kl{NNN} --recomposite-thumbnail`（`thumbnail_bg.png` から `thumbnail.png` を作る。画像は生成しないが、先に API キーの有無を確かめるので、キーの無い環境では止まる）。B案の例: `python3 -c "import shutil, pathlib, kl_image_gen as g; d = pathlib.Path.home() / 'Desktop/kagaku-life/images'; shutil.copyfile(d / 'thumbnail_bg.png', d / 'thumbnail_b.png'); g.composite_thumbnail_keyword(d / 'thumbnail_b.png', '<keyword>', '<line>')"`（`<keyword>`・`<line>` はエピソード JSON の `thumbnail_b`） |
  | Shorts の画像（`shorts{N}_S{NN}.png`、顔アップ `shorts{N}_S00_face.png`） | 同左 | 768×1376（9:16） | kl057 以降、Shorts は本編画像の縦切り出し（AI 生成なし）が既定。**切り出せないカットだけ**を Muse 対象にする（下の「Shorts の扱い」）。顔アップは `face_hook_image_prompt` があるときのみ |
- **切り替えの対象外（通常どおり）**:
  - 実物写真（`real_photo`、`assets/photos/`）と、そこから作る Shorts の縦画像。
  - 固定背景（`image_asset` が `base_cafe` 等のシーン）、`reuse_scene_id` の使い回し。
  - **コードで描く資料カード・グラフ・まとめ／一歩のカード**（`kl_dialogue.py cards`、`assets/cards/`）。これらは Gemini を使わず ¥0 で、文字の正確さをコードで担保しているため、Muse 生成に置き換えない。指示の「素材カード全点」は、**Gemini で生成していた図表調の画像（`type` が data/check で `image_prompt` を持つシーン）**と読む。この読み方を変える場合（カードも Muse に描かせる等）は、試行の開始前に Muse が指示する。
- 画像のスタイル・構図の制約は現行どおり（`kl_image_gen.py` の `BASE_CONTEXT`・`CHART_CONTEXT`・`DIALOGUE_NARRATIVE_LAYOUT`・`DIALOGUE_CHART_LAYOUT`・`DIALOGUE_THUMB_LAYOUT`、`style_for()`／`layout_note()`）。仕様ファイルのプロンプトは、**これらを展開した完成形のプロンプト**を書く（Muse が `kl_image_gen.py` を見なくても同じ画が描けるように）。

## Shorts の扱い（`kl_image_gen.py` の実挙動に合わせた手順）

`crop_main_to_shorts` は、切り出せないカットを**自動で Gemini の再構成生成に回す**（Muse 対象のカットまで Gemini で作られてしまう）。また切り出しの被写体判定（`kl_zoom_anchor`）と切り出し後 QA も Gemini を呼ぶ（少額）。事前に切り出し可否だけを調べるオプションは無い。そこで:

1. **事前に、セッションが目視で切り出し可否を決める**（本編画像が仕様ファイルの1回目で届く前でも、`image_prompt` から判断できる分は決めておく）。Muse 対象（縦に描き直す）にするカット: 図表調（`type` が data/check）、固定素材（`image_prompt` 無し）、被写体が1つでない／端に寄る構図。それ以外は切り出し対象。
2. Muse 対象のカットは、**本編画像（`S{NN}.png`）が届いてから**、追補の仕様ファイル `muse_image_spec_kl{NNN}_shorts.md` に載せる。プロンプトは「添付の `S{NN}.png` と同じ場面を 9:16 に描き直す」形（`build_shorts_reframe_prompt` ＋ dialogue 用の COMPOSITION 指示を展開）。**参照画像 `S{NN}.png` を必ず指定する。**
3. 追補分が届くまで、Shorts の `kl_image_gen.py` を回さない。届いたら、**本編画像（`S{NN}.png`、Muse 分も含む）を Desktop の `images/` に取り込んだうえで**、**切り出し対象のカットと実物写真のカット**を `python3 kl_image_gen.py --episode kl{NNN} --shorts-scenes {番号}`（番号はカンマ区切り）で作る（Muse 分の番号は指定しない。番号に入れないカットは作られない）。実物写真のカットはコードの写真処理（AI 不使用）。番号は「各 Shorts の中の何番目のカットか」で、エピソード内の全 Shorts に同じ番号が当たる（顔アップは 0 番）。Muse 分の番号を指定しない運用だと、Shorts が複数本あるときは、同じ番号の別 Shorts のカットも作られないので、Shorts ごとに仕様を確認する。
4. 切り出しが想定外にフォールバック生成になった場合は、**「Gemini に戻した枚数」に数える**。ログの文言は2種類あるので両方を見る（「従来の生成にフォールバック」＝切り出し不可、「未生成のため独立生成にフォールバック」＝本編画像が Desktop に無い）。切り出しの被写体判定・QA の Gemini 呼び出しは「残った Gemini 利用」として結果に注記する。

## 手順

1. **仕様ファイルを作る（STEP 6「静止画生成」の時点、`kl_image_gen.py` を回す代わりに）。** 対象画像の一覧を `muse_image_spec_kl{NNN}.md` 1つにまとめる。1枚につき次の5項目:
   - ファイル名 / サイズ・画角（上の表の値と「16:9」「9:16」） / プロンプト（完成形・英文のまま） / 用途（どのシーンの何を見せる絵か。台詞の要約1行、立ち絵・字幕が乗る位置の注意） / 参照指定（`--reference-scene` 相当で背景を揃えたいシーンがあれば、そのファイル名）
   - 冒頭に共通事項: エピソード ID・タイトル、画風の共通指示、禁止（枠・帯・字幕・指定外の文字混入。**図表調は例外で、指定したラベル・数値だけは画像内に描く**。図は中央70%・下22%は無地の背景）、登場人物の外見（`cast.json`・研究者の国籍の手がかり。`feedback_researcher_ethnicity_matches_institution` 準拠）、納品形式（PNG、指定ファイル名、同じフォルダの `images/` 直下）。
2. **Drive に置く。** 慣例どおり `~/Library/CloudStorage/GoogleDrive-naru.nakajima@gmail.com/マイドライブ/Kagaku-Life/KL{NNN}/images/` に仕様ファイルを置く（`kl_finalize.py` と同じ場所。納品先もここ）。仕様ファイルのレビュー前の Desktop → Drive 同期のルール（`feedback_review_before_drive_sync`）は、仕様ファイルには適用しない（画像ではないため）。
3. **#cc-reports に報告する。** `event=step_done / step=muse_image_trial_ready / by=<担当者名> / state=ok / next=Muse の生成待ち / needs_user=なし / ref=<Drive のフォルダ URL>` の1行（形式は `kl-new.md`「進捗の報告」）。フォルダ URL は Drive の `KL{NNN}/images/` のもの。**URL の取り方:** ローカルのパスからは共有リンクを直接得られないので、Drive for desktop が付けるフォルダの ID（`xattr -p` 等のファイル属性）が取れればそれで `https://drive.google.com/drive/folders/<ID>` を作る。取れなければブラウザ（kl 制作用 Chrome）で Drive の該当フォルダを開いて URL を控える。どちらも不可なら、パス（`マイドライブ/Kagaku-Life/KL{NNN}/images/`）を書き、`needs_user` に「フォルダ URL 未取得」と書いて Muse に伝える。ready 報告の時刻を記録する（計測用）。
4. **Muse が生成して格納する**（KL制作チャット経由。Muse が4枚ずつ生成し、指定ファイル名で同じフォルダに入れる。セッションは生成しない）。
5. **到着を確認して通常の QA を行う。** 通常と同じ QA（STEP 6.5・6.6・6.7 の観点、画風の一貫性、立ち絵・字幕位置の空き、人物の外見一貫性、文字（図表調以外は混入がないこと、図表調は指定ラベル・数値が正確なこと）、サイズ 1376×768／768×1376。**サイズが違うとき:** 幅÷高さが目標（1376÷768＝1.792、Shorts は 768÷1376＝0.558）から ±2% 以内なら、LANCZOS で指定サイズへリサイズして使ってよい（±2% 以内の差は、リサイズ時のわずかな引き伸ばしとして許容）。それを超えて違えば NG として作り直しに入れる）を、**Gemini の自動 QA を使わず**（Muse 生成はコスト回避が目的のため）、セッションの目視（`Read`）＋映像担当 kl-art-director で行う。全点を1枚ずつ見る（サンプルにしない）。
   - NG があれば、作り直しリスト `muse_image_retry_kl{NNN}_r{N}.md`（N=ラウンド番号）を同じフォルダに置く。1枚につき **ファイル名・理由・修正プロンプト**。#cc-reports に `step=muse_image_trial_retry / state=retry / next=Muse の作り直し待ち / ref=<フォルダ URL>` で報告する。
   - 作り直しのラウンドは、品質が出ない場合に無制限には続けない。**同じ画像で3回 NG になったら、その画像だけ Gemini で作る（`kl_image_gen.py --scenes`）判断をセッションがしてよい**（試行の結果には「Gemini に戻した枚数」として残す）。
6. **全点そろったら通常工程へ。** Desktop の `images/` に取り込んで（`kl_finalize.py` の通常のコピーに乗せる）、以降は通常どおり。**対象分は `kl_image_gen.py` を回さない**（全体実行は未到着分を Gemini で生成してしまう）。サムネイルの文字合成は上の方法、Shorts は「Shorts の扱い」のとおり。**Gemini に戻す画像だけは、種類に合わせて実行する。本編・サムネイル背景は必ず `--no-qa` を付ける**: 本編＝`--scenes {scene_id} --no-qa`（サムネイル・Shorts は作られない）／サムネイル背景＝`--thumbnail-only --no-qa`／Shorts＝`--shorts-scenes {番号}`（Shorts は画風ドリフトチェックの対象外なので `--no-qa` は任意。付けない場合は切り出しの QA で Gemini を呼ぶので、「残った Gemini 利用」に数える）。**`--no-qa` を付ける理由:** `--scenes` で1枚でも新規生成すると、画風ドリフトチェック（`kl_image_gen.py` 910行〜）が本編の全画像を比べ、外れ値と判定された画像を Gemini で作り直して**上書きする**。Muse と Gemini は画風が違うので Muse の画像が外れ値になりやすい。`--no-qa` で自動チェックを止め、QA は目視で行う。実行前に Desktop の `images/` を別の場所へ退避しておき、意図せず上書きされた画像があれば「Gemini に戻した枚数」に数える。
7. **計測して結果に残す**（下の「計測項目」）。
8. **Kevin の最終判定に、試行画像の品質所見を含める。** kl-manager を呼ぶときに、試行であること・仕様ファイルのパス・計測値・品質所見（現行 Gemini 画像との差：画風、構図、人物の一貫性、文字混入、立ち絵・字幕との相性）を渡し、判定欄に「試行画像の品質所見」を書かせる。**エピソード完了時に、結果サマリを #cc-reports で報告する**（`event=done` の報告とは別に、`step=muse_image_trial_summary` の1行＋要点。`ref=` に結果ファイル）。

## 計測項目（結果ファイルに残す）

| 項目 | 取り方 |
|---|---|
| 総枚数 | 仕様ファイルの枚数（追補含む）。種類別（本編／サムネ背景／Shorts）も |
| 生成ラウンド数 | 初回＋作り直し（retry）の回数。Muse が4枚ずつ生成するので、1ラウンド＝仕様ファイルの全点または retry リスト全点が揃うまで |
| ready 報告から全点到着までの時間 | `step=muse_image_trial_ready` の投稿時刻 → 最後の1枚が Drive に入った時刻（ファイルの更新時刻で確認） |
| QA の初回合格率・作り直し回数 | 初回合格枚数／総枚数、作り直しを要した枚数と延べ回数、Gemini に戻した枚数 |
| Muse 側の上限イベントの有無 | 生成回数・レート等の上限に当たったか（Muse からの申告を記録。なければ「なし（Muse 申告）」） |
| 回避できた Gemini 画像費用の見積り | 通常の1話の Gemini 画像費用の目安 約 ¥195 を、通常 Gemini 生成していた枚数に対する Muse 生成枚数の比で按分（Gemini に戻した分は引く）。QA を Gemini で回さなかった分は別に注記。**見積りであることを明記**（実測のコストログがあれば、そちらを優先） |
| 品質所見 | 現行との差（上の手順8）。画像ごとの NG 理由の傾向 |

## 品質が届かない場合

その話だけ Gemini で作り直してよい（セッション判断）。他話への展開はしない（この試行の対象外）。判断した理由と、作り直した枚数・費用を結果に残す。

## 対象外（この文書・試行では扱わない）

`kl-new.md`・制作コードの変更、他話への展開、実物写真・コードで描くカードの Muse 生成化、公開・アップロード。

## 開始時のチェックリスト（kl057 のセッション向け）

- [ ] この文書を読んだ（`docs/muse_image_trial.md`）。対象の話数を決めた。
- [ ] STEP 6 で、`kl_image_gen.py` を回す前に、仕様ファイルを作って Drive に置いた。
- [ ] `step=muse_image_trial_ready` を #cc-reports に出し、時刻を控えた。
- [ ] 到着確認後、全点を1枚ずつ QA した。NG は retry リスト＋ `step=muse_image_trial_retry`。
- [ ] 全点そろうまで、対象分に `kl_image_gen.py` を回していない。
- [ ] 計測項目を結果ファイルに残した。完了時に `step=muse_image_trial_summary` を報告した。

## 試行の終了・不採用（2026-11-16）

- 試行は kl057 で終了し、**不採用**。以後の話の画像生成は、従来どおり Gemini で行う（2026-11-16、本人の判断）。
- 理由：作り直しの多さ（本編は初回4枚中2枚、Shorts 追補は4枚中2枚が作り直し）、割合による位置指定が守られにくかったこと、受け渡しに手間がかかったこと。画風は参照画像（kl057 の S08）を基準にすることで揃えられたが、総合では現行方式に及ばなかった。
- kl057 の結果：本編＋サムネイルの4枚は Muse 生成で確定（Gemini への戻しなし）。Shorts は S05・S06 を Muse 納品のまま採用、S01・S02 は PIL で位置調整のうえ採用、S03・S04 は切り出し不可のため Gemini で縦に再構成した。
