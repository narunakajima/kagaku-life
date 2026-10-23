# kl048 資料集め: 承認が形だけになる（rubber-stamping）実測

調査日: 2026-10-23。取得手段は WebFetch（要約を返す方式）のため、「原文」は取得結果に引用として出た短い文のみ。全文を自分の目で読んだ資料は無い。台本に使う前に原典で再確認すること。
凡例: 確認=ページを開いて内容を得た／部分確認=要旨のみ／未確認=開けず検索結果のみ。著者所属がページに無い場合は「ページに記載なし」とした（推測で補っていない）。

## 研究一覧と主要数字（早見）

| # | 区分 | 資料 | 主要数字 | 状態 |
|---|---|---|---|---|
| 1 | A | Poly ら 2020 JMIR Med Inform（系統的レビュー） | 薬の警告の上書き率 平均46.2〜96.2%（23本） | 確認 |
| 2 | A | Villa Zapata ら MEDINFO 2021（スコーピングレビュー） | 薬物相互作用警告の上書き率 55〜98%（34本） | 部分確認（要旨のみ） |
| 3 | A | Ancker ら 2017 BMC MIDM | 繰り返しの通知ほど受け入れが下がる。経時的な慣れは見られず | 確認 |
| 4 | B | Utz ら 2019 ACM CCS | 80,000人超の実サイト実験 | 部分確認（数字未取得） |
| 5 | B | Obar & Oeldorf-Hirsch 2018 | 543人中74%がプライバシーポリシーを飛ばす | 未確認（二次報道のみ） |
| 6 | C | Dratsch ら 2023 Radiology | 誤ったAI提案で正答率 約80%→20%未満（経験浅）、82%→45.5%（経験豊富） | 部分確認（RSNA報道経由） |
| 7 | C | Green 2022 Computer Law & Security Review | 41の方針を分析し、人による監督は期待どおり機能しないと論じる | 部分確認（要旨のみ） |
| 8 | D | Anthropic 2026-02-18 自律性の実測 | 全自動承認は新規ユーザー約20%→750セッションで40%超 | 確認（公式ページ） |
| 9 | D | Anthropic 2026-03-25 auto mode 記事 | 「ユーザーは93%を承認する」 | 確認（公式ページ） |
| 10 | D | Yu ら 2026 arXiv 2606.22721「Habituation at the Gate」 | 承認率 30.1%→36.8%、コメント量 -22% | 部分確認（要旨のみ） |
| 11 | E | Buçinca ら 2021 CSCW | 「認知強制」で過信が有意に減る（N=199）。ただし好まれない | 部分確認（要旨のみ） |
| 12 | E | Anthropic auto mode 記事の分類器の数字 | 実際の危険行為52件で見逃し17% | 確認（公式ページ） |

---

## (A) 医療の警告疲れ

### 1. Poly TN, Islam MM, Yang HC, Li YCJ. Appropriateness of Overridden Alerts in Computerized Physician Order Entry: Systematic Review.
- URL: https://pmc.ncbi.nlm.nih.gov/articles/PMC7400042/ （JMIR 版 https://medinform.jmir.org/2020/7/e15653/）
- 所属: 台北医学大学（Taipei Medical University）生物医学情報研究所ほか（台湾）
- 掲載: JMIR Medical Informatics 8(7):e15653、2020年7月
- 対象: 2000年〜2019年3月の5データベースから23本。対象人数・総警告数はページに記載なし（360本をタイトル・要旨で選別）
- 主要数字: 「The range of average override alerts was 46.2%-96.2%.」薬物相互作用警告の上書きが適切だった割合は「drug-drug interaction 0%-95%」（考察では 0〜84% とも書かれ、本文内で不一致）。上書き理由で多いのは「will monitor」「patients have tolerated before」。
- 結論の方向: 上書き率は高い。薬物相互作用・腎機能・高齢者の警告の上書きは不適切なことが多い一方、重複投薬・アレルギー・採用薬の警告の上書きは適切なことが多い（つまり「全部形だけ」ではない）。
- 限界（著者）: 「First, we could not determine the bias of the included studies because of the heterogeneous nature of the studies.」有害事象の割合は資料が少なく報告できない。一部の研究は上書きの小さな無作為標本しか見ていない。適切さの判定はカルテ情報に依存。

