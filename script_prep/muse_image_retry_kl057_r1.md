# kl057 Muse 画像 作り直しリスト（ラウンド1）

作成: 2026-11-16 / 作成者: KLチーム 映像担当 レオ（kl-art-director）
元の仕様: `muse_image_spec_kl057.md`（同じフォルダ）。手順の正本: `docs/muse_image_trial.md` 手順5。

## 結果の一覧

| ファイル | 判定 | 作り直し |
|---|---|---|
| S06.png | 合格（そのまま使う） | なし |
| S08.png | 合格（そのまま使う） | なし。**画風の基準にする**（下の2枚はこの絵の画風に合わせる） |
| S10.png | NG | あり（1回目） |
| thumbnail_bg.png | NG | あり（1回目） |

納品: 同じフォルダの `images/` 直下に、**同じファイル名で上書き**。PNG、1376×768（16:9）。

## 共通: 画風の合わせ方

S08.png（夜の食卓・ノートPC・ケトル2つ）の画風に合わせる。可能なら **S08.png を画風の参照画像として渡す**。
特徴: 細かい粒子のテクスチャ、輪郭線は細く控えめ（太い黒のペン線にしない）、やわらかいグラデーションの陰影、スレートブルー／ティール／ウォームグレーに暖かいアンバーの光1つ。水彩のにじみ、平たいベタ塗り、漫画のペン画にしない。

---

## 1. S10.png

- **ファイル名:** `S10.png`
- **参照指定:** S08.png（画風のみ。構図・物は参照しない）
- **理由:**
  1. 空の光る形が吹き出しに見えない（しっぽの無いアメーバ形の輪郭線だけ）。「店が会話で話題にされる」が伝わらない
  2. 店の並びが欧米のブティック街（石畳・洋風の店構え）。視聴者は日本の店主で、論点3「お金を出した店が勧められる？」は自分の店の話として見る。日本の商店街にする（サムネイルも日本の商店街なので揃える）
  3. 画風が平たい塗りで、S06・S08 と揃っていない
- **修正プロンプト（完成形・英文）:**

```
Rich flat editorial illustration style with soft warm lamp/window lighting and a visible fine grain/noise texture overlay, thin subtle outlines (no heavy black ink lines), gentle shading gradients rather than flat cel-shading or flat fills. Match the exact rendering style of the reference image S08.png. Muted, sophisticated palette (slate blue, teal, warm gray) with one warm coral/amber accent light glowing softly within the scene. Cozy, intimate, magazine-editorial illustration quality. Not photorealistic, no anime style, no watercolor bleeding, no harsh dramatic light rays.

Scene: A small, well-kept Japanese neighborhood shopping street (shotengai) at dusk, seen at eye level from the middle of the street. A row of four different small two-story Japanese shop buildings side by side: a bakery with bread in the window, a florist with buckets of flowers out front, a small hardware store with tools and brooms by the door, and a little cafe. Japanese details: short fabric noren curtains in plain colors with no letters, small slanted awnings, sliding glass doors, a utility pole with overhead wires, a bicycle parked by a shop, potted plants. All signboards are completely blank (no letters, no numbers, no logos). Warm light glows in every window; the shops are open and lively, no closed shutters. In the evening sky above the shops, a softly glowing rounded speech bubble clearly shaped like a comic speech balloon, with a small pointed tail pointing down toward the shops, filled with a gentle warm amber glow (not just an outline). Hopeful, calm mood. No people, no hands, no robots, no readable text or logos anywhere.

COMPOSITION: place the main subject and all important details in the upper and central part of the frame (the central 70% of the width, the top 75% of the height); the speech bubble sits above the center of the row of shops. In the lower-left corner, the lower-right corner and the bottom fifth of the frame, simply continue the same street's paved road surface naturally, with no important objects there — never leave it blank, white, empty or cut out. The image is one single continuous, fully painted scene edge to edge: no borders, no frames, no inset pictures, no panels, no bars, no captions.
```

## 2. thumbnail_bg.png

- **ファイル名:** `thumbnail_bg.png`
- **参照指定:** S08.png（画風のみ）。作り直した S10.png と同じ街並みの雰囲気に揃えると良い
- **理由:**
  1. 吹き出しが画面の上部中央に大きく出ている（縦およそ19%〜55%）。見出し「お金を出せば／勧められる？」を合成すると、吹き出しの上半分が文字の下に隠れ、主題が読めなくなる（合成して確認済み）。仕様の「上42%は空だけ」を満たしていない
  2. 古い木造の町並みで、店のシャッターが閉まり、灰色で寂しい印象（シャッター街に見える）。店主の視聴者に「希望」ではなく「さびれ」を感じさせる
  3. 画風が水彩のにじみで、本編3枚と揃っていない
- **修正プロンプト（完成形・英文）:**

```
Rich flat editorial illustration style with soft warm lamp/window lighting and a visible fine grain/noise texture overlay, thin subtle outlines (no heavy black ink lines), gentle shading gradients rather than flat cel-shading or flat fills. Match the exact rendering style of the reference image S08.png. Muted, sophisticated palette (slate blue, teal, warm gray) with one warm coral/amber accent light glowing softly within the scene. Not photorealistic, no anime style, no watercolor bleeding, no harsh dramatic light rays.

Thumbnail (16:9): A small, well-kept Japanese neighborhood shopping street (shotengai) at dusk, continuous across the whole frame with no panels, boxes or borders. Main subject, centered left-to-right: one small, open, warmly lit Japanese shopfront with a plain fabric noren curtain (no letters) and a completely blank signboard, its windows glowing amber. Floating just above its roof, a softly glowing rounded speech bubble clearly shaped like a comic speech balloon, with a small pointed tail pointing down toward the shop, filled with a gentle warm amber glow. The speech bubble is medium-sized: about one quarter of the frame width, and its TOP EDGE must be below the middle of the frame height (the whole bubble sits between 48% and 72% of the frame height from the top). The top 45% of the frame is only a calm, softly lit evening sky with a faint warm glow near the horizon — no bubble, no rooftops sticking up, nothing important there. The left 30% and right 30% of the frame show neighboring Japanese shops, softly blurred and out of focus, lights on and open (no closed shutters), continuing the street unbroken. Hopeful and inviting mood, not lonely or deserted. No people, no robots, no text, no letters, no logos anywhere.

COMPOSITION: the visual subject (shopfront and speech bubble) is in the central 40% of the width and in the lower-middle band of the frame. The top 45%, the left 30% and the right 30% continue the same scene's background naturally (softly out of focus, never blank, white or cut out). Fully painted edge to edge. One single continuous image: no people, no borders, no inset pictures, no text.
```

---

メモ（セッション側）: S10 は Shorts 3・4カット目の元画像。作り直しが届いてから Shorts の Muse 追補（`muse_image_spec_kl057_shorts.md`）を作る。S08 は ノートPC〜ケトルが横に約920px 広がっており、縦切り出し（幅432px）にはケトル2つ（x 680〜1050）だけが入り、PC の画面は入らない。Shorts 5カット目は「ケトル2つで切る」で台詞（2つの商品で迷う）には足りるが、PC 画面が要るなら Muse 追補にする（セッションが判断）。
