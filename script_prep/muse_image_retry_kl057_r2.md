# kl057 Muse 画像 作り直しリスト（ラウンド2・Shorts 追補分）

作成: 2026-11-16 / 作成者: KLチーム 映像担当 レオ（kl-art-director）
元の仕様: `muse_image_spec_kl057_shorts.md`（同じフォルダ）。手順の正本: `docs/muse_image_trial.md` 手順5・「Shorts の扱い」。

## 結果の一覧

| ファイル | 判定 | 作り直し |
|---|---|---|
| shorts1_S01.png | NG | あり（1回目） |
| shorts1_S02.png | NG | あり（1回目） |
| shorts1_S05.png | 合格（そのまま使う） | なし |
| shorts1_S06.png | 合格（そのまま使う） | なし。**店の画風・明るさの基準にする** |

納品: 同じフォルダの `images/` 直下に、**同じファイル名で上書き**。PNG、768×1376（9:16）。

## 共通: なぜ NG か（2枚とも同じ理由）

Shorts では、字幕（1行・白文字）が**画面の高さのちょうど真ん中より少し下（上から約54〜58%）**に重なり、二人の立ち絵が**下の約30%**に乗る。
届いた2枚は、主題のスマホが画面の高さ49〜65%にあり、**スマホの画面の真ん中を字幕が横切る**。仕様では「上から25〜47%」を指定していたが、反映されていない。

画風・場面・物（同じ店、同じスマホ、値札、リボンの箱、ペンダントライト、ガラス扉）は申し分ないので、**そのまま、カメラの向きだけ変えてスマホを画面の上半分へ上げる**。
目安: 「スマホの下の端が、画面の上から半分の線より上にある」こと。真ん中の帯（上から50〜62%）には、カウンターの無地の木目か、カウンターの前板だけが来るようにする。

参照画像: 店の2枚は **shorts1_S06.png（今回合格した縦の絵）と S06.png** を添付する。画風・色・物は shorts1_S06.png にそろえる。

---

## 1. shorts1_S01.png

- **ファイル名:** `shorts1_S01.png`
- **参照指定:** `shorts1_S06.png`（必ず添付。画風・店・物の基準）、`S06.png`（物の確認用）
- **用途:** カット1（Shorts の1秒目）、沙織「AIの中に、店の窓口？」。上の端に大きなフック文字（上から約7%と16%）が乗る
- **理由:**
  1. スマホ（画面の会話の吹き出し）が上から49〜62%にあり、1行字幕がスマホの画面の真ん中を横切る。1秒目に「何の絵か」が分からなくなる
  2. 構図が最後のカット（shorts1_S06.png）とほぼ同じ（左に棚、右にガラス扉、手前にカウンターのスマホ）。最初と最後で絵の変化が無い。カット1は**スマホに寄った絵**にする
- **修正プロンプト（完成形・英文）:**

```
Use the attached reference images (shorts1_S06.png and S06.png) for the exact same shop, the same smartphone, the same objects and the same art style. Draw a NEW 9:16 vertical portrait image for mobile short-form video: a close-up of the smartphone on the shop counter, seen from above at a steep downward angle.

Art style (match shorts1_S06.png exactly): rich flat editorial illustration with soft warm lamp light and a visible fine grain/noise texture overlay, thin subtle outlines (no heavy black ink lines), gentle shading gradients rather than flat cel-shading. Muted palette (slate blue, teal, warm gray) with one warm coral/amber accent light from the pendant lamp. Not photorealistic, no anime style, no watercolor bleeding.

Scene: The same wooden shop counter in the early evening. The same smartphone lies flat on the counter, large, filling about 80% of the image width, its screen glowing softly in warm peach light with several abstract rounded chat bubbles in teal and orange and one small product thumbnail (no readable text, no numbers, no logos). The corner of the same blank paper price tag peeks in at one side. Above the phone, the far edge of the counter and the softly blurred shelves of goods with the glowing pendant lamp fill the top of the frame. Calm, hopeful mood. No people, no hands, no robots, no readable text, numbers or signs with words.

COMPOSITION (very important): the whole smartphone must sit in the UPPER part of the image — its top edge at about 18% and its bottom edge at about 46% of the image height from the top. The bottom edge of the phone must be ABOVE the horizontal center line of the image, because a subtitle line is placed across the middle of the image (about 50% to 62% from the top) and must not cover the phone screen. The top 15% (blurred shelves and pendant lamp) stays calm because large hook text is placed there. From 50% down to the bottom, show only the plain wood grain of the counter surface and then the counter's front panel, with no objects. Never blank, white or cut out. One single continuous image: no borders, no inset pictures, no bars, no captions.
```

