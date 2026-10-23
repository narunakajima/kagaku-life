# kl048 一次資料調査: 常時稼働型AIエージェント4種（調査日 2026-10-23）

## 取得上の注意（必ず読む）
- 本文の「原文」は WebFetch（小型モデルによる要約付き取得）が返した引用。原文そのままとは限らない。**台本に引用符つきで使う前に、ブラウザで該当ページを開いて原文を目視確認すること。**
- **OpenAI の公式ページ（openai.com/index/introducing-dots、help.openai.com の全記事）は WebFetch・curl とも HTTP 403 で本文を開けなかった。** OpenAI の項は「検索結果の要約」と「deploymentsafety.openai.com（取得できた）」に基づく。help.openai.com の記述は**原文未確認**として扱う。
- 「資料に書いていない」は「このページに書いていない」の意味。他のページ（未取得のセキュリティページ等）にある可能性は残る。
- 報道・比較ブログは使っていない（手がかりの検索にだけ使用）。

---

## 1. Anthropic Claude Duet（研究プレビュー）

資料:
- A1 公式発表 "Introducing Claude Duet" https://claude.com/resources/articles/claude-duet （公式ブログ相当、2026-10-21）
- A2 ヘルプ "Get started with Claude Duet" https://support.claude.com/en/articles/17631495-get-started-with-claude-duet （ヘルプ、公開日の記載なし。「Updated yesterday」表示）
- A3 製品ページ https://claude.com/product/claude-duet

| 項目 | 内容 | 出典・原文 |
|---|---|---|
| (a) 自動で行う範囲 | 読む・下書き・準備は自動。毎朝、接続アプリの要点を短く送る。数時間ごとに接続アカウントを確認。短い依頼からアプリと手順を判断してバックグラウンドで進める。日中の更新、返事のない件の追いかけもする | A1 "reads, drafts, and prepares work on its own" / "Each morning, it sends you a short brief on the most important items across your connected apps." / 確認間隔 "every few hours" / "it works out which apps to use and what steps to take in the background"。A2 に日中更新・追いかけ（要約） |
| (b) 承認を求める操作 | 送信、支払い、署名、削除。購入は毎回（Link/Shop Pay。Link は上限額の承認まで決済しない）。**承認があってもやらない操作**: 証券売買、口座間の資金移動、他人のアカウントへのアクセス。接続は必ず本人が開始 | A1 "before it sends a message, makes a payment, signs a document, or deletes anything"、"A few things are off-limits even with your approval." A2 "designed to ask before each purchase"、"You start every connection yourself."、off-limits の例示。A1 は「他の全操作に承認が及ぶか」は書いていない |
| (c) 誤動作・攻撃対策 | プロンプトインジェクション対策はブラウザ利用の研究由来。敵対的テスト、外部ペンテスト、公開バグ報奨金（検索結果の要約。A1 本文の該当行は要再確認）。認証情報はモデルが直接見ない。機密情報の分類器（最上位の機密は共有を拒否、その他は本人が明示したときだけ通す）。**「no defense is perfect」と明記**。読んだ内容は命令でなく情報として扱う設計 | A1 "defenses against hidden instructions and prompt injection come from our browser-use research" / "so it never directly sees your passwords or sign-in tokens" / "designed to reject requests to share the strictest tier of information"。A2 "that content can contain instructions meant to mislead it"、"no defense is perfect"、"When a site asks for a password, you type it into a separate form on your device."。A1 は具体的な攻撃成功率や詳細設計を「in the coming days」公開としている |
| (d) 責任・補償・ログ・取り消し | **責任配分・補償: 記載なし。取り消し: 記載なし。ログ: 専用の活動ログの記述なし**（Tasks タブで進行中の作業は見える、製品ページに「何をしたか／しているかを見て舵取りできる」）。アプリの接続解除はいつでも可。接続解除しても過去の情報の記憶は残る | A3 "You can see what Claude Duet has done and is doing for you, and steer it."。A2 "you can disconnect any app at any time"。学習利用・保持期間: 記載なし |
| (e) 提供地域・プラン・開始日 | **米国のみ**、Pro / Max のみ、待機リスト制の研究プレビュー。Team / Enterprise は対象外。iOS・Android アプリと claude.ai。追加料金の記載なし、背景確認も利用上限に含まれる。**日本では使えない（米国限定と明記）** | A1 "We're starting today with Pro and Max users in the US." / "Claude Duet is included in Pro and Max plans." A3 "Team and Enterprise plans are not included yet." 開始日 2026-10-21 |