### 2. Villa Zapata L, Subbian V, Boyce RD, Hansten PD, Horn JR, Gephart SM, Romero A, Malone DC. （薬物相互作用警告の上書き率のレビュー）
- URL: https://ebooks.iospress.nl/pdf/doi/10.3233/SHTI220101
- 掲載: Studies in Health Technology and Informatics 290（MEDINFO 2021）pp.380-384。所属はページに記載なし
- 内容: 34本。上書き率の範囲 55%〜98%（統合値は報告なし）。結論は、ユーザー・薬・施設の要因を考慮すべきで、上書きによる害を測る指標が要る、とのこと。
- 限界: 要旨しか見られず未確認。

### 3. Ancker JS ら. Effects of workload, work complexity, and repeated alerts on alert fatigue in a clinical decision support system.
- URL: https://pmc.ncbi.nlm.nih.gov/articles/PMC5387195/
- 所属: Weill Cornell Medical College（ニューヨーク）ほか Mount Sinai、Institute for Family Health
- 掲載: BMC Medical Informatics and Decision Making 17:36、2017年4月
- 対象: 外来プライマリケア医療者112人の電子カルテ記録（2010年1月〜2013年6月）の後ろ向きコホート
- 結果: 「Alert acceptance was associated with work complexity and repeated alerts, but not with the amount of work.」同じ患者への繰り返しが薬警告の約3分の1、リマインダーの約4分の1。リマインダーは同一診察での1件増ごとに受け入れが約30%低下（二次要約）。**「The newly deployed reminders did not show a pattern of declining response rates over time.」時間とともに慣れて無視が増える（脱感作）仮説は支持されなかった。**「Nurse practitioners were 4 times as likely to accept drug alerts as physicians.」
- 限界（著者）: 観察研究、1つの商用カルテシステム。重症度と上書きの適切さは未評価。「we cannot conclude definitively that reducing override rates would reduce rate of inappropriate overrides.」
- 食い違い: 「時間がたつと確認が減る」を直接は支持しない。支持されたのは、通知の量・繰り返しと受け入れ低下の関連。

メモ: 「上書き率が平均90%」という統合解析（Felisberto 2024 とされる）はブログ経由の情報のみで、著者名・原典を確認できなかった。**使わない。**O'Sullivan らの44本・79.8%（95%CI 73.0〜86.7）は JMIR のプレプリント（査読前）で、検索結果の要約のみ。**使うなら「査読前」と明記し、原典を確認する。**

## (B) 同意疲れ

### 4. Utz C, Degeling M, Fahl S, Schaub F, Holz T. (Un)informed Consent: Studying GDPR Consent Notices in the Field.
- URL: https://arxiv.org/abs/1909.02638
- 掲載: ACM CCS '19（ロンドン）、2019年。所属はページに記載なし
- 内容: ドイツの1つのサイトで3つの実験、「more than 80,000 unique users」。欧州の人気サイトの60%超が同意通知を表示。
- 二次情報（検索要約、未確認）: 事前選択やボタン配置で同意率が変わる。「同意疲れ」そのものを直接測った研究ではない。数字は原典のPDFが読めず**未取得**。
- 限界: ページに限界の節なし。単一サイト（これは私の推論で、著者の記述ではない）。

### 5. Obar JA, Oeldorf-Hirsch A. The biggest lie on the Internet: ignoring the privacy policies and terms of service policies of social networking services. Information, Communication & Society, 2018。
- URL: https://papers.ssrn.com/abstract=2757465 （403 で開けず）
- **未確認。** 検索結果の報道（Help Net Security など）による: 偽のSNS「NameDrop」で学生543人、74%がポリシーを飛ばして「クイック参加」、読んだ人の平均閲覧時間はプライバシーポリシー73秒・利用規約51秒（推定必要時間は30分・16分）、543人中399人は規約を読まず。規約に「第一子を渡す」条項があった。
- 注意: 参加者は大学生。台本で使うなら原典を開いて数字を確認してから。

## (C) 人による監督は機能するか

