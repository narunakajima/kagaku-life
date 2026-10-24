# BGM の方針とパイプライン

> この文書は 2026-10-24 に CLAUDE.md から移した詳細・記録。本文は移す前のまま（見出しの名前も同じ。コードや手順書の「CLAUDE.md「〇〇」参照」は、ここの同名の節を指す）。

### BGMパイプライン（2026-08-21追加）

samurai-chroniclesのBGMパイプライン（Freesound検索→音声QA→ライブラリ管理→
実音声での最終チェック→CC BYクレジット注入）をkagaku-life向けに移植した。
動画生成（`kl_video_gen.py`、クロスフェード合成部分）自体は未実装のため、
現時点では候補選定〜ライブラリ登録までが対象。境界計算・クロスフェードの
設計はSCの `sc_video_gen.py` と同じ考え方を踏襲する想定（上記「境界計算
ルール」参照）。

#### 掛け合い形式のBGM方針（2026-10-06、なるさんが承認。kl035以降の正）

**コンセプト: BGMは二人の会話のテンポを支えるリズム。感情を語るのは台詞。** 前向きで押し付けがましくないこと、
epic/horror 等の禁止は旧方針から残す。旧方針の「温かく・希望が持てる」（ピアノのバラード・泣きのストリングス）を
既定にするのはやめた。旧形式の「小さな幸せ」のオチと結びついたトーンで、掛け合いには遅く湿っぽいため。
**ジャンル（AI／ヒューマノイド／医療／食と健康／暮らしの技術）や判定（もうすぐ来る／3年／根拠待ち／眉唾）で曲調は変えない**
（固定の二人と判定ラベルが看板なので、音も「この番組の音」に統一する。outroだけ判定別に2系統持つ案は今回は入れない）。

**根拠（2026-10-06の調査）:**
- kl034 で なるさんが intro を3回差し替えた（ライブラリのピアノ → オルゴール → 明るいシンセ調「Vibrant Positivity」）。
  main も2回差し替えて lo-fi ビートになった。outro のピアノは差し替えなし。静か・ゆっくり・ビートなしの曲が掛け合いの冒頭で
  2回続けて却下された、というのが確実に言えること（楽器よりテンポとビートの有無を見ている、は推測）
- 掛け合い形式の区間の長さは intro 127〜157秒・**main 164〜197秒**・outro 54〜95秒（kl031〜kl034）。一方 main の曲は
  30〜36秒（kl002・kl031・kl032・kl034）で、`aloop` で5〜6回、つなぎ目の処理なしに頭へ戻っていた
- ライブラリ33曲中28曲の `tags` が `warm/gentle` なのは曲調ではなく、`kl_bgm_library.py` の既定値のせいだった（修正済み）

**役割ごとの狙い:**

| 役割 | 主なシーン | 狙い | テンポ・楽器・展開 |
|---|---|---|---|
| intro | teaser→setup→paper→dream | ニュースの引き、「何それ？」のワクワク | 105〜125 BPM。シンセのアルペジオ／プラック＋軽いビート（4つ打ち・ポップ系）、明るい長調。頭の2〜4小節で立ち上がる（長い前奏は不可） |
| main | tsukkomi→check（→2本目の paper・dream） | 考える・確かめるときの軽い緊張と遊び | 70〜100 BPM。lo-fi／ヒップホップのビート、ピチカート、ミュートしたシンセベース。メロディは薄く、繰り返しが主役 |
| outro | verdict→closing | 判定の決着感と、次回への軽い余韻 | 85〜100 BPM。intro と同系統の明るさを少し落ち着かせたもの（エレピ／ピアノ＋軽いビート）。泣きのストリングス・盛り上がりは不可 |

- 役割は3つのまま。intro→main→outro の順に戻らない（`kl_dialogue.validate_episode`）。`verdict_first` では冒頭で言う判定も
  intro の曲で鳴らし（引きは intro の役目）、最後の判定は outro でもう一度。`news_roundup` は main が最も長くなるので、
  下記の長さの条件を必ず確認する