## 2. shorts1_S02.png

- **ファイル名:** `shorts1_S02.png`
- **参照指定:** `shorts1_S06.png`（必ず添付。画風・店・物の基準）、`S06.png`（物の確認用）
- **用途:** カット2、大輔「店が自分で、値段や在庫、返品や配送の決まりを入れられる。それに、店が用意した案内役のAIに、お客さんが質問できる。」（字幕が3〜4枚続く、長いカット）。スマホと、値札・リボンの箱が**横に並んで**見える（店の情報が入っている感じ）
- **理由:**
  1. スマホ（上から45〜65%）・値札（52〜65%）・箱（46〜60%）の3つとも、字幕の帯の中にある。長いカットなので、字幕が4枚続く間ずっと主題が隠れる
  2. カット1は今回スマホの寄りに変えるので、カット2は**一歩引いた中くらいの絵**にして、スマホ・値札・箱の3つを並べる（カット1との変化を出す）
- **修正プロンプト（完成形・英文）:**

```
Use the attached reference images (shorts1_S06.png and S06.png) for the exact same shop, the same smartphone, the same objects and the same art style. Draw a NEW 9:16 vertical portrait image for mobile short-form video: a medium view of the shop counter with three objects in a row.

Art style (match shorts1_S06.png exactly): rich flat editorial illustration with soft warm lamp light and a visible fine grain/noise texture overlay, thin subtle outlines (no heavy black ink lines), gentle shading gradients rather than flat cel-shading. Muted palette (slate blue, teal, warm gray) with one warm coral/amber accent light from the pendant lamp. Not photorealistic, no anime style, no watercolor bleeding.

Scene: The same small neighborhood shop in the early evening, seen from behind the counter at a moderate downward angle. On the wooden counter, three objects stand side by side from left to right, all clearly visible and not overlapping: the same smartphone lying flat with its screen glowing softly with abstract rounded chat bubbles and one small product thumbnail (no readable text, no logos), the same blank paper price tag on a string, and the same small gift box tied with an orange ribbon. Behind them, the shelves of neatly arranged goods and the glowing pendant lamp, slightly blurred. Calm, hopeful mood. No people, no hands, no robots, no readable text, numbers or signs with words.

COMPOSITION (very important): the shelves and pendant lamp fill the top of the image down to about 22%. The far edge of the counter is at about 24%. The three objects (smartphone, price tag, gift box) all sit between 26% and 46% of the image height from the top, centered horizontally and together spanning about 85% of the image width. The bottom of every object must be ABOVE the horizontal center line of the image, because a subtitle line is placed across the middle of the image (about 50% to 62% from the top) and must not cover them. From 50% down to the bottom, show only the plain wood grain of the counter surface, then the counter's front panel and the floor, with no objects. Never blank, white or cut out. One single continuous image: no borders, no inset pictures, no bars, no captions.
```

---

## 合格した2枚の所見（作り直し不要）

- **shorts1_S05.png:** S08 と同じ食卓・ノートPC・ケトル2つ・ランプ・夜の窓・葉の額。PC の画面（吹き出しとケトル2つの小さな絵）が上から33〜52%で、字幕の帯（約54〜58%）にかからない。実物のケトル2つは立ち絵の帯（下30%）にかかるが、仕様どおり「一部見えればよい」側の物なので問題なし。正面からの左右対称の構図で S08（斜め上から）より平たい印象、紅茶のマグが無い、の2点は許容範囲
- **shorts1_S06.png:** S06 と同じ店・同じガラス扉・夕方の通り・街灯。扉が上半分の中央にある。スマホは上から46〜56%で、字幕の1行が画面の下の端にわずかにかかるが、この絵の主題は扉の向こうの通りなので許容。最後のカットの「↓ 続きは本編で」（上から80%）は床の上で読める
