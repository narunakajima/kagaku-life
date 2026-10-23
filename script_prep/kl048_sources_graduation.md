# kl048 論点: 「承認の卒業」（ルールを教えて事後報告）は設計されているか・裏付けはあるか（調査日 2026-10-23）

## 取得上の注意
- 「原文」は WebFetch（小型モデル経由）が返した引用。ツール側で1引用125字までに制限され、原文そのままとは限らない。**台本に引用符つきで使う前に、ブラウザで原ページを目視確認すること。**
- OpenAI（openai.com、help.openai.com）は今回も HTTP 403 で開けなかった。Dots は検索結果の要約のみで **未確認**。
- 「書いていない」は「取得したそのページに書いていない」の意味。
- 報道・ブログは手がかりのみ。数字は資料のとおりに写した。
- 用語: 「承認の卒業」を、(1) 人が自分でルール／許可を渡す、(2) 次回から確認なしで動く、(3) 後から活動ログで確認できる、(4) 取り消せる、の4要素に分けて見た。

---

## 1. 四つのサービスの公式資料

### 1-1. Claude Duet（Anthropic）
資料: 発表 https://claude.com/resources/articles/claude-duet （Anthropic、2026-10-21）／ヘルプ https://support.claude.com/en/articles/17631495-get-started-with-claude-duet （公開日の記載なし）
- ルールを教える／常に許可: **記載なし**（2ページとも）。発表の取得結果は "not described"。
- 承認: 「before it sends a message, makes a payment, signs a document, or deletes anything, it shows you exactly what it's about to do and waits for your approval」（発表。取得結果の引用）。購入は「designed to ask before each purchase」（ヘルプ）。「Some actions are off-limits even with your approval.」
- 承認を後回し: 「If you can't approve right away, Claude Duet finishes the rest of the task and brings the approval back to you later.」（ヘルプ）
- 自動の仕組み（注意）: 発表に「Actions are approved by our auto mode classifier」とある（取得結果の引用）。ユーザーが渡す許可ルールではなく、**分類器（モデル）が代わりに承認する設計**。
- 通知の調整: 「You can also tell it what you want to hear about and how often.」（通知の話で、行動の許可ではない）
- 活動の確認: 活動ログの記載なし。「The Tasks tab shows what Claude Duet is working on.」（ヘルプ）。製品ページ https://claude.com/product/claude-duet に「see what Claude Duet has done and is doing for you, and steer it」（前回メモ）。
- 取り消し: 記載なし。アプリの接続解除はいつでも可（「you can disconnect any app at any time」）。
- 限界: 日本では使えない（米国のみ、Pro/Max）。発表は詳細な安全設計を後日公開としている（前回メモ）。

### 1-2. Meta Muse
資料: ヘルプ「Muse のガイダンスと承認」 https://www.meta.com/help/artificial-intelligence/1385290430137537/ （公開日の絶対表示なし。前回メモで「6週間前」更新）。発表 https://about.fb.com/news/2026/09/introducing-muse/ （2026-09-08）、日本発表 https://about.fb.com/ja/news/2026/10/muse-personal-ai-agent-launches-in-japan/ （2026-10-23）
- **「常に許可」あり。** 承認時の選択肢: 「1回だけ許可」「このタスクを許可」「このサイトを許可」「常に許可」「却下」。「常に許可:今後、Museはこのコネクターに対してこのタイプのアクションを、再度の確認なしに実行できます」
- **学習あり。**「Museは、どのような決定に承認が必要かを学習していきます。」（学習の中身・条件の説明は取得範囲に無い）
- 設定の段階: コネクターは「Ask for some actions」（書き込みと重要な読み取りの前に確認）／「常に確認」。ウェブアクセスも「一部のアクションをリクエスト」／「常に確認」。
- **活動ログあり。**「アシスタントアイコンをタップしてアクティビティログにアクセスし、Museが実行したアクションやあなたが付与したアクセス許可の時系列の記録を確認できます。」
- 取り消し: 「チャットでMuseに一部のアクション(ウェブサイトの読み込みや購入前の価格比較など)を元に戻したり、停止したりするよう指示できます。」メール送信などは元に戻せない。
- 管理画面に「コネクター」「アーティファクトと日時指定タスク」「許可したウェブサイト」の項目（付与した許可を見直す入口とみられるが、**許可の取り消し方の説明は未確認**）。
- 監督の呼びかけ（原文）:「AIのアクションを定期的に監督して、自分の意図と一致していることを確認してください。」責任: 「Museのアクションを注意深く導き、承認する責任はあなたにあります。」
- 限界: 「常に許可」の対象の粒度は「このコネクターのこのタイプのアクション」まで。利用者がルールを文章で書く機能は取得範囲に無い。日本で使える（2026-10-23開始）。

