# /kl-upload — くらしを変える科学 YouTubeアップロード

本編・Shorts を YouTube（幸せな未来のサイエンスチャンネル、`@kagaku-life`）にアップロードする
コマンド。

**デフォルト動作: 火・木・土 19:00 JST の最短空きスロットに自動予約（週3回、2026-08-27改訂）。**
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

ユーザーにエピソード番号を聞く（例: 1、001、kl001 などどの形式でも受け付ける）。
内部では `kl001` 形式に正規化する。対象エピソードの`status`が`produced`（画像・音声・動画
すべて完成、Google Drive格納済み）であることを`topics_queue.json`で確認する。

特別な指定がある場合のみ追加オプションを使用:
- 「今すぐ公開」「即時」→ `--now`
- 「○月○日 ○時に公開」→ `--publish-at "YYYY-MM-DD HH:MM"`

## STEP 2 — アップロード実行

**通常（火・木・土19:00 JST 最短空きスロットに自動予約）:**
```bash
python3 $HOME/kagaku-life/kl_sns_up.py --episode kl{NNN}
```

**即時公開:**
```bash
python3 $HOME/kagaku-life/kl_sns_up.py --episode kl{NNN} --now
```

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
2. 火・木・土 19:00 JST を今日から1日ずつ走査し、使用済みでない・かつ現在時刻より
   未来の最初のスロットを採用する

## STEP 3 — 完了報告

```
✓ アップロード完了（予約公開: 2026-08-29 19:00 JST（自動））
  本編:   https://youtu.be/{VIDEO_ID}
  Shorts: https://youtu.be/{SHORTS_ID}
  ※ 指定日時まで非公開状態です。YouTube Studio で確認できます。
```

**Shortsの「関連動画」（本編）の設定は、このあとのSTEP 3.5でClaudeがChromeで行う
（2026-10-02から。それまではユーザーに依頼していた）。**

**サムネイルの「テストと比較」（A案 vs B案）は2026-10-01から一時中止中。依頼しない。**
構成を大きく変えた（ロゴイントロ廃止・タイトルの付け方・Shortsの冒頭）直後で、サムネイルの差か
構成の差かを切り分けられないため。`kl_sns_up.py` はA案（`thumbnail.png`）のみアップロードする。
`thumbnail_b.png` がDriveにある回もあるが、使わなくてよい。再開の目安は、新構成のエピソードが
数話積み上がって構成が安定してから（CLAUDE.md「サムネイルのA/Bテストの一時中止」参照）。
再開する場合の手順（旧）: YouTube Studio の本編の編集画面で「テストと比較」を開き、A案と
Drive `Kagaku-Life/KL{NNN}/images/thumbnail_b.png`（B案）を登録してもらう。判定は総再生時間で
行われ、Shortsは対象外。結果は `/kl-analytics` で記録する。

## STEP 3.5 — Shortsの「関連動画」を設定する（Chromeを自動操作、2026-10-02追加）

Shortsの最後のカットは「↓ 続きは本編で」と誘導しているので、YouTube Studioで
Shortsの「関連動画」に本編を設定しておかないと誘導先がない（YouTube公式ブログ:
Shortsの最後の5秒で言葉と画面の両方で関連動画へ誘導する）。`kl_sns_up.py` からは
設定していない（YouTube Data APIで設定できるかは未確認）ため、Claude in Chrome
（ユーザーのログイン済みChrome。内蔵ブラウザはログインが必要で使えない）で操作する。

**重要な制約: Studioの関連動画の選択画面には「公開済みの動画」しか出ない。**
STEP 2で予約したばかりの本編は公開日まで選べないので、今回アップロードした回は
この時点では設定できない。そこで「公開日時を過ぎていて、まだ設定していないエピソード」を
全てまとめて対象にする（前回までに予約した回が、公開された後の `/kl-upload` で拾われる）。
完了の記録は `episodes/kl{NNN}.json` の `related_video_set: true`。

### 手順

1. 対象を出す:
   ```bash
   python3 kl_related_targets.py
   ```
   「設定が必要なShortsはありません」なら、このSTEPは終了（今回の回は公開後の
   `/kl-upload` で設定される、と完了報告に一言添える）。Chromeは開かない。

2. Chromeを用意する。**起動時点でChromeが動いていたかを必ず記録する**:
   ```bash
   pgrep -x "Google Chrome" >/dev/null && echo running || echo not-running
   ```
   `not-running` なら `open -a "Google Chrome"` で起動する（この場合は最後に終了する）。
   `list_connected_browsers` でClaude in Chrome拡張の接続を確認する（起動直後は数十秒かかる
   ことがある）。接続できなければ、このSTEPは諦めて完了報告にその旨を書く（Chromeは
   自分で起動していた場合のみ終了する）。ツールが未読込なら `ToolSearch` で
   `mcp__claude-in-chrome__*`（`browser_batch`・`computer`・`navigate`・`tabs_context_mcp` 等）を
   まとめて読み込む。

3. チャンネルを切り替える。Chromeは通常、別チャンネル（ランプのひとりごと等）でログインして
   いる。アバター → 「アカウントを切り替える」で **「幸せな未来のサイエンス」（@kagaku-life、
   チャンネルID `UCj5pDosl_4FiaZ_NdNg7IcA`）** を選ぶ。**作業後に元のチャンネルへ戻す必要は
   ない**（2026-10-04、ユーザー指示）。切り替え後、`studio.youtube.com/channel/` のURLが
   上記のIDになっていることを確認する。**他チャンネルの動画は絶対に編集しない。**

