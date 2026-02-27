#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VibeVoice-ASR（Microsoft 製、mlx-audio 経由）による音声認識処理。
文字起こし・話者分離・タイムスタンプを1パスで出力する。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

from ja_dubbing.config import VIBEVOICE_CONTEXT, VIBEVOICE_MAX_TOKENS, VIBEVOICE_MODEL
from ja_dubbing.core.models import DiarizationSegment, Segment
from ja_dubbing.utils import PipelineError, print_step

# モデルの遅延ロード用グローバルキャッシュ
_VIBEVOICE_MODEL = None

# 非音声タグのパターン（[Music], [Noise], [Environmental Sounds], [Speech] など）
_NON_SPEECH_PATTERN = re.compile(r"^\[.*\]$")


def _load_model_func():
    """mlx-audio のモデルロード関数を取得する。"""
    try:
        from mlx_audio.stt.utils import load_model
        return load_model
    except ImportError:
        pass

    try:
        from mlx_audio.stt.utils import load as load_model
        return load_model
    except ImportError as exc:
        raise PipelineError(
            "mlx-audio[stt] がインストールされていません。\n"
            "VibeVoice-ASR を使うには以下を実行してください:\n"
            "  uv pip install 'mlx-audio[stt]>=0.3.0'\n"
        ) from exc


def _get_vibevoice_model():
    """VibeVoice-ASR モデルを遅延ロードする。"""
    global _VIBEVOICE_MODEL
    if _VIBEVOICE_MODEL is not None:
        return _VIBEVOICE_MODEL

    load_model = _load_model_func()

    print_step(f"  VibeVoice-ASR モデルをロード中: {VIBEVOICE_MODEL}")
    _VIBEVOICE_MODEL = load_model(VIBEVOICE_MODEL)
    print_step("  VibeVoice-ASR モデルのロード完了")
    return _VIBEVOICE_MODEL


def _is_non_speech(text: str) -> bool:
    """テキストが非音声タグかどうかを判定する。"""
    return bool(_NON_SPEECH_PATTERN.match(text.strip()))


def vibevoice_transcribe(
    wav_path: Path,
) -> Tuple[List[Segment], List[DiarizationSegment]]:
    """
    VibeVoice-ASR で文字起こしと話者分離を同時に実行する。

    戻り値は (segments, diarization) のタプル。
    segments には既に speaker_id が付与されている。
    diarization は後続のリファレンス音声生成で使用する。
    """
    model = _get_vibevoice_model()

    # generate メソッドのパラメータを組み立てる
    gen_kwargs = {
        "max_tokens": VIBEVOICE_MAX_TOKENS,
        "temperature": 0.0,
    }
    if VIBEVOICE_CONTEXT.strip():
        gen_kwargs["context"] = VIBEVOICE_CONTEXT.strip()

    print_step(f"  VibeVoice-ASR 実行中: {wav_path.name}")
    print_step(f"    max_tokens={VIBEVOICE_MAX_TOKENS}")
    if VIBEVOICE_CONTEXT.strip():
        print_step(f"    context={VIBEVOICE_CONTEXT.strip()}")

    result = model.generate(
        audio=str(wav_path),
        verbose=False,
        **gen_kwargs,
    )

    # result.segments からセグメントと話者分離情報を抽出する
    raw_segments = (
        result.segments
        if hasattr(result, "segments") and result.segments
        else []
    )

    segments: List[Segment] = []
    diarization: List[DiarizationSegment] = []
    idx = 0

    for seg in raw_segments:
        if not isinstance(seg, dict):
            continue

        text = (seg.get("text", "")).strip()
        if not text:
            continue

        # 非音声タグをスキップ
        if _is_non_speech(text):
            continue

        # speaker_id がないセグメントはスキップ
        speaker_id_raw = seg.get("speaker_id")
        if speaker_id_raw is None:
            continue

        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", 0.0))
        if end <= start:
            continue

        # speaker_id を整数から "SPEAKER_00" 形式に変換
        try:
            speaker_id_int = int(speaker_id_raw)
        except (ValueError, TypeError):
            speaker_id_int = 0
        speaker_label = f"SPEAKER_{speaker_id_int:02d}"

        segments.append(
            Segment(
                idx=idx,
                start=start,
                end=end,
                text_en=text,
                speaker_id=speaker_label,
            )
        )

        diarization.append(
            DiarizationSegment(
                start=start,
                end=end,
                speaker=speaker_label,
            )
        )

        idx += 1

    if not segments:
        raise PipelineError(
            "VibeVoice-ASR: 文字起こし結果が空です。"
            "音声ファイルに発話が含まれていない可能性があります。"
        )

    speaker_ids = sorted(set(s.speaker_id for s in segments))
    print_step(
        f"  VibeVoice-ASR 完了: {len(segments)} セグメント, "
        f"話者数={len(speaker_ids)}, ID={speaker_ids}"
    )

    return segments, diarization


def release_vibevoice_model() -> None:
    """メモリ節約のため VibeVoice-ASR モデルを解放する。"""
    global _VIBEVOICE_MODEL
    _VIBEVOICE_MODEL = None