### 1-3. OpenAI Dots
資料: 公式本文は403で**未確認**。下は検索結果の要約（help.openai.com/en/articles/20001529 系の複製ページの要約）で、**原文未確認**。
- 「Custom Rules」で、対応する操作を「自分でやってよい」「承認が要る」「やってはいけない」の3つに分けられる（要約）。設定から確認できる（要約）。
- コアの安全要件（パスワード変更時に本人へ引き継ぐ等）、Autoreview、先回り調査の制限はカスタムルールで外せない（要約）。
- 既定は階層的: 最も機微な操作（パスワード変更・送金）は本人が実行。データの完全削除・ソフトのインストールは毎回承認の場合がある。定期メッセージ送信などは**事前承認も可能**で、事前承認は許可した範囲に限られる（要約）。
- 活動の確認・取り消し・責任: 前回メモの検索要約（Activity View、一時停止）のみ。**原文未確認**。
- 結論: 仕組みとしては4社中最も「ルールを教える」に近い記述だが、**原文で確かめられていないので台本には使えない**。

### 1-4. xAI Grok Bot
資料: https://docs.x.ai/grok-bot/security 、https://docs.x.ai/grok-bot/overview （日付の記載なし。前回メモ参照）
- **「常に許可」とルール記述あり。** 承認時の選択肢: 「Allow once」「Always allow」（"can save a matching rule"）「Deny」。
- ルールは 設定 → General → Auto-review で個人が設定。**Ask first**（"always stop matching actions"）と **Allow automatically**（"let matching actions proceed only when the reviewer finds no other reason to stop"）の2種。衝突したら Ask first が勝つ。
- 書き方の例（原文）: Ask first「ask first before sending any external email」、Allow automatically「allow automatically when running `git status` in `/workspace/reports`」。広いルール（「allow everything in the browser」）は避け、「narrow and tied to a known action」とする。
- 自動許可でも**独立した審査モデル Auto Review**が通る（「an independent review model that evaluates risky Bot actions before they run」）。つまり自動許可ルール＝無審査ではない。
- 承認の範囲: 「An approval controls the proposed action, not work already completed.」
- 個人ルールはチームルールより緩くできない（「can only make behavior stricter」）。
- 活動の確認: 一般利用者向けの活動ログの記載なし。Action Recording（Enterprise、管理者が有効化、既定オフ、保持90日）と監査ログ（Enterprise）。
- 取り消し／ルール削除: **保存済みルールの削除方法の説明なし**（"does not say how members revoke or delete individual saved rules"）。プラグインの認可の取り消しは可。
- 限界: 地域の記載なし（日本で使えるか不明）。

### 1-5. 仕組みの例: Claude Code の許可ルール
資料: https://code.claude.com/docs/en/permissions （Anthropic 公式ドキュメント、日付の記載なし）
- 承認プロンプトに「Yes, and don't ask again for: npm test *」が出る。Bash コマンドは「リポジトリとコマンドごとに恒久的」、ファイル編集は「セッション終了まで」（表）。恒久の場合 `.claude/settings.local.json` に保存され、以後の全セッションに適用。
- ルール: allow / ask / deny。「Rules are evaluated in order: deny, then ask, then allow. The first match in that order determines the outcome」。広い deny は狭い allow より優先。
- 確認・取り消し: `/permissions` で全ルールとその出所の設定ファイルを一覧し、追加・削除できる。
- 強制の主体:「Permission rules are enforced by Claude Code, not by the model.」プロンプトやCLAUDE.mdの指示は許可を変えない。
- モード: `acceptEdits`（作業フォルダ内の編集と一部のファイル操作を自動承認）、auto（分類器が承認）、`bypassPermissions`（確認を省略、「Only use this mode in isolated environments like containers or VMs」）。
- 限界: コーディングツールの仕様。生活者向けのエージェントの設計の証拠ではない。