**方針の例外・改訂（2026-10-06、なるさんの承認）:** (1) main の BPM 範囲は 80〜100 から **70〜100** に広げた（kl034 で採用したLofi Beat 70bpm を範囲内にするため）。(2) kl034 の outro（ピアノ独奏、Light Playful sounds3）は、最終検証が「ビートなしは原則避ける」で要差し替えと判定したが、なるさんが承認済みのため**例外として残す**。新規の回では原則どおり、outro もビートのある曲を選ぶ。

**選曲基準:**
- 合格: ボーカルなし（ハミング・「オー」も不可）／台詞の帯域（1〜4kHz）で鳴り続けるリード楽器が無い／冒頭10秒以内に曲の性格が
  出る／極端な音圧差が無い／CC0優先、次に CC BY（NC・ND・SA は不可）
- **長さ: その役割の区間の長さ×0.7以上が目安。main は120秒以上**（区間が160〜200秒あるため）。短い曲を使う場合は、
  `kl_video_gen.py` がつなぎ目をクロスフェードでならしてループする（下記）が、**つなぎ目を必ず人が聴いて確認する**
- 不合格: 環境音・フィールド録音の混入、曲中の無音・テンポ変化・ドロップ、短調の悲しい曲、泣きのストリングス、
  壮大なオーケストラ、ホラー調、攻撃的なEDM／ダブステップ、オルゴールや遅いソロピアノ（intro・main は不可、outro も
  ビートなしは原則避ける）

**ライブラリの運用:**
- **同じ曲は直近5話で1回まで。各話で3役割のうち最低1曲は新曲（main を優先）。`used_in` が6話以上の曲は掛け合い形式では使わない**
  （2026-10-06時点で該当: kl002-BGM-main 9話、kl001-BGM-intro・kl001-BGM-outro・kl005-BGM-main 各7話、
  kl001-BGM-main・kl002-BGM-outro 各6話）
- `kl_bgm_library.py --add` で、曲調を `--bpm --mood --instruments --has-beat --era（dialogue／legacy_monologue） --role-fit`
  として記録する（任意。未指定は空）。`duration` は ffprobe で実測して記録し、Freesound の id・曲名は
  `kl_freesound_download.py` のメタ情報から `source_id`／`source_name` に入る。ファイル名から推測する `tags` の
  `warm/gentle` の既定値はやめた（該当語が無ければ空）
- 既存33曲の付け替え（`era` の仕分け）は未実施。曲名で分かる「Heartfelt Piano and Violin」「Regretful Guitar」
  「Noir…Emotive Piano」「Cinematic Emotion」「Reflective Piano」と、60秒未満の main 曲は旧形式向きの候補

**Freesound の検索（`kl_freesound_download.py`、2026-10-06新設。lamp-whisper と共有の `freesound_download.py` は変更しない）:**
- Freesound のクエリ語は**すべて必須（AND）**。3語以上は0件になりやすいので2語までにする（超えると警告）
- `filter` に `category:Music` を付ける。旧スクリプトの条件では「warm gentle」の上位30件の57%（17件）が
  Soundscapes／Sound effects（雨・虫・川など）で、1位に「Rain_Hitting_Window_9」が来ていた
- 並び順は `score`（関連度）。旧スクリプトの `rating_desc` は評価の高い同じ曲を上に出し、それが LW/SC と共有の
  既出リスト（約800件）で消えて0件になっていた（「warm uplifting」は上位15件がすべて既出）。既出リストは
  kagaku-life 専用（`~/.claude/scripts/.kl_freesound_seen_ids`）にした
- **クエリに「-語」を付ける除外は使わない。** 実測で「positive electronic」（90秒以上・Music）65件が `-voice` で6件、
  `-field-recording` で5件、`-ambient` で3件に減った（説明文の「no vocals」にも当たり、挙動が不安定）。代わりに名前・タグに
  環境音・声の語（rain, birds, ambience, vocal, singing など）を含むものを手元で落とす
- 長さの下限は役割別（intro 90秒・main 120秒・outro 45秒）。満たす候補が無ければ30秒以上に緩めて探し直し、「短い曲（ループで
  使う）」と表示する
