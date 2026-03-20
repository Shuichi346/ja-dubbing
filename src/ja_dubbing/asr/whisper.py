#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
whisper.cpp CLI（+ Silero VAD）による音声認識処理。
whisper-cli バイナリを subprocess で呼び出し、JSON 出力をパースする。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List

from ja_dubbing.config import (
    VAD_MODEL,
    WHISPER_CPP_DIR,
    WHISPER_LANG,
    WHISPER_MODEL,
)
from ja_dubbing.core.models import Segment
from ja_dubbing.utils import PipelineError, print_step, run_cmd, which_or_raise


def _resolve_whisper_cli() -> str:
    """whisper-cli バイナリのパスを解決する。"""
    candidate = WHISPER_CPP_DIR / "build" / "bin" / "whisper-cli"
    if candidate.exists():
        return str(candidate)

    import shutil
    path_bin = shutil.which("whisper-cli")
    if path_bin:
        return path_bin

    raise PipelineError(
        "whisper-cli が見つかりません。\n"
        "以下を実行して whisper.cpp をセットアップしてください:\n"
        "  chmod +x scripts/setup_whisper.sh\n"
        "  ./scripts/setup_whisper.sh\n"
    )


def _resolve_whisper_model() -> str:
    """Whisper モデルファイルのパスを解決する。"""
    model_file = WHISPER_CPP_DIR / "models" / f"ggml-{WHISPER_MODEL}.bin"
    if model_file.exists():
        return str(model_file)

    raise PipelineError(
        f"Whisper モデルが見つかりません: {model_file}\n"
        "以下を実行してモデルをダウンロードしてください:\n"
        "  ./scripts/setup_whisper.sh\n"
    )


def _resolve_vad_model() -> str:
    """VAD モデルファイルのパスを解決する。"""
    vad_file = WHISPER_CPP_DIR / "models" / f"ggml-{VAD_MODEL}.bin"
    if vad_file.exists():
        return str(vad_file)

    raise PipelineError(
        f"VAD モデルが見つかりません: {vad_file}\n"
        "以下を実行して VAD モデルをダウンロードしてください:\n"
        "  ./scripts/setup_whisper.sh\n"
    )


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
    """whisper.cpp CLI + VAD で音声を文字起こしする。"""
    whisper_cli = _resolve_whisper_cli()
    model_path = _resolve_whisper_model()
    vad_model_path = _resolve_vad_model()

    n_threads = max(1, (os.cpu_count() or 8) - 2)

    output_base = wav_path.parent / wav_path.stem
    json_path = Path(f"{output_base}.json")

    cmd = [
        whisper_cli,
        "--model", model_path,
        "--file", str(wav_path),
        "--language", WHISPER_LANG,
        "--threads", str(n_threads),
        "--vad",
        "--vad-model", vad_model_path,
        "--output-json",
        "--output-file", str(output_base),
        "--no-prints",
    ]

    print_step(f"  whisper-cli 実行中: {wav_path.name}")
    print_step(f"    モデル: {WHISPER_MODEL}")
    print_step(f"    VAD: {VAD_MODEL}")
    print_step(f"    スレッド数: {n_threads}")

    run_cmd(cmd)

    if not json_path.exists():
        raise PipelineError(
            f"whisper-cli の JSON 出力が見つかりません: {json_path}"
        )

    segments = _parse_whisper_json(json_path)

    if not segments:
        raise PipelineError("whisper.cpp: 文字起こし結果が空です。")

    print_step(f"  whisper.cpp 完了: {len(segments)} セグメント")
    return segments


def _parse_whisper_json(json_path: Path) -> List[Segment]:
    """whisper.cpp の JSON 出力をパースしてセグメントリストを返す。"""
    raw = json_path.read_text(encoding="utf-8")
    data = json.loads(raw)

    transcription = data.get("transcription", [])
    segments: List[Segment] = []

    for entry in transcription:
        offsets = entry.get("offsets", {})
        start_ms = int(offsets.get("from", 0))
        end_ms = int(offsets.get("to", 0))
        text = (entry.get("text", "") or "").strip()

        if not text:
            continue

        start_sec = start_ms / 1000.0
        end_sec = end_ms / 1000.0

        if end_sec <= start_sec:
            continue

        segments.append(
            Segment(
                idx=len(segments),
                start=start_sec,
                end=end_sec,
                text_en=text,
            )
        )

    return segments


def transcribe_short_audio(wav_path: Path, language: str = "") -> str:
    """
    短い音声ファイル（参照音声等）を whisper.cpp で文字起こしする。
    全セグメントのテキストを結合して返す。
    失敗時は空文字列を返す。
    """
    if not wav_path.exists():
        return ""

    # 16kHz mono WAV に変換（whisper.cpp の入力要件）
    tmp_wav = wav_path.parent / f"{wav_path.stem}_w16k.wav"
    try:
        which_or_raise("ffmpeg")
        run_cmd([
            "ffmpeg", "-y",
            "-i", str(wav_path),
            "-vn", "-ac", "1", "-ar", "16000",
            "-c:a", "pcm_s16le",
            str(tmp_wav),
        ])
    except Exception:
        return ""

    try:
        whisper_cli = _resolve_whisper_cli()
        model_path = _resolve_whisper_model()
    except PipelineError:
        tmp_wav.unlink(missing_ok=True)
        return ""

    lang = language if language else WHISPER_LANG
    output_base = tmp_wav.parent / tmp_wav.stem
    json_path = Path(f"{output_base}.json")

    cmd = [
        whisper_cli,
        "--model", model_path,
        "--file", str(tmp_wav),
        "--language", lang,
        "--threads", "4",
        "--output-json",
        "--output-file", str(output_base),
        "--no-prints",
    ]

    try:
        run_cmd(cmd)
    except Exception:
        tmp_wav.unlink(missing_ok=True)
        json_path.unlink(missing_ok=True)
        return ""

    text = ""
    if json_path.exists():
        try:
            segments = _parse_whisper_json(json_path)
            text = " ".join(
                s.text_en.strip() for s in segments if s.text_en.strip()
            )
        except Exception:
            text = ""

    tmp_wav.unlink(missing_ok=True)
    json_path.unlink(missing_ok=True)

    return text.strip()


def release_whisper_model() -> None:
    """whisper.cpp CLI 方式ではモデルの明示的解放は不要（互換性のため残す）。"""
    pass
