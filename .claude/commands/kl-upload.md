# /kl-upload — くらしを変える科学 YouTubeアップロード

本編・Shorts を YouTube（幸せな未来のサイエンスチャンネル、`@kagaku-life`）にアップロードする
コマンド。

**デフォルト動作: 火・木・土の19:00 JST（1日1本）の最短空きスロットに自動予約（2026-11-17〜）。** （ネタがないときは公開しない週もある。曜日・回数は更新頻度の約束ではなく、
「週◯回」「火・木・土」と具体的な回数・曜日は動画・サイト・概要欄のどこにも書かない（「毎週更新」は可）。2026-11-17）
1エピソード=1スロットで、他エピソードの`scheduled_at`と重複しない直近の未来スロットを
自動割り当てする（LWの水・金・日17:00と同じ「最短空きスロット」方式）。

## 認証

lamp-whisper / samurai-chronicles と同じ認証アプリを使用:
- `~/.claude/secrets/yt_client_secrets.json`
- `~/.claude/secrets/yt_token_kl.json`（初回認証後に自動生成、kagaku-life専用）

初回実行時、認証チャンネル名がコンソールに表示される。「幸せな未来のサイエンスチャンネル」に
なっていることを確認すること。表示されたチャンネルIDを`kl_sns_up.py`の
`KAGAKU_LIFE_CHANNEL_ID`定数に書き込んでおくと、以降誤チャンネルへのアップロードを自動で
防げるようになる（未設定の間はチェックがスキップされ、警告のみ表示される）。

---

## STEP 1 — エピソード番号を確認する

ユーザーにエピソード番号を聞く（例: 1、001、kl001 などどの形式でも受け付ける）。ただし、制作コマンド（`/*-new`）から続けて呼ばれたとき（最終動画の確認に対する Muse 経由の承認で `upload=yes` が付いていたとき）は、聞かずに、その会話で確定済みの番号を引き継ぐ。
内部では `kl001` 形式に正規化する。対象エピソードの`status`が`produced`（画像・音声・動画
すべて完成、Google Drive格納済み）であることを`topics_queue.json`で確認する。

特別な指定がある場合のみ追加オプションを使用:
- 「今すぐ公開」「即時」→ `--now`
- 「○月○日 ○時に公開」→ `--publish-at "YYYY-MM-DD HH:MM"`

## STEP 2 — アップロード実行

**【実行前の確認（必須。2026-11-19、kl059 で Drive の `output/` に動画が無いまま入りかけたため）】** アップロードの前に、Drive の `Kagaku-Life/KL{NNN}/output/` に本編・Shorts があり、
Desktop の `~/Desktop/kagaku-life/output/` と同じファイルサイズであることを確かめる（`ls -l` で比べる）。無い・サイズが違うときは、先に `python3 kl_finalize.py --episode kl{NNN}` を実行する
（`/kl-new` STEP 12 の手順 5 の抜け）。確かめてからアップロードを実行する。

**通常（火・木・土の19:00 JST・1日1本の最短空きスロットに自動予約）:**
```bash
python3 $HOME/kagaku-life/kl_sns_up.py --episode kl{NNN}
```

**即時公開:**
```bash
python3 $HOME/kagaku-life/kl_sns_up.py --episode kl{NNN} --now
```

即時公開（`--now`）でも、公開日時は `kl_sns_up.py` がエピソードJSONに記録する
（2026-11-16、指示2026-11-16-001で対応）。月次集計はこの公開日時を基準にするため、
STEP 3 の完了報告で記録が残っていることを確認する。

**日時を手動指定（JST）:**
```bash
python3 $HOME/kagaku-life/kl_sns_up.py --episode kl{NNN} --publish-at "2026-08-29 19:00"
```

アップロード内容:
- 本編動画（Google Drive `Kagaku-Life/KL{NNN}/output/kl{NNN}.mp4`）+ サムネイル
  （`Kagaku-Life/KL{NNN}/images/thumbnail.png`）