4. 対象のShortsごとに（`kl_related_targets.py` が出した shorts ID・検索語を使う）。
   **座標クリックは使わない**（ウィンドウサイズが操作ごとに変わり、2026-10-02にクリックが外れた）。
   ページ内のスクリプト `studio_related_video.js` を `javascript_tool` で実行する:
   1. 最初に1回だけ、スクリプトの「関数本体」（`return (async()=>{ ... })()` の部分）を
      StudioのページのlocalStorageに保存する:
      `localStorage.setItem('rel_fn', `<関数本体>`)`
   2. 1本ごとに `studio.youtube.com/video/{SHORTS_ID}/edit` を開き（未保存の変更があると
      「Leave site?」が出るので `navigate` は `force: true`）、3秒待ってから実行する:
      `await (new Function('KW','FORCE',localStorage.getItem('rel_fn')))("検索語", false)`
      複数本は `browser_batch` に「navigate → wait 3 → javascript_tool」を並べると速い
      （1バッチ6〜8本。接続が切れて途中で止まることがあるが、実行は何度やっても安全な
      作りで、設定済みなら `skip:'already'` で飛ばす）。
   3. スクリプトがやること: 現在の関連動画が「なし」でなければ何もしない（`skip:'already'`、
      `before` が現在値）／「子ども向けか」が**未選択のときだけ**「いいえ、子ども向けでは
      ありません」を選ぶ（選択済みの値は書き換えない）／関連動画の選択画面で検索語に合う
      **本編**（`#Shorts` が付かない方）を選ぶ／「保存」を押す。
      結果は `{id, kid, before, label, rel, saved}` のJSONで返る。
   4. **確認する**: `skip` だった回は `before` が**その回の本編のタイトルと一致するか**見る。
      一致しなければ取り違えなので、`FORCE=true` で再実行して上書きする（SCのep016で
      別の回の本編が設定されていた実例がある）。`err:'no-option'` の回（検索語に合う本編が
      ない）はスキップして報告する。保存後は読み込み直して、関連動画欄が本編のタイトルで
      あることを確かめる（`saved` の値だけに頼らない。`saved:false` でも保存されていた例がある）。
      確認できた回だけ `python3 kl_related_targets.py --mark kl{NNN}`。
   5. 全部終わったら `localStorage.removeItem('rel_fn')` で片付ける。
   - 関連動画以外の設定（公開日時・タイトル・説明・字幕など）は変更しない。
   - 想定と違うUI（要素が見つからない等）で `err` が続く場合は、無理に操作せずそのSTEPを
     中断して報告する。


5. 後片付け（**必ずこの順**。チャンネルは元に戻さなくてよい）:
   1. `localStorage.removeItem('rel_fn')` で保存したスクリプトを片付ける（手順4-5）。
   2. 自分で開いたタブ（MCPのタブグループ内）を閉じる。
   3. **手順2で自分がChromeを起動した場合のみ**、Chromeを終了する:
      ```bash
      osascript -e 'quit app "Google Chrome"'
      ```
      **すでにChromeが動いていた場合は終了しない**（ユーザーが他のタブ・作業を開いている
      ため）。自分が開いたタブを閉じるだけにして、完了報告に「Chromeは元から開いて
      いたので終了していません」と書く。

6. 完了報告に、設定した件数・スキップした回（理由つき）・Chromeを終了したかを書く。
   `episodes/kl*.json` に `related_video_set` の変更が出るので、STEP 4で一緒にコミットする。

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

## STEP 5 — topics_queue.json のステータス更新

`kl_sns_up.py` は `run()` 内で `update_topics_queue_status()` を実行し、`youtube_url`書き戻しと
同じタイミングで `topics_queue.json` の該当エントリの `status` を自動的に `published` に更新する
（2026-09-08自動化。手順書頼みの手動更新だと実行し忘れても誰も気づかないという教訓から、
STEP4のコミット自動化と同様にコード側に移した）。該当エントリが見つからない場合はコンソールに
警告が出るので、その場合のみ手動で確認・更新する。

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

## STEP 7 — Desktopの残骸を削除する

STEP2のアップロードが成功し、対象素材（画像・音声・動画・BGM）がGoogle Drive
`Kagaku-Life/KL{NNN}/`に格納済み（`/kl-new` STEP11の`kl_finalize.py`実行分）であることを
前提に、確認用に使っていた`~/Desktop/kagaku-life/`フォルダ全体を削除する
（中身だけでなくフォルダ自体を削除する。「常に最新1エピソード分のみを置く」方針のため、
次エピソードの`/kl-new`実行時にまた新規作成される）。

```bash
rm -rf ~/Desktop/kagaku-life/
```

Drive同期前（`kl_finalize.py`未実行、または一部ファイルが見つからないとの警告が出ている状態）
であればこのSTEPは実行しない——先にDrive同期を完了させること。

---

## 実装済みの記録（旧: 今後の拡張予定）

公開サイト（samurai-chronicles の `sc_build_site.py` 相当、`kl_build_site.py`）の
自動再生成はSTEP6として実装済み（2026-08-30）。公開実績が6本積み上がった時点で
着手した（CLAUDE.md「サイト構築（後続タスク）」参照）。ビルド自体は
`episodes/kl*.json`と`topics_queue.json`のみを読むローカル処理で、
生成後のGit push以降の実際のデプロイ反映（Vercel）はリポジトリ側のCI連携に
委ねている（このコマンド自体はデプロイの完了を待ち受けない）。
