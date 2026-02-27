#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Whisperセグメントと話者分離結果の突合処理。
"""

from __future__ import annotations

from typing import List

from ja_dubbing.core.models import DiarizationSegment, Segment


def assign_speakers(
    segments: List[Segment],
    diarization: List[DiarizationSegment],
) -> List[Segment]:
    """
    各Whisperセグメントに最も重複時間が長い話者IDを割り当てる。
    重複がない場合は、直前セグメントの話者IDを引き継ぐ。
    直前もない場合は、時間的に最も近いdiarizationセグメントの話者を使用する。
    """
    result: List[Segment] = []
    prev_speaker = ""

    for seg in segments:
        overlap: dict[str, float] = {}
        for dia in diarization:
            # 重複区間を計算
            ov_start = max(seg.start, dia.start)
            ov_end = min(seg.end, dia.end)
            if ov_end > ov_start:
                overlap[dia.speaker] = (
                    overlap.get(dia.speaker, 0.0) + (ov_end - ov_start)
                )

        if overlap:
            best_speaker = max(overlap, key=lambda k: overlap[k])
        else:
            # 重複なし: 直前セグメントの話者を引き継ぐ
            best_speaker = prev_speaker if prev_speaker else ""

            # 直前もない場合: 時間的に最も近いdiarizationセグメントの話者を使用
            if not best_speaker and diarization:
                seg_mid = (seg.start + seg.end) / 2.0
                closest = min(
                    diarization,
                    key=lambda d: min(
                        abs(d.start - seg_mid), abs(d.end - seg_mid)
                    ),
                )
                best_speaker = closest.speaker

            # それでも見つからない場合はUNKNOWN
            if not best_speaker:
                best_speaker = "UNKNOWN"

        prev_speaker = best_speaker

        result.append(Segment(
            idx=seg.idx,
            start=seg.start,
            end=seg.end,
            text_en=seg.text_en,
            text_ja=seg.text_ja,
            speaker_id=best_speaker,
        ))
    return result
