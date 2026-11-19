# 作業漏れの再発防止策（kl059、2026-11-19）— LW・SC に適用するための引き継ぎ

KL で実装した内容と、LW・SC に同じ形で入れるときの手順。**LW・SC への適用は、なるさんの確認（Muse 経由）が出るまで行わない。**
適用は、それぞれのリポジトリのセッションで行う（このセッションは KL の作業ディレクトリからだけ触る）。

## 何が起きたか（要約）
- 工程の報告を出さずに次へ進んだ／「次は〇〇」と書くだけで応答を終えて止まった（2回）／承認待ちの監視が承認を検知したのに結果ファイルを読まず、約1.5時間取り込めなかった／Drive の2回目の格納（動画生成の後）が抜けかけた。
- 構造的な原因: ①報告・次工程の呼び出しの決まりが、手順書の冒頭に1か所だけで各工程の中にない ②応答を終えるときに「次の工程が動いているか」を確かめる仕組みがない ③メインの会話は自分が止まったことを感知できず、承認待ちの完了通知後の動作が強制されていない。

## KL での実装（コミット 089fe8e）
| 変更 | ファイル |
|---|---|
| 各 STEP の末尾に「締めの3点」（報告→次工程をその場で実行→待機から戻ったら #cc-inbox と結果ファイルを最初に確かめる） | `.claude/commands/kl-new.md`（STEP 4〜13）、`.claude/commands/kl-upload.md`（STEP 2〜6） |
| STEP 11: `kl-manager` を Agent で呼ぶ、と明記（「読み替え」の文だけにしない） | `kl-new.md` |
| 承認待ち手順の強化（完了通知後は最初に結果ファイルを Read／exit 3 は張り直す／待機中も #cc-inbox を自分で読む／原因は実物を確かめてから書く） | `kl-new.md`「承認待ちポーリング待機」 |
| Drive 格納の順序を番号付き（動画生成→フレーム確認→判断待ち→承認→**finalize 再実行**→upload）に。kl-upload の前に Drive の output/ とサイズを確認 | `kl-new.md` STEP 12、`kl-upload.md` STEP 2 |
| 報告の文面生成・状態記録・team_log を1つに | `kl_report.py`（状態は `team/session_state.json`、git 追跡外） |
| 応答終了時の自動チェック（Stop フック） | `kl_stop_check.py`、`.claude/settings.json` の `hooks.Stop` |
| 長い工程のタイマー（`sleep` をバックグラウンドで走らせ、満了通知で途中経過を投稿） | `kl-new.md`「進捗の報告」 |

## Stop フックの動き（`kl_stop_check.py`）
`team/session_state.json` を見て、案件が進行中のとき次のどれかなら `{"decision":"block","reason":…}` を返して応答の終了を止める。
1. 未読の承認の結果ファイル（`/tmp/lw-approval/<案件>-*.json` の `status=approved` で、取り込み印より新しい）がある
2. `waiting=none` で `pending_next` がある（「次は〇〇」と書いて終える状態）
3. `waiting=approval` なのに承認の監視プロセスが動いていない
止めない: 案件なし／状態が6時間以上古い／`waiting` が `bg`・`agent`／`waiting=approval` で監視が動作中／`stop_hook_active`（ループ防止）。
試験は6パターンで確認済み（止める3・通す3）。

## LW・SC に入れるときの読み替え
- `project=KL` → `LW`／`SC`、案件IDの形式（`kl059` → 各プロジェクトの形式）、`approval-watch.py` の `--project`
- 手順書のファイル名・STEP 番号は各リポジトリのものに合わせる（締めの3点の文面はそのまま使える）
- `kl_report.py`・`kl_stop_check.py` は、各リポジトリに置く（`kl_` の接頭辞・`team_log.py` の呼び出し・Slack の案件スレッドの扱いを合わせる）
- Stop フックは、そのリポジトリの `.claude/settings.json` に登録（設定の変更なので、各リポジトリでも承認を得ること）
- 効果の判定は KL で kl060・kl061（催促0・停止0・承認の取り込み10分以内）。先に KL で効くか見てから広げる選択肢もある
