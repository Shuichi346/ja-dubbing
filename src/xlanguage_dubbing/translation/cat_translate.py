#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CAT-Translate-7b (GGUF) による英日翻訳処理。
llama-cpp-python を使い、プロセス内で直接推論する（サーバー不要）。
モデルは huggingface_hub 経由で自動ダウンロードされる。

翻訳異常検出:
  - 入力（英語）: 同一フレーズのN回以上繰り返しでスキップ
  - 出力（日本語）: 同一フレーズのN回以上繰り返しで異常とみなす
"""

from __future__ import annotations

import gc
import re
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Optional

from xlanguage_dubbing.config import (
    CAT_TRANSLATE_FILE,
    CAT_TRANSLATE_N_CTX,
    CAT_TRANSLATE_N_GPU_LAYERS,
    CAT_TRANSLATE_REPEAT_PENALTY,
    CAT_TRANSLATE_REPO,
    CAT_TRANSLATE_RETRIES,
    CAT_TRANSLATE_RETRY_BACKOFF_SEC,
    INPUT_REPEAT_THRESHOLD,
    INPUT_UNIQUE_RATIO_THRESHOLD,
    OUTPUT_REPEAT_THRESHOLD,
)
from xlanguage_dubbing.core.models import Segment
from xlanguage_dubbing.core.progress import ProgressStore
from xlanguage_dubbing.audio.segment_io import load_segments_json, save_segments_json_atomic
from xlanguage_dubbing.utils import PipelineError, print_step


class CatTranslateError(Exception):
    """CAT-Translate 翻訳エラー。"""


# モデルの遅延ロード用グローバルキャッシュ
_CAT_MODEL = None


# =========================================================
# モデル管理
# =========================================================


def _get_model_path() -> str:
    """GGUF モデルファイルのパスを取得する（未ダウンロードなら自動ダウンロード）。"""
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise PipelineError(
            "huggingface-hub がインストールされていません。\n"
            "以下を実行してください:\n"
            "  uv sync\n"
        ) from exc

    print_step(f"  モデルを取得中: {CAT_TRANSLATE_REPO}/{CAT_TRANSLATE_FILE}")
    path = hf_hub_download(
        repo_id=CAT_TRANSLATE_REPO,
        filename=CAT_TRANSLATE_FILE,
    )
    print_step(f"  モデルパス: {path}")
    return path


def _get_cat_model():
    """CAT-Translate モデルを遅延ロードする。"""
    global _CAT_MODEL
    if _CAT_MODEL is not None:
        return _CAT_MODEL

    try:
        from llama_cpp import Llama
    except ImportError as exc:
        raise PipelineError(
            "llama-cpp-python がインストールされていません。\n"
            "以下を実行してください:\n"
            "  uv sync\n"
        ) from exc

    model_path = _get_model_path()

    print_step("  CAT-Translate モデルをロード中...")
    _CAT_MODEL = Llama(
        model_path=model_path,
        n_gpu_layers=CAT_TRANSLATE_N_GPU_LAYERS,
        n_ctx=CAT_TRANSLATE_N_CTX,
        verbose=False,
    )
    print_step("  CAT-Translate モデルのロード完了")
    return _CAT_MODEL


# =========================================================
# 翻訳「出力」（日本語）の異常検出
# =========================================================


def _detect_repeated_phrases_ja(text_ja: str) -> bool:
    """
    翻訳結果（日本語）に同一フレーズがN回以上繰り返されていたら異常とみなす。
    句読点（。、！？）で分割し、同一フレーズの出現回数を検査する。
    """
    t = (text_ja or "").strip()
    if not t:
        return False

    # 句読点で分割して各フレーズを取得する
    phrases = re.split(r"[。、！？!?,.\s]+", t)
    phrases = [p.strip() for p in phrases if len(p.strip()) >= 2]

    if len(phrases) < OUTPUT_REPEAT_THRESHOLD:
        return False

    counter = Counter(phrases)
    most_common_count = counter.most_common(1)[0][1]
    if most_common_count >= OUTPUT_REPEAT_THRESHOLD:
        return True

    # 連続する同一フレーズも検出する
    consecutive = 1
    for i in range(1, len(phrases)):
        if phrases[i] == phrases[i - 1]:
            consecutive += 1
            if consecutive >= OUTPUT_REPEAT_THRESHOLD:
                return True
        else:
            consecutive = 1

    return False


def is_translation_glitch(text_ja: str) -> bool:
    """翻訳結果が異常（繰り返し）かどうかを判定する。"""
    return _detect_repeated_phrases_ja(text_ja)


# =========================================================
# 翻訳「入力」（英語）の繰り返し検出
# =========================================================


def _is_repetitive_input(text_en: str) -> bool:
    """入力テキストが繰り返しで翻訳不要かを判定する。"""
    t = (text_en or "").strip()
    if not t:
        return True

    phrases = re.findall(r'"([^"]+)"', t)
    if not phrases:
        phrases = re.split(r"(?<=[\.\!\?])\s+", t)
        phrases = [p.strip() for p in phrases if p.strip()]

    if len(phrases) <= 2:
        return False

    unique_phrases = set(p.strip().lower() for p in phrases)
    unique_ratio = len(unique_phrases) / len(phrases)
    if unique_ratio < INPUT_UNIQUE_RATIO_THRESHOLD:
        return True

    counter = Counter(p.strip().lower() for p in phrases)
    most_common_count = counter.most_common(1)[0][1]
    if most_common_count >= INPUT_REPEAT_THRESHOLD:
        return True

    return False


# =========================================================
# 翻訳実行
# =========================================================


def _translate_text(text: str) -> str:
    """
    CAT-Translate-7b で英語テキストを日本語に翻訳する。
    チャットテンプレート（ChatML形式）は GGUF メタデータから自動適用される。
    """
    model = _get_cat_model()

    prompt_content = (
        f"Translate the following English text into Japanese.\n\n{text}"
    )

    messages = [
        {"role": "user", "content": prompt_content},
    ]

    response = model.create_chat_completion(
        messages=messages,
        max_tokens=CAT_TRANSLATE_N_CTX // 2,
        temperature=0.0,
        top_p=1.0,
        repeat_penalty=CAT_TRANSLATE_REPEAT_PENALTY,
    )

    choices = response.get("choices", [])
    if not choices:
        return ""

    result = choices[0].get("message", {}).get("content", "")
    return result.strip()


# =========================================================
# 翻訳クライアント
# =========================================================


class CatTranslateClient:
    """CAT-Translate 翻訳クライアント。"""

    def __init__(self) -> None:
        self._call_count = 0
        self._gc_interval = 50

    def translate(
        self,
        text: str,
        retries: int = CAT_TRANSLATE_RETRIES,
        retry_backoff_sec: float = CAT_TRANSLATE_RETRY_BACKOFF_SEC,
    ) -> tuple[str, str]:
        """テキストを英日翻訳する。"""
        last_err: Optional[Exception] = None
        for attempt in range(1, retries + 1):
            try:
                result = _translate_text(text)
                self._call_count += 1
                if self._call_count % self._gc_interval == 0:
                    gc.collect()
                return result, "stop"
            except Exception as exc:
                last_err = exc
                if attempt < retries:
                    wait_sec = retry_backoff_sec * attempt
                    print_step(
                        f"    翻訳リトライ {attempt}/{retries}: "
                        f"{wait_sec:.1f}秒待機... ({exc})"
                    )
                    time.sleep(wait_sec)

        raise CatTranslateError(f"翻訳失敗(リトライ枯渇): {last_err}")


# =========================================================
# セグメント翻訳
# =========================================================


def _new_segment_en_only(seg: Segment) -> Segment:
    """英語テキストのみを保持したセグメントを生成する（翻訳再開用）。"""
    return replace(seg, text_ja="")


def translate_segment_safely(client: CatTranslateClient, text_en: str) -> str:
    """セグメントを安全に翻訳する。"""
    t = (text_en or "").strip()
    if not t:
        return ""

    if _is_repetitive_input(t):
        print_step("    繰り返し入力を検出 → スキップ")
        return "（繰り返し音声）"

    if len(t) <= 2000:
        out, _ = client.translate(t)
        ja = out.strip()
        if is_translation_glitch(ja):
            return "翻訳エラー"
        return ja

    parts = re.split(r"(?<=[\.\!\?])\s+", t)
    outs: list[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if _is_repetitive_input(p):
            outs.append("繰り返し音声エラー")
            continue
        out, _ = client.translate(p)
        ja = out.strip()
        if is_translation_glitch(ja):
            outs.append("翻訳エラー")
        else:
            outs.append(ja)

    joined = " ".join([o for o in outs if o])
    if is_translation_glitch(joined):
        return "翻訳エラー"
    return joined


def translate_segments_resumable(
    client: CatTranslateClient,
    segments_en: list[Segment],
    seg_json_enja: Path,
    progress: ProgressStore,
) -> list[Segment]:
    """セグメントを再開可能な形式で翻訳する。"""
    if seg_json_enja.exists():
        try:
            loaded = load_segments_json(seg_json_enja)
            if len(loaded) == len(segments_en):
                segments = loaded
            else:
                segments = [_new_segment_en_only(s) for s in segments_en]
        except Exception:
            segments = [_new_segment_en_only(s) for s in segments_en]
    else:
        segments = [_new_segment_en_only(s) for s in segments_en]

    total = len(segments)
    for segno, seg in enumerate(segments, start=1):
        if (seg.text_ja or "").strip():
            if is_translation_glitch(seg.text_ja):
                segments[segno - 1] = replace(seg, text_ja="翻訳エラー")
                save_segments_json_atomic(segments, seg_json_enja)
                progress.set_step("translate_done", False)
                progress.set_artifact(
                    "segments_en_ja_json", str(seg_json_enja)
                )
                progress.save()
            continue

        print_step(
            f"  翻訳 {segno}/{total}: {seg.start:.3f}-{seg.end:.3f}  "
            f"'{seg.text_en[:60]}'"
        )
        ja = translate_segment_safely(client, seg.text_en)
        segments[segno - 1] = replace(seg, text_ja=ja)
        save_segments_json_atomic(segments, seg_json_enja)
        progress.set_step("translate_done", False)
        progress.set_artifact("segments_en_ja_json", str(seg_json_enja))
        progress.save()

    progress.set_step("translate_done", True)
    progress.save()
    return segments