### 1-6. 仕組みの例: Claude Code「auto mode」の設計根拠
資料: https://anthropic.com/engineering/claude-code-auto-mode （Anthropic エンジニアリング、2026-03-25）
- 動機（原文）:「Over time that leads to approval fatigue, where people stop paying close attention to what they're approving.」手動プロンプトの **93% をユーザーが承認**している（取得結果。母数・期間は取得範囲に無い）。
- 「Auto mode is a new mode for Claude Code that delegates approvals to model-based classifiers.」
- 見逃し率: 実際の行き過ぎた操作（n=52）で偽陰性 17%（「the honest number」）、模擬の情報持ち出し（n=1,000）で 5.7%。実運用相当（n=10,000）の誤ブロック 0.4%。
- 限界（原文）:「is not a drop-in replacement for careful human review on high-stakes infrastructure.」連続3回拒否または計20回で人に戻す。
- 注意: 「承認を毎回求めるやり方は形骸化する」という**提供企業自身の認識**であり、第三者の測定ではない。

---

## 2. Anthropic「Measuring AI agent autonomy in practice」原文確認
URL: https://www.anthropic.com/research/measuring-agent-autonomy 、発表: Anthropic（著者に McCain, Millar, Huang ほか多数、Societal Impacts 系チーム）、2026-02-18。取得は小型モデル経由の引用（上の注意参照）。
- 対象: Claude Code の**対話セッションのうち、2025-09-19 以降に登録した利用者**の利用。
- 自動承認（原文）:「Newer users (<50 sessions) employ full auto-approve roughly 20% of the time」「by 750 sessions, this increases to over 40% of sessions.」→ **メモの「約20%→40%超」は原文どおり。** 数字は「セッションのうち full auto-approve を使った割合」。
- 限界の注記（原文の趣旨）: Claude Code の既定は手動承認なので、この増加は**利用者が設定を変えたことを反映している可能性**がある。
- 割り込み（原文）:「New users (those with around 10 sessions) interrupt Claude in 5% of turns」「more experienced users interrupt in around 9% of turns.」→ **「約5%→約9%」も原文どおり**（ターン単位）。
- 著者の解釈（原文）:「New users are more likely to approve each action before it's taken.」「Experienced users are more likely to let Claude work autonomously」。「Effective oversight doesn't require approving every action but being in a position to intervene when it matters.」要約文として「they tend to shift from approving individual actions to monitoring what the agent does.」→ **「承認から監視へ移る」という趣旨の記述はある**（ご提示の言い回しに近い文が実在）。
- 限界（原文）: Anthropic の1社のみ。「Many of our strongest findings are grounded in data from Claude Code」。リスク・自律度は Claude による分類で人は中身を見られない。2025年末〜2026年初の期間。公開APIは個別のツール呼び出しで、全体の流れを過大に拾う可能性。
- 提言（原文の趣旨）: 配備後の監視への投資、製品は利用者の監督を前提に設計する。**特定の承認ルールの義務化は時期尚早**（承認要件が安全上の利点なしに摩擦を増やす可能性）。
- **記録しておくこと:** この研究は「経験とともに自動承認が増える／割り込みも増える」という**行動の観察**であり、(a) 事故が増えたか減ったか、(b) 割り込みが適切だったか、(c) 自動承認が安全だったか、は測っていない。著者の解釈（監視へ移る）も仮説的な説明で、検証はされていない。前回メモの「約73%に人が関与」「取り消せない行動0.8%」は別の分析（公開API）。

---

## 3. 研究

### (a) 古典
- **Sheridan（1992）** Telerobotics, Automation, and Human Supervisory Control, MIT Press。出版情報は図書館目録で確認（393頁）。監督制御の定義は Wikipedia 経由で「in the strictest sense, supervisory control means that one or more human operators are intermittently programming」（定義の続きは取得できず）。人が断続的に指示を与え、自動の部分が自律的に動く構成。**「management by exception」という語は、取得した範囲では確認できなかった**（書籍本文も未確認）。この語を台本で Sheridan に帰属させない。
- **Parasuraman, Sheridan & Wickens（2000）** IEEE Trans. Syst., Man, Cybern. A, 30, 286–297。自動化を4種の機能（情報取得／情報分析／意思決定・行動選択／行動実行）に分け、それぞれ手動から完全自動までの段階があるとするモデル。要旨は検索結果の複製による（出版社ページ未取得）。「承認の卒業」は「行動実行を自動に、判断の選択は人」のように**機能ごとに自動化の段階を選べる**ことと整合するが、この論文が承認ルールを論じているわけではない。
- **Bainbridge（1983）** Ironies of automation, Automatica 19(6), 775–779。要旨: 産業プロセスの自動化が人の問題を**減らすのでなく拡大**しうる、という議論。PDFはスキャンで本文を取得できず、監視・技能低下の記述は二次要約止まり（原文未確認）。
- **Lee & See（2004）** Trust in Automation: Designing for Appropriate Reliance, Human Factors 46(1), 50–80。検索の二次要約: 信頼が自動化の能力と合っていること（較正）が適切な利用につながり、**過信は危険な使用、不信は利益の未使用**を招く。要旨・定義の原文は取得できず（ログイン壁）、**原文未確認**。
- **適応的自動化**（状況に応じて自動化の度合いを変える）: 一次資料は今回取得できず。**未確認**。

