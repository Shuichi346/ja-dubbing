#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FFmpeg関連ユーティリティ。
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from ja_dubbing.config import (
    ENGLISH_VOLUME,
    JAPANESE_VOLUME,
    OUTPUT_SIZE,
    TTS_CHANNELS,
    TTS_SAMPLE_RATE,
)
from ja_dubbing.utils import (
    PipelineError,
    atomic_write_text,
    ensure_dir,
    ffmpeg_concat_quote,
    run_cmd,
    which_or_raise,
)

# 映像・音声チャンクの最低区間幅（秒）
_MIN_TRIM_SEC = 0.05


def ffprobe_duration_sec(media_path: Path) -> float:
    """メディアファイルの長さを取得する。"""
    which_or_raise("ffprobe")
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1",
        str(media_path),
    ]
    proc = run_cmd(cmd)
    s = (proc.stdout or "").strip()
    try:
        return float(s)
    except ValueError as exc:
        raise PipelineError(
            f"ffprobe duration の解析に失敗: {media_path} / '{s}'"
        ) from exc


def ffprobe_has_audio(media_path: Path) -> bool:
    """メディアファイルに音声があるかを確認する。"""
    which_or_raise("ffprobe")
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=index",
        "-of", "csv=p=0",
        str(media_path),
    ]
    proc = run_cmd(cmd, check=False)
    return bool((proc.stdout or "").strip())


def extract_audio_segment(
    video_in: Path,
    out_wav: Path,
    *,
    start: float,
    end: float,
    sample_rate: int = 44100,
    channels: int = 1,
) -> None:
    """動画の指定区間から音声のみを抽出する。入力側シークで高速化。"""
    which_or_raise("ffmpeg")
    ensure_dir(out_wav.parent)
    duration = max(0.0, end - start)
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start:.6f}",
        "-i", str(video_in),
        "-vn",
        "-t", f"{duration:.6f}",
        "-ac", str(channels),
        "-ar", str(sample_rate),
        "-c:a", "pcm_s16le",
        str(out_wav),
    ]
    run_cmd(cmd)


def build_atempo_filter(speed_factor: float) -> str:
    """atempoフィルタ文字列を生成する。"""
    if speed_factor <= 0:
        raise PipelineError(f"不正な speed_factor: {speed_factor}")

    factors: List[float] = []
    x = float(speed_factor)

    while x > 2.0:
        factors.append(2.0)
        x /= 2.0
    while x < 0.5:
        factors.append(0.5)
        x /= 0.5

    factors.append(x)
    return ",".join([f"atempo={f:.6f}" for f in factors])


def _safe_trim_range(start: float, end: float) -> tuple[float, float]:
    """trim区間が短すぎる場合に最低幅を確保する。"""
    s = max(0.0, float(start))
    e = max(s, float(end))
    if e - s < _MIN_TRIM_SEC:
        e = s + _MIN_TRIM_SEC
    return s, e


def encode_video_chunk_ts(
    video_in: Path,
    out_ts: Path,
    *,
    start: float,
    end: float,
    speed: float,
) -> None:
    """動画チャンクをTSにエンコードする。入力側シークで高速化。"""
    which_or_raise("ffmpeg")
    ensure_dir(out_ts.parent)

    s, e = _safe_trim_range(start, end)
    spd = max(1e-6, float(speed))
    duration = e - s

    # trim フィルタは入力側シーク後の相対時間で指定する
    vf = (
        f"trim=start=0:end={duration:.6f},"
        f"setpts=(PTS-STARTPTS)/{spd:.8f},"
        f"scale=-2:{OUTPUT_SIZE}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{s:.6f}",
        "-i", str(video_in),
        "-an",
        "-vf", vf,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "veryfast",
        "-crf", "23",
        "-g", "60",
        "-keyint_min", "60",
        "-sc_threshold", "0",
        "-mpegts_flags", "+resend_headers",
        "-f", "mpegts",
        str(out_ts),
    ]
    run_cmd(cmd)


