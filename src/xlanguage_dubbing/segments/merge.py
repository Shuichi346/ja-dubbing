#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Whisperセグメント結合処理。
"""

from __future__ import annotations

import re
from typing import List, Optional

from xlanguage_dubbing.config import (
    MERGE_FORCE_IF_VERY_SHORT_SEC,
    MERGE_GAP_SEC,
    MERGE_MAX_CHARS,
    MERGE_MAX_SEC,
)
from xlanguage_dubbing.core.models import Segment


def _ends_sentence(text: str) -> bool:
    """テキストが文末で終わっているかを判定する。"""
    t = (text or "").strip()
    return bool(re.search(r"[\.!\?。！？]$", t))


def merge_segments(segments: List[Segment]) -> List[Segment]:
    """短すぎるセグメントを結合して実用単位に戻す。同一話者のみ結合可能。"""
    if not segments:
        return []

    merged: List[Segment] = []
    buf: Optional[Segment] = None

    def flush() -> None:
        nonlocal buf
        if buf is not None and (buf.text_en or "").strip():
            merged.append(buf)
        buf = None

    for s in segments:
        text = (s.text_en or "").strip()
        if not text:
            continue

        if buf is None:
            buf = Segment(
                idx=len(merged), start=s.start, end=s.end,
                text_en=text, speaker_id=s.speaker_id,
            )
            continue

        gap = max(0.0, s.start - buf.end)
        new_text = (buf.text_en + " " + text).strip()
        new_dur = max(0.0, s.end - buf.start)

        short_buf = buf.duration <= MERGE_FORCE_IF_VERY_SHORT_SEC
        short_cur = s.duration <= MERGE_FORCE_IF_VERY_SHORT_SEC

        can_merge = (
            gap <= MERGE_GAP_SEC
            and new_dur <= MERGE_MAX_SEC
            and len(new_text) <= MERGE_MAX_CHARS
            and buf.speaker_id == s.speaker_id
            and (short_buf or short_cur or not _ends_sentence(buf.text_en))
        )

        if can_merge:
            buf = Segment(
                idx=buf.idx, start=buf.start, end=s.end,
                text_en=new_text, speaker_id=buf.speaker_id,
            )
        else:
            flush()
            buf = Segment(
                idx=len(merged), start=s.start, end=s.end,
                text_en=text, speaker_id=s.speaker_id,
            )

    flush()

    out: List[Segment] = []
    for i, s in enumerate(merged):
        out.append(Segment(
            idx=i, start=s.start, end=s.end,
            text_en=s.text_en, speaker_id=s.speaker_id,
        ))
    return out
