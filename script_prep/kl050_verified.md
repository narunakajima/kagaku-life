# kl050 原文で確認済みの一次資料（2026-10-27、メインがHTMLを直接取得して文字列を確認）

お題: iOS 27.2 で日本語の Siri AI が使えるようになった（2026-10-26 配信、日本時間 10/27）。
「バックボーンは Gemini と聞く」「Apple 純正アプリは触れるが Google アプリは触れない」「賢さは Gemini の一世代前の印象」を、資料と使った人の声で確かめる。
台詞・資料カードの「原文」は、このファイルの英文・日本語をそのまま使う。ここに無い数字は、台本に使う前に原典で確かめる。
（WebFetch の要約は引用に使っていない。curl で取得した HTML のテキストから抜き出した。）

## R0 iOS 27.2 の更新内容（Apple サポート、10/26）
https://support.apple.com/en-us/149076
- 「This update provides enhancements to Siri AI with the ability to retain useful context from previous Siri interactions as well as draw from a wider range of personal context.」
- 「Siri AI (All iPhone 16 models and later, iPhone 15 Pro, iPhone 15 Pro Max)」
- 「Siri AI can recall your past conversations, so you can ask Siri about something it told you before, like the restaurants it recommended last week」
- 「Siri AI can draw from more sources to give you a great answer, including photos attached in Messages, Calendar event attendees, your voicemails, and better results from Safari history and Reading List」
- 「Excluded Apps lets you choose which apps Siri, Search, and suggestions can access, all from one setting」
- 「Siri AI is available in more languages, with support for French, Japanese, Korean, Portuguese, and Spanish. Siri AI is not available in the EU or mainland China」
- このページに「beta」の語は無い。ベータ扱いは R1 の発表文で確認。

## R1 Siri AI 発表（Apple Newsroom、2026-09-14）
https://www.apple.com/newsroom/2026/09/siri-ai-a-profoundly-more-capable-and-personal-assistant-is-here/
- 「Siri AI begins rolling out today in beta in English, and will expand to French, Japanese, Korean, Portuguese, and Spanish next month.」
- 「These new capabilities are powered by the next generation of Apple Foundation Models, custom-built in collaboration with Google and its Gemini models for deeply integrated Apple Intelligence experiences. These latest models run on device and on servers using Private Cloud Compute.」
  → Apple の言い方は「Google と Gemini モデルとの協業で作った（custom-built in collaboration with）」。「Gemini そのもの」とも「Gemini は入っていない」とも書いていない。
- 「Siri AI already works seamlessly with apps from Apple's vast ecosystem of developers. Users can continue to take action in the apps they already use with Siri, like texting a friend in WhatsApp or playing a book on Audible. And soon, users will be able to ask Siri AI to draft an email in Microsoft Outlook, search for a homework assignment in Notability, or add a restaurant recommendation to Tripsy.」
  → 発表が名指しした他社アプリは WhatsApp・Audible（今）、Outlook・Notability・Tripsy（近日）。Google のアプリの名前は無い。日本語版の対応アプリの一覧はこの資料に無い。
- 「Certain Apple Intelligence features that rely on server-side models are subject to daily usage limits, including but not limited to Siri AI, intelligent photo editing tools, Image Playground, and AFM 3 Cloud models in Shortcuts. Daily limits may vary by feature, request complexity, system demand, system policies, and other factors. Expanded access to such features will be available for a fee in the future.」
- 「Siri AI will not be available initially in the EU on iOS, iPadOS, and watchOS.」「Siri AI and the other new Apple Intelligence features will not be available in China while Apple works through regulatory requirements.」

## R2 利用上限のサポートページ（Apple サポート、公開日 2026-09-09）
https://support.apple.com/en-us/127901
- 「In the future, Apple will implement usage limits on these and other Apple Intelligence and Siri AI features to ensure a high-quality, reliable experience for everyone. If you reach a limit in a particular feature, that feature will become available again after a time out period. Limits may vary by feature, request complexity, system demand, system policies, and other factors. Increased access to such features will be available for a fee.」
- 対象に「Siri AI」。回数・料金は書かれていない。
- ⚠ R1（9/14）は「subject to daily usage limits」（今ある）、R2（9/9）は「In the future … will implement」（これから）と、時制が違う。台詞では「上限がある／これから厳しくなるかもしれない」と断定せず、「Apple の資料は、1日の上限があること、回数は公表していないこと、枠を増やすのは有料になることを書いている」までを言う。

