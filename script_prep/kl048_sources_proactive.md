# kl048 資料調査: 先に提案・介入するAI/支援システムの研究

調査日: 2026-10-23。担当範囲は「プロアクティブAIの利用者実験」「混合主導の古典」「先に提案されたときの人の反応」。
記載ルール: 数字は資料の記載のまま。推測は「(推測)」と明記。開けなかった・本文を確認できなかった箇所は「未確認」。
報道・ブログは使っていない（検索結果のまとめサイトは手がかりのみ、根拠にしていない）。

## 0. 一覧表

| # | 資料 | 年 | 掲載先 | 被験者 | 期間 | 確認範囲 |
|---|---|---|---|---|---|---|
| 1 | Chen ほか "Need Help? Designing Proactive AI Assistants for Programming" | 2025 | CHI '25（査読済み、arXiv v2も） | 65人（学生） | 各条件20分 | arXiv HTML（本文の先頭10万字） |
| 2 | Pu ほか "Assistance or Disruption?"（Codellaborator） | 2025 | CHI '25 | 18人（学生） | 1回の実験 | arXiv HTML（本文の先頭10万字＋後半の限界） |
| 3 | Kuo ほか "Developer Interaction Patterns with Proactive AI: A Five-Day Field Study" | 2026 | IUI '26採択（arXivプレプリントを確認） | 15人（プロの開発者） | 5日 | arXiv HTML（先頭10万字） |
| 4 | Liu ほか "Sensing What Surveys Miss" | 2026 | arXivプレプリント（CHI '26関連と記載） | 32人 | 実験室 | arXiv HTML（先頭10万字。限界の節は未確認） |
| 5 | Oh ほか "Foundations of Proactive Agents" (Proactivity-Gym) | 2026 | arXivプレプリント（査読の記載なし） | 30人 | 「模擬された1週間」の資料を読んで評価 | arXiv HTML（先頭10万字） |
| 6 | Cha ほか "Hello There! Is Now a Good Time to Talk?" | 2020 | IMWUT 4(3) | 40人（寮生） | 1週間 | 概要のみ（検索結果の要旨。本文は未確認） |
| 7 | Wei, Dingler, Kostakos "Understanding User Perceptions of Proactive Smart Speakers" | 2021 | IMWUT | 13人 | 3週間（自宅） | 概要のみ（本文は未確認） |
| 8 | He ほか "Plan-Then-Execute" | 2025 | CHI '25 | 248人 | 1回 | arXiv HTML（先頭10万字）。頼まれたことをAIが実行する研究で、「先回り」ではない。主体性・信頼の参考として |
| 9 | Horvitz "Principles of Mixed-Initiative User Interfaces" | 1999 | CHI '99 | 実験なし（設計論文） | - | 原文PDFから本文を直接読んだ |
| 10 | Mark, Gudith, Klocke "The Cost of Interrupted Work: More Speed and Stress" | 2008 | CHI 2008 | 約48人（自由度から逆算。推測） | 20分程度 | 原文PDFを直接読んだ |
| 11 | Adamczyk & Bailey "If not now, when?" | 2004 | CHI 2004 | 未確認 | 未確認 | 要旨のみ（本文のURLに接続できず） |
| 12 | Lu ほか "Proactive Agent" (ProactiveBench) | 2024 | arXiv（ACL 2025かは未確認） | 利用者実験ではなくベンチマーク | - | 検索結果の要旨のみ。本調査では使わない |

---

## 1. LLMベースの先回り支援: 利用者実験

### 1-1. Chen ほか 2025（CHI '25）— 先回りコード提案、65人
- URL: https://arxiv.org/abs/2410.04596 （HTML: https://arxiv.org/html/2410.04596v2）
- 著者所属: Valerie Chen, Alan Zhu, Ameet Talwalkar（カーネギーメロン大）、Sebastian Zhao（UCバークレー）、Hussein Mozannar（Microsoft Research）、David Sontag（MIT）
- 公開: 2025年（arXiv v2は2025-02-28）。掲載: CHI '25（横浜）
- 被験者・条件: プログラミング経験のある学生65人。先回りの3変種（Suggest and Preview／Suggest／Persistent Suggest）のどれかに割り当て、それぞれが「頼んだときだけ答えるチャット」と比べられた（各条件20分）。Persistent Suggestは待ち時間が5秒（他は20秒）、提案5個（他は3個）、誘導プロンプトなし
- 主要な数字:
  - テストを通した割合が基準より増えた: Suggest and Preview +12.1%（±5.1）、Suggest +18%（±5.8）、Persistent Suggest +11.6%（±5.0）。p値はそれぞれ0.01、0.002、0.02
  - 先回り版を基準より好んだ割合: 80%、90%、47%（Persistent Suggestは約半数）
  - Persistent Suggestでは提案を開いた回数は多い（9.5対6.4回/課題）が、コピーした回数は少ない（2.1対3.1）
  - 記録された75件の操作のうち受け入れ69、却下6（この75件が全操作か一部かは未確認）
  - 数値の邪魔さ評価は報告なし。Persistent Suggestの参加者は「distracting」「annoying」と述べた