### (b) 権限を渡した後に事故が増えるか減るかの測定
- **Parasuraman & Manzey（2010）** Complacency and Bias in Human Use of Automation, Human Factors 52(3), 381–410。要旨の要約: 複数課題の負荷下で自動化に注意が向かない「complacency」と、不完全な支援での**見落とし・誤従順の誤り**（automation bias）は重なる現象で、注意が中心。検索結果の要約に「訓練や指示でなくならない」とあるが、この文は**原文では未確認**。
- **Skitka, Mosier & Burdick（1999）** Does automation bias decision-making?, Int. J. Human-Computer Studies 51(5), 991-1006。模擬飛行課題で、非常に信頼できるが不完全な自動支援がある群が、支援なし群より監視課題で成績が低かった（二次要約）。学生80名とするのは業界誌の報道。**実験室の模擬課題**。
- **Endsley & Kiris（1995）** Human Factors 37(2), 381–394。航法課題の自動化で状況認識が下がり、自動化が失敗したときの判断が遅れた。**人が操作する度合いが高いほど状況認識の低下が小さい**（要約）。参加者数等は未確認。
- **Ting Yan（2026-08-27）** Do User-Authored Permission Policies Improve Protection Against AI Agent Overreach? arXiv:2608.27443（プレプリント、単著、査読の記載なし）。**本題に最も近い唯一の実験。** 非専門家113名が、模擬の1日（18の操作、うち7つが依頼の範囲を超える行き過ぎ）を、(1) 毎回承認、(2) モデルによる自動審査、(3) 自分で書いたルール（allow／ask／never）のいずれかで監督。結果（要旨）: ルール群は行き過ぎを**毎回承認より20.1ポイント、自動審査より14.5ポイント少なくしか止められなかった**（95%CI それぞれ[-32.1, -8.1]、[-25.8, -3.2]）。実行時のプロンプトは18.0→10.9に減ったが、ルール設定の時間を含めると介入時間は有意に短くならなかった。ルール140件中114件は「ask」。ルール群で実行された行き過ぎ148件のうち、133件は人の承認後、15件が「allow」ルールで自動実行。限界: 行き過ぎの分析は探索的、模擬の1日18操作、非専門家のみ、全文は未精読。**「ルールを渡すと安全になる」とは言えず、むしろ逆向きの結果。**
- **Anthropic（2026-03-25）** 上記1-6。手動承認の93%が承認される（形骸化の根拠）と、分類器が代行したときの見逃し率。第三者ではない。
- **Anthropic（2026-02-18）** 上記2。権限を渡す行動の観察のみで、事故の増減は測っていない。
- 「権限を渡した利用者の事故率の推移」を実地で測った一次資料: **見つからず**。

### (c) 事後監査・ログ確認が機能するか
- **Ben Green（2022）** The Flaws of Policies Requiring Human Oversight of Government Algorithms, Computer Law & Security Review 45。arXiv:2109.05067。41の政策を調べ、「evidence suggests that people are unable to perform the desired oversight functions」と主張。個別の根拠研究は取得範囲に無い。**政府アルゴリズムの話で、AIエージェントの事後確認の測定ではない。**
- 検索で、AIエージェントの「人が後から確認する」仕組みの有効性を測った実験は**見つからなかった**。EU側の政策コメントは「エージェントが動き、人は事後にレビューする（する場合）」の構造は不十分だと論じるが、これは**主張であって測定ではない**（futurium の記事、手がかり止まり）。
- Anthropic の自律度の研究（2）は「人が割り込む」頻度は測るが、**割り込みで問題が防げたか、見逃しがどれだけあったか**は測っていない（人による後段の確認は見えないと自ら限界に書く、前回メモ）。

