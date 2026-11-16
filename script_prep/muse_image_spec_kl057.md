# kl057 画像の Muse 生成仕様（1話試行）

作成: 2026-11-16 / 作成者: KLチーム 映像担当 レオ（kl-art-director）
手順の正本: `docs/muse_image_trial.md`（手順1・2）。この仕様は `kl_image_gen.py` を回す代わりに作ったもの。制作フロー・制作コードは変更していない。

## 共通事項

- **エピソード ID:** kl057
- **タイトル（youtube_title）:** ChatGPTの中に店のページ。お金を出した店が勧められる？（11月時点）
- **形式:** 掛け合い（dialogue）・構成 rounds_v4。二人の立ち絵（大輔・沙織）は動画側で合成するので、**画像には人物を描かない**
- **枚数:** 4枚（本編 3枚＋サムネイル背景 1枚）。Shorts はこの仕様に含めない（末尾メモ参照）
- **画風の共通指示（全4枚。下の各プロンプトの冒頭に同じ文として展開済み）:** 温かい窓・ランプの光と細かい粒子のテクスチャのある、雑誌のエディトリアル風フラットイラスト。やわらかい陰影のグラデーション（ベタ塗りのセル調ではない）。落ち着いた色（スレートブルー、ティール、ウォームグレー）に、暖かいコーラル／アンバーの差し色の光を1つ。写真調にしない、アニメ調にしない、強いドラマチックな光線を入れない
- **禁止事項（全4枚）:**
  - 枠・帯・パネル・はめ込み画像・字幕・キャプション・UI の帯を描かない（1枚の絵が端から端まで続く）
  - 指定外の文字・数字・ロゴを描かない（看板は無地、画面は抽象的な吹き出しのみ。読める文字は一切なし）
  - 人物・手・ロボットを描かない
  - **本編（S06・S08・S10）:** 動画では左下と右下に二人の立ち絵、下部に字幕帯が乗る。主題と重要な物は「横の中央70%・縦の上75%」に置き、左下・右下・下の1/5は同じ場面の床・机の面・壁・道を自然に続ける（空白・白・切り抜きにしない。そこに重要な物を置かない）
  - **サムネイル背景（thumbnail_bg）:** 見出し文字・立ち絵・判定の札は後でコードが合成する。**左右それぞれ30%と上42%は、ぼかした店先と夕方の空だけの静かな部分**にし、背景は途切れずに続ける。主題は中央の帯（左右中央）に置く
- **登場人物の外見:** 描かない（立ち絵は固定素材を合成。研究者・被験者も登場しない）。BASE_CONTEXT の「日本人の顔立ち」の一文は原文どおり展開してあるが、人物は描かないこと
- **納品形式:** PNG。ファイル名は下の指定どおり。**この仕様ファイルと同じフォルダ（Drive `マイドライブ/Kagaku-Life/KL057/images/`）の直下**に置く。サイズは 1376×768（16:9）。比が ±2% 以内ならこちらでリサイズする

---

## 1. S06.png

- **ファイル名:** `S06.png`
- **サイズ・画角:** 1376×768（16:9）
- **プロンプト（完成形・英文）:**

```
Rich flat editorial illustration style with soft warm lamp/window lighting and a subtle grain/noise texture overlay: naturalistic character proportions and skin tones, gentle shading gradients rather than flat cel-shading. Muted, sophisticated palette (slate blue, teal, warm gray) with one warm coral/amber accent light glowing softly within the scene. Cozy, intimate, magazine-editorial illustration quality. Not photorealistic, no anime style, no harsh dramatic light rays. Characters have authentically Japanese facial features (this is a Japanese-audience channel) — not Western or ambiguous.

Scene: Interior of a small independent neighborhood shop in the early evening, seen from just behind the counter: a wooden counter with a smartphone lying flat on it, its screen glowing softly with a few abstract rounded chat bubbles and a small product thumbnail (no readable text, no logos), a paper price tag and a small gift box beside it. Shelves of neatly arranged goods and a glass front door with a warm street glow behind. Calm, hopeful mood. No people, no hands, no robots, no readable text or signs with words. Warm editorial illustration style.

COMPOSITION: place the main subject and all important details in the upper and central part of the frame (the central 70% of the width, the top 75% of the height). In the lower-left corner, the lower-right corner and the bottom fifth of the frame, simply continue the same scene's floor, rug, table surface or wall naturally, with no important objects there — never leave it blank, white, empty or cut out. The image is one single continuous, fully painted scene edge to edge: no borders, no frames, no inset pictures, no panels, no bars, no captions.
```