製品ページ A3 は「Prompt injection」への言及なし。ただし A1・A2 に記述あり。既知の限界: A1/A3 "may misread a thread or miscalibrate what's urgent"。

---

## 2. Meta Muse

資料:
- M1 公式発表 https://about.fb.com/news/2026/09/introducing-muse/ （2026-09-08公開、2026-09-30更新表示。更新内容は不明）
- M2 日本発表 https://about.fb.com/ja/news/2026/10/muse-personal-ai-agent-launches-in-japan/ （2026-10-23）
- M3 ヘルプ「Muse のガイダンスと承認」 https://www.meta.com/help/artificial-intelligence/1385290430137537/ （「更新:6週間前」、絶対日付なし）
- M4 ヘルプ「Muse のウェブ閲覧」 https://www.meta.com/help/artificial-intelligence/2124746764949121/
- M5 補足利用規約 https://muse.ai/terms （最終更新 2026-09-08）

| 項目 | 内容 | 出典・原文 |
|---|---|---|
| (a) 自動で行う範囲 | アプリを閉じても作業を続け、変化や承認が要るときに戻る。目標を与えると計画を立てて自分で進める。覚えた内容から頼まれなくても提案する。メールは「読むだけ」か「送信も」かを本人が選ぶ。自動の範囲の一覧は M3 に明記なし（「どの判断に承認が要るか学習していく」） | M1 "Muse keeps working after people close the app"、"For things like email, people choose what Muse can do, whether it reads their mail or can also send on their behalf."。M3「Museは、どのような決定に承認が必要かを学習していきます。」 |
| (b) 承認を求める操作 | 送信（メール等）と購入。設定「一部の操作で確認」では**すべての書き込み操作と重要な読み取り操作の前に許可を求める**。ブラウザの購入など重要操作の前は確認する設計。ウェブアクセスの既定の承認要件は設定で変更可 | M1 "Muse checks with the person before sensitive actions like sending an email or making a purchase."。M3「Museはすべての書き込みアクションと重要な読み取りアクションの前にアクセス許可を要求します。」。M4「購入などの重要なアクションをブラウザーで実行する前に、利用者に確認を求めるよう設計されています。」 |
| (c) 誤動作・攻撃対策 | 別エージェント「Sentinel」が同じマシン上でシステムレベルで隔離され、**Sentinel が承認しない限り Muse の通信はインターネットに出ない**（必要なら本人に確認）。専用VM。パスワード・支払い方法は Muse（モデル）から見えない。認証情報は専用ストア。**プロンプトインジェクションへの言及: M1・M3・M4 にいずれも記載なし**。テスト・レッドチームの記載もなし。Muse の出力は不正確の可能性あり（規約） | M1 "A separate Sentinel agent runs on that same machine, kept apart from Muse at the system level." / "Nothing Muse does reaches the internet unless the Sentinel approves it."。M2「Museは、利用者のパスワードや支払い方法を確認できず」。M4「認証情報はセキュアな認証情報ストアに保存されます。」 |
| (d) 責任・補償・ログ・取り消し | **ログ: あり**（活動ログ=実行した操作と付与した許可の時系列、M1 は "complete audit trail of everything it has done and plans to do"）。**取り消し: 一部のみ**（ページ読み込みや購入前の価格比較などはチャットで取り消し・停止の指示可。メール送信などは取り消せないと明記）。**責任: 利用者**（承認する責任、第三者や受信者との間のエラーを直す責任も利用者）。規約は指示について利用者が単独で責任を負うとする。補償の記載は見つからず（未確認）。Meta は操作記録にアクセス・保持することがある | M3「メールを送信するなどのアクションは、自分が実行する場合と同様に、元に戻すことはできません。」「Museはあなたに代わって行動するため、Museのアクションを注意深く導き、承認する責任はあなたにあります。」「サードパーティのサービスや受信者との間で発生したエラーを含め、エラーの修正は利用者の責任です。」。M5 第7条4項「利用者は、Museに提供する指示、目標およびガイダンスについて単独で責任を負います。」、第10条「Museが実行したアクションの記録にアクセスし、それを保持することがあります。」、第11条「利用者は、精度を独自に確認せずにアクションまたは出力に依拠すべきではありません。」 |
| データの扱い | AI学習への利用はオプトアウト可。会話とVM内データを Meta の広告システムに共有しない | M1 "People can also opt out of their interactions being used to train Meta's AI models."、"Muse doesn't share a person's conversations or the data in their VM with Meta's ad systems." |
| (e) 提供地域・プラン・開始日 | 2026-09-08 米国で開始（iOS/Android/muse.ai）。**2026-10-23 に日本でも提供開始**（米国・カナダ以外では初）。基本機能は無料、多用向けに有料プラン。M1 に金額の記載なし。日本の連携先: Gmail、Googleカレンダー、Instagram、メルカリ、マネーフォワード ME、チケットぴあ ほか。新機能（音声・アバター等）の日本提供は別途案内 | M2「Museは日本において本日より iOS、Android、および muse.ai で提供を開始します。」「多くの基本的な機能は無料で利用でき、さらに活用したい方向けにはサブスクリプションプランもご用意しています。」。M2 に対応言語の記載なし。金額は報道のみ（未確認） |

