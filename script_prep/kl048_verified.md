# kl048 原文で確認済みの一次資料（2026-10-23、メインがHTML取得・ブラウザで確認）

調査メモ（kl048_sources_*.md）は小型モデル経由の引用を含む。台詞・資料カードの「原文」はこのファイルの文言を使う。
ここに無い数字は、台本に使う前に原典で確かめる。

## R0 Claude Duet 発表（Anthropic、2026-10-21）
https://claude.com/resources/articles/claude-duet
- 「A research preview is available by waitlist today, starting with US Pro and Max subscribers.」
- 「a new app where Claude works as a proactive agent. It comes to you with what needs your attention」
- 「Duet reads, drafts, and prepares work on its own. But before it sends a message, makes a payment, signs a document, or deletes anything, it shows you exactly what it's about to do and waits for your approval. A few things are off-limits even with your approval, like trading securities or moving money between accounts.」
- 「Actions are approved by our auto mode classifier, the same safeguard that protects Claude and Claude Code from taking steps you didn't ask for.」
- 利用者がルールを教える・「常に許可」する仕組みの記載は、発表とヘルプ（R1）に無い。

## R1 Claude Duet ヘルプ
https://support.claude.com/en/articles/17631495-get-started-with-claude-duet
- 「Claude Duet is available as a research preview to users on the Pro and Max plans in the US, through a waitlist.」
- 例:「Check Stripe for unpaid invoices and draft reminder emails for me to approve.」

## R2 Muse 日本での提供開始（Meta、2026-10-23）
https://about.fb.com/ja/news/2026/10/muse-personal-ai-agent-launches-in-japan/
- 「Metaは10月23日（日本時間）より、パーソナルAIエージェント「Muse」の日本での提供を開始します。日本は、今年9月に先行して提供を開始した北米以外で、初めての提供地域となります。」
- 「多くの基本的な機能は無料で利用でき、さらに活用したい方向けにはサブスクリプションプランもご用意しています。」

## R3 Muse ヘルプ「Museがあなたのガイダンスと承認に基づいて機能する仕組み」（日本語、ブラウザで確認）
https://www.meta.com/ja-jp/help/superintelligence/1385290430137537/
- 「しかし、完璧な自動システムは存在しません。Museはあなたに代わって行動するため、Museのアクションを注意深く導き、承認する責任はあなたにあります。」
- 「Museは間違えたり、予期せぬ行動をとったりすることがあります。」
- 「学習段階では、Museの仕組みに慣れるまで、リスクの少ないタスクから始めましょう。」
- 「サードパーティのサービスや受信者との間で発生したエラーを含め、エラーの修正は利用者の責任です。」
- 「Museは、どのような決定に承認が必要かを学習していきます。」
- 承認の選択肢: 「1回だけ許可」「このタスクを許可」「このサイトを許可」「常に許可:今後、Museはこのコネクターに対してこのタイプのアクションを、再度の確認なしに実行できます」「却下」
- 「アクティビティログにアクセスし、Museが実行したアクションやあなたが付与したアクセス許可の時系列の記録を確認できます。」
- 「メールを送信するなどのアクションは、自分が実行する場合と同様に、元に戻すことはできません。」

## R4 dots のご紹介（OpenAI、2026-09-29、日本語版をブラウザで確認）
https://openai.com/ja-JP/index/introducing-dots/
- 「ときには、頼もうと思うより先に動いてくれることもあります。」
- 「初期テスターの dot が、ある媒体への請求を忘れていたことに気づき、請求書を作成し、テスターの承認を得て送信しました。」
- 「直接やり取りしていないときも、dot はバックグラウンドであなたをサポートできる方法を探します。これを「先回りリサーチ」と呼んでいます。dot は、すでに接続しているアプリを、読み取り専用に制限されたツールを使って参照します。そのため、メッセージを送信したり、アプリ内のコンテンツを変更したり、ブラウザーやコンピューターを操作したりすることはできません。」
- 「dot には、どのような場合に自律的に行動し、どのような場合に承認を求めるかを定めたルールが、あらかじめ組み込まれています。カスタムルールでは、特定のアクションを許可したり、承認を必須にしたり、ブロックしたりできます。組み込みの安全要件は常に適用されます。」
- 「パスワードの変更など、一部の機密性の高いタスクは、必ずユーザー自身で行う必要があります。」
- 「dot も間違えることがあるため、重要な結果につながる作業は必ず確認してください。」
- 提供: 「対象地域の Pro ユーザーおよび Business のプレミアムシート」。日本が対象地域かは未確認。
- kl034 で dots を扱い済み。単独の紹介にしない。