- **用途:** シーン6（論点1「AIは、店のことを正しく話せる？」の頭、type paper）。小さな店のカウンターに置かれたスマホに、AIとの会話が光っている絵で「店がChatGPTに自分の情報を直接届ける入口ができた」を見せる。台詞の要約: 店がChatGPTの中の自分の店を名乗り出て、本人確認を通ると値段・返品の決まりを入れられる。画面には1行目からと10行目から（後半の「町のパン屋や工務店でも看板になる」）の2回出る。**左下・右下に立ち絵、下に字幕帯**が乗るので、スマホとカウンターの主題は中央寄り・上寄りに。Shorts（1・2・6カット目）でも使う
- **参照指定:** なし

## 2. S08.png

- **ファイル名:** `S08.png`
- **サイズ・画角:** 1376×768（16:9）
- **プロンプト（完成形・英文）:**

```
Rich flat editorial illustration style with soft warm lamp/window lighting and a subtle grain/noise texture overlay: naturalistic character proportions and skin tones, gentle shading gradients rather than flat cel-shading. Muted, sophisticated palette (slate blue, teal, warm gray) with one warm coral/amber accent light glowing softly within the scene. Cozy, intimate, magazine-editorial illustration quality. Not photorealistic, no anime style, no harsh dramatic light rays. Characters have authentically Japanese facial features (this is a Japanese-audience channel) — not Western or ambiguous.

Scene: A laptop open on a wooden dining table at night in a quiet home, its screen showing an abstract chat layout with rounded speech bubbles and two small product pictures side by side (two similar electric kettles), no readable text and no logos. Next to the laptop, the two real kettles of slightly different shapes stand side by side, and a mug of tea. Soft warm lamp light, calm and curious mood. No people, no hands, no readable text. Warm editorial illustration style.

COMPOSITION: place the main subject and all important details in the upper and central part of the frame (the central 70% of the width, the top 75% of the height). In the lower-left corner, the lower-right corner and the bottom fifth of the frame, simply continue the same scene's floor, rug, table surface or wall naturally, with no important objects there — never leave it blank, white, empty or cut out. The image is one single continuous, fully painted scene edge to edge: no borders, no frames, no inset pictures, no panels, no bars, no captions.
```

- **用途:** シーン8（論点2「店のAIは、お客さんの役に立つ？」の頭、type paper）。夜の家の食卓でノートPCの画面に2つの電気ケトルの比較の会話、その横に実物のケトル2つ。発表の例「2つの商品で迷ったとき、どこが違うか・どっちが合うか」を店の案内役AIに聞ける、を見せる。台詞の要約: 店のページで案内役のAIに違いを聞ける。会話は元の会話と分けて表示され、夜中の「返品できる？」にも店の決まりで答える。画面には1行目からと11行目からの2回出る。**左下・右下に立ち絵、下に字幕帯**が乗るので、PCとケトル2つは中央70%・上75%に収める（ケトルが左右の端に寄らないこと）。Shorts（5カット目）でも使う
- **参照指定:** なし

## 3. S10.png

- **ファイル名:** `S10.png`
- **サイズ・画角:** 1376×768（16:9）
- **プロンプト（完成形・英文）:**

```
Rich flat editorial illustration style with soft warm lamp/window lighting and a subtle grain/noise texture overlay: naturalistic character proportions and skin tones, gentle shading gradients rather than flat cel-shading. Muted, sophisticated palette (slate blue, teal, warm gray) with one warm coral/amber accent light glowing softly within the scene. Cozy, intimate, magazine-editorial illustration quality. Not photorealistic, no anime style, no harsh dramatic light rays. Characters have authentically Japanese facial features (this is a Japanese-audience channel) — not Western or ambiguous.

Scene: A small shopping street at dusk, seen at eye level from the middle of the street: a row of different small shopfronts (a bakery, a florist, a hardware store, a cafe) with blank signboards and no readable letters, warm light in the windows, a few potted plants and a bicycle parked by a door. Above the street, a softly glowing, abstract rounded speech-bubble shape floats faintly in the evening sky, suggesting conversation. Hopeful, calm mood. No people, no robots, no readable text or logos. Warm editorial illustration style.

COMPOSITION: place the main subject and all important details in the upper and central part of the frame (the central 70% of the width, the top 75% of the height). In the lower-left corner, the lower-right corner and the bottom fifth of the frame, simply continue the same scene's floor, rug, table surface or wall naturally, with no important objects there — never leave it blank, white, empty or cut out. The image is one single continuous, fully painted scene edge to edge: no borders, no frames, no inset pictures, no panels, no bars, no captions.
```