- 原文（短く）: "when the suggestions are provided too often, participants are less likely to make use of the suggestions." / "participants are likely to accept more “actionable” suggestions, rather than ones that may be merely informative." / "the non-proactive chat assistant was best because it didn't interrupt what I was doing."
- 著者の限界: 課題は与えられたもので自発的でない、テスト通過率が生産性の指標として適切か不明、参加者は学生のみ、ウェブエディタで企業向けIDEほど機能がない、チャット型だけの比較、提案の正しさへの言及が参加者から出なかった。相互作用の分析は探索的でt検定では条件間の有意差なし
- 食い違い/注意: 「先回りが成績を上げる」と「頻度が高いと使われず半数しか好まない」が同じ論文に同居。本文の後半2.9万字は未確認

### 1-2. Pu ほか 2025（CHI '25）— Codellaborator、18人
- URL: https://arxiv.org/abs/2502.18658 （DOI 10.1145/3706598.3713357）
- 著者所属: Kevin Pu・Daniel Lazaro・Tovi Grossman（トロント大）、Ian Arawjo（モントリオール大）、Haijun Xia（UCサンディエゴ）、Ziang Xiao（ジョンズ・ホプキンス大）、Yan Chen（バージニア工科大）
- 公開: 2025、CHI '25
- 被験者・条件: 上級のCS学生18人、被験者内。PromptOnly（頼んだときだけ）／CodeGhost（先回り、AIの存在表示なし）／Codellaborator（先回り、AIの存在表示と別スレッド付き）。Python課題3つ、54回、1,004回のやり取り
- 主要な数字:
  - 先回り介入398件のうち、有効に使われた212件（53.3%）、邪魔になった48件（12.1%）、無視された138件（34.7%）
  - 「邪魔された」感（1〜7）: CodeGhost 4.61／Codellaborator 3.78／PromptOnly 1.56（Friedman χ²=22.1、p<0.001。CodeGhostとCodellaboratorの差は有意でない）
  - AIの動きに気づけた度合い（1〜7）: PromptOnly 6.56／Codellaborator 5.44／CodeGhost 4.17
  - 「道具か相棒か」: PromptOnlyは道具寄り5.67、先回り2条件は相棒寄り（4.17、3.61）
  - 完成時間（平均16分46秒）は条件で差なし。54回中50回がテスト全通過
- 原文（参加者の発言）: "the more proactivity there was, the less ownership I felt"（P7）／"just feeling-wise, that is not my code."（P15）。著者: "It is essential to put the user in authority of the final design." 目標として "work with AI, not driven by AI"
- 著者の限界: 単一ファイルのPython、セッションは保存されない、課題が小さく低リスク、LLMの出力が一貫せず信頼に影響
- 注意: 「受け入れ率」という指標はなく、近いのは「有効に関与した53.3%」

### 1-3. Kuo ほか 2026（IUI '26）— 実際のIDEで5日、プロ15人
- URL: https://arxiv.org/abs/2601.10253 （DOI 10.1145/3742413.3789148）
- 著者所属: Nadine Kuo（JetBrains、アムステルダム）、Agnia Sergeyuk（JetBrains Research）、Valerie Chen（CMU）、Maliheh Izadi（デルフト工科大）。**製品会社（JetBrains）の研究者が著者**
- 公開: 2026-01（arXiv）。IUI '26（2026-03）採択と記載。データ収集は2025-05-07〜06-03
- 被験者・条件: プロの開発者15人（29人を選抜）、IDEを使う5日間。介入3種（あいまいなプロンプトのとき／AIの編集を却下したとき／コミットしたとき）。介入229件、5,732の操作点
- 主要な数字:
  - コミット後（N=155）: 関与52%（最高）
  - AI編集を却下した直後（N=39）: 関与31%、却下62%（最低）
  - あいまいなプロンプト（N=35）: 関与46%、却下23%、無視31%
  - 先回りで始まった会話の解釈時間 平均45.4秒（N=33）対 頼まれて始まった会話 101.4秒（N=50）（p=0.0016）
  - 使いやすさ(SUS) 72.8/100。提案を信頼できると答えた人27%、受け入れて快適47%、作業が速くなったと答えた人66%
