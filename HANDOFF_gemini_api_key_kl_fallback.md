# GEMINI_API_KEY_KL 環境変数フォールバック不具合 — 引き継ぎメモ

作成: 2026-09-10（GoogleAPIコスト分析セッション中に発覚。別セッションで修正対応するための引き継ぎ用）

## 背景

GoogleAPIのコストをプロジェクト別（LW / SC / KL / General Use）に比較する目的で、
GCPプロジェクトを4つに分割し、Gemini APIキーもプロジェクトごとに用意した。
しかし請求先アカウント `0103C5-511C9E-E05F76` の直近90日間（2026/06/12〜09/09）の
請求データを確認したところ、KL Project（`gen-lang-client-0227409824` = kagaku-life）
の使用費用が **¥0** だった。一方でLW Projectは¥45,909（前期比+89%）と、単独チャンネル
にしては大きい。kagaku-lifeは同期間中ほぼ毎日エピソードを制作しており、¥0は
「未使用」として不自然。

## 診断

`~/.zshenv`（**全てのzshシェルで読み込まれる**）:

```sh
export GEMINI_API_KEY="<LWのキーと同一の値>"
export GEMINI_API_KEY_SC="<SC用のキー>"
```

`~/.zshrc`（**対話シェルのみで読み込まれる**）:

```sh
export GEMINI_API_KEY_KL="<KL用のキー>"
export GEMINI_API_KEY_SC="<SC用のキー、重複>"
export GEMINI_API_KEY_LW="<GEMINI_API_KEYと同一の値、重複>"
```

`GEMINI_API_KEY_KL` は `.zshrc` にしか定義がない。zshの仕様上 `.zshrc` は
**対話シェルでしか読み込まれない**ため、cron・他スクリプトからのサブプロセス起動
など非対話シェル経由で実行されると `GEMINI_API_KEY_KL` は存在せず未設定になる。

kagaku-life側の以下5本は次のフォールバック順でキーを読む実装:

```python
API_KEY = os.environ.get("GEMINI_API_KEY_KL") or os.environ.get("GEMINI_API_KEY", "")
```

- `kl_image_gen.py`
- `kl_tts_gen.py`
- `kl_bgm_qa.py`
- `kl_voice_recommend.py`
- `kl_zoom_anchor.py`

非対話シェルで実行された場合、`GEMINI_API_KEY_KL` が未設定のため **無印の
`GEMINI_API_KEY`（= LWのキー）に静かにフォールバックする**。エラーも出ないため
気づきにくい。

さらに次の6本は、**KLキーへのフォールバック処理自体が実装されておらず、
常に無印の `GEMINI_API_KEY`（LWのキー）を使用する**:

- `kl_paper_screen.py`
- `kl_fact_check.py`
- `kl_paper_hypecheck.py`
- `kl_paper_interest_score.py`
- `kl_bgm_final_check.py`
- `kl_shortlist_rescore.py`

（`stage1_pool.json` 〜 `stage4_ranked.json` の巨大なJSONを見る限り、論文スクリーニング
系だけでもかなりの回数のテキスト生成が発生していると見られ、これが全てLWキー経由に
なっている）

## 証拠

- Cloud Console「APIとサービス」ダッシュボード（KL Project, 過去30日）:
  Gemini APIへのリクエストは **6件のみ（うち2件エラー = 33%）**。中央値レイテンシ
  2,621ms。kagaku-lifeの実際の制作ペース（エピソードをほぼ毎日制作）に対して
  明らかに少なすぎる。
- 請求先アカウントのプロジェクト別レポート（過去90日）: KL Project ¥0、
  LW Project ¥45,909（前期比+89%）。LWの伸びの一部はkagaku-life分の誤計上の
  可能性がある。
- KL Projectの認証情報ページには、サービスアカウント紐付けのAPIキーが
  1件登録済み（作成日 2026/08/30, `ais-gemini-key-d62016550d234f7@...`）。
  キー自体は存在するが、ほぼ使われていない。

## 影響

- KL Project単体でのコスト計測が機能していない（¥0はほぼ見せかけ）
- LW Projectのコストにkagaku-life分が混入しており、当初目的の「4プロジェクト
  比較」の数値が正確でない
