# kl057 Shorts 画像の Muse 生成仕様（追補）

作成: 2026-11-16 / 作成者: KLチーム 映像担当 レオ（kl-art-director）
手順の正本: `docs/muse_image_trial.md`「Shorts の扱い」2。本編の仕様は `muse_image_spec_kl057.md`（同じフォルダ）。

## 共通事項

- **エピソード ID:** kl057（Shorts 1本・6カット）
- **枚数:** 4枚（カット 1・2・5・6）。カット 3・4 は本編 S10.png の縦切り出し（AI 生成なし）でまかなうので、この仕様に含めない
- **参照画像（必須）:** 各項目の「参照指定」の本編画像を必ず添付し、**その絵と同じ場面・同じ画風・同じ物**で 9:16 に描き直す。新しい場面にしない。画風の基準は S08.png（細かい粒子、細く控えめな輪郭線、やわらかいグラデーションの陰影、スレートブルー／ティール／ウォームグレーに暖かいアンバーの光1つ）
- **Shorts の画面の重なり:** 字幕（1行）が**画面の高さ56%の位置**（およそ50〜62%の帯）に、二人の立ち絵が**下の約30%**（左下・右下）に乗る。主題（スマホの画面・ノートPCの画面）は**上の48%以内**に置き、50%より下は同じ場面の机・床・壁を自然に続ける（空白・白・切り抜きにしない）
- **禁止:** 枠・帯・パネル・はめ込み画像・字幕・キャプションを描かない。人物・手・ロボットを描かない。読める文字・数字・ロゴを一切描かない（画面は抽象的な吹き出しと小さな商品の絵だけ）
- **納品形式:** PNG、768×1376（9:16）。比が ±2% 以内ならこちらでリサイズする。ファイル名は下の指定どおり、この仕様ファイルと同じフォルダ（Drive `マイドライブ/Kagaku-Life/KL057/images/`）の直下

## 縦切り出しにしなかった理由（セッション側メモ）

- S06（カット1・2・6）: 主題のスマホが画面の縦46〜65%に来るため、9:16 に切ると字幕（56%）がスマホの画面の真ん中に重なる。3カットとも同じ絵になるのも避けたい（カット3・4も同じ絵が続くため、Shorts 全体で絵が3種類しかなくなる）
- S08（カット5）: ノートPCとケトル2つが横に約920px 広がり、縦の窓（幅432px）にはどちらか片方しか入らない。台詞（店のAIは買う・予約する・注文を確かめる、ができない）に要るのは PC の画面側。自動の被写体判定が「被写体2つ」と判定して Gemini の再構成に回るおそれもある

---

## 1. shorts1_S01.png

- **ファイル名:** `shorts1_S01.png`
- **サイズ・画角:** 768×1376（9:16）
- **参照指定:** `S06.png`（必ず添付）
- **用途:** カット1、沙織「AIの中に、店の窓口？」（Shorts の1秒目）。小さな店のカウンターのスマホに AI との会話が光っている。スマホと画面が一目で分かること
- **プロンプト（完成形・英文）:**

```
Reframe this exact reference image (S06.png) into a 9:16 vertical portrait composition for mobile short-form video. Keep the same subject, setting, lighting, and art style exactly as in the reference image — do not change the scene content. Extend/recompose the framing so the main subject is centered and prominent in a vertical frame, generating plausible additional scene content above/below as needed to fill the vertical canvas.

Art style (match the reference): rich flat editorial illustration with soft warm lamp/window lighting and a visible fine grain/noise texture overlay, thin subtle outlines (no heavy black ink lines), gentle shading gradients rather than flat cel-shading. Muted palette (slate blue, teal, warm gray) with one warm coral/amber accent light. Not photorealistic, no anime style, no watercolor bleeding.

Scene: Interior of a small independent neighborhood shop in the early evening, seen from just behind the counter: a wooden counter with a smartphone lying flat on it, its screen glowing softly with a few abstract rounded chat bubbles and a small product thumbnail (no readable text, no logos), a paper price tag and a small gift box beside it. Shelves of neatly arranged goods behind, with the pendant lamp glowing. Calm, hopeful mood. No people, no hands, no robots, no readable text or signs with words.

COMPOSITION: the smartphone on the counter is the main subject, centered horizontally and large, with its glowing screen placed between 25% and 45% of the frame height from the top; the shelves and pendant lamp fill the top quarter. Keep the main subject in the upper half of the vertical frame. Below 50% of the frame height, continue the same wooden counter front and shop floor naturally with no important objects (never blank, white or cut out). One single continuous image: no borders, no inset pictures, no bars, no captions.
```