- 原文: "interventions at workflow boundaries (e.g., post-commit) achieved 52% engagement rates"
- 著者の限界: 参加者がJetBrainsの調査パネルで製品に慣れている、役職・経験・言語で層別していない、先回り機能は大きなAI支援の一部で印象に影響しうる、効果は自己申告（コード品質は測れず）、テレメトリと調査を個人で結び付けられない、サンプルが小さく介入の種類ごとの回数に偏り
- 注意: 検索結果のまとめには「提案の却下はタスク切替が理由で不賛成ではないことが多い」とあるが、これは私が原文で確認できていない（未確認）

### 1-4. Liu ほか 2026（CHI '26関連）— 助けが出るタイミングの合わせ方、32人
- URL: https://arxiv.org/abs/2602.00880
- 著者所属: Ailin Liu・Yesmine Karoui・Frauke Kreuter・Francesco Chiossi（ミュンヘン大）、Fiona Draxler（マンハイム大）
- 公開: 2026-02、arXivプレプリント
- 被験者・条件: 32人。一般知識クイズ中に、皮膚電気・マウス動作から「助けが要りそうな時」を推定してLLM(Llama-2-7B)が補足を出す。3条件（本人に合わせた／逆にずらした／ランダム）
- 主要な数字: 補足の受け入れ率 本人に合わせた67.6%／ランダム44.4%／ずらした38.8%（p<0.001）。表示回数は差なし（14.03、11.19、11.50）。正答率 62%／55%／51%（基準41%）。完了時間は差なし
- インタビュー: 27人が「受け入れるかは自分の答えへの自信しだい」と述べた。16人が「助けを期待したときと出たときのずれ」を挙げ、遅れた助けにいら立ち・待ちが生じた。30人が作業を邪魔しなかったと述べた
- 原文: "I declined only when I was really sure about the answer"（P27）
- 限界: 限界の節は未確認。上記の小さい標本・単一大学は私の推測ではなく、著者記載でもない
- 注意: 課題はクイズで、仕事や日常の先回りではない

### 1-5. Oh ほか 2026 — Proactivity-Gym、30人（模擬1週間）
- URL: https://arxiv.org/abs/2609.37267
- 著者所属: Jio Oh・Seunghyun Do・Steven Euijong Whang（KAIST）、Young-Jun Lee・Dongyeop Kang（ミネソタ大）
- 公開: 2026-09-29、arXivプレプリント（査読の記載なし）
- 被験者・条件: 30人（学生と関連分野の社会人）。14のシナリオ（うち4つは「1週間のやり取りの記録」）を読んで、比較・5段階評価。信頼と介入の適切さは模擬の2日目・4日目・7日目に評価。**実際の1週間の使用ではなく、模擬記録を読んだ評価**
- 主要な数字:
  - 作業と競合する形で出た正しい支援の受け入れ 26.7%、対して寝ている間にやって翌朝直す支援 97.8%
  - 10分の確認だけで衝突もないときでも 64.4%が「寝ている間の支援」を選ぶ
  - 介入の仕方が合っているエージェントを選んだ割合 88.3%（中身の質は同じにして）
  - 信頼は「合っている→ずれた」で1.86点下がり、逆（ずれ→合う）では1.27点上がった。「合う→ずれ→合う」では信頼が3.43までしか戻らず、最初の4.43を下回った（最後の介入の評価は4.71）
- 原文: "After one wrong action, an agent has to consistently behave well for a long time to recover trust."（P26）
- 著者の限界: テストベッドの単純化、利用者シミュレータをLLMで生成、実運用ではなくシナリオと記録、長期の実環境評価が必要と述べる
- 注意: **本物の長期実験ではない。** 「信頼が戻りにくい」は模擬記録を読んだ人の評価

## 2. 先回りの音声エージェント（LLM以前）

### 2-1. Cha ほか 2020（IMWUT 4(3)）— 40人、1週間
- URL: https://doi.org/10.1145/3411810 （PDF: https://ic.kaist.ac.kr/files/papers/cha2020hello.pdf は接続不可、未確認）
- 所属: KAIST（概要の記載。著者の個別所属は未確認）
- 内容（検索結果の要旨より）: 寮の学生40人、音声での経験サンプリング装置、1週間、3,572件の現場報告、19の行動カテゴリ。忙しさ・気分・「ながら」の衝突、家での動き・同席者が関係
- 別の論文（Xuan ほか、arXiv 2505.09938）の記述: 元の研究では、勉強・仕事・交流の最中は応答が多いが、休憩や作業の切れ目で割り込みを受け入れやすい、とされる。同論文は「勉強に集中すると決めたら返事しなかった」「ネガティブな状態では話しかけに応じにくい」という発言を引用。**ここは孫引きで、Cha本文では未確認**
- 本文の数字（応答率など）は未確認