- Shorts動画（`kl{NNN}_shorts.mp4`、タイトルに #Shorts を付加。説明文は
  `episodes/kl{NNN}.json`の`shorts[0].hook_lines`から自動生成）
- 予約の場合: 本編・Shorts ともに同じ日時で予約される
- 字幕（SRT）アップロードは行わない（テロップは動画に焼き込み済みのため）

スロット割り当てロジック（2026-08-27改訂）:
1. 全エピソードJSON（`episodes/kl*.json`）の`scheduled_at`から使用済みの公開日を集める
2. 毎日 19:00 JST を今日から1日ずつ走査し、使用済みでない・かつ現在時刻より
   未来の最初のスロットを採用する


**【締め（必須。2026-11-19、kl059 の作業漏れの再発防止）】** この STEP が終わったら、同じ応答の中で続けて行う: (1) `python3 kl_report.py step --case kl{NNN} --step "upload 2 アップロード実行" --by <担当者名> --next "STEP 3 完了報告"` で報告文を作り、#cc-reports の案件スレッドに投稿して #cc-inbox を読む。(2) 次の工程（STEP 3 完了報告）をその場で実行する。「次は〇〇」と書いて応答を終えない（待ってよいのは、完了通知が来る作業か呼び出し中の担当者があるときだけ。`--waiting bg|agent`）。(3) 待機から戻ったら、最初に #cc-inbox と結果ファイルを確かめる。

## STEP 3 — 完了報告

```
✓ アップロード完了（予約公開: 2026-08-29 19:00 JST（自動））
  本編:   https://youtu.be/{VIDEO_ID}
  Shorts: https://youtu.be/{SHORTS_ID}
  ※ 指定日時まで非公開状態です。YouTube Studio で確認できます。
```

**Shortsの「関連動画」（本編）の設定は、公開後に Muse（クラウド）が公開10分後に自動で行う（STEP 3.5参照。セッションでは設定しない）。**

**サムネイルの「テストと比較」（A案 vs B案）は2026-10-01から一時中止中。依頼しない。**
構成を大きく変えた（ロゴイントロ廃止・タイトルの付け方・Shortsの冒頭）直後で、サムネイルの差か
構成の差かを切り分けられないため。`kl_sns_up.py` はA案（`thumbnail.png`）のみアップロードする。
`thumbnail_b.png` がDriveにある回もあるが、使わなくてよい。再開の目安は、新構成のエピソードが
数話積み上がって構成が安定してから（CLAUDE.md「サムネイルのA/Bテストの一時中止」参照）。
再開する場合の手順（旧）: YouTube Studio の本編の編集画面で「テストと比較」を開き、A案と
Drive `Kagaku-Life/KL{NNN}/images/thumbnail_b.png`（B案）を登録してもらう。判定は総再生時間で
行われ、Shortsは対象外。結果は `/kl-analytics` で記録する。


**【締め（必須。2026-11-19、kl059 の作業漏れの再発防止）】** この STEP が終わったら、同じ応答の中で続けて行う: (1) `python3 kl_report.py step --case kl{NNN} --step "upload 3 完了報告" --by <担当者名> --next "STEP 3.5 関連動画（Muse が自動設定。セッションは記録のみ）→STEP 3.6"` で報告文を作り、#cc-reports の案件スレッドに投稿して #cc-inbox を読む。(2) 次の工程（STEP 3.5 関連動画（Muse が自動設定。セッションは記録のみ）→STEP 3.6）をその場で実行する。「次は〇〇」と書いて応答を終えない（待ってよいのは、完了通知が来る作業か呼び出し中の担当者があるときだけ。`--waiting bg|agent`）。(3) 待機から戻ったら、最初に #cc-inbox と結果ファイルを確かめる。

## STEP 3.5 — Shortsの「関連動画」（2026-11-17〜: クラウド自動設定に移行。手動設定は廃止）