- score 順の1位が良い曲とは限らない（実測で「1984 It Came From A Synth!」が実際はオーケストラ調だった）。役割ごとに
  `--count 2〜3` で複数取り、QAと耳で比べる。`--list 10` でダウンロードせずに候補を見られる
- 検索語の例（2語まで）:

| intro | main | outro |
|---|---|---|
| synth arpeggio, upbeat synth, corporate upbeat, energetic corporate, positive electronic, bright pop, future bass | lofi beat, minimal beat, thinking music, puzzle music, hiphop instrumental, lofi hiphop, pizzicato playful | electric piano, lofi chill, light beat, chill electronic, acoustic pop, warm electronic, rhodes chill |

  実測（2026-10-06、新条件での総ヒット数／手元の除外後の候補数）: synth arpeggio 27/22、lofi beat 74/46、thinking music 43/25、
  electric piano 44/30、lofi chill 122/33。「tech pop」「optimistic ending」は0件、「curious pizzicato」「quirky playful」は
  ほぼ0件なので使わない。避ける語: warm, gentle, heartfelt, emotional, cinematic, epic, ambient, meditation, relax, sad, music box
- ライブラリ外の候補（未採用、記録のみ）: YouTube Audio Library（YouTube上の利用は許諾が明確、多くはクレジット不要。
  ダウンロードは手作業、YouTube以外での利用は不可）、Pixabay Music（クレジット不要。Content ID の申し立てリスク、出所の管理が弱い）

**ループのつなぎ目（`kl_video_gen.make_seamless_bgm`、2026-10-06）:** 曲が区間より短いとき、曲の頭と末尾の無音を落とし、
同じ曲を必要な回数並べて1.5秒のクロスフェード（`acrossfade`）でつないだ長い曲を先に作ってから使う（本編の3区間と Shorts の
main）。曲が十分長ければ何もしない（既存の長い曲の音は変わらない）。kl034 の main（31.9秒、末尾0.5秒が無音）は、以前は
約30秒ごとに無音のすき間ができていた。

**検証（2026-10-06に作り直した。判定がぶれていたため）:**
- `kl_bgm_qa.py`（ボーカルの有無）: 温度0で3回判定して多数決。**1回でも「あり」なら不合格（割れた場合も安全側）。**
  「あり」の場合は声が聞こえる時刻を出すので、人はその前後5秒だけ聴く。空の応答・前置きつきの応答は取り直す／読み取る。
  実測で既定の `gemini-flash-latest` は6曲中3曲で判定が割れた（ソロピアノに「男性ボーカル」など）一方、
  `--model gemini-pro-latest` は6曲×3回すべて一致した。flash で割れたら pro で取り直すか、時刻の前後を耳で確かめる
- `kl_bgm_final_check.py`（掛け合い形式）: 2段階で採点し、温度0で3回の中央値を取る
  1. **狙いを伝えずに**曲単体（頭30秒）を聴き取らせ、楽器・ビートの有無・声の有無・推定BPMを得る。狙い（「明るいシンセ＋
     軽いビート」）を先に伝えると、オルゴールを「シンセプラックと軽快なビート」と書いて全項目5点を付けることが実測で起きた
  2. 聴き取り結果＋台詞とBGM（動画と同じ0.12）の簡易ミックス（各区間の頭30秒）＋ループのつなぎ目の前後12秒で、
     役割ごとに5項目（役割への適合・台詞とぶつからない・テンポの範囲・ループのつなぎ目・ボーカルなし）を1〜5点で出す。
     声あり→ボーカル1点、intro/main でビートなし→役割への適合は2点以下、テンポは BPM（ファイル名・メタ情報、無ければ
     聴き取りの中央値）から機械的に採点する
  - 合格: 役割ごとに全項目3点以上かつ平均3.5以上。最終行は「最終判定: 合格」か「最終判定: 要差し替え（main など）」
  - 実測: 旧形式の3曲（オルゴール／ソロピアノのバラード／アンビエント）は3役割とも不合格になり、kl034 の intro・main は合格、
    outro（ピアノ独奏）は新方針では不合格になった
  - 人が聴く箇所は絞る: 各区間の頭15秒、main のループのつなぎ目、intro から main への切り替わり
