#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
リタイム関連処理。
音声に合わせて動画速度を変更する。
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from xlanguage_dubbing.core.models import RetimePart, Segment, TtsMeta

# 映像チャンクとして成立しない極端に短い区間の閾値（秒）
_MIN_CHUNK_SEC = 0.15


def build_retime_parts(
    segments: List[Segment],
    tts_meta: Dict[int, TtsMeta],
    video_duration_sec: float,
) -> Tuple[List[RetimePart], float]:
    """
    元動画を「ギャップ(等速) + 発話(伸縮) + ... + 末尾(等速)」に分解する。
    新しいタイムラインの合計秒数も返す。
    """
    raw_parts: List[RetimePart] = []
    cursor = 0.0
    vd = max(0.0, float(video_duration_sec))

    for segno, seg in enumerate(segments, start=1):
        if cursor >= vd - 1e-6:
            break

        start = max(0.0, float(seg.start))
        end = max(start, float(seg.end))
        start = min(start, vd)
        end = min(end, vd)

        if end <= cursor + 1e-6:
            continue

        # ギャップ（等速）
        if start > cursor + 1e-6:
            gap_dur = start - cursor
            raw_parts.append(
                RetimePart(
                    kind="gap",
                    orig_start=cursor,
                    orig_end=start,
                    out_duration=gap_dur,
                    speed=1.0,
                )
            )

        # 発話区間
        orig_dur = max(0.001, end - start)
        meta = tts_meta.get(segno)

        if meta and meta.duration_sec > 0.0:
            out_dur = float(meta.duration_sec)
            speed = orig_dur / max(0.001, out_dur)
            raw_parts.append(
                RetimePart(
                    kind="speech",
                    orig_start=start,
                    orig_end=end,
                    out_duration=out_dur,
                    speed=speed,
                    segno=segno,
                )
            )
        else:
            raw_parts.append(
                RetimePart(
                    kind="speech",
                    orig_start=start,
                    orig_end=end,
                    out_duration=orig_dur,
                    speed=1.0,
                    segno=segno,
                )
            )

        cursor = end

    # 末尾（等速）
    if vd > cursor + 1e-6:
        tail_dur = vd - cursor
        raw_parts.append(
            RetimePart(
                kind="tail",
                orig_start=cursor,
                orig_end=vd,
                out_duration=tail_dur,
                speed=1.0,
            )
        )

    # 短すぎるギャップ/テールを隣接パートに吸収する
    parts = _merge_tiny_parts(raw_parts)

    total_out = sum(p.out_duration for p in parts)
    return parts, float(total_out)


def _merge_tiny_parts(raw: List[RetimePart]) -> List[RetimePart]:
    """
    映像として成立しないほど短い gap / tail パートを
    隣接する speech パートの元区間に吸収する。
    """
    if not raw:
        return []

    result: List[RetimePart] = []

    i = 0
    while i < len(raw):
        part = raw[i]
        orig_dur = max(0.0, part.orig_end - part.orig_start)

        # speech パートはそのまま保持
        if part.kind == "speech":
            result.append(part)
            i += 1
            continue

        # gap / tail が十分な長さならそのまま
        if orig_dur >= _MIN_CHUNK_SEC:
            result.append(part)
            i += 1
            continue

        # 短すぎる gap / tail → 次の speech パートの先頭に吸収を試みる
        if i + 1 < len(raw) and raw[i + 1].kind == "speech":
            nxt = raw[i + 1]
            new_orig_start = part.orig_start
            new_orig_dur = max(0.001, nxt.orig_end - new_orig_start)
            new_speed = new_orig_dur / max(0.001, nxt.out_duration)
            result.append(
                RetimePart(
                    kind=nxt.kind,
                    orig_start=new_orig_start,
                    orig_end=nxt.orig_end,
                    out_duration=nxt.out_duration,
                    speed=new_speed,
                    segno=nxt.segno,
                )
            )
            i += 2
            continue

        # 前の speech パートの末尾に吸収を試みる
        if result and result[-1].kind == "speech":
            prev = result[-1]
            new_orig_end = part.orig_end
            new_orig_dur = max(0.001, new_orig_end - prev.orig_start)
            new_speed = new_orig_dur / max(0.001, prev.out_duration)
            result[-1] = RetimePart(
                kind=prev.kind,
                orig_start=prev.orig_start,
                orig_end=new_orig_end,
                out_duration=prev.out_duration,
                speed=new_speed,
                segno=prev.segno,
            )
            i += 1
            continue

        # どちらにも吸収できない場合はそのまま残す
        result.append(part)
        i += 1

    return result