- 特に `kl_paper_screen.py` 系（論文スクリーニングの大量テキスト生成）は
  完全にLWキー固定。修正時は「単純にKLキー参照を追加するだけでよいか」
  「意図的にLWキー共用にしていたのか」を確認してから直すこと（意図不明なまま
  一律修正すると、逆に既存の動作を壊す可能性がある）

## 対処方針（未実装）

1. `~/.zshenv` に `GEMINI_API_KEY_KL` を追加する（非対話シェルでも確実に
   読み込まれるようにする）。もしくは `.zshrc` の3行を全て `.zshenv` に
   移動する方がシンプルで確実。
2. 上記6本のスクリプトに `GEMINI_API_KEY_KL` 優先のフォールバックを追加し、
   既存5本と同じパターンに統一する。
3. 修正後、`echo $GEMINI_API_KEY_KL` が対話・非対話どちらのシェルでも同じ値を
   返すことを確認する（`bash -c 'echo $GEMINI_API_KEY_KL'` や cron相当の
   非対話実行で検証）。
4. KL ProjectのAPIキー自体が `AQ.Ab8...` という特殊形式（サービスアカウント
   紐付け）である点も、通常の `AIzaSy...` 形式キーと挙動が異なる可能性があるため
   念のため有効性を再確認する。
5. （任意・根本対策）`.env` ファイル方式に移行し、各プロジェクトのスクリプトが
   起動時に確実に自分専用のキーだけを読み込むようにする。対話/非対話シェルの
   違いに起因する今回のような事故を構造的に防げる。

## 次にやること

上記1・2を実装し、3で動作確認。その後、次回のコスト確認時にKL Projectの
「APIとサービス」ダッシュボードでリクエスト数が実制作量に見合うレベルまで
増えているか、請求レポートでKL Projectに正しく費用が計上されているかをチェック
する。あわせてLW Projectの費用が「本来のlamp-whisper単体分」まで下がるかも
確認すること（下がった差分がこれまでkagaku-life分だった、という裏付けになる）。

## ✅ 対応済み（2026-09-10、別セッションで実施）

1. `~/.zshenv` に `GEMINI_API_KEY_KL` と `GEMINI_API_KEY_LW` を追加し、
   `~/.zshrc` からは3行の`export`を削除（`source ~/.zshenv`のみ残す）。
   `zsh -c`（非対話）・`zsh -i -c`（対話）の両方で`GEMINI_API_KEY_KL`が
   同じ値を返すことを確認済み。
2. 以下6本に`GEMINI_API_KEY_KL`優先のフォールバックを追加し、既存5本
   （`kl_image_gen.py`等）と同じパターンに統一した:
   `kl_paper_screen.py` / `kl_fact_check.py` / `kl_paper_hypecheck.py` /
   `kl_paper_interest_score.py` / `kl_bgm_final_check.py` /
   `kl_shortlist_rescore.py`
   （意図的なLWキー共用の形跡は見当たらず、単純な実装漏れと判断して修正した）
3. `GEMINI_API_KEY_KL`（`AQ.Ab8...`形式）を実際にGemini APIへ呼び出し、
   正常に応答することを確認済み（特殊形式でも問題なく動作する）。
4. `.env`方式への移行（対処方針5、根本対策）は未着手。今回の修正で
   実害（対話/非対話シェルの違いによる誤フォールバック）は解消したため、
   優先度は下げてよいと判断。

**次にやること（未実施）:** 数日〜1週間ほど制作を継続したのち、KL Projectの
「APIとサービス」ダッシュボードでリクエスト数・請求レポートを再確認し、
実制作量に見合う費用が計上されるようになったか、LW Projectの費用が
本来のlamp-whisper単体分まで下がったかを検証する。

## 参考: 90日間のコスト分析資料

このHANDOFFの元になったコスト分析（4プロジェクト比較・AIモデル別内訳）は
Claudeが作成したレポートを参照。ユーザーに共有済みのArtifactリンクがある
（このメモには含めていないため、必要なら本人に確認）。