## 2. shorts1_S02.png

- **ファイル名:** `shorts1_S02.png`
- **サイズ・画角:** 768×1376（9:16）
- **参照指定:** `S06.png`（必ず添付）
- **用途:** カット2、大輔「店が自分で、値段や在庫、返品や配送の決まりを入れられる。それに、店が用意した案内役のAIに、お客さんが質問できる。」。カット1より**スマホに寄った**構図で、画面の会話・小さな商品の絵と、横の値札・贈り物の箱が見える（店の情報が入っている感じ）。カット1と同じ店・同じスマホ
- **プロンプト（完成形・英文）:**

```
Reframe this exact reference image (S06.png) into a 9:16 vertical portrait composition for mobile short-form video, as a closer view of the same counter. Keep the same subject, setting, lighting, and art style exactly as in the reference image — do not change the scene content. Recompose the framing so the main subject is centered and prominent in a vertical frame, generating plausible additional scene content above/below as needed to fill the vertical canvas.

Art style (match the reference): rich flat editorial illustration with soft warm lamp/window lighting and a visible fine grain/noise texture overlay, thin subtle outlines (no heavy black ink lines), gentle shading gradients rather than flat cel-shading. Muted palette (slate blue, teal, warm gray) with one warm coral/amber accent light. Not photorealistic, no anime style, no watercolor bleeding.

Scene: A closer, slightly higher view of the same wooden shop counter in the early evening: the same smartphone lying flat, filling most of the frame width, its screen glowing softly with several abstract rounded chat bubbles in two colors and one small product thumbnail (no readable text, no logos). Right beside it, the same blank paper price tag on a string and the same small gift box tied with an orange ribbon. Softly blurred shelves of goods in the background. Calm, hopeful mood. No people, no hands, no robots, no readable text, numbers or signs with words.

COMPOSITION: the smartphone screen, price tag and gift box are the main subject, centered horizontally, all placed between 15% and 47% of the frame height from the top. Keep the main subject in the upper half of the vertical frame. Below 50% of the frame height, continue the same wooden counter surface and counter front naturally with no important objects (never blank, white or cut out). One single continuous image: no borders, no inset pictures, no bars, no captions.
```

## 3. shorts1_S05.png

- **ファイル名:** `shorts1_S05.png`
- **サイズ・画角:** 768×1376（9:16）
- **参照指定:** `S08.png`（必ず添付）
- **用途:** カット5、沙織「店のAIは、買う、予約する、注文を確かめる、のどれもできない。」。夜の食卓のノートPCの画面（店の案内役 AI との会話と、電気ケトル2つの小さな絵）が主題。実物のケトル2つはその下・手前に一部見えればよい
- **プロンプト（完成形・英文）:**

