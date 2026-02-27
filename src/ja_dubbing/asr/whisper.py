#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pywhispercppによる音声認識処理。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

from ja_dubbing.config import WHISPER_LANG, WHISPER_MODEL
from ja_dubbing.core.models import Segment
from ja_dubbing.utils import PipelineError, run_cmd, which_or_raise

_WHISPER_MODEL = None


def _get_whisper_model():
    """pywhispercppモデルを遅延ロードする。"""
    global _WHISPER_MODEL
    if _WHISPER_MODEL is not None:
        return _WHISPER_MODEL

    try:
        from pywhispercpp.model import Model
    except ImportError as exc:
        raise PipelineError(
            "pywhispercpp がインストールされていません。\n"
            "以下を実行してください:\n"
            "  uv pip install git+https://github.com/absadiki/pywhispercpp\n"
        ) from exc

    n_threads = max(1, (os.cpu_count() or 8) - 2)
    _WHISPER_MODEL = Model(
        WHISPER_MODEL,
        n_threads=n_threads,
        language=WHISPER_LANG,
        print_realtime=False,
        print_progress=False,
    )
    return _WHISPER_MODEL


def extract_wav_for_whisper(video_path: Path, wav_path: Path) -> None:
    """動画から16kHz mono WAVを抽出する。"""
    which_or_raise("ffmpeg")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vn", "-ac", "1", "-ar", "16000",
        "-c:a", "pcm_s16le",
        str(wav_path),
    ]
    run_cmd(cmd)


def whisper_transcribe(wav_path: Path) -> List[Segment]:
    """pywhispercppで音声を文字起こしする。"""
    model = _get_whisper_model()
    raw_segments = model.transcribe(str(wav_path))

    segments: List[Segment] = []
    for i, seg in enumerate(raw_segments):
        # t0, t1 は 10ms 単位（centisecond）: 1秒 = 100
        start = seg.t0 / 100.0
        end = seg.t1 / 100.0
        text = (seg.text or "").strip()
        if not text:
            continue
        segments.append(Segment(idx=i, start=start, end=end, text_en=text))

    if not segments:
        raise PipelineError("pywhispercpp: 文字起こし結果が空です。")
    return segments


def release_whisper_model() -> None:
    """メモリ節約のためWhisperモデルを解放する。"""
    global _WHISPER_MODEL
    _WHISPER_MODEL = None