Shortsの「関連動画」（本編への誘導）は、**公開後に Muse（クラウド）が公開10分後に自動で設定する**。
`/kl-upload` の中では設定しない（Chromeも開かない）。
分担が Muse 側に移った2026-11-13以降も、旧STEP（セッションがChromeで設定する手順）がこの手順書に残っていたため、本節へ置き換えた（2026-11-17、ユーザー決定。SC は移行時に更新済み）。

- 設定の記録（`episodes/kl{NNN}.json` の `related_video_set`）は自動処理側が更新する
- セッションの役割は、対象エピソード・公開日時・動画IDを記録するところまで。関連動画を設定できないことを理由に「要確認」として残さない
- 公開後に Muse の設定が失敗していた場合だけ、その報告が別途上がる（セッションがその場で手動設定はしない）

---

## STEP 3.6 — 未返信コメントに内容に合わせて返信する（2026-10-20追加）

アップロード後（STEP 3.5 の後）、チャンネル（`UCj5pDosl_4FiaZ_NdNg7IcA`）の**未返信コメント**に、
**確認なしで**日本語で返信する。LWの定型返信と違い、コメント内容に合わせて Claude が1件ずつ書く。

- **報告の形（2026-11-17〜、ユーザー決定）:** コメント返信は確認不要のセッション作業であり、完了報告で「要確認」と書かない。見送った分は従来どおり、完了報告で本文と理由を伝える

1. 取得: `python3 kl_comment_reply.py list`（JSON。`thread_id`・動画タイトル・投稿者・本文）。空なら終了。
2. 返信文はコミュニティ担当 `kl-community`（`subagent_type: "kl-community"`、`model: "sonnet"`）に書かせる（2026-10-27〜、担当者制）。
   依頼文には、`list` の出力JSONのパス、保存先（スクラッチパッドの `{"thread_id": "返信文"}` のJSON）、下の「返信の方針」全文を書く。
   終わったら `python3 team_log.py add --agent kl-community --episode kl{NNN} --step 3.6 --result ok --note "返信N件・見送りN件"` で記録する。
3. 投稿: `python3 kl_comment_reply.py post <JSONパス>`（返信済みIDは `data/comment_replies.json` に記録。STEP 4 のコミットに含まれる）。

**返信の方針（無難第一）:**
- 1〜2文、丁寧語、チャンネルの誠実なトーン。視聴・コメントへの感謝＋コメントの内容に軽く触れる程度。
- 具体例: 感想→「ご覧いただきありがとうございます。〇〇に注目していただけて嬉しいです」／
  ツッコミ・補足→「補足ありがとうございます。参考にさせていただきます」／応援→感謝のみ。
- **書かないこと:** 動画・論文にない事実や数値の断言、医療・投資・健康の助言、今後の動画の約束、
  政治・宗教など意見が分かれる話題への立場表明、他者や他チャンネルの批評、絵文字の乱用（使っても1つまで）。
- **返信せずに見送る（完了報告で本文と理由を伝える）:** スパム・宣伝・詐欺っぽいリンク、誹謗中傷・攻撃的な
  コメント、事実誤り（動画の誤りの指摘）や専門的な質問で、無難に答えられないもの。
  これらは `post` のJSONに含めない（次回も未返信として残るので、ユーザーが判断できる）。
- 動画の誤りを指摘するコメントは、返信せずに必ずユーザーへ報告する。
- 失敗してもアップロード自体には影響しない。


**【締め（必須。2026-11-19、kl059 の作業漏れの再発防止）】** この STEP が終わったら、同じ応答の中で続けて行う: (1) `python3 kl_report.py step --case kl{NNN} --step "upload 3.6 コメント返信" --by <担当者名> --next "STEP 3.7 固定コメント"` で報告文を作り、#cc-reports の案件スレッドに投稿して #cc-inbox を読む。(2) 次の工程（STEP 3.7 固定コメント）をその場で実行する。「次は〇〇」と書いて応答を終えない（待ってよいのは、完了通知が来る作業か呼び出し中の担当者があるときだけ。`--waiting bg|agent`）。(3) 待機から戻ったら、最初に #cc-inbox と結果ファイルを確かめる。

