#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ASR エンジンの統一インターフェース。
"""

from __future__ import annotations

from ja_dubbing.config import ASR_ENGINE


def get_asr_engine() -> str:
    """現在選択されている ASR エンジン名を返す。"""
    return ASR_ENGINE.strip().lower()
