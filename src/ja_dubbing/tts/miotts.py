#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MioTTS-Inference APIによる音声合成処理。
話者クローン音声を生成する。
セグメント単位リファレンスを優先し、なければ話者代表リファレンスにフォールバックする。
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from ja_dubbing.audio.ffmpeg import ffprobe_duration_sec
from ja_dubbing.config import (
    MIOTTS_API_URL,
    MIOTTS_HTTP_TIMEOUT,
    MIOTTS_MAX_TEXT_LENGTH,
    MIOTTS_TTS_RETRIES,
    MIN_SEGMENT_SEC,
    TTS_CHANNELS,
    TTS_SAMPLE_RATE,
)
from ja_dubbing.core.models import Segment, TtsMeta
from ja_dubbing.tts.reference import SpeakerReferenceCache
from ja_dubbing.utils import (
    PipelineError,
    atomic_write_json,
    ensure_dir,
    load_json_if_exists,
    print_step,
    run_cmd,
    sanitize_text_for_tts,
    which_or_raise,
)


def miotts_synthesize(
    text_ja: str,
    out_wav: Path,
    reference_base64: str,
) -> None:
    """MioTTS APIでリファレンス音声によるクローン音声を生成する。"""
    ensure_dir(out_wav.parent)
    url = f"{MIOTTS_API_URL.rstrip('/')}/v1/tts"

    payload: Dict[str, Any] = {
        "text": text_ja,
        "reference": {
            "type": "base64",
            "data": reference_base64,
        },
        "output": {
            "format": "wav",
        },
    }

    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "audio/wav",
    }

    try:
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=MIOTTS_HTTP_TIMEOUT) as resp:
            wav_bytes = resp.read()
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = str(exc)
        raise PipelineError(f"MioTTS HTTPError {exc.code}: {body}") from exc
    except Exception as exc:
        raise PipelineError(f"MioTTS 呼び出し失敗: {exc}") from exc

    out_wav.write_bytes(wav_bytes)


def miotts_synthesize_preset(
    text_ja: str,
    out_wav: Path,
    preset_id: str = "jp_female",
) -> None:
    """MioTTS APIでプリセット音声を生成する（リファレンスなし時のフォールバック）。"""
    ensure_dir(out_wav.parent)
    url = f"{MIOTTS_API_URL.rstrip('/')}/v1/tts"

    payload: Dict[str, Any] = {
        "text": text_ja,
        "reference": {
            "type": "preset",
            "preset_id": preset_id,
        },
        "output": {
            "format": "wav",
        },
    }

    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "audio/wav",
    }

    try:
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=MIOTTS_HTTP_TIMEOUT) as resp:
            wav_bytes = resp.read()
    except Exception as exc:
        raise PipelineError(f"MioTTS プリセット呼び出し失敗: {exc}") from exc

    out_wav.write_bytes(wav_bytes)


def ensure_wav_format(in_wav: Path, out_wav: Path) -> None:
    """WAVファイルのフォーマットを統一する。"""
    which_or_raise("ffmpeg")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(in_wav),
        "-ac", str(TTS_CHANNELS),
        "-ar", str(TTS_SAMPLE_RATE),
        "-c:a", "pcm_s16le",
        str(out_wav),
    ]
    run_cmd(cmd)


def convert_to_flac(in_wav: Path, out_flac: Path) -> None:
    """WAVをFLACに変換する。"""
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


def _truncate_text_for_miotts(text: str) -> str:
    """MioTTSのテキスト長制限に収まるよう切り詰める。"""
    if len(text) <= MIOTTS_MAX_TEXT_LENGTH:
        return text
    # 句読点の位置で安全に切る
    truncated = text[:MIOTTS_MAX_TEXT_LENGTH]
    for sep in ["。", "、", ".", ",", " "]:
        pos = truncated.rfind(sep)
        if pos > MIOTTS_MAX_TEXT_LENGTH // 2:
            return truncated[: pos + 1]
    return truncated


