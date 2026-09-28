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

## 検証状況（2026-09-28 Macで実施・更新）

- ❌ **「google-genai 2.25.0でオフライン検証済み」という当初の記述は誤り。** PyPIに
  存在する最新版は 1.47.0 が上限で、2.25.0 というバージョンは存在しない。
- ❌ **`types.Part.speech_metadata` は google-genai 1.47.0（2026-09-28時点のPyPI最新）に
  型定義されていない。** `pip install -U google-genai` しても 1.47.0 のまま
  （最新）。SDK経由で `types.Part(text=..., speech_metadata=types.SpeechMetadata(...))`
  を呼ぶと `AttributeError: module 'google.genai.types' has no attribute
  'SpeechMetadata'` で失敗することを実機で確認した（samurai-chronicles側で先に確認、
  同じgoogle-genaiパッケージを使うKL側でも同様の失敗を確認済み）。
- ✅ **APIモデル自体（`gemini-3.8-flash-tts`）は実在し、`speech_metadata` は
  生のREST API（`generateContent` エンドポイントへ直接POST）経由なら正しく
  機能することを実機検証済み。** persona/research 両ボイスで実際に音声生成し、
  Geminiによる文字起こしでSTYLE_PREFIXの英文が読み上げに漏れていないこと、
  台本と完全一致すること、WAVヘッダーが二重化していないこと（RIFF出現1回のみ）を
  確認した。
- ✅ **`kl_tts_gen.py` を修正済み・push済み。** `build_contents()` を
  `_tts_rest_call()`（生REST）に置き換え、`synth()` から呼び出す形に変更した
  （QA用の音声読み込み `qa_narration_with_gemini` は speech_metadata を使わない
  ためSDKのままで問題ない）。使い捨てのテストエピソードで persona/research
  両方の音声生成→QA通過→ファイル整合性確認まで完了している。
- `kl_voice_recommend.py` は `contents=text`（プレーン文字列）で呼んでおり
  speech_metadata を使っていないため、このSDK制約の影響を受けない（修正不要）。

## 次にやること

1. **samurai-chronicles: 完了。** `sc_tts_gen.py` は生REST方式で動作確認済み。
2. **kagaku-life: 完了。** `kl_tts_gen.py` も生REST方式で動作確認済み。
3. 両リポジトリとも実エピソードでの通し生成（複数シーン・複数話）はまだ
   試していないため、本番投入時は最初の1話分は特に注意して確認するとよい。
4. mainへのマージはユーザー判断で（PRは未作成のまま、両リポジトリとも
   ブランチ `claude/gemini-flash-tts-google-api-02xfsb` に留まっている）。

## うまくいかなかった場合

- `speech_metadata` 関連のエラー → SDKではなく生RESTを使っているか確認
  （`_tts_rest_call` 経由になっているか）。
- 3.8 の品質・挙動に問題があれば、`MODEL` を `gemini-3.1-flash-tts-preview` に戻し、
  `_tts_rest_call` ではなく従来のテキスト先頭埋め込み方式（演技指導をtextに
  連結してSDK経由で呼ぶ）に戻す必要がある。その場合はこのコミットごと revert するのが確実。
- コスト優先にしたくなったら `gemini-3.8-flash-lite-tts` への差し替えも可
  （`MODEL` の変更のみ、`_tts_rest_call` はそのまま使える）。

## 参考
- https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash-tts
- https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-8-text-to-speech/
- https://github.com/grabartley/runelite-voiced-dialogue/issues/236 （3.1→3.8 移行時の破壊的変更の整理）