def encode_english_audio_chunk_flac(
    video_in: Path,
    out_flac: Path,
    *,
    start: float,
    end: float,
    speed: float,
) -> None:
    """英語音声チャンクをFLACにエンコードする。入力側シークで高速化。"""
    which_or_raise("ffmpeg")
    ensure_dir(out_flac.parent)

    s, e = _safe_trim_range(start, end)
    spd = max(1e-6, float(speed))
    duration = e - s

    atempo = build_atempo_filter(spd)
    # 入力側シーク後の相対時間で atrim を指定する
    af = (
        f"atrim=start=0:end={duration:.6f},"
        f"asetpts=PTS-STARTPTS,"
        f"{atempo},"
        f"aresample=async=1:first_pts=0"
    )

    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{s:.6f}",
        "-i", str(video_in),
        "-vn",
        "-af", af,
        "-ac", str(TTS_CHANNELS),
        "-ar", str(TTS_SAMPLE_RATE),
        "-c:a", "flac",
        str(out_flac),
    ]
    run_cmd(cmd)


def create_silence_flac(out_flac: Path, duration_sec: float) -> None:
    """無音FLACを作成する。"""
    which_or_raise("ffmpeg")
    ensure_dir(out_flac.parent)
    dur = max(0.0, float(duration_sec))
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"anullsrc=r={TTS_SAMPLE_RATE}:cl=stereo",
        "-t", f"{dur:.6f}",
        "-ac", str(TTS_CHANNELS),
        "-ar", str(TTS_SAMPLE_RATE),
        "-c:a", "flac",
        str(out_flac),
    ]
    run_cmd(cmd)


def concat_ts_files(in_files: List[Path], out_ts: Path, list_file: Path) -> None:
    """TSファイルを結合する。"""
    which_or_raise("ffmpeg")
    ensure_dir(out_ts.parent)
    ensure_dir(list_file.parent)

    lines = []
    for p in in_files:
        lines.append(f"file '{ffmpeg_concat_quote(str(p.resolve()))}'")
    atomic_write_text(list_file, "\n".join(lines) + "\n", encoding="utf-8")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        str(out_ts),
    ]
    run_cmd(cmd)


def concat_audio_to_flac(in_files: List[Path], out_flac: Path, list_file: Path) -> None:
    """音声ファイルをFLACに結合する。"""
    which_or_raise("ffmpeg")
    ensure_dir(out_flac.parent)
    ensure_dir(list_file.parent)

    lines = []
    for p in in_files:
        lines.append(f"file '{ffmpeg_concat_quote(str(p.resolve()))}'")
    atomic_write_text(list_file, "\n".join(lines) + "\n", encoding="utf-8")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_file),
        "-ac", str(TTS_CHANNELS),
        "-ar", str(TTS_SAMPLE_RATE),
        "-c:a", "flac",
        str(out_flac),
    ]
    run_cmd(cmd)


def remux_ts_to_mp4(video_ts: Path, out_mp4: Path) -> None:
    """TSをMP4にリマックスする。"""
    which_or_raise("ffmpeg")
    ensure_dir(out_mp4.parent)
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_ts),
        "-c", "copy",
        "-movflags", "+faststart",
        str(out_mp4),
    ]
    run_cmd(cmd)


def mux_retimed_video_with_tracks(
    video_in_mp4: Path,
    japanese_flac: Path,
    out_mp4: Path,
    *,
    english_flac: Optional[Path],
) -> None:
    """リタイム済み映像に音声を合成する。"""
    which_or_raise("ffmpeg")
    ensure_dir(out_mp4.parent)

    if english_flac and english_flac.exists():
        filter_complex = (
            f"[1:a]volume={JAPANESE_VOLUME}[ja];"
            f"[2:a]volume={ENGLISH_VOLUME}[en];"
            f"[ja][en]amix=inputs=2:duration=first:normalize=0[aout]"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_in_mp4),
            "-i", str(japanese_flac),
            "-i", str(english_flac),
            "-filter_complex", filter_complex,
            "-map", "0:v:0",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(out_mp4),
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_in_mp4),
            "-i", str(japanese_flac),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(out_mp4),
        ]
    run_cmd(cmd)
