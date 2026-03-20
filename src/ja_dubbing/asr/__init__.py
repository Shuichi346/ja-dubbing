#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ASR エンジンの統一インターフェース。
"""

from __future__ import annotations

from pathlib import Path

from ja_dubbing.config import ASR_ENGINE


def get_asr_engine() -> str:
    """現在選択されている ASR エンジン名を返す。"""
    return ASR_ENGINE.strip().lower()


def transcribe_reference_audio(wav_path: Path, language: str = "") -> str:
    """
    参照音声ファイルを文字起こしする統一エントリポイント。
    ASR_ENGINE の設定に応じて whisper.cpp または VibeVoice を使用する。
    失敗時は空文字列を返す。
    """
    engine = get_asr_engine()

    if engine == "vibevoice":
        from ja_dubbing.asr.vibevoice import transcribe_short_audio_vibevoice
        return transcribe_short_audio_vibevoice(wav_path)

    from ja_dubbing.asr.whisper import transcribe_short_audio
    return transcribe_short_audio(wav_path, language=language)