---

## 判断

### Q1. 「承認の卒業（ルールを教えて事後報告）」がサービス側に設計されているのは四つのうちどれか
- **Meta Muse**（公式ヘルプで確認）: 承認時の「常に許可」＋「どの決定に承認が必要かを学習」＋活動ログ（付与した許可の時系列も）＋一部の取り消し。4要素のうち、取り消しは一部のみ。**ただし利用者が文章でルールを書く機能は確認できず、付与した許可の取り消し方は未確認。**
- **Grok Bot**（公式ドキュメントで確認）: 「Always allow」でルールを保存、Allow automatically／Ask first を自分で書ける（最も明示的なルール記述）。ただし自動許可でも Auto Review を通る。**一般利用者向けの活動ログと、保存ルールの削除方法は確認できず。**
- **OpenAI Dots**: 検索要約では Custom Rules（自動／承認／禁止の3分類）と事前承認があるが、**原文未確認**。
- **Claude Duet**: 公式資料に「ルールを教える／常に許可」の記載なし。代わりに分類器が承認を代行する設計。**四つのうち、利用者が権限を渡す形の「卒業」は書かれていない。**
- 参考: Claude Code は allow／ask／deny、「don't ask again」、`/permissions` での一覧・削除まで公式に設計されている（コーディング用）。

### Q2. 裏付ける測定はあるか
- **「慣れると自動承認が増える」という行動の観察はある**（Anthropic、Claude Code、20%→40%超、割り込み5%→9%。設定変更の影響の可能性を著者が注記）。
- **「渡した後に安全か」の測定は、足りない。** 唯一近い実験（Yan 2026、プレプリント、模擬課題、非専門家113名）は、利用者の書いたルールが行き過ぎを毎回承認より**多く通した**という逆向きの結果。毎回承認の形骸化（Anthropic自身が手動プロンプトの93%承認と述べる）も、承認を減らす理由にはなるが、安全の証明ではない。
- 事後ログ確認の有効性を測った研究は見つからず、「足りない」。自動化一般では、監視役の人が見落としやすいことを示す古典（Parasuraman & Manzey、Skitka ほか、Bainbridge）がある一方、これらは「事後報告」方式そのものを測った研究ではない。

### Q3. 一般の人に誠実に3文で説明できるか
言える、ただし「効く」とは言わない形で。
1. 「最近のAIアシスタントの一部には、確認画面で『今後は聞かずにやってよい』を選んだり、あとからやったことの履歴を見たりできるものがあり、Meta の Muse や xAI の Grok Bot の公式資料に書かれています（Claude Duet の公式資料には、この選択肢の記載がありません）。」
2. 「Anthropic の調べでは、コード作業の AI を使い続けた人ほど毎回の承認をやめて任せる割合が増え（約20%から40%超）、同時に途中で口を出す回数も増えました。ただしこれは『何をしたか』の観察で、任せたあとに事故が増えたか減ったかは測っていません。」
3. 「模擬の実験（2026年8月、査読前、113人）では、自分で決めたルールで任せた人は、毎回確認した人より、依頼の範囲を超えた操作を止められなかったので、任せ方は『いったん任せて後で見る』だけでなく、任せる操作を限り、履歴を実際に見ることが必要になりそうです（これは私たちの推測であって、研究の結論ではありません）。」
- 3文目の最後の括弧は、資料の結論ではなく推測と分かるよう台本でも区別すること。足りない点: 事後ログ確認の効果の測定、実際の利用者での事故率、Dots の原文、Muse／Grok Bot の許可の取り消し方、Duet に関する追加資料（発表は詳細を後日公開としている）。

## 未確認一覧
- OpenAI Dots の原文すべて（403）。
- Lee & See 2004、Bainbridge 1983、Sheridan 1992 の本文（二次要約のみ）。Sheridan の「management by exception」の出典は不明。適応的自動化の一次資料は未取得。
- Yan 2026 の全文（要旨とメタデータのみ。査読前）。Green 2022 の根拠研究の個別。
- Anthropic 2件の発表時点以降の更新、「93%」の母数・期間。
- Muse の「学習」の具体、許可の取り消し方、ヘルプの公開日。Grok Bot の日本提供可否。