```
Reframe this exact reference image (S08.png) into a 9:16 vertical portrait composition for mobile short-form video. Keep the same subject, setting, lighting, and art style exactly as in the reference image — do not change the scene content. Recompose the framing so the main subject is centered and prominent in a vertical frame, generating plausible additional scene content above/below as needed to fill the vertical canvas.

Art style (match the reference exactly): rich flat editorial illustration with soft warm lamp light and a visible fine grain/noise texture overlay, thin subtle outlines (no heavy black ink lines), gentle shading gradients rather than flat cel-shading. Muted palette (slate blue, teal, warm gray) with one warm amber accent light from the table lamp. Not photorealistic, no anime style, no watercolor bleeding.

Scene: The same laptop open on the same wooden dining table at night in a quiet home, seen from a slightly higher angle. Its screen shows an abstract chat layout with rounded speech bubbles and two small product pictures side by side (two similar electric kettles), no readable text and no logos. The table lamp glows warmly behind the laptop and the night window is above. The same two real kettles of slightly different shapes stand just in front of and below the laptop, partly visible, with the mug of tea. Calm and curious mood. No people, no hands, no readable text.

COMPOSITION: the laptop screen is the main subject, centered horizontally and large, placed between 18% and 46% of the frame height from the top; the lamp and the night window fill the top part. Keep the main subject in the upper half of the vertical frame. Below 50% of the frame height, show only the tops of the two kettles and the wooden table surface, then continue the table and floor naturally with no important objects (never blank, white or cut out). One single continuous image: no borders, no inset pictures, no bars, no captions.
```

## 4. shorts1_S06.png

- **ファイル名:** `shorts1_S06.png`
- **サイズ・画角:** 768×1376（9:16）
- **参照指定:** `S06.png`（必ず添付）
- **用途:** カット6（最後のカット）、大輔「店はどう見つけてもらう時代になる？ 判定は本編で。」。動画側が「↓ 続きは本編で」を重ねる。同じ店の中から、**ガラスの入口の向こうの夕方の通り**を見る構図（お客さんがどこから来るか）。カウンターのスマホが手前で光っている。カット1・2と同じ店
- **プロンプト（完成形・英文）:**

```
Reframe this exact reference image (S06.png) into a 9:16 vertical portrait composition for mobile short-form video, turning slightly toward the shop's glass front door. Keep the same shop, setting, lighting, and art style exactly as in the reference image — do not change the scene content. Recompose the framing so the main subject is centered and prominent in a vertical frame, generating plausible additional scene content above/below as needed to fill the vertical canvas.

Art style (match the reference): rich flat editorial illustration with soft warm lamp/window lighting and a visible fine grain/noise texture overlay, thin subtle outlines (no heavy black ink lines), gentle shading gradients rather than flat cel-shading. Muted palette (slate blue, teal, warm gray) with one warm coral/amber accent light. Not photorealistic, no anime style, no watercolor bleeding.

Scene: Inside the same small neighborhood shop in the early evening, looking from behind the counter toward the same glass front door: through the glass, a softly glowing evening street with warm shop windows and a street lamp. In the near foreground at the bottom of the upper half, the edge of the same wooden counter with the same smartphone lying flat, its screen glowing softly with abstract rounded chat bubbles (no readable text, no logos). Hopeful, inviting mood, as if waiting for a new customer. No people, no hands, no robots, no readable text or signs with words.

COMPOSITION: the glass door with the glowing street behind it is centered horizontally in the top 40% of the frame; the glowing smartphone on the counter sits just below it, between 38% and 48% of the frame height. Keep the main subject in the upper half of the vertical frame. Below 50% of the frame height, continue the same counter front and shop floor naturally with no important objects (never blank, white or cut out). One single continuous image: no borders, no inset pictures, no bars, no captions.
```

---

## 納品後のセッション側の手順

1. 4枚を Desktop の `images/` に取り込み、目視 QA（字幕の帯・立ち絵の位置に主題が重ならないか、S06／S08 と同じ場面・画風か、文字混入なし）
2. カット 3・4 を本編の切り出しで作る: `python3 kl_image_gen.py --episode kl057 --shorts-scenes 3,4 --no-qa`（被写体判定 `kl_zoom_anchor` は Gemini を呼ぶ＝「残った Gemini 利用」に数える）。ログに「従来の生成にフォールバック」が出たら「Gemini に戻した枚数」に数える。作られた `shorts1_S03.png`・`shorts1_S04.png` を開き、吹き出しが窓に入っているか確かめる
