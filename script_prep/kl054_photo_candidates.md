# kl054 写真の候補（創薬の回、2026-11-08 映像担当 レオ）

`python3 kl_photo_commons.py search` で 32 語を検索し（Wikimedia Commons の API）、候補 37 件の情報（ライセンス・作者・大きさ・説明文）を API で取り直して確かめた。
**ここに書いたものは、Commons 上に実在し、ライセンスがツールの許可範囲（パブリックドメイン／CC0／CC BY／CC BY-SA）にあることを API で確かめたものだけ。**
画像そのものはまだダウンロードしていない（目で見ていない）。使う前に `fetch` で取り込み、`assets/photos/*.png` を Read で見て、写っているもの・人の顔が無いことを確かめる。

- 使い方: 1シーンに複数入れるときは `--slot`、`apply --from-line N` で scene.visuals に入る（`script_prep/kl054_visual_rules_proposal.md`）
- CC BY / CC BY-SA は作者名の表示が必要（ツールが画面の右上と概要欄に自動で入れる）。CC BY-SA は、動画そのものに同じライセンスを付ける義務までは通常かからない（写真を動画の一部として使うだけの場合）と解されることが多いが、判断が分かれる使い方（写真の加工・切り抜き）をするときは制作者に確認する
- 人の顔が主役のもの・肖像は除いた（下の「使わない」）
- 「図」は英語の文字が入った説明図。数値・ラベルは原図のまま（捏造ではない）だが、日本語の視聴者には読めないので、背景（`bg_asset`）か、短い間だけ見せる用

## A. 細胞・抗体（論点: 抗体の設計、CAR-T、免疫細胞）