- **用途:** シーン10（論点3「お金を出した店が勧められる？」の頭、type paper）。夕方の商店街に並ぶ小さな店（パン屋・花屋・金物屋・カフェ）と、空に浮かぶ抽象的な吹き出し。「大きな会社やお金を出した店だけでなく、町の店がAIの会話で話題にされるか」を見せる。台詞の要約: 沙織「結局お金を出した店が勧められるのでは？」→ 大輔「登録しても上位表示や売上は保証しない、と案内ページにある」。画面に出るのは1行目だけで短い（2行目から資料カード）。**左下・右下に立ち絵、下に字幕帯**が乗るので、店の並びと吹き出しは中央70%・上75%に。道の下側（左下・右下・下1/5）は石畳・路面を自然に続ける。Shorts（3・4カット目）でも使う
- **参照指定:** なし（サムネイル背景と同じ商店街の題材だが、揃える必要はない）

## 4. thumbnail_bg.png

- **ファイル名:** `thumbnail_bg.png`（`thumbnail.png` ではない。文字・立ち絵の合成はこちらで行う）
- **サイズ・画角:** 1376×768（16:9）
- **プロンプト（完成形・英文）:**

```
Rich flat editorial illustration style with soft warm lamp/window lighting and a subtle grain/noise texture overlay: naturalistic character proportions and skin tones, gentle shading gradients rather than flat cel-shading. Muted, sophisticated palette (slate blue, teal, warm gray) with one warm coral/amber accent light glowing softly within the scene. Cozy, intimate, magazine-editorial illustration quality. Not photorealistic, no anime style, no harsh dramatic light rays. Characters have authentically Japanese facial features (this is a Japanese-audience channel) — not Western or ambiguous.

Thumbnail (16:9): A small shopping street at dusk, continuous across the whole frame with no panels, boxes or borders. Keep the left 30%, the right 30% and the top 42% of the frame quiet and uncluttered (softly blurred shopfronts and a calm evening sky only), but the background must continue unbroken behind them. Main subject, centered left-to-right in the middle band: one small warmly lit shopfront with a blank signboard, and floating just above its doorway a large softly glowing rounded speech bubble, as if the shop is being talked about in a conversation. Hopeful and intriguing. No people, no robots, no text, no logos.

COMPOSITION: put the visual subject in the middle band of the frame, centered horizontally. In the top 30%, the lower-left corner and the lower-right corner, simply continue the same scene's background naturally (softly out of focus, never blank, white or cut out). Fully painted edge to edge. One single continuous image: no people other than those described, no borders, no inset pictures, no text.
```

- **用途:** サムネイルの背景（A案）。中央に暖かく灯った小さな店先1軒と、その入口の上に大きく光る吹き出し（「AIの会話で店が話題にされる」）。この上に `kl_dialogue.composite_thumbnail_dialogue` が見出し（上部）・二人の立ち絵（左右）・判定の札を合成する。**左右それぞれ30%と上42%はぼかした店先と夕空だけ**にする（ここに見出しと立ち絵が乗る）。注意: 上の余白はエピソード側の指定（上42%）が共通の構図文（上30%）より広い。**広いほう（上42%）を優先**する。店先と吹き出しは中央の帯（横は中央40%、縦は42%〜下端近く）に収める
- **参照指定:** なし

---

## 末尾メモ: Shorts の Muse 対象見込み（本編画像の到着前の目視判断）

Shorts は1本・6カット。既定は本編画像の縦切り出し（AI 生成なし）。切り出せないカットだけ、本編画像が届いてから追補 `muse_image_spec_kl057_shorts.md`（参照画像 `S{NN}.png` 必須）に載せる。

| カット | 使う本編画像 | 見込み | 理由 |
|---|---|---|---|
| 1 | S06 | 切り出し対象 | 主題がカウンター上のスマホ1つ。中央の縦長に収まる見込み |
| 2 | S06 | 切り出し対象 | 同上 |
| 3 | S10 | **Muse 対象になりそう** | 主題が横に並ぶ複数の店先＋空の吹き出し。縦9:16に切ると店の並びが切れ、被写体が1つに定まらない |
| 4 | S10 | **Muse 対象になりそう** | 同上 |
| 5 | S08 | 要確認（到着後に判断） | ノートPCとケトル2つが横に並ぶ。中央に寄って描かれていれば切り出せるが、左右に広がっていれば Muse 対象 |
| 6 | S06 | 切り出し対象 | 1・2と同じ |

- 番号は「Shorts の中の何番目のカットか」。Shorts は1本だけなので、Muse 分（3・4、5は判断次第）を `--shorts-scenes` から外しても、他の Shorts に影響しない
- 切り出し対象分は `python3 kl_image_gen.py --episode kl057 --shorts-scenes 1,2,6`（5を切り出すなら加える）。追補分が届くまでは回さない
