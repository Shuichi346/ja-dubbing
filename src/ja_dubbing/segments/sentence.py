#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
翻訳ユニット結合処理。
"""

from __future__ import annotations

from typing import List, Optional

from ja_dubbing.core.models import Segment
from ja_dubbing.utils import normalize_spaces


def merge_sentence_units(
    segments: List[Segment],
    *,
    max_sentences: int,
    merge_max_chars: int,
    max_gap_sec: float,
) -> List[Segment]:
    """隣接する文を結合して翻訳ユニットを作成する。同一話者のみ結合可能。"""
    if not segments:
        return []

    out: List[Segment] = []
    buf_start: Optional[float] = None
    buf_end: Optional[float] = None
    buf_text = ""
    buf_count = 0
    buf_speaker = ""

    def flush() -> None:
        nonlocal buf_start, buf_end, buf_text, buf_count, buf_speaker
        if buf_start is None or buf_end is None:
            buf_text = ""
            buf_count = 0
            buf_speaker = ""
            return
        t = normalize_spaces(buf_text)
        if t:
            out.append(
                Segment(
                    idx=len(out),
                    start=float(buf_start),
                    end=float(buf_end),
                    text_en=t,
                    speaker_id=buf_speaker,
                )
            )
        buf_start = None
        buf_end = None
        buf_text = ""
        buf_count = 0
        buf_speaker = ""

    for seg in segments:
        t = normalize_spaces(seg.text_en)
        if not t:
            continue

        if buf_start is None:
            buf_start = seg.start
            buf_end = seg.end
            buf_text = t
            buf_count = 1
            buf_speaker = seg.speaker_id
            continue

        gap = max(0.0, seg.start - float(buf_end))
        candidate = normalize_spaces(f"{buf_text} {t}")
        can_merge = (
            buf_count < max_sentences
            and gap <= max_gap_sec
            and len(candidate) <= merge_max_chars
            and buf_speaker == seg.speaker_id
        )

        if can_merge:
            buf_end = seg.end
            buf_text = candidate
            buf_count += 1
        else:
            flush()
            buf_start = seg.start
            buf_end = seg.end
            buf_text = t
            buf_count = 1
            buf_speaker = seg.speaker_id

    flush()
    return out