| ファイル | ライセンス | 作者・出所 | 大きさ | 写っているもの（Commons の説明） | 使いどころ |
|---|---|---|---|---|---|
| [Healthy Human T Cell.jpg](https://commons.wikimedia.org/wiki/File:Healthy_Human_T_Cell.jpg) | Public domain | NIAID/NIH | 1884x1884 | 健康な人のT細胞の電子顕微鏡写真 | CAR-T・細胞治療の話の頭。「免疫の細胞」の実物 |
| [T Lymphocyte, also known as a T cell (yellow color).jpg](https://commons.wikimedia.org/wiki/File:T_Lymphocyte,_also_known_as_a_T_cell_(yellow_color).jpg) | CC BY 2.0 | NIAID | 2428x1888 | T細胞（黄色に着色）の電子顕微鏡写真 | 同上（横長で画面に収まりがよい） |
| [Pembrolizumab 5DK3.png](https://commons.wikimedia.org/wiki/File:Pembrolizumab_5DK3.png) | Public domain | Fvasconcellos | 2048x2048 | 抗体医薬ペムブロリズマブの分子模型（空間充填） | 「抗体」の形を見せる。特定の薬名は台詞で言わない限り出さない（画面に文字なし） |
| [Ofatumumab 3GIZ.png](https://commons.wikimedia.org/wiki/File:Ofatumumab_3GIZ.png) | Public domain | Fvasconcellos | 2048x2048 | 抗体医薬オファツムマブの分子模型 | 同上（別の色合い） |
| [Antibody IgG1 surface.png](https://commons.wikimedia.org/wiki/File:Antibody_IgG1_surface.png) | CC BY-SA 4.0 | Tokenzero | 1845x1543 | IgG1 抗体の構造（軽鎖・重鎖を色分け） | 「Y字の抗体」の説明。Generate Biomedicines・BigHat（抗体の設計）の論点 |
| [CAR T-Cell Therapy.jpg](https://commons.wikimedia.org/wiki/File:CAR_T-Cell_Therapy.jpg) | Public domain | 米国立がん研究所（NCI） | 1305x1727 | CAR-T 療法の手順の図（英語） | 図。CAR-T とは何かを1枚で（縦長。左右はぼかしで埋まる） |
| [CAR T cell manufacturing and therapy.webp](https://commons.wikimedia.org/wiki/File:CAR_T_cell_manufacturing_and_therapy.webp) | CC BY 4.0 | Sheykhhasan, Manoochehri | 1925x971 | CAR-T の製造と治療の流れの図（英語） | 図。製造の論点（BMS）。ファイル形式 webp は取り込みで PNG になる |

## B. 実験室・自動化（論点: AI が実験を回す、候補の絞り込み）

| ファイル | ライセンス | 作者・出所 | 大きさ | 写っているもの | 使いどころ |
|---|---|---|---|---|---|
| [Chemical Genomics Robot.jpg](https://commons.wikimedia.org/wiki/File:Chemical_Genomics_Robot.jpg) | Public domain | Maggie Bartlett, 米国立ヒトゲノム研究所（NHGRI） | 2784x1848 | アッセイプレートを運ぶロボットアーム | 第一候補。「実験を機械が回す」 |
| [Robot arm handles an assay plate.jpg](https://commons.wikimedia.org/wiki/File:Robot_arm_handles_an_assay_plate.jpg) | Public domain | NIAID | 1464x824 | ハイスループットスクリーニングでプレートを扱うロボットアーム | 同上（やや小さい。動画のキャプチャー） |
| [Biomek NXP lab robot 2.jpg](https://commons.wikimedia.org/wiki/File:Biomek_NXP_lab_robot_2.jpg) | CC BY-SA 3.0 | Nadina Wiórkiewicz | 3192x2128 | 分注ロボット（Beckman Coulter Biomek NXP） | 製品名は台詞で言わない |
| [High-throughput screening.jpg](https://commons.wikimedia.org/wiki/File:High-throughput_screening.jpg) | CC BY-SA 3.0 | Tiia Monto | 2121x1520 | ドイツ博物館の展示のスクリーニング装置 | 候補を大量に試す話 |
| [96 Well Plate (NIH BioArt 7).png](https://commons.wikimedia.org/wiki/File:96_Well_Plate_(NIH_BioArt_7).png) | Public domain | NIAID Ryan Kissinger | 1911x1259 | 96穴プレート（イラスト） | 「1枚で96通り試す」 |
| [96-well plate.jpg](https://commons.wikimedia.org/wiki/File:96-well_plate.jpg) | CC BY-SA 4.0 | Jaime Neto | 5472x3648 | 96穴プレートの写真 | 同上（写真） |
| [Disposable Pipette Tips in Laboratory Tip Boxes.jpg](https://commons.wikimedia.org/wiki/File:Disposable_Pipette_Tips_in_Laboratory_Tip_Boxes.jpg) | CC BY-SA 4.0 | Gannu03 | 8192x5464 | 色分けした箱に並ぶピペットのチップ | 実験室の手作業 |
| [Pipette de laboratoire sur fond blanc au Bénin 01.jpg](https://commons.wikimedia.org/wiki/File:Pipette_de_laboratoire_sur_fond_blanc_au_B%C3%A9nin_01.jpg) | CC BY-SA 4.0 | Adoscam | 4496x3000 | 白背景のピペット | 手作業の象徴。カードの背景にも |
| [Liquid chromatograph with mass spectrometer, in CAFIA laboratory, Czech Republic.png](https://commons.wikimedia.org/wiki/File:Liquid_chromatograph_with_mass_spectrometer,_in_CAFIA_laboratory,_Czech_Republic.png) | CC BY-SA 4.0 | Sarka Na kopci | 2387x1846 | 液体クロマトグラフ質量分析計 | Enveda（植物の成分を分析）の論点 |
| [Whitney Genetics Lab eDNA Frozen Samples (22726332679).jpg](https://commons.wikimedia.org/wiki/File:Whitney_Genetics_Lab_eDNA_Frozen_Samples_(22726332679).jpg) | Public domain | 米国魚類野生生物局 | 4928x3264 | 冷凍庫に保管した試料 | 試料・データの蓄積 |

## C. 製造・薬・臨床（論点: 製造、薬が届くまで、臨床試験、書類）

| ファイル | ライセンス | 作者・出所 | 大きさ | 写っているもの | 使いどころ |
|---|---|---|---|---|---|
| [Bioreactor in operation.jpg](https://commons.wikimedia.org/wiki/File:Bioreactor_in_operation.jpg) | CC BY-SA 4.0 | Habin Zhang | 4032x3024 | 稼働中のバイオリアクター | 抗体・細胞の製造（BMS） |
| [Bioreactor 1.jpg](https://commons.wikimedia.org/wiki/File:Bioreactor_1.jpg) | CC BY-SA 4.0 | Luis Fernando Flores LAB | 4096x3072 | バイオリアクター | 同上 |
| [Пластхим - ... Линия за таблетиране.jpg](https://commons.wikimedia.org/wiki/File:%D0%9F%D0%BB%D0%B0%D1%81%D1%82%D1%85%D0%B8%D0%BC_-_%D1%86%D0%B5%D1%85_%D0%B7%D0%B0_%D1%82%D0%B0%D0%B1%D0%BB%D0%B5%D1%82%D0%B8%D1%80%D0%B0%D0%BD%D0%B5_%D0%B8_%D1%85%D0%B8%D0%BC%D0%BE%D1%87%D0%B8%D1%81%D1%82%D0%BA%D0%B0._%D0%9B%D0%B8%D0%BD%D0%B8%D1%8F_%D0%B7%D0%B0_%D1%82%D0%B0%D0%B1%D0%BB%D0%B5%D1%82%D0%B8%D1%80%D0%B0%D0%BD%D0%B5.jpg) | CC BY-SA 4.0 | Hristo Boevski | 4590x2976 | ブルガリアの錠剤の製造ライン（1980年ごろ） | 「薬の工場」。古い写真なので、新しい製造の話には使わない（注記に年代） |
| [Hospital Pharmacy.JPG](https://commons.wikimedia.org/wiki/File:Hospital_Pharmacy.JPG) | Public domain | User:Mattes | 2048x1536 | タイの公立病院の薬局の中 | 「薬が患者に届く」締め・判定 |
| [Former pharmacy, shelves with medicines.jpg](https://commons.wikimedia.org/wiki/File:Former_pharmacy,_shelves_with_medicines.jpg) | CC BY 4.0 | Zalasem1 | 4000x3000 | 古い薬局の薬の棚 | 同上 |
| [Staples, Staple Remover, and Paper Documents (45985597455).jpg](https://commons.wikimedia.org/wiki/File:Staples,_Staple_Remover,_and_Paper_Documents_(45985597455).jpg) | CC BY-SA 2.0 | Tony Webster | 7952x5304 | 紙の書類の束とホチキス | 承認申請の書類づくり（AI が書類を書く論点） |
| [Data center infrastructure in the United States.jpg](https://commons.wikimedia.org/wiki/File:Data_center_infrastructure_in_the_United_States.jpg) | Public domain | 米エネルギー省／NREL | 5100x3300 | データセンターの設備 | AI の側（計算機）。お題と予想 |
| [BalticServers data center.jpg](https://commons.wikimedia.org/wiki/File:BalticServers_data_center.jpg) | CC BY-SA 3.0 | BalticServers.com | 2048x1360 | サーバー室 | 同上（会社名は台詞で言わない） |
| [DNA-Helix-Rendering 20220603.png](https://commons.wikimedia.org/wiki/File:DNA-Helix-Rendering_20220603.png) | CC0 | PantheraLeo1359531 | 18000x2160 | DNA の二重らせんの CG（超横長） | 背景（`bg_asset`）向き。超横長なので中央の帯になる |

## D. 病気・食べ物（Mithril Medicine の筋ジストロフィー、アレルギー）

| ファイル | ライセンス | 作者・出所 | 大きさ | 写っているもの | 使いどころ |
|---|---|---|---|---|---|
| [Muskel ( 1).jpg](https://commons.wikimedia.org/wiki/File:Muskel_(_1).jpg) | CC BY-SA 3.0 | Rollroboter | 3886x2578 | 骨格筋の線維の顕微鏡写真（HE染色、縦断面） | 「筋肉の細胞」。筋ジストロフィーの説明の頭 |
| [Duchenne-muscular-dystrophy.jpg](https://commons.wikimedia.org/wiki/File:Duchenne-muscular-dystrophy.jpg) | Public domain | Edwin P. Ewing, Jr.（CDC） | 1809x1204 | デュシェンヌ型の患者の筋組織の病理標本（筋線維が脂肪に置き換わる） | **注意:** 亡くなった患者の標本。病気の重さを見せすぎないか、使う前に制作者確認を勧める |
| [Peanuts (Arachis hypogaea) - in shell, ....jpg](https://commons.wikimedia.org/wiki/File:Peanuts_(Arachis_hypogaea)_-_in_shell,_shell_cracked_open,_shelled,_peeled.jpg) | CC BY-SA 4.0 | Ivar Leidus | 6000x4000 | 殻つき・むいたピーナッツ | 食物アレルギーが話に出るなら |
| [Lab mouse mg 3263.jpg](https://commons.wikimedia.org/wiki/File:Lab_mouse_mg_3263.jpg) | CC BY-SA 2.0 fr | Rama | 4368x2912 | 実験用マウス | 動物実験の段階。動物実験は視聴者の受け止めが分かれるので、台詞で触れるときだけ |

## 使わない・見送ったもの

- 人の顔が主役（ツールの人物判定に該当、または説明に人名）: `Researchers review cancer data.jpg`（NCI の研究者2人）、`Researcher holding a lab mouse ...`、クリーンルームの作業者の写真（`Reinraum BBS Automation Blaichach.jpg` ほか）、NCI 所長などの肖像
- 「No restrictions」（Flickr Commons の古い資料）: ツールが × にしている（ライセンス名が許可の一覧に無い）。使わない
- 小さい（幅1280px未満）: 多数。ぼやけるので使わない
- 製品名・商標が主役: `Comirnaty Omicron XBB.1.5 vials 2023.jpg`（ワクチンの瓶。今回の題材と無関係）
- クリーンルーム: 見つかったのは半導体工場（`Clean room.jpg`・`CNE cleanroom 1.jpg`）で、製薬のクリーンルームではない。製薬の製造には使わない
- 提携6社・Mithril Medicine・Anthropic の写真（社屋・ロゴ・製品）: Commons では見つからなかった。使うなら各社のプレス素材を、利用条件を確かめて `kl_photo_commons.py import` で取り込む（制作者が保存した画像を渡す。ロゴは商標なので使わない）

## 公的機関の画像（Commons 以外）

NIH・NCI・NIAID・CDC の職員が職務で作った画像は、米国では著作権の対象外（パブリックドメイン）として扱われることが多く、上の候補にも NIAID・NCI・NHGRI・CDC の画像が Commons 経由で入っている。
各機関のサイト（NCI Visuals Online、NIAID の Flickr、CDC の PHIL）から直接使う場合は、画像ごとの利用条件（第三者の写真が混ざる、Flickr は CC BY 2.0 など）がページに書かれているので、`import` で `--terms` と `--terms-url` にそのページを記録する。今回はサイトを直接は確かめていないので、候補には入れていない。