---

## 3. OpenAI Dots

資料:
- O1 発表 https://openai.com/index/introducing-dots/ （2026-09-29。**403で本文未取得**）
- O2 ヘルプ https://help.openai.com/en/articles/20001530-getting-started-with-your-dot 、https://help.openai.com/en/articles/20001529-dots-privacy-security-and-safety-faqs 、https://help.openai.com/en/articles/20001554-manage-dots-in-chatgpt-workspaces （**403で本文未取得**。検索結果の要約のみ）
- O3 システムカード https://deploymentsafety.openai.com/gpt-6-astra （取得可。dots 付録の追加は変更履歴で 2026-09-29）

| 項目 | 内容 | 出典・原文 |
|---|---|---|
| (a) 自動で行う範囲 | 会話の合間も作業を進める常時稼働エージェント。専用のクラウドPC。アイドル時は接続アプリを使った**読み取り専用**のバックグラウンド調査（検索要約の記述。原文未確認） | O3 変更履歴 "remarkably capable, always-on agents built to handle everything"（取得済み）。他は O1/O2 の検索要約のみ・**原文未確認** |
| (b) 承認を求める操作 | 検索要約によれば3層: ①パスワード変更・送金など最も機微な操作は**本人が引き継いで自分で行う**、②データの永久削除・ソフトのインストール等は**都度承認の場合がある**、③「カスタムルール」で許可/要承認/禁止を設定可（コアの安全要件は外せない）。Enterprise は管理者が許可（既定オフ） | O2（help.openai.com）の検索要約。**原文未確認**。システムカードにも確認方針の言及あり（下記） |
| (c) 誤動作・攻撃対策 | システムカードに dots 専用の付録あり。項目名のみ確認: プロンプトインジェクションの自動／手動レッドチーム、制限の遵守、永続的・先回り型ワークフローでの整合性（範囲や権限の変化、連鎖タスクでの境界維持、誤解を招く先回り入力への頑健性）、auto-review の評価、リアルタイムの安全監視。**dots 付録の本文は取得できず、数値は確認できていない**。Astra 全体の数値（dots 専用ではない）: 間接プロンプトインジェクション頑健性 96.23%→99.79%、Gray Swan IPI での攻撃成功率推定 8.5%（GPT-5.6 Sol は 27.0%）、確認ポリシー付きでの不整合な結果率 3.4%→3.0% | O3 "We train Astra to be careful when performing consequential actions."（Astra 全般）。検索要約によれば dots 付録は「新着メール等に触れる機会が多いため追加のレッドチームを行った」「疑わしい依頼を検出して保留し、通知または入力を求めた」「確認ポリシーを更新して再テストした」（**本文未確認**） |
| (d) 責任・補償・ログ・取り消し | 検索要約: デスクトップの Activity View で進行中のタスクを見られる、追加情報・修正・方向転換・停止の依頼ができる、いつでも一時停止できる。責任配分・補償・取り消し: **確認できず**。Memory を切っても既に渡った情報は消えない（要約） | O2 検索要約のみ・**原文未確認** |
| (e) 提供地域・プラン・開始日 | 2026-09-29 発表。Pro と Business Premium の18歳以上、対応市場。**Pro は EEA・スイス・英国を除外**（要約）。最初の1体は料金に含む。Enterprise は管理者が有効化するベータ（既定オフ）。**日本が対応市場かは確認できていない** | O1/O2 検索要約・**原文未確認**。日本の可否は資料に出てこなかった |

