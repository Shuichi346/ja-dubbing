#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
翻訳ユニット結合処理。
"""

from __future__ import annotations

from typing import List, Optional

from xlanguage_dubbing.core.models import Segment
from xlanguage_dubbing.utils import normalize_spaces


def merge_sentence_units(
    segments: List[Segment],
    *,
    max_sentences: int,
    merge_max_chars: int,
    max_gap_sec: float,
) -> List[Segment]:
    """隣接する文を結合して翻訳ユニットを作成する。"""
    if not segments:
        return []

    out: List[Segment] = []
    buf_start: Optional[float] = None
    buf_end: Optional[float] = None
    buf_text = ""
    buf_count = 0
    buf_speaker = ""
    buf_lang = ""

    def flush() -> None:
        nonlocal buf_start, buf_end, buf_text, buf_count, buf_speaker, buf_lang
        if buf_start is None or buf_end is None:
            buf_text = ""
            buf_count = 0
            buf_speaker = ""
            buf_lang = ""
            return
        t = normalize_spaces(buf_text)
        if t:
            out.append(
                Segment(
                    idx=len(out),
                    start=float(buf_start),
                    end=float(buf_end),
                    text_src=t,
                    speaker_id=buf_speaker,
                    detected_lang=buf_lang,
                )
            )
        buf_start = None
        buf_end = None
        buf_text = ""
        buf_count = 0
        buf_speaker = ""
        buf_lang = ""

    for seg in segments:
        t = normalize_spaces(seg.text_src)
        if not t:
            continue

        if buf_start is None:
            buf_start = seg.start
            buf_end = seg.end
            buf_text = t
            buf_count = 1
            buf_speaker = seg.speaker_id
            buf_lang = seg.detected_lang
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
            if not buf_lang:
                buf_lang = seg.detected_lang
        else:
            flush()
            buf_start = seg.start
            buf_end = seg.end
            buf_text = t
            buf_count = 1
            buf_speaker = seg.speaker_id
            buf_lang = seg.detected_lang

    flush()
    return out