---

## STEP 3.7 — 公開した本編に「問い」の固定コメントを置く（2026-11-16追加、月次評価2026-10分の提案3）

アップロード後（STEP 3.6 の後）、公開した**本編**動画に、視聴者への問いを1つ置いたコメントを
投稿し、固定（ピン留め）する。コメントの入口を作るのが目的。Shorts には置かない。

1. 文案: その回の問い（STEP 1.5 の問いゲートで決めた問い）を、視聴者への質問文にする。
   文案はコミュニティ担当 `kl-community`（`subagent_type: "kl-community"`、`model: "sonnet"`）に書かせる。
   方針は STEP 3.6 の「返信の方針」に準じる（1〜2文、丁寧語。動画にない事実や数値の断言、
   今後の動画の約束は書かない）。**文案はユーザーの承認なしで投稿してよい。代わりに編集長 `kl-manager` が文案を確認して OK を出してから投稿する**
   （2026-11-17、なるさんの指示。確認する点は、方針に反していないこと・問いが回の内容と合っていること・誤字がないこと。
   編集長が直しを求めたら、クロエが直してから再確認する。OK の記録は `team_log.py add --agent kl-manager --step 3.7 --result ok`）。
2. 投稿と固定: コメントを投稿し、固定する。**公開前の動画にはコメントを置けないので、STEP 3.5 と同じく
   「公開日時を過ぎていて、まだ固定コメントを置いていない本編」をまとめて対象にする**（前回までに予約した回が、公開後の
   `/kl-upload` で拾われる）。YouTube Data API にピン留めの公式エンドポイントがないため、Claude in Chrome で
   YouTube Studio（チャンネル `UCj5pDosl_4FiaZ_NdNg7IcA`）から投稿して固定する（Chrome は**制作専用 Chrome** を使う。接続先の確認とチャンネルの確認は
   CLAUDE.md「Chrome 作業の前の接続先の確認」に従い、作業で開いたタブ・グループは最後に閉じる。他チャンネルの動画には絶対に置かない）。
   **誤字を投稿しないための手順（2026-11-17、kl051 で「親御さん」を「誌親さん」と打って1度削除した）:** 文案は `pin_comments.json` から `json.dumps` で `\u` 形式に出して、
   `computer type` と、入力欄の中身（`#contenteditable-root` の `innerText`）との一致確認に同じ文字列を使う。**一致したときだけ**投稿ボタンを押す（一致しなければ投稿しない）。
   投稿後は `ytd-comment-thread-renderer` の投稿者が `@kagaku-life` であることと、固定のトースト「コメントを固定しました」を確かめる。
   誤りを投稿してしまったら、そのコメントだけを削除して正しい文で出し直し、完了報告に書く。
   完了したら `episodes/kl{NNN}.json` に `pinned_comment_set: true` を記録する。
   Chrome が使えないなど実施できないときは、無理をせず、完了報告で「固定コメントは要確認（未実施）」と理由を伝える。
3. 記録: `python3 team_log.py add --agent kl-community --episode kl{NNN} --step 3.7 --result ok --note "固定コメント投稿"` で記録する。
   失敗してもアップロード自体には影響しない。


**【締め（必須。2026-11-19、kl059 の作業漏れの再発防止）】** この STEP が終わったら、同じ応答の中で続けて行う: (1) `python3 kl_report.py step --case kl{NNN} --step "upload 3.7 固定コメント" --by <担当者名> --next "STEP 4 コミット・push 確認"` で報告文を作り、#cc-reports の案件スレッドに投稿して #cc-inbox を読む。(2) 次の工程（STEP 4 コミット・push 確認）をその場で実行する。「次は〇〇」と書いて応答を終えない（待ってよいのは、完了通知が来る作業か呼び出し中の担当者があるときだけ。`--waiting bg|agent`）。(3) 待機から戻ったら、最初に #cc-inbox と結果ファイルを確かめる。

---

## STEP 4 — コミット・プッシュ確認