---

## 4. xAI Grok Bot

資料:
- X1 発表 https://x.ai/news/introducing-grok-bot （2026-08-11、ベータ）
- X2 プラン拡大 https://x.ai/news/grok-bot-more-plans （2026-08-26）
- X3 ドキュメント概要 https://docs.x.ai/grok-bot/overview 、モバイル https://docs.x.ai/grok-bot/mobile 、チーム/企業 https://docs.x.ai/grok-bot/teams-and-enterprises 、セキュリティ https://docs.x.ai/grok-bot/security （日付の記載なし）

| 項目 | 内容 | 出典・原文 |
|---|---|---|
| (a) 自動で行う範囲 | 専用クラウドPC（ブラウザ・ファイル・ターミナル）で、ユーザー不在でも複数手順の仕事を進める。コネクタがあれば使い、無ければコンピュータ操作。**1つのアカウントの全 Bot が1台のPCを共有**。ログイン・2要素認証・支払いの手順は本人に渡す | X1 "Bots share a computer of their own in the cloud, so jobs do not stall when you step away." X3 "They use connectors where available and computer use for everything else." / "The computer belongs to your account, not to an individual Bot." / 企業ページ "It hands login, two-factor authentication, and payment steps to the member." |
| (b) 承認を求める操作 | 「承認が要るときだけ戻る」。メッセージは下書きを承認してから送信（編集して Send / Discard）。機微な操作は**別の審査モデル Auto Review**を通る。ローカル実行は既定でコマンドごとの承認。ルールが衝突したら「Ask first」が優先。承認の効力は提案された操作のみ（完了済みの作業には及ばない）。**承認が必須な操作の一覧は未確認**（ページが列挙していない） | X1 "only come back when something needs your approval"。X3 "drafts you approve before they are sent."、企業ページ "Sensitive actions require user approval"、"Ask first wins when rules conflict."、セキュリティ "An approval controls the proposed action, not work already completed." |
| (c) 誤動作・攻撃対策 | Auto Review は「危険な Bot の操作を実行前に評価する独立した審査モデル」で、明示的な境界の代わりではなく補完。**プロンプトインジェクション: 「リスクを減らすが無くさない（reduce, but do not eliminate）ので、影響の大きい操作は承認の後ろに置く」と明記**。コネクタのトークンはPCに保存しない。サイトが自動化を拒否したら回避せず本人に渡す。数値・テスト結果の記載は確認できず | セキュリティ "an independent review model that evaluates risky Bot actions before they run"、"reduce, but do not eliminate, risk from malicious content"、"Connector tokens are never stored on the computer."。X3 "The Bot hands those steps to you rather than working around them." |
| (d) 責任・補償・ログ・取り消し | ログ: 管理者向けの監査ログと、操作記録は**別系統**（"Audit Logs and Action Recording use separate pipelines"）。取り消し: **専用の取り消し機能の記載なし**（リセットで未同期の作業が失われうる、という注意はある）。責任配分・補償: **記載なし**。Bot は持ち主以上の権限を持たない。Privacy Mode 有効時は顧客データを学習に使わない（企業）。契約終了後30日以内にデータ削除または返却（DPA） | セキュリティ "A Bot can never hold more access than the person it belongs to."、"recent unsynced work can be lost."。企業ページ "With Privacy Mode enabled, customer data is not used for training"。セキュリティ "deleted or returned within 30 days of written direction after the service ends." |
| (e) 提供地域・プラン・開始日 | 2026-08-11 ベータ開始（デスクトップ・iOS）。2026-08-26 に SuperGrok／SuperGrok Plus／Heavy、Cursor Pro／Pro+／Ultra、Cursor Teams が対象に。Bot の利用枠は各プランとは別。企業は待機リスト。**地域・日本の可否: 記載なし**（X 上での @bot 呼び出しは「全地域では未提供」） | X1 "Grok Bot is in beta and available today for SuperGrok, SuperGrok Plus, and SuperGrok Heavy."。X2 "Grok Bot is now included with all SuperGrok, Cursor Pro, and Cursor Teams plans."、"Grok Bot comes with its own usage, separate from your Grok and Cursor plans." X3 "is not available in every region yet."（@bot 機能について） |