## R5 Grok Bot セキュリティ（xAI docs）
https://docs.x.ai/grok-bot/security
- 「Allow once lets the Bot continue with that action, Always allow can save a matching rule, and Deny blocks it.」
- 「Ask first rules always stop matching actions, and Allow automatically rules let matching actions proceed only when the reviewer finds no other reason to stop.」「Ask first wins when rules conflict.」
- 「Keep rules narrow and tied to a known action, like "ask first before sending any external email"」
- 「Auto Review is the review layer behind those prompts: an independent review model that evaluates risky Bot actions before they run」
- 日本での提供可否は未確認。

## R6 Anthropic「Measuring AI agent autonomy in practice」（2026-02-18。提供元自身の測定、査読論文ではない）
https://www.anthropic.com/research/measuring-agent-autonomy
- 「Newer users (<50 sessions) employ full auto-approve roughly 20% of the time; by 750 sessions, this increases to over 40% of sessions. This shift is gradual, suggesting a steady accumulation of trust.」
- 「Claude Code's default settings require users to manually approve each action, so part of this transition may reflect users configuring th[eir settings]」（設定を変えた分を含む可能性、と著者自身が注記）
- 「New users (those with around 10 sessions) interrupt Claude in 5% of turns, while more experienced users interrupt in around 9% of turns」「Experienced users interrupt Claude more often, not less.」
- 「Data reflects all interactive Claude Code usage for users who signed up after September 19, 2025.」（対象は Claude Code＝主にプログラミング）
- 「as users gain experience with agents, they tend to shift from approving individual actions to monitoring what the agent does and intervening when needed. In Claude Code, for example, experienced users auto-approve more but also interrupt more.」
- 「Effective oversight of agents requires more than putting a human in the approval chain.」
- 事故が増えたか減ったかは測っていない。

## R7 Anthropic Engineering「Claude Code auto mode」（2026-03-25。提供元自身の測定）
https://www.anthropic.com/engineering/claude-code-auto-mode
- 「Manual prompts sit in the middle, and in practice users accept 93% of them anyway.」
- 「Real overeager actions (n = 52). Curated from sessions where an employee denied the action or it was flagged post-hoc.」（社員の実際の利用から）
- 全体の流れで 誤検知 0.4%、行き過ぎた操作の見逃し 17%。「The 17% false-negative rate on real overeager actions is the honest number.」
- 「If you are manually approving every action carefully, it's arguably a regression—you're trading your own [judgment …]」
- Duet の承認はこの分類器（R0）。ただし 17% は Claude Code の社員利用での数字で、Duet で測った数字ではない（混ぜない）。

## R8 Yan「（承認を事前のルールにする）」arXiv:2608.27443（2026-08、単著、まだ専門家の審査前）
https://arxiv.org/abs/2608.27443
- 「We analyzed 113 participants without professional software backgrounds across three conditions: per-action human-in-the-loop approval (HITL), automated per-action model review (AUTO), or user-authored consequence policy (POLICY).」
- 「All supervised an 18-action simulated day, including 7 overreach actions.」
- 「POLICY blocked less overreach than HITL (-20.1 percentage points, 95% CI [-32.1, -8.1]) and AUTO (-14.5 points, 95% CI [-25.8, -3.2]). POLICY lowered runtime prompts from 18.0 to 10.9, but total intervention time was not reliably lower when rule setup was included.」
- 「Exploratory analysis showed that participants chose "ask" for 114 of 140 POLICY rules」
- 模擬の1日・非専門家・一度ルールを書くだけ（教え直しの繰り返しは無い）。全文は未精読。

## 未確認（使う前に原典で確かめる）
- Chen ほか CHI '25（arXiv 2410.04596、65人、先回り提案の頻度と好み 80%/90%/47%）
- Pu ほか CHI '25（18人、先回り介入398件、邪魔された感 4.61/3.78 vs 1.56）
- Dratsch ほか Radiology 2023（誤ったAI提案で正答率 82%→45.5% など。RSNA 報道経由のみ）
