# TTS を gemini-3.8-flash-tts へ移行 — 引き継ぎメモ

作成: 2026-09-28（クラウドセッションで実装・push済み。**実音声での動作確認は未実施**のため、Macでの確認を別途行うための引き継ぎ用）

対象ブランチ: `claude/gemini-flash-tts-google-api-02xfsb`（samurai-chronicles / kagaku-life の両方、同名）
同じメモを両リポジトリに置いている。

## 背景

2026-09-23 に Google が Gemini 3.8 Flash TTS / Flash-Lite TTS を Gemini API（Google AI Studio）で
正式版（stable、`-preview` なし）としてリリースした。従来使っていた `gemini-3.1-flash-tts-preview`
の後継として案内されている。ユーザー判断: 「SC・KLはボイスにこだわりがないので切り替えてOK」。

| モデルID | 用途 | 出力単価 |
|---|---|---|
| `gemini-3.8-flash-tts` | 高品質（**今回採用**） | $9.00 / 1M 音声トークン（約$0.81/時間） |
| `gemini-3.8-flash-lite-tts` | 大量・低コスト向け | $6.00 / 1M 音声トークン（約$0.54/時間） |

入力はどちらも $0.50 / 1M トークン。2027-01-01 に値上げ（約2倍）予定との報道あり。
従来の30ボイス（Charon / Orus / Autonoe 等）は3.8でも引き続き指定できる（声質が変わっている可能性はある）。

## 3.8 での破壊的変更（2点）

1. **入力テキストが「読み上げ原稿そのもの」として扱われる。**
   従来のようにテキスト先頭へ演技指導（"Say in a warm ... voice: " 等）を付けると、
   指示文まで読み上げられてしまう。演技指導は `Part.speech_metadata.style` で本文と分けて渡す。
2. **出力がヘッダー付き WAV（RIFF）になった。**
   従来はヘッダーなしの生PCM。受け取ったバイト列をそのまま `wave.writeframes()` で包むと
   ヘッダーが二重になり、冒頭にノイズが乗る。

## 実施した変更

### samurai-chronicles
- `sc_tts_gen.py`
  - `TTS_MODEL` を `gemini-3.8-flash-tts` に変更
  - `build_prompt()`（スタイル＋本文の文字列連結）→ `build_contents()` に置き換え。
    `NARRATOR_STYLE` + `SCENE_TYPE_ADDENDUM` を `speech_metadata.style` で渡す
  - WAV/PCM は元から `data[:4] == b"RIFF"` 判定で両対応済みのため保存処理は変更なし

### kagaku-life
- `kl_tts_gen.py`
  - `MODEL` を `gemini-3.8-flash-tts` に変更
  - `build_contents()` を追加し、`STYLE_PREFIX` / `narration_voices.persona_style` を
    `speech_metadata.style` で渡す。既存の指示文は末尾が「: 」の書式のため、
    末尾のコロン・空白を落としてから渡す（episodes/*.json 側の修正は不要）
  - `_to_wav_bytes()` を RIFF 判定付きにし、保存もこれを通す（ヘッダー二重化防止）
- `kl_voice_recommend.py`
  - `TTS_MODEL` を本番と同じ `gemini-3.8-flash-tts` に揃えた（旧 `gemini-2.5-pro-preview-tts`）
  - RIFF 判定付きで保存
- `CLAUDE.md`「ボイス選定方針」のモデル名を更新

## 検証状況

- ✅ オフライン検証（google-genai 2.25.0）: 本文と `speech_metadata.style` が分離されたリクエストに
  組み立てられること、WAV形式の返答をダミーで流して保存したファイルのヘッダーが二重にならず
  フレーム数が正しいことを確認
- ❌ **実APIでの生成は未実施**（クラウド環境にAPIキーがないため）

## 次にやること（Macで）

1. ブランチを取得: `git fetch origin && git checkout claude/gemini-flash-tts-google-api-02xfsb`（両リポジトリ）
2. SDK更新（`speech_metadata` は新しめのSDKが必要）: `pip install -U google-genai`
3. 1シーンだけ生成して聴く:
   ```bash
   python3 sc_tts_gen.py --episode <ep> --scenes 1
   python3 kl_tts_gen.py --episode <kl> --scenes 1
   ```
4. 確認ポイント
   - 演技指導の英文が読み上げられていないか
   - トーン・速さが指示どおりか（KLの研究ボイスは「落ち着いているがテンポよく」、SCは重厚なドキュメンタリー調）
   - 冒頭にノイズ（ヘッダー二重化）がないか
   - 既存のQA（台本不一致チェック・SCの繰り返し検知 `MAIN_EXPECTED_WPM` 等）が誤検知を連発しないか
     （話速が変わっていれば WPM 閾値の見直しが必要になる可能性あり）
5. 問題なければ main へマージ（PRは未作成）

## うまくいかなかった場合

- `speech_metadata` 関連のエラー → SDK バージョンを確認。
- 3.8 の品質・挙動に問題があれば、`TTS_MODEL` / `MODEL` を `gemini-3.1-flash-tts-preview` に戻せばよい。
  ただし `build_contents()` のまま 3.1 に戻すと演技指導が効くかは未確認なので、
  その場合はコミットごと revert するのが確実。
- コスト優先にしたくなったら `gemini-3.8-flash-lite-tts` への差し替えも可（コード上はモデル名の変更のみ）。

## 参考
- https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash-tts
- https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-8-text-to-speech/
- https://github.com/grabartley/runelite-voiced-dialogue/issues/236 （3.1→3.8 移行時の破壊的変更の整理）