def _resolve_reference_base64(
    segno: int,
    speaker_id: str,
    ref_cache: SpeakerReferenceCache,
) -> Optional[str]:
    """セグメント単位リファレンスを優先し、なければ話者代表にフォールバックする。"""
    seg_b64 = ref_cache.get_segment_reference_base64(segno)
    if seg_b64:
        return seg_b64
    return ref_cache.get_reference_base64(speaker_id)


def _synthesize_with_retry(
    text: str,
    tmp_raw: Path,
    ref_b64: Optional[str],
    max_retries: int = MIOTTS_TTS_RETRIES,
) -> None:
    """MioTTS APIをリトライ付きで呼び出す。"""
    last_err: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            if ref_b64:
                miotts_synthesize(text, tmp_raw, ref_b64)
            else:
                miotts_synthesize_preset(text, tmp_raw, preset_id="jp_female")
            return
        except Exception as exc:
            last_err = exc
            if attempt < max_retries:
                wait = 2.0 * attempt
                print_step(
                    f"    TTS リトライ {attempt}/{max_retries}: "
                    f"{wait:.0f}秒待機... ({exc})"
                )
                time.sleep(wait)

    raise PipelineError(f"MioTTS リトライ枯渇: {last_err}")


def generate_segment_tts(
    seg: Segment,
    out_audio_stub: Path,
    ref_cache: SpeakerReferenceCache,
    segno: int = 0,
) -> Optional[TtsMeta]:
    """セグメントの話者クローン音声を生成する。"""
    if seg.duration < MIN_SEGMENT_SEC:
        return None

    text = sanitize_text_for_tts(seg.text_ja)
    if not text:
        return None

    text = _truncate_text_for_miotts(text)

    out_flac = out_audio_stub.with_suffix(".flac")
    if out_flac.exists():
        dur = ffprobe_duration_sec(out_flac)
        if dur > 0:
            return TtsMeta(
                segno=segno, flac_path=str(out_flac), duration_sec=float(dur)
            )

    # セグメント単位リファレンスを優先、なければ話者代表を使用
    ref_b64 = _resolve_reference_base64(segno, seg.speaker_id, ref_cache)

    tmp_raw = out_audio_stub.with_suffix(".raw.wav")
    tmp_norm = out_audio_stub.with_suffix(".norm.wav")

    try:
        _synthesize_with_retry(text, tmp_raw, ref_b64)

        ensure_wav_format(tmp_raw, tmp_norm)
        convert_to_flac(tmp_norm, out_flac)

        dur = ffprobe_duration_sec(out_flac)
    finally:
        for p in [tmp_raw, tmp_norm]:
            try:
                if p.exists():
                    p.unlink()
            except Exception:
                pass

    if dur <= 0:
        return None
    return TtsMeta(segno=segno, flac_path=str(out_flac), duration_sec=float(dur))


def load_tts_meta(path: Path) -> Dict[int, TtsMeta]:
    """TTSメタ情報を読み込む。"""
    obj = load_json_if_exists(path)
    if not isinstance(obj, list):
        return {}
    out: Dict[int, TtsMeta] = {}
    for row in obj:
        if not isinstance(row, dict):
            continue
        segno = int(row.get("segno", 0) or 0)
        flac_path = str(row.get("flac_path", "") or "")
        dur = float(row.get("duration_sec", 0.0) or 0.0)
        if segno <= 0 or not flac_path or dur <= 0:
            continue
        out[segno] = TtsMeta(segno=segno, flac_path=flac_path, duration_sec=dur)
    return out


def save_tts_meta_atomic(path: Path, meta: Dict[int, TtsMeta]) -> None:
    """TTSメタ情報をアトミックに保存する。"""
    rows: List[Dict[str, Any]] = []
    for segno in sorted(meta.keys()):
        m = meta[segno]
        rows.append(
            {
                "segno": m.segno,
                "flac_path": m.flac_path,
                "duration_sec": m.duration_sec,
            }
        )
    atomic_write_json(path, rows)