`kl_sns_up.py` は `run()` の末尾で `commit_remaining_changes()` を実行し、
`git status --porcelain` に差分があれば（`episodes/kl{NNN}.json` への
`youtube_url`/`shorts_url`/`scheduled_at`書き戻し分など）自動でまとめてコミット・pushする。
そのため STEP 2 のアップロード実行が成功していれば、このステップで手動コミットする必要は
通常ない。

STEP 3 の完了報告後、念のため `git status` で作業ツリーがクリーンか確認する：

```bash
git status --short
```

**差分が残っている場合のみ**（自動コミットが何らかの理由で走らなかった場合のフォールバック）、
手動でコミット・pushする。


**【締め（必須。2026-11-19、kl059 の作業漏れの再発防止）】** この STEP が終わったら、同じ応答の中で続けて行う: (1) `python3 kl_report.py step --case kl{NNN} --step "upload 4 コミット・push" --by <担当者名> --next "STEP 5 キュー状態の確認"` で報告文を作り、#cc-reports の案件スレッドに投稿して #cc-inbox を読む。(2) 次の工程（STEP 5 キュー状態の確認）をその場で実行する。「次は〇〇」と書いて応答を終えない（待ってよいのは、完了通知が来る作業か呼び出し中の担当者があるときだけ。`--waiting bg|agent`）。(3) 待機から戻ったら、最初に #cc-inbox と結果ファイルを確かめる。

## STEP 5 — topics_queue.json のステータス更新

`kl_sns_up.py` は `run()` 内で `update_topics_queue_status()` を実行し、`youtube_url`書き戻しと
同じタイミングで `topics_queue.json` の該当エントリの `status` を自動的に `published` に更新する
（2026-09-08自動化。手順書頼みの手動更新だと実行し忘れても誰も気づかないという教訓から、
STEP4のコミット自動化と同様にコード側に移した）。該当エントリが見つからない場合はコンソールに
警告が出るので、その場合のみ手動で確認・更新する。


**【締め（必須。2026-11-19、kl059 の作業漏れの再発防止）】** この STEP が終わったら、同じ応答の中で続けて行う: (1) `python3 kl_report.py step --case kl{NNN} --step "upload 5 キュー更新" --by <担当者名> --next "STEP 6 公式サイト再生成"` で報告文を作り、#cc-reports の案件スレッドに投稿して #cc-inbox を読む。(2) 次の工程（STEP 6 公式サイト再生成）をその場で実行する。「次は〇〇」と書いて応答を終えない（待ってよいのは、完了通知が来る作業か呼び出し中の担当者があるときだけ。`--waiting bg|agent`）。(3) 待機から戻ったら、最初に #cc-inbox と結果ファイルを確かめる。

## STEP 6 — 公式サイトを再生成する

公式サイト（`kagaku-life.com`、`kl_build_site.py`が生成する`index.html`/
`episodes.html`/`playlists.html`）は、`episodes/kl*.json`の`youtube_url`/
`scheduled_at`を元に「公開済み」「近日公開」を自動判定する。STEP2の
アップロード成功により該当エピソードJSONに`youtube_url`/`scheduled_at`が
書き戻された状態なので、ここで再生成して反映させる。

```bash
python3 kl_build_site.py
```

**「公開済み」の判定は`youtube_url`が設定済み、かつ`scheduled_at`が
過去（JST）であること。** 予約公開の場合、公開日時が来るまでは
「近日公開」扱いのまま（タイトル等は表示されない）。そのため、
このコマンドは**予約日時が実際に到来した後にも改めて実行する必要がある**
（例えばその日以降に別エピソードの`/kl-upload`を実行したタイミングで
まとめて反映される想定。今のところ日時経過だけをトリガーに自動実行する
仕組みはない）。

生成後、差分を確認してコミット・pushする:

```bash
git add index.html episodes.html playlists.html
git status --short
```