### 6. Dratsch T ら. Automation Bias in Mammography: The Impact of Artificial Intelligence BI-RADS Suggestions on Reader Performance.
- URL: https://www.rsna.org/news/2023/may/ai-bias-may-impair-accuracy （RSNA の解説。論文本体は未開）
- 所属: ケルン大学病院 画像診断・IVR研究所（ドイツ）ほか独・蘭の機関
- 掲載: Radiology、2023年5月
- 対象: 放射線科医27人、マンモグラフィ50枚（練習10件は正しい提案、本番40件のうち12件に誤った提案）
- 結果: 経験の浅い医師は提案が正しいとき約80%、誤りのとき20%未満（二次要約では 80%→19.8%）。経験豊富（平均15年超）は82%→45.5%。経験があっても影響を受けるが程度は小さい。
- 限界: AIの提案は研究者が用意した固定のもの（実システムではない）。経験群ごとの人数は報道に記載なし。BI-RADSの分類は診断そのものではない。
- これは「誤った助言に追従する」実測であり、「形だけの承認」の時間経過ではない。

### 7. Green B. The flaws of policies requiring human oversight of government algorithms.
- URL: https://arxiv.org/abs/2109.05067
- 掲載: Computer Law & Security Review 45、2022年。著者所属はページに記載なし
- 内容: 人による監督を求める41の方針を調べ、「人は期待される監督をしばしばできない」と論じる文献レビュー。新たな実験ではない（私の要約）。
- 注意: 要旨のみ確認。個別の数字は取れていない。

## (D) AIエージェントでの承認の実測

### 8. Anthropic. Measuring AI agent autonomy in practice（2026年2月18日）
- URL: https://www.anthropic.com/research/measuring-agent-autonomy
- 発表元: Anthropic（自社データの分析。査読論文ではない）
- 対象: Claude Code の対話セッション50万件、公開API のツール呼び出し998,481件ほか。分析対象は2025年9月19日以降に登録したユーザー。ユーザー数は記載なし。
- 結果: 新規ユーザー（50セッション未満）は「employ full auto-approve roughly 20% of the time」、750セッションで「over 40% of sessions」。「gradual, suggesting a steady accumulation of trust.」中断率は新規約5%/ターン→経験者約9%。「Experienced users interrupt Claude more often, not less.」（別の二次記事は「50%超」と書くが公式は40%超。**公式を採用**）
- 解釈の注意: 自動承認の増加は「信頼の蓄積」とも読め、「惰性」とは区別されていない。しかも経験者はむしろ中断が増えている。単純に「形だけになる」とは言えない、食い違う材料。
- 限界（著者）: 「We can only analyze traffic from a single model provider: Anthropic.」期間は2025年末〜2026年初。プライバシー上、元データを人が確認できない。Claude Code は主にソフトウェア開発向け。
- 補足: 「Claude Code's default settings require users to manually approve each action.」

### 9. Anthropic Engineering. Claude Code auto mode（2026年3月25日）
- URL: https://anthropic.com/engineering/claude-code-auto-mode
- 原文: 「in practice users accept 93% of them anyway.」「Over time that leads to approval fatigue, where people stop paying close attention to what they're approving.」
- 注意: 93%は「承認された割合」で、「注意せず承認した割合」ではない（承認が妥当だっただけの可能性を排除できない）。「approval fatigue」は記事の主張で、注意の低下を直接測った数字ではない。
- 二次報道（未確認・使わない）: 「人は偽装された危険コマンドを13.6%しか見つけられなかった」。この記事に人間の検出テストは無かった。出典不明。

### 10. Yu H ら. Habituation at the Gate: Rising Approval and Declining Scrutiny in Human Review of AI Agent Code
- URL: https://arxiv.org/abs/2606.22721
- 掲載: arXiv（cs.SE）2026年6月21日投稿、KDD 2026 Workshop on Agentic Software Engineering 採択と記載。所属はページに記載なし。査読の深さは不明（ワークショップ、5ページ）
- 対象: AIDev データセット、繰り返しレビューした400人、11,429件のレビュー、7か月
- 結果: 承認率 30.1%→36.8%（Wilcoxon p<10^-6）、経験十分位の1番目→10番目で +14.5ポイント。レビュー待ち時間3.5倍、インラインコメント量 -22%（p=0.0014）。著者は「reflexive habituation under growing workload」と読むのが「most consistent」とする。
- 限界: 観察研究で因果は言えない。待ち時間・コメント数は注意の代理指標。PR難度の統制は中央値の大きさのみ（私が要旨から読み取った点で、著者の限界の節は未確認）。
- 重要: 数字の小ささに注意。承認率の変化は約7ポイントで、「ほぼ全部通す」ではない。