### 2-2. Wei, Dingler, Kostakos 2021（IMWUT）— 13人、3週間、自宅
- URL: https://doi.org/10.1145/3494965 （本文は未確認）
- 要旨より: 市販のGoogle Homeを先回りするよう改造、先回りの発話は経験サンプリング。機械学習で「応答するか」を予測した精度は71.6%。退屈と気分が「話しかけてよい状態」と有意に相関
- 同じグループの CHI 2022 "What Could Possibly Go Wrong When Interacting with Proactive Smart Speakers?" は、3週間・13軒の家庭で1,213回のやり取りからエラーを分析（検索結果の要旨のみ、本文は未確認）
- **LLM前の音声スピーカーで、数週間の現場研究としては唯一見つかったもの。ただし13人**

## 3. 古典

### 3-1. Horvitz 1999（CHI '99, pp.159-166）— 混合主導の原則
- URL: https://erichorvitz.com/uiact.htm （PDF: https://www.erichorvitz.com/chi99horvitz.pdf。本文はこのPDFから直接読んだ）
- 所属: Microsoft Research（Decision Theory & Adaptive Systems Group）
- 種類: 設計論文。被験者実験の数字はない（LookOut＝Outlookの予定自動入力の例で原則を説明）
- 問題の整理（原文）: "poor guessing about the goals and needs of users, inadequate consideration of the costs and benefits of automated action, poor timing of action, and inadequate attention to opportunities that allow a user to guide the invocation of automated services and to refine potentially suboptimal results"
- 12の原則（見出し）: (1)価値を足す自動化 (2)利用者の目標の不確かさを考える (3)注意の状態を考えてタイミングを決める (4)コスト・利益・不確かさから最適な行動を推定 (5)対話で重要な不確かさを解く (6)呼び出しと停止を直接・効率的に (7)外した時のコストを最小に (8)不確かさに合わせてサービスの精度を落とす (9)結果を一緒に直す仕組み (10)社会的にふさわしい振る舞い (11)直近のやり取りの記憶 (12)観察して学び続ける
- 原文: (3) "Agents should employ models of the attention of users and consider the costs and benefits of deferring action to a time when action will be less distracting." / (8) "A preference for doing less but doing it correctly under uncertainty can provide users with a valuable advance towards a solution and minimize the need for costly undoing or backtracking."
- 限界: 実験で検証した論文ではなく、原則の提案

### 3-2. Mark, Gudith, Klocke 2008（CHI 2008, pp.107-110）— 中断の代償
- URL: https://www.ics.uci.edu/~gmark/chi08-mark.pdf （本文を直接読んだ）
- 所属: カリフォルニア大アーバイン校（Mark）、ベルリン・フンボルト大（Gudith, Klocke）
- 被験者・条件: メール課題。中断なし／同じ文脈の中断／別の文脈の中断。F(2,92)から約48人（推測）。人数の明記は確認していない
- 結果: 中断された課題のほうが短い時間で終わり、質は同じ。ただしストレス・フラストレーション・時間のプレッシャー・努力の評価が高い（例: ストレス 基準6.92、同じ文脈中断9.46）。中断の文脈は差を生まない
- 原文: "people compensate for interruptions by working faster, but this comes at a price: experiencing more stress, higher frustration, time pressure and effort."
- 著者の限界: "We cannot say whether people would cope over time" — 20分の中断作業のみ
- **これは人間による中断（実験者が質問する）の研究で、AIの提案ではない**

### 3-3. Adamczyk & Bailey 2004（CHI 2004, pp.271-278）
- URL: https://hci.rwth-aachen.de/materials/conferences/CHI2004/1p271.pdf （接続不可）
- 所属: イリノイ大アーバナ・シャンペーン校
- 要旨（検索結果）: 割り込む時点で感情状態と社会的な印象が変わる。被験者数・数字は**未確認**
- 後続のBaileyらの研究について「作業の切れ目で割り込むと再開の遅れと不快が少ない」という検索結果の記述があるが、原文未確認

## 4. 主体性・信頼（先回りに近いもの）

