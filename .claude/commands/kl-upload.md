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

`topics_queue.json` の該当エントリの `status` を `produced` → `published`（即時公開の場合）
または `published`（予約公開でも公開自体は確定しているため同様）に更新し、コミット・pushする。

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