## (E) 対策

### 11. Buçinca Z, Malaya MB, Gajos KZ. To Trust or to Think: Cognitive Forcing Functions Can Reduce Overreliance on AI in AI-assisted Decision-making.
- URL: https://arxiv.org/abs/2102.09692
- 掲載: Proc. ACM HCI 5(CSCW1), Article 188, 2021。所属（ハーバード大学）は関連ページ上の表記のみ、arXivページには記載なし。
- 対象: N=199。認知強制3種を、単純な説明つきAI2種・AIなしと比較。
- 結果: 認知強制で過信が有意に減る（効果量・割合はページに記載なし）。ただし「people assigned the least favorable subjective ratings to the designs that reduced the overreliance the most」、つまり効果のある設計ほど好まれない。必要認知欲求が高い人ほど効果大。
- 限界: 要旨のみ。タスクの詳細は未確認。

### 12. Anthropic auto mode の分類器（上記9と同じ記事）
- 数字: 実際の「やりすぎ行動」52件で、完全版の見逃し17%（第1段 6.6%）。通常通信1万件の誤検知率 0.4%（第1段 8.5%）。
- 著者の限界: 17%を「the honest number」と呼び、52件は少ない。「not a drop-in replacement for careful human review on high-stakes infrastructure.」「a regression if compared with careful manual approval」と自認。
- これは「人の確認を機械に置き換える」案の実測で、「承認の設計を工夫した効果」の一種。ただし自社製品の自己評価である点に注意。

その他（Dratsch の著者提案）: 本人の責任を意識させる、AIの確信度を見せる、といった対策は提案で、効果を測った数字は無し。Ancker らも、重複通知を減らす案は提案で、減らして上書きが減るかは未検証。

---

## 判断

**(a) 「承認が形だけになる」を示す研究は何本か:**
- 「承認・上書きの率が非常に高い」を数字で示すのは、A の系統的レビュー2本（上書き率 46〜96%、55〜98%）。ただし Poly らは多くの上書きが妥当だったとも報告し、「形だけ」と断定できない。
- 「経験とともに承認が増える」を示すのは D の3本（Anthropic 公式、Yu ら）。自動承認 20%→40%超、承認率 30.1%→36.8%。
- 「時間とともに無視が増える」を直接支持した A のAncker らは、**支持しなかった**（慣れの傾向は無し）。結果が食い違っている。
- 「誤った助言に人が追従する」は Dratsch（正答率の大幅低下）。
- 数字の強さはどれも一部の領域・条件で、「人は必ず形だけになる」とまでは言えない。

**(b) AIエージェントの承認を測った研究はあるか:** ある。ただし Anthropic の2本は自社製品の自社データで、査読論文ではない。Yu らは AIコード生成エージェントの PR レビュー（コマンド承認ではない）で、ワークショップ論文。警告疲れ・過信の研究（A・C）は人とAIの別領域なので、エージェントの代用として扱う。コマンド承認での「人が危険を見逃す割合」は、一次資料を確認できていない（ブログで見た33%や13.6%は出典不明で、使えない）。

**(c) 一般の人に誠実に3文で説明できるか:** 条件つきで可。ただし限定が要る。
案: 「病院の薬の警告は、調べた研究で半分から9割以上が無視・上書きされていて、その多くが妥当な判断とは限りません。AIエージェントでも、Anthropicの自社データでは使い慣れた人ほど自動承認が増え、別の研究では承認率が少し上がりレビューは薄くなっていました。ただし、時間とともに慣れて無視が増えると直接示せた研究はなく、対策の効果も限られた実験しかないので、『承認は形だけになりがち』までが言えることです。」

**足りないもの:** (1) エージェントのコマンド承認で人が危険を見逃す割合の一次資料（査読論文または公式データ）。(2) 「承認の頻度を絞る・重要な操作だけ止める」設計を実測した研究（見つかったのは Buçinca の認知強制と Anthropic の分類器のみで、前者は別の課題、後者は自己評価）。(3) B の同意疲れは Utz の数字と Obar の原典が未確認。この3点は「足りない」。台本の柱にするには、(1)(2)を追加で探すか、「実測はまだ少ない」と台本で言うのが誠実。