---

## 資料に基づく共通点
1. **4社とも「相手に出す・お金を動かす」操作は人の承認を前に置く**設計を掲げる（Duet: 送信・支払い・署名・削除、Muse: 送信・購入、Grok: 機微な操作・下書き送信、Dots: 検索要約では機微度の3層）。
2. **パスワードなどの認証情報をモデルに直接見せない**（Duet、Muse、Grok は本人に渡す）。
3. **専用のクラウドPC／VMで動き、裏で働き続ける**（4社）。
4. 承認の外側に**第二の安全装置**を置く: Duet=承認のほかに機微情報の分類器、Muse=Sentinel、Grok=Auto Review、Dots=リアルタイム監視（システムカードの項目名）。
5. 限界を認める記述: Duet「no defense is perfect」、Grok「reduce, but do not eliminate」、Muse は出力が不正確になりうると規約に記載。

## 違い
- **責任の書き方**: Muse だけが「承認する責任・エラーを直す責任は利用者」「メール送信は取り消せない」と明記（M3、M5）。Duet と Grok は責任配分を書いていない。
- **ログ・取り消し**: Muse は活動ログと「一部の操作の取り消し」を明記。Grok はログが管理者向け中心で取り消し機能の記載なし。Duet は専用ログの記載なし。
- **機微な操作の扱い**: Duet は承認があっても禁止する操作（証券売買・資金移動）を明示。Dots は本人が引き継ぐ操作を設ける（要約）。Muse・Grok に同種の「承認しても不可」の明記は取得範囲では確認できず。
- **インジェクションへの言及**: Duet と Grok は明記。Muse は取得した3ページに記載なし。Dots はシステムカードに専用付録があるが本文未取得。
- **日本で使えるか（2026-10-23時点）**: Muse=**使える（本日開始）**、Duet=**使えない（米国限定）**、Dots=**不明**（Pro は EEA・スイス・英国を除外、日本は資料から確認できず）、Grok Bot=**不明**（地域の記載なし）。

## 確認できなかった点
- OpenAI の公式発表とヘルプの原文（403）。承認の3層、Activity View、停止、地域は検索要約のみ。dots 付録の本文と数値。
- Dots の日本での提供可否。Grok Bot の提供地域。
- Duet の「活動ログ」「取り消し」「責任」「学習への利用」「保持期間」。Duet の詳細な安全設計の公開（A1 は「coming days」としている）。
- Muse のプロンプトインジェクション対策、第三者テスト、補償の有無。M1 の 9/30 更新内容。M3 の公開日。Muse の月額（報道では$20/$100だが公式未確認）。
- Grok Bot の承認必須操作の一覧、Auto Review の精度、責任・補償、個人向けの学習利用の扱い（企業向け Privacy Mode のみ確認）。
- 表の「原文」は小型モデル経由の引用。引用符つきで使う前に原ページの目視確認が必要。

## 判断: 公式資料だけで、4サービスの承認設計を並べて語れるか
- **Duet・Muse・Grok Bot の3つは、公式資料で並べて語れる**（承認の対象、第二の安全装置、限界の認め方、提供状況まで原文付きで拾えた）。ただし「責任配分」を並べられるのは Muse だけで、他は「書いていない」と言うことになる。
- **Dots は現状では並べて語れない。** 公式本文を読めておらず、help.openai.com の内容は検索要約止まり。ブラウザで O1・O2 とシステムカードの dots 付録を開いて原文を取れば、並べられる見込み。取れない場合は「3層の承認」の主張を台本に使わない。
- 日本の視聴者向けの切り口としては、**Muse が今日から日本で使える唯一のサービス**（確認できた範囲）で、利用者責任と取り消せない操作が明記されている点が、公式資料から言える最も具体的な材料。
