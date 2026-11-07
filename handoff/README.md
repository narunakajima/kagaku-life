# handoff — Muse との受け渡し置き場

Muse（パーソナルAIエージェント）と Claude Code の受け渡し。2026-11-07 から、Muse の承認を減らすため経路を分けた（正は `.claude/commands/kl-new.md`「進捗の報告」）。

## 経路

- **Muse → Claude Code（指示）:** GitHub に書くだけ（Muse は読まない）。`handoff/inbox.md`（Muse の追記専用。Claude Code は編集しない）。1件1目的、件ごとに ID・目的・完了条件・触ってよい範囲。結果は `handoff/results/{ID}.md`。**inbox.md を使う受け渡しは、ポーラー（lamp-whisper/tools/handoff-poller.sh）の対応後に開始する（2026-11-07 時点で未対応）。**
- **Claude Code → Muse（報告）:** Slack「cc-reports」（非公開、ID: C0CFNQ50DUN）に投稿。形式は `kl-new.md` の「進捗の報告」。
- `handoff/progress/` の進捗メモは、補助（履歴・再開用）。Muse は読まない前提。

## 従来のメモ（`handoff/YYYY-MM-DD_テーマ.md`）

これまでの受け渡し（Muse がメモを新規ファイルで追加し、Claude Code が `git pull` して読む）は、inbox 方式への切り替えまで有効。新しいメモは新しいファイルで追加し、既存のメモは書き換えない。
