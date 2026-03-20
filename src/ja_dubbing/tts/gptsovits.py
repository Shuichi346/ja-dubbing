#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GPT-SoVITS API (api_v2.py) による音声合成処理。
V2ProPlus モデルをゼロショットボイスクローンで使用する。

MioTTS との主な違い:
- 参照音声は3〜10秒（推奨5秒）の短い音声で声質（音色）のみ抽出される
- 参照音声の抑揚・テンポ・感情は出力にほとんど引き継がれない
- 話者ごとに1つの代表リファレンスを使い回せる（セグメント単位リファレンス不要）
- APIには prompt_text（参照音声の書き起こし）と prompt_lang を渡す（品質向上のため）
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

from ja_dubbing.audio.ffmpeg import ffprobe_duration_sec
from ja_dubbing.config import (
    GPTSOVITS_API_URL,
    GPTSOVITS_BATCH_SIZE,
    GPTSOVITS_HTTP_TIMEOUT,
    GPTSOVITS_MEDIA_TYPE,
    GPTSOVITS_PROMPT_LANG,
    GPTSOVITS_REPETITION_PENALTY,
    GPTSOVITS_SPEED_FACTOR,
    GPTSOVITS_TEMPERATURE,
    GPTSOVITS_TEXT_LANG,
    GPTSOVITS_TEXT_SPLIT_METHOD,
    GPTSOVITS_TOP_K,
    GPTSOVITS_TOP_P,
    GPTSOVITS_TTS_RETRIES,
    MIN_SEGMENT_SEC,
    TTS_CHANNELS,
    TTS_SAMPLE_RATE,
)
from ja_dubbing.core.models import Segment, TtsMeta
from ja_dubbing.tts.reference import SpeakerReferenceCache
from ja_dubbing.utils import (
    PipelineError,
    ensure_dir,
    print_step,
    run_cmd,
    sanitize_text_for_tts,
    which_or_raise,
)


def gptsovits_synthesize(
    text: str,
    out_wav: Path,
    ref_audio_path: str,
    prompt_text: str = "",
    prompt_lang: str = "",
) -> None:
    """GPT-SoVITS API で音声を合成する。"""
    ensure_dir(out_wav.parent)
    url = f"{GPTSOVITS_API_URL.rstrip('/')}/tts"

    payload: Dict[str, Any] = {
        "text": text,
        "text_lang": GPTSOVITS_TEXT_LANG,
        "ref_audio_path": ref_audio_path,
        "prompt_text": prompt_text,
        "prompt_lang": prompt_lang or GPTSOVITS_PROMPT_LANG,
        "top_k": GPTSOVITS_TOP_K,
        "top_p": GPTSOVITS_TOP_P,
        "temperature": GPTSOVITS_TEMPERATURE,
        "text_split_method": GPTSOVITS_TEXT_SPLIT_METHOD,
        "batch_size": GPTSOVITS_BATCH_SIZE,
        "speed_factor": GPTSOVITS_SPEED_FACTOR,
        "streaming_mode": False,
        "media_type": GPTSOVITS_MEDIA_TYPE,
        "repetition_penalty": GPTSOVITS_REPETITION_PENALTY,
        "parallel_infer": True,
        "seed": -1,
    }

    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
    }

    try:
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=GPTSOVITS_HTTP_TIMEOUT) as resp:
            audio_bytes = resp.read()
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = str(exc)
        raise PipelineError(
            f"GPT-SoVITS HTTPError {exc.code}: {body}"
        ) from exc
    except Exception as exc:
        raise PipelineError(f"GPT-SoVITS API 呼び出し失敗: {exc}") from exc

    if len(audio_bytes) < 100:
        raise PipelineError(
            f"GPT-SoVITS: 返された音声データが極端に小さい ({len(audio_bytes)} bytes)"
        )

    out_wav.write_bytes(audio_bytes)


def _convert_to_flac(in_wav: Path, out_flac: Path) -> None:
    """GPT-SoVITS が出力した WAV をプロジェクト標準の FLAC に変換する。"""
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


def _synthesize_with_retry(
    text: str,
    tmp_wav: Path,
    ref_audio_path: str,
    prompt_text: str,
    prompt_lang: str,
    max_retries: int = GPTSOVITS_TTS_RETRIES,
) -> None:
    """GPT-SoVITS API をリトライ付きで呼び出す。"""
    last_err: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            gptsovits_synthesize(
                text, tmp_wav, ref_audio_path,
                prompt_text=prompt_text,
                prompt_lang=prompt_lang,
            )
            return
        except Exception as exc:
            last_err = exc
            if attempt < max_retries:
                wait = 2.0 * attempt
                print_step(
                    f"    GPT-SoVITS TTS リトライ {attempt}/{max_retries}: "
                    f"{wait:.0f}秒待機... ({exc})"
                )
                time.sleep(wait)

    raise PipelineError(f"GPT-SoVITS TTS リトライ枯渇: {last_err}")


def generate_segment_tts_gptsovits(
    seg: Segment,
    out_audio_stub: Path,
    ref_cache: SpeakerReferenceCache,
    segno: int = 0,
) -> Optional[TtsMeta]:
    """GPT-SoVITS でセグメントのゼロショットボイスクローン音声を生成する。"""
    if seg.duration < MIN_SEGMENT_SEC:
        return None

    text = sanitize_text_for_tts(seg.text_ja)
    if not text:
        return None

    out_flac = out_audio_stub.with_suffix(".flac")

    # 既存のFLACがあればそれを使う
    if out_flac.exists():
        dur = ffprobe_duration_sec(out_flac)
        if dur > 0:
            return TtsMeta(
                segno=segno, flac_path=str(out_flac), duration_sec=float(dur)
            )

    # 話者代表リファレンスの絶対パスを取得（GPT-SoVITS サーバーに渡す）
    ref_path = ref_cache.get_gptsovits_reference_path(seg.speaker_id)
    if ref_path is None:
        print_step(
            f"    警告: 話者 {seg.speaker_id} のリファレンス音声がありません。スキップ。"
        )
        return None

    # 参照音声の書き起こしテキストと言語を取得
    prompt_text = ref_cache.get_gptsovits_prompt_text(seg.speaker_id)
    prompt_lang = ref_cache.get_gptsovits_prompt_lang(seg.speaker_id)

    tmp_wav = out_audio_stub.with_suffix(".gptsovits.wav")

    try:
        _synthesize_with_retry(
            text, tmp_wav,
            ref_audio_path=str(ref_path),
            prompt_text=prompt_text,
            prompt_lang=prompt_lang,
        )

        _convert_to_flac(tmp_wav, out_flac)
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