## R3 第3世代 Apple Foundation Models（Apple Machine Learning Research、2026-06-08、2026-09-09 更新）
https://machinelearning.apple.com/research/introducing-third-generation-of-apple-foundation-models
- 「At the heart of this architecture is our third generation of Apple Foundation Models (AFM), a family of five foundation models custom-built in collaboration with Google.」
- 「For AFM 3 Cloud Pro, we worked with Google and NVIDIA to extend Private Cloud Compute to NVIDIA GPUs in Google Cloud」
- 評価は「in-house human graders」（Apple 社内の人間の採点）。比べた相手は**自社の前の世代**だけ:
  - 「the updated AFM 3 Core model improved upon its predecessor, earning preference on 45.6 percent of prompts compared to 23.3 percent for the 2025 baseline」
  - 「(AFM 3 Cloud) was preferred on 64.7 percent of prompts compared to only 8.7 percent for the 2025 AFM Server model」
  - 「AFM 3 Cloud Pro … a relative improvement in overall response satisfaction of roughly 10 percent for text」（AFM 3 Cloud に対して）
- 「These evaluations reflect our models at their current stage of development. During the beta period, we'll continue improving them」
- 「We look forward to sharing more details on our latest foundation models, including updated evaluations and benchmarks, in a technical report later this summer.」（2026-10-27 時点で、技術レポートは確認できた範囲では見つかっていない。「見つけられなかった」までしか言えない）
- Gemini・他社モデルとの性能比較は、このページに無い（「Gemini」の語は本文に無く、「Google」だけ）。
- 日本語は評価対象の言語グループ（PFIGSCJK）に含まれるが、日本語だけの数字は無い。

## 使った人の声（報道。台詞では「匿名の傾向」としてだけ使い、媒体名・筆者名は言わない。数字や断定を一次資料のように扱わない）
- ITmedia Mobile（石野純也、2026-10-24、リリース候補版）1〜3ページ: 同名の候補が約9人いても意図した人に送れた／家族関係から「子ども」に送れた／チラシをカメラで読んで30件超の予定を一括でカレンダーに追加／賃貸の画面を読んで返信の下書き。課題: 応答速度、読み上げの読み違い・アクセント、対応アプリが限られる（開発者が Spotlight と App Intents に対応したアプリだけ検索できる）、Messenger は確認できない、Gmail は「読めたが、仕事のメールは検索できず、メールの作成もできなかった」（筆者の iPhone Air）、何が見えて何が見えないか分かりにくい。結論は「有望だがまだ十分に実用的ではない」。
- Gizmodo Japan（2026-10-27）: 「わりと使えますよ」。LINE・Messenger は検索できなかった。応答は硬い。同姓同名の連絡先を正しく特定できた。
- dig-it（先行レビュー、27.2 開発者ベータ）: 第一印象は「期待したほどの進化は感じない」、応答まで少し間がある、話し方は ChatGPT と比べてぎこちない。一方で、現在地と予定から乗換案内を出して予定に登録、近くの店の営業時間、メールの検索と要約はできた。日本語の認識精度は大きく向上した。LINE は探せない（対応検討中と報じられている）。
- note（AI×note=まさき、2026-10-26）: LINE は読めない。応答が硬い。
- Android Authority（英語、iOS 27 開発者ベータの英語版を48時間試した記事）: 個人データの検索は Siri AI の勝ち（Gemini は該当のメッセージやメールを見つけられなかった）、画像生成・複数端末での連携は Gemini の勝ち、画面の理解は互角。
- 「Gemini の一世代前の印象」という声: 制作者（なるさん）の使用感。報道の中に、Gemini と同じ土俵で測った数字は見つかっていない（R3 の評価は自社の前世代との比較のみ。第三者の順位表にも載っていないと報じられている）。

## 言ってよいこと・言ってはいけないこと
- 言ってよい: Apple は「Google と Gemini モデルとの協業で作った」と書いている（R1）。Apple 自身の資料には、Gemini と比べた数字が無い（R3）。日本語版は iOS 27.2 で使えるが、Apple はベータ扱いにしている（R1）。1日の上限があると書いているが、回数は非公表で、枠を増やすのは有料（R1・R2）。更新内容に「過去の会話を覚える」「メッセージの写真・カレンダーの参加者・留守番電話・Safari の履歴を材料にできる」「読ませたくないアプリを除外できる」（R0）。
- 言ってはいけない: 「Siri の中身は Gemini」と断定する／「Gemini は入っていない」と断定する（どちらも資料に無い。報道で割れている）。「Gemini の一世代前の賢さ」と断定する（比べた数字が無い）。報道だけにある数字（参照アプリ数、30件以上の対応アプリ、300,000アプリなど）。Google のアプリが「対応していない」と断定する（Apple の資料に無い。「発表が名指しした他社アプリに Google のものは無い」「使った人の報告では、Gmail は一部読めるが限られる」と言う）。Siri AI の Extensions（Claude や Gemini を Siri に差し込む仕組み）は資料で確認できていない。話に出すなら「確認できていない」と言う。
- 日本語版の対応アプリの一覧は Apple の資料で確認できていない。
