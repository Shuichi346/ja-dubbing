#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kokoro TTS による音声合成処理。
ボイスクローンは非対応だが、軽量（82Mパラメータ）で高速な推論が可能。
日本語発音には misaki[ja] + unidic の事前ダウンロードが必要。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import numpy as np

from ja_dubbing.audio.ffmpeg import ffprobe_duration_sec
from ja_dubbing.config import (
    KOKORO_MODEL,
    KOKORO_SAMPLE_RATE,
    KOKORO_SPEED,
    KOKORO_VOICE,
    MIN_SEGMENT_SEC,
    TTS_CHANNELS,
    TTS_SAMPLE_RATE,
)
from ja_dubbing.core.models import Segment, TtsMeta
from ja_dubbing.utils import (
    PipelineError,
    ensure_dir,
    print_step,
    run_cmd,
    sanitize_text_for_tts,
    which_or_raise,
)

# パイプラインの遅延ロード用グローバルキャッシュ
_KOKORO_PIPELINE = None


def _get_kokoro_pipeline():
    """Kokoro KPipeline を遅延ロードする。"""
    global _KOKORO_PIPELINE
    if _KOKORO_PIPELINE is not None:
        return _KOKORO_PIPELINE

    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

    try:
        from kokoro import KPipeline
    except ImportError as exc:
        raise PipelineError(
            "kokoro がインストールされていません。\n"
            "以下を実行してください:\n"
            "  uv sync\n"
            "  uv run python -m unidic download\n"
        ) from exc

    print_step(f"  Kokoro TTS パイプライン初期化中: model={KOKORO_MODEL}, voice={KOKORO_VOICE}")
    _KOKORO_PIPELINE = KPipeline(lang_code="j", model=KOKORO_MODEL)
    print_step("  Kokoro TTS パイプライン初期化完了")
    return _KOKORO_PIPELINE


def ensure_unidic_downloaded() -> None:
    """unidic 辞書がダウンロード済みか確認し、未ダウンロードなら警告する。"""
    try:
        import unidic
        dicdir = unidic.DICDIR
        if Path(dicdir).exists() and any(Path(dicdir).iterdir()):
            return
    except (ImportError, AttributeError, TypeError):
        pass

    print_step(
        "警告: unidic 辞書がダウンロードされていません。\n"
        "日本語の正規化が正しく行われない可能性があります。\n"
        "以下を実行してください:\n"
        "  uv run python -m unidic download"
    )


def kokoro_synthesize_to_wav(text_ja: str, out_wav: Path) -> bool:
    """Kokoro TTS で日本語テキストから WAV ファイルを生成する。"""
    ensure_dir(out_wav.parent)

    pipeline = _get_kokoro_pipeline()

    try:
        import soundfile as sf
    except ImportError as exc:
        raise PipelineError(
            "soundfile がインストールされていません。\n"
            "  uv sync を実行してください。\n"
        ) from exc

    audio_chunks: list = []
    try:
        generator = pipeline(
            text_ja,
            voice=KOKORO_VOICE,
            speed=KOKORO_SPEED,
        )
        for _gs, _ps, audio in generator:
            if audio is not None and len(audio) > 0:
                if hasattr(audio, "numpy"):
                    audio = audio.numpy()
                audio_chunks.append(audio)
    except Exception as exc:
        raise PipelineError(f"Kokoro TTS 生成エラー: {exc}") from exc

    if not audio_chunks:
        return False

    full_audio = np.concatenate(audio_chunks)

    if len(full_audio) == 0:
        return False

    sf.write(str(out_wav), full_audio, KOKORO_SAMPLE_RATE)
    return True


def convert_kokoro_wav_to_flac(in_wav: Path, out_flac: Path) -> None:
    """Kokoro が出力した WAV（24kHz mono）をプロジェクト標準の FLAC に変換する。"""
    which_or_raise("ffmpeg")
    ensure_dir(out_flac.parent)
    cmd = [
        "ffmpeg", "-y",
        "-i", str(in_wav),
        "-ac", str(TTS_CHANNELS),
        "-ar", str(TTS_SAMPLE_RATE),
        "-c:a", "flac",
        str(out_flac),
    ]
    run_cmd(cmd)


def generate_segment_tts_kokoro(
    seg: Segment,
    out_audio_stub: Path,
    segno: int = 0,
) -> Optional[TtsMeta]:
    """Kokoro TTS でセグメントの日本語音声を生成する。"""
    if seg.duration < MIN_SEGMENT_SEC:
        return None

    text = sanitize_text_for_tts(seg.text_ja)
    if not text:
        return None

    out_flac = out_audio_stub.with_suffix(".flac")

    if out_flac.exists():
        dur = ffprobe_duration_sec(out_flac)
        if dur > 0:
            return TtsMeta(
                segno=segno, flac_path=str(out_flac), duration_sec=float(dur)
            )

    tmp_wav = out_audio_stub.with_suffix(".kokoro.wav")

    try:
        success = kokoro_synthesize_to_wav(text, tmp_wav)
        if not success:
            return None

        convert_kokoro_wav_to_flac(tmp_wav, out_flac)
        dur = ffprobe_duration_sec(out_flac)
    finally:
        try:
            if tmp_wav.exists():
                tmp_wav.unlink()
        except Exception:
            pass

    if dur <= 0:
        return None

    return TtsMeta(segno=segno, flac_path=str(out_flac), duration_sec=float(dur))
