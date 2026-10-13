# 引き継ぎメモ: ニュース ベスト3の夜間実行（2026-10-14、MacBook → iMac）

## 目的

`/kl-new` の最初の「ベスト3の提示」は、収集・採点・注目度の実測で毎回かなり待たされる。
これを毎晩クラウドで済ませ、結果をSlackに送っておく（なるさんの指示）。
朝はSlackを見て選び、`/kl-new` は採点済みのデータから始める。

## なるさんが決めたこと

- 動かす場所: **クラウド**（Claude Codeのクラウドルーティン。iMac・MacBookの常駐ジョブにはしない）
- 件数: **ベスト3のまま**（一度「ベスト5」と言ったが取り消し。`kl_news_scan.py` は変更していない）
- Slackの送り先: **ストックボットと同じダイレクトメッセージ**
- ストックボットのSlack設定は **iMacにある**（MacBookからは見えない。だからiMacに引き継ぐ）

## 済んだこと（MacBookのセッション）

クラウドルーティンを作成した。

- 名前: `KL ニュース ベスト3（毎晩）`
- ID: `trig_019jk89sE3bz1hmcHD7u1hnh`
- 管理画面: https://claude.ai/code/routines/trig_019jk89sE3bz1hmcHD7u1hnh
- 時刻: 毎日 午前4時ごろ（日本時間）。cron は UTC で `0 19 * * *`。初回は 2026-10-15 04:02 JST
  （時刻はなるさんに確認していない。こちらで午前4時にした）
- 環境: Default（`env_01CVTaGLE3ky9sviaHbQzoVV`）、モデル: `claude-sonnet-5-5`
- リポジトリ: `https://github.com/narunakajima/kagaku-life`
- 使えるツール: Bash, Read, Write, Edit, Glob, Grep, WebSearch, WebFetch
- コネクタ: 作成時に Gmail・Google Drive・Calendar・Canva などが自動で付いたので、すべて外した
  （`clear_mcp_connections`）。Slackはコネクタではなく curl で送る

ルーティンが毎晩やること（プロンプトの要約。全文は管理画面か `RemoteTrigger` の `get` で見られる）:

1. `CLAUDE.md` と `.claude/commands/kl-new.md` のケースCを読む
2. `kl_news_scan.py` を collect → score --top 15 → tag → enrich → buzz → list --top 10 --check-urls、
   続けて `kl_concern_select.py`
3. kl-new.md のルールでベスト3を仕上げる（健康系の枠・既視感・ジャンルの間隔・URL確認。
   競合動画は WebSearch で代用し、調べられなければ「競合未確認」と書く）
4. `news_candidates.json` をコミットして main に push（できなければ `nightly/news-YYYYMMDD` ブランチ）
5. Slackに送る（いつもの提示の形。本命0件の日も「今夜は本命なし」と理由を送る）
6. ネタの決定・台本づくりには進まない

## 残っていること（iMacのセッションでやる）

### 1. クラウド環境に環境変数を登録する（なるさんの操作）

クラウドにはMacの環境変数が届かない。クラウド環境（Default）の設定に登録する。
**キーの値はチャット・ファイル・コミットに書かない。なるさんが設定画面に直接入れる。**

| 変数名 | 中身 |
|---|---|
| `GEMINI_API_KEY_KL` | GeminiのAPIキー（Macの `~/.zshenv` と同じもの） |
| `SLACK_WEBHOOK_URL_KL` | ストックボットがWebhookで送っている場合、そのURL |
| `SLACK_BOT_TOKEN_KL` と `SLACK_CHANNEL_KL` | ストックボットがボットトークンで送っている場合、トークンと、ダイレクトメッセージの送り先ID |

Slackは上の2通りのどちらか一方でよい（ルーティンはWebhookを先に見て、無ければトークンを使う）。

iMacのセッションで最初にやること: **ストックボットがSlackにどう送っているかを調べる**
（Webhookかボットトークンか、送り先のIDは何か、設定ファイルの場所）。場所と方式だけを
なるさんに伝え、値そのものは表示しない。ストックボットのリポジトリ・設定の場所は
MacBook側では分かっていない。

### 2. 試し実行して確かめる

登録が済んだら `RemoteTrigger`（`ToolSearch` で `select:RemoteTrigger` を読み込む）で
`{action: "run", trigger_id: "trig_019jk89sE3bz1hmcHD7u1hnh"}` を実行し、
`list_runs` → `get_run_log` で結果を見る。まだ一度も動かしていないので、次は未確認:

- クラウドから Gemini・各RSS・Googleニュース・Slack に通信できるか
  （だめなら環境のネットワーク設定で許可が要る）
- main に直接 push できるか（だめなら別ブランチに push される。その場合は朝に取り込む手順を決める）
- `google-genai` などPythonの依存が入るか
- Slackの文面が読みやすい長さ・形か（長すぎれば、プロンプトを `update` で直す）
- 実行にかかる時間と、Geminiの費用（score は検索つきで1件ずつ課金、毎晩15件）

### 3. うまく動いたら

- `.claude/commands/kl-new.md` のケースCに、「夜間ルーティンが済ませているので、当日の
  `news_candidates.json` があれば collect〜buzz を飛ばして `list` から始める」旨を足す
  （今は未記載。朝の `/kl-new` が同じ処理をもう一度走らせると、待ち時間も課金も二重になる）
- `CLAUDE.md` に夜間ルーティンの節を足す（ID・時刻・環境変数名・送り先）
- このメモ（`HANDOFF_nightly_news_2026-10-14.md`）を削除する

## 注意

- 環境変数を登録する前に午前4時を迎えた場合: Geminiのキーが無ければ何もせず終了。
  Geminiのキーだけあれば採点と push まで行い、Slackには届かない
- 止めたいときは `RemoteTrigger` の `update` で `{"enabled": false}`。削除は管理画面から
  （APIでは削除できない）
- 夜間ルーティンが main に push するので、朝の作業前に `git pull` する