- Pu 2025（上記1-2）: 先回りが多いほど所有感が下がるという参加者の声。数値の主体性尺度はこの要約では確認できていない（本文前半を読んだ範囲では「awareness」「tool vs partner」の尺度のみ）
- Oh 2026（1-5）: 介入のずれが信頼を下げ、戻りにくい（模擬）
- He ほか 2025 "Plan-Then-Execute"（CHI '25、248人、デルフト工科大ほか）: https://arxiv.org/abs/2502.01390 。AIが計画と実行をする日常タスクで、人が計画・実行に関与しても較正された信頼は上がらなかった（H1・H3 不支持）。関与は計画の質を下げることもあった。計画段階の関与は精神的負荷・フラストレーションを増やした。**頼まれた作業の委任であり、先回りではない**
- Liu 2026: 受け入れは自信しだい（27人が言及）

---

## 5. 判断

### (a) 受け入れる条件・嫌がる条件は何本で示されているか
**先回りAIそのものについては約6本**: Chen 2025、Pu 2025、Kuo 2026、Liu 2026、Oh 2026（模擬）、Cha 2020（音声、本文は要旨しか未確認）。Wei 2021（音声）を含めれば7本。ほぼ共通に言えること（方向）:
- 作業の切れ目（コミット後）や休憩では受け入れやすい（Kuo: コミット後52%対 却下直後31%。Cha: 孫引き）
- 頻度が多い・しつこいと使われない／邪魔に感じる（Chen: Persistent Suggestは好み47%）
- 実行できる提案は受け入れられやすく、情報だけの提案は少ない（Chen、原文引用）
- 本人の自信・状態に合わせると受け入れ率が上がる（Liu: 67.6%対38.8〜44.4%）
- 作業と競合するとき受け入れは低い（Oh: 26.7%、模擬）
- 先回りが増えると所有感が下がるという声（Pu、少人数の発言と定性）
**食い違い・弱い点**: Chenは先回りで成績が上がり、Puは完成時間に差なしで「邪魔された」感が上がる。尺度と課題が違い、同じ土俵で比べられない。被験者は学生が中心（Chen、Pu、Liuは学生・大学募集）。プロはKuoの15人のみ。コーディング以外の日常生活の先回り（予定・買い物・健康など）のLLM実験は、今回の検索で見つけられなかった。

### (b) 数週間以上で追った研究はあるか
**LLMの先回りでは見つからなかった。** 最長はKuoの5日（実使用）。Cha 2020は1週間（音声、LLMなし）、Wei 2021は3週間・13人（音声スピーカー、LLMなし）。Oh 2026の「1週間」は模擬記録を読んだ評価で、実使用ではない。Mark 2008は20分。「慣れで嫌がらなくなるのか、信頼が積み上がるのか」を実使用で示した資料は**足りない**。（今回の検索の範囲での話で、「存在しない」とまでは言えない。）

### (c) 一般の人に誠実に3文で説明できるか
できる範囲に限れば可能:
1. 「頼まれる前に動くAI」について、実験で見えているのは、作業の区切りで出れば使われやすく、しつこいと使われなくなる、ということ（主にプログラミング作業の実験、数十人規模、多くは学生）。
2. 先回りが増えるほど、自分でやっている感じが薄れたと語る人もいて、AIが一度ずれると信頼は戻りにくいという評価もある（ただし後者は模擬記録を読んだ30人の評価）。
3. 数週間〜数か月使い続けたらどうなるかを実際の利用で確かめた研究は、今回の調査では見つかっていない。
**言えないこと**: 「先回りAIで人の暮らしがこう変わる」という一般論、日常生活（家庭・健康・仕事全般）への当てはめ、長期の変化。これらを台本で言うなら「根拠が足りない」と言う側に回る必要がある。

### 総合
(a) 条件の方向は複数の研究でおおむねそろっている（ただしコーディング中心・短期・少人数）。(b) 数週間以上のLLM実使用研究は足りない。(c) 3文の説明は、上記の範囲を明示すれば誠実にできる。台本で「先回りAI」を広く論じるなら、上の限定（コーディング中心・最長5日）を台詞で言う必要がある。

## 6. 未確認・次にやるなら
- Cha 2020、Wei 2021・2022 の本文（数字）、Adamczyk & Bailey 2004 の被験者数と数字: 本文を開けなかった
- Chen・Pu・Kuo・Liu・Oh は先頭10万字までの読み取り。後半（議論・付録）の細部は未確認
- 日常生活（予定・メール・音声）の先回りLLMの実験、数週間以上の追跡は、追加検索が必要
- Horvitzの原文PDFはこの環境でテキスト抽出して確認。図表は確認していない
