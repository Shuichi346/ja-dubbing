# Changelog

## [8.0.0] - 2026-04-09

### Added

- 多言語対応: 他言語音声 → 他言語音声の吹き替えに対応
  - `INPUT_LANG` 設定（デフォルト: `auto`）を追加。ASR の自動言語判定に対応
  - `OUTPUT_LANG` 設定を追加。出力言語を明示的に指定
  - 各セグメントに検出言語 `detected_lang` フィールドを追加
- TranslateGemma-12b-it (GGUF) による多言語翻訳エンジンを追加
  - 日英/英日ペア以外の翻訳で自動選択される（55言語対応）
  - CAT-Translate は日英/英日ペアのみに特化して継続使用
- `src/xlanguage_dubbing/lang_utils.py` を新規追加（言語検出・言語コード変換）
- `src/xlanguage_dubbing/translation/translategemma.py` を新規追加

### Changed

- プロジェクト名を `ja-dubbing` → `xlanguage-dubbing` に変更
  - パッケージ名: `ja_dubbing` → `xlanguage_dubbing`
  - CLI コマンド: `ja-dubbing` → `xlanguage-dubbing`
  - 出力サフィックス: `_jaDub.mp4` → `_xlDub.mp4`
- デフォルト ASR エンジンを `whisper` → `vibevoice` に変更
  - VibeVoice-ASR はコードスイッチング対応で多言語混在音声に最適
- 音量設定を汎用化: `ENGLISH_VOLUME` → `ORIGINAL_VOLUME`、`JAPANESE_VOLUME` → `DUBBED_VOLUME`
- whisper.cpp の言語設定を `INPUT_LANG` 連動に変更（`auto` 対応）
- セグメント JSON に `detected_lang` フィールドを追加
- バージョンを 7.0.0 → 8.0.0 に更新

## [7.0.0] - 2026-04-09

### Removed

- Kokoro TTS エンジンのサポートを完全に削除

### Changed

- TTS エンジンを OmniVoice に一本化
- バージョンを 6.0.0 → 7.0.0 に更新

## [6.0.0]

- OmniVoice + Kokoro TTS のデュアルエンジン対応
- CAT-Translate-7b によるローカル翻訳
- VibeVoice-ASR 対応
