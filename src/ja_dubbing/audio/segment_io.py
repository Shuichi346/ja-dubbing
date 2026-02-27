#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
セグメントJSON I/O、SRT出力。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

from ja_dubbing.core.models import Segment
from ja_dubbing.utils import (
    PipelineError,
    atomic_write_json,
    atomic_write_text,
    load_json_if_exists,
)


# =========================
# セグメントJSON I/O
# =========================


def segments_to_payload(segments: List[Segment]) -> List[Dict[str, Any]]:
    """セグメントリストをJSONペイロードに変換する。"""
    return [
        {
            "idx": s.idx,
            "start": s.start,
            "end": s.end,
            "text_en": s.text_en,
            "text_ja": s.text_ja,
            "speaker_id": s.speaker_id,
        }
        for s in segments
    ]


def payload_to_segments(payload: Any) -> List[Segment]:
    """JSONペイロードからセグメントリストを生成する。"""
    if not isinstance(payload, list):
        raise PipelineError("segments json がリスト形式ではありません。")
    out: List[Segment] = []
    for i, row in enumerate(payload):
        if not isinstance(row, dict):
            continue
        out.append(
            Segment(
                idx=int(row.get("idx", i)),
                start=float(row.get("start", 0.0)),
                end=float(row.get("end", 0.0)),
                text_en=str(row.get("text_en", "") or ""),
                text_ja=str(row.get("text_ja", "") or ""),
                speaker_id=str(row.get("speaker_id", "") or ""),
            )
        )
    return out


def save_segments_json_atomic(segments: List[Segment], out_json: Path) -> None:
    """セグメントをJSONにアトミック保存する。"""
    atomic_write_json(out_json, segments_to_payload(segments))


def load_segments_json(out_json: Path) -> List[Segment]:
    """JSONからセグメントを読み込む。"""
    obj = load_json_if_exists(out_json)
    if obj is None:
        raise PipelineError(f"segments json が読み込めません: {out_json}")
    return payload_to_segments(obj)


# =========================
# SRT出力
# =========================


def _format_srt_timestamp(sec: float) -> str:
    """秒をSRTのタイムスタンプ形式に変換する。"""
    if sec < 0:
        sec = 0.0
    total_ms = int(round(sec * 1000.0))
    ms = total_ms % 1000
    total_s = total_ms // 1000
    s = total_s % 60
    total_m = total_s // 60
    m = total_m % 60
    h = total_m // 60
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _segments_to_srt_text(segments: List[Segment]) -> str:
    """セグメントリストからSRTテキストを生成する。"""
    lines: List[str] = []
    counter = 1
    for seg in segments:
        text = (seg.text_en or "").strip()
        if not text:
            continue
        start = float(seg.start)
        end = float(seg.end)
        if end < start:
            end = start
        lines.append(str(counter))
        lines.append(
            f"{_format_srt_timestamp(start)} --> {_format_srt_timestamp(end)}"
        )
        lines.append(re.sub(r"\s+", " ", text).strip())
        lines.append("")
        counter += 1
    return "\n".join(lines).rstrip() + "\n"


def save_srt_atomic(segments: List[Segment], out_srt: Path) -> None:
    """SRTをアトミックに保存する。"""
    srt_text = _segments_to_srt_text(segments)
    atomic_write_text(out_srt, srt_text, encoding="utf-8")