**Vercelへのデプロイ:** このリポジトリ（`kagaku-life`）がVercelの
GitHub連携でデプロイされている場合、`main`へのpushで自動デプロイされる
想定。ローカルにVercel CLIの認証が通っていない場合（`vercel whoami`が
失敗する場合）はCLIから手動デプロイはできないため、push後にVercelの
ダッシュボードで実際にデプロイが走ったか確認するようユーザーに促す。


**【締め（必須。2026-11-19、kl059 の作業漏れの再発防止）】** この STEP が終わったら、同じ応答の中で続けて行う: (1) `python3 kl_report.py step --case kl{NNN} --step "upload 6 サイト再生成" --by <担当者名> --next "STEP 7 Desktop の後片付け"` で報告文を作り、#cc-reports の案件スレッドに投稿して #cc-inbox を読む。(2) 次の工程（STEP 7 Desktop の後片付け）をその場で実行する。「次は〇〇」と書いて応答を終えない（待ってよいのは、完了通知が来る作業か呼び出し中の担当者があるときだけ。`--waiting bg|agent`）。(3) 待機から戻ったら、最初に #cc-inbox と結果ファイルを確かめる。

## STEP 7 — Desktopの残骸を削除する

STEP2のアップロードが成功し、対象素材（画像・音声・動画・BGM）がGoogle Drive
`Kagaku-Life/KL{NNN}/`に格納済み（`/kl-new` STEP11の`kl_finalize.py`実行分）であることを
前提に、確認用に使っていた`~/Desktop/kagaku-life/`フォルダ全体を削除する
（中身だけでなくフォルダ自体を削除する。「常に最新1エピソード分のみを置く」方針のため、
次エピソードの`/kl-new`実行時にまた新規作成される）。

削除の前に、`~/Desktop/kagaku-life/output/` の本編・Shortsが Drive `Kagaku-Life/KL{NNN}/output/` に同じファイルサイズであることを確認する（`ls -l` で比べる）。一致していれば、ユーザーに聞かずに削除する（2026-11-03、なるさんの指示）。

```bash
rm -rf ~/Desktop/kagaku-life/
```

**完了報告の最後に、次の制作の前に `/clear` で会話を整理し、`/kl-new`（STEP 0 の `git pull` から始まる）を実行することを
ユーザーに一言勧める**（2026-10-16〜。長い会話のままだと古い経緯を引きずるため）。

Drive同期前（`kl_finalize.py`未実行、または一部ファイルが見つからないとの警告が出ている状態）
であればこのSTEPは実行しない——先にDrive同期を完了させること。

**案件を閉じる（2026-11-19）:** STEP 7 まで終わったら、`python3 kl_report.py done --case kl{NNN}` を実行し、出力の1行（`event=done`、本文に本編・Shortsの URL・予約日時・コメント返信件数を書く）を #cc-reports の案件スレッドに投稿する。これで Stop フック（`kl_stop_check.py`）の監視が外れる。

---

## 実装済みの記録（旧: 今後の拡張予定）

公開サイト（samurai-chronicles の `sc_build_site.py` 相当、`kl_build_site.py`）の
自動再生成はSTEP6として実装済み（2026-08-30）。公開実績が6本積み上がった時点で
着手した（CLAUDE.md「サイト構築（後続タスク）」参照）。ビルド自体は
`episodes/kl*.json`と`topics_queue.json`のみを読むローカル処理で、
生成後のGit push以降の実際のデプロイ反映（Vercel）はリポジトリ側のCI連携に
委ねている（このコマンド自体はデプロイの完了を待ち受けない）。


---

## 再生リスト（2026-10-06〜）

`kl_sns_up.py` は本編のアップロード直後に、`topics_queue.json` の `genre` に対応する再生リスト（`theme_playlists.json`、5ジャンル）へ本編を自動で追加する（`kl_playlists.py`）。`genre` が未設定だとスキップして警告が出るので、`/kl-new` STAGE5で必ず `genre`/`health` を入れておくこと。失敗してもアップロード自体は止まらない。後から入れ直すときは `python3 kl_playlists.py --episode kl{NNN}`。Shortsは再生リストに入れない。
