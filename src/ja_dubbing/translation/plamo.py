#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plamo-translate-cli (MCP) による翻訳処理。
サーバーモードの plamo-translate に MCP クライアントで接続して翻訳する。

推論暴走対策:
  - 翻訳を別プロセスで実行し、タイムアウト時はプロセスごと強制終了する
  - PLAMO_TRANSLATE_CLI_REPETITION_PENALTY 環境変数で繰り返し抑制
  - タイムアウト後にサーバーヘルスチェックを行い、復旧を待つ
"""

from __future__ import annotations

import gc
import multiprocessing
import os
import re
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Optional

from ja_dubbing.config import (
    GLITCH_MIN_REPEAT,
    GLITCH_PHRASE,
    INPUT_REPEAT_THRESHOLD,
    INPUT_UNIQUE_RATIO_THRESHOLD,
    PLAMO_TRANSLATE_RETRIES,
    PLAMO_TRANSLATE_RETRY_BACKOFF_SEC,
    TRANSLATE_TIMEOUT_SEC,
)
from ja_dubbing.core.models import Segment
from ja_dubbing.core.progress import ProgressStore
from ja_dubbing.audio.segment_io import load_segments_json, save_segments_json_atomic
from ja_dubbing.utils import PipelineError, print_step


class PlamoTranslateError(Exception):
    """plamo-translate翻訳エラー。"""


# =========================================================
# 推論暴走抑制の環境変数
# =========================================================

_REPETITION_PENALTY_ENV = "PLAMO_TRANSLATE_CLI_REPETITION_PENALTY"
_REPETITION_CONTEXT_SIZE_ENV = "PLAMO_TRANSLATE_CLI_REPETITION_CONTEXT_SIZE"

# タイムアウト後のサーバー復旧待機（秒）
_SERVER_RECOVERY_WAIT_SEC = 5.0
_SERVER_RECOVERY_MAX_WAIT_SEC = 60.0


# =========================================================
# 翻訳「出力」（日本語）の異常検出
# =========================================================


def is_translation_glitch(text_ja: str) -> bool:
    """翻訳結果が異常（繰り返し）かどうかを判定する。"""
    t = (text_ja or "").strip()
    if not t:
        return False

    compact = re.sub(r"\s+", "", t)
    escaped = re.escape(GLITCH_PHRASE)
    pat = re.compile(
        rf"(?:{escaped}.{{0,20}}){{{GLITCH_MIN_REPEAT},}}"
    )
    return bool(pat.search(compact))


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
# 別プロセスでの翻訳実行（推論暴走対策の核心）
# =========================================================


def _translate_in_subprocess(text: str, result_queue: multiprocessing.Queue) -> None:
    """
    別プロセスで翻訳を実行する。
    プロセス内で asyncio イベントループを新規作成するため、
    タイムアウト時にプロセスを kill すればリソースが完全にクリーンアップされる。
    """
    import asyncio

    async def _run() -> str:
        try:
            from plamo_translate.clients.translate import MCPClient
        except ImportError:
            return "__IMPORT_ERROR__"

        client = MCPClient(stream=False)
        messages = [
            {"role": "user", "content": f"input lang=English\n{text}"},
            {"role": "user", "content": "output lang=Japanese\n"},
        ]
        result_parts: list[str] = []
        async for chunk in client.translate(messages):
            result_parts.append(chunk)
        return "".join(result_parts).strip()

    try:
        result = asyncio.run(_run())
        result_queue.put(("ok", result))
    except Exception as exc:
        result_queue.put(("error", str(exc)))


def _translate_with_process_isolation(text: str, timeout_sec: float) -> str:
    """
    翻訳を別プロセスで実行し、タイムアウト時はプロセスごと強制終了する。
    MCPセッションのリーク問題を完全に回避する。
    """
    ctx = multiprocessing.get_context("spawn")
    result_queue = ctx.Queue()
    proc = ctx.Process(
        target=_translate_in_subprocess,
        args=(text, result_queue),
        daemon=True,
    )
    proc.start()
    proc.join(timeout=timeout_sec)

    if proc.is_alive():
        proc.kill()
        proc.join(timeout=5)
        raise PlamoTranslateError(
            f"翻訳タイムアウト（{timeout_sec:.0f}秒）: "
            f"テキスト先頭='{text[:80]}...'"
        )

    if result_queue.empty():
        exit_code = proc.exitcode
        raise PlamoTranslateError(
            f"翻訳プロセスが結果を返さずに終了しました（exit_code={exit_code}）。"
        )

    status, value = result_queue.get_nowait()
    if status == "error":
        raise PlamoTranslateError(f"翻訳エラー: {value}")
    if value == "__IMPORT_ERROR__":
        raise PipelineError(
            "plamo-translate がインストールされていません。\n"
            "以下を実行してください:\n"
            "  uv pip install plamo-translate\n"
        )

    return value


# =========================================================
# サーバー復旧待機
# =========================================================


def _wait_for_server_recovery() -> None:
    """翻訳タイムアウト後にサーバーが復旧するまで待機する。"""
    from ja_dubbing.servers.health import check_plamo_translate_server

    print_step("    plamo-translate サーバーの復旧を確認中...")
    waited = 0.0
    interval = _SERVER_RECOVERY_WAIT_SEC
    while waited < _SERVER_RECOVERY_MAX_WAIT_SEC:
        if check_plamo_translate_server():
            print_step("    plamo-translate サーバー復旧確認")
            return
        time.sleep(interval)
        waited += interval
        print_step(
            f"    サーバー復旧待機中... "
            f"({waited:.0f}/{_SERVER_RECOVERY_MAX_WAIT_SEC:.0f}秒)"
        )

    print_step(
        "    警告: plamo-translate サーバーが復旧しません。"
        "翻訳を続行しますが、失敗する可能性があります。"
    )


# =========================================================
# 翻訳クライアント
# =========================================================


def _setup_repetition_penalty_env() -> None:
    """推論暴走抑制のための環境変数を設定する（未設定の場合のみ）。"""
    if os.environ.get(_REPETITION_PENALTY_ENV) is None:
        os.environ[_REPETITION_PENALTY_ENV] = "1.2"
    if os.environ.get(_REPETITION_CONTEXT_SIZE_ENV) is None:
        os.environ[_REPETITION_CONTEXT_SIZE_ENV] = "200"


class PlamoTranslateClient:
    """plamo-translate-cli MCPクライアントラッパー。"""

    def __init__(self) -> None:
        _setup_repetition_penalty_env()
        self._call_count = 0
        self._gc_interval = 50

    def translate(
        self,
        text: str,
        retries: int = PLAMO_TRANSLATE_RETRIES,
        retry_backoff_sec: float = PLAMO_TRANSLATE_RETRY_BACKOFF_SEC,
    ) -> tuple[str, str]:
        """テキストを英日翻訳する。"""
        last_err: Optional[Exception] = None
        for attempt in range(1, retries + 1):
            try:
                result = _translate_with_process_isolation(
                    text, TRANSLATE_TIMEOUT_SEC
                )
                self._call_count += 1
                if self._call_count % self._gc_interval == 0:
                    gc.collect()
                return result, "stop"
            except PlamoTranslateError as exc:
                last_err = exc
                is_timeout = "タイムアウト" in str(exc)
                if attempt < retries:
                    if is_timeout:
                        _wait_for_server_recovery()
                    wait_sec = retry_backoff_sec * attempt
                    print_step(
                        f"    翻訳リトライ {attempt}/{retries}: "
                        f"{wait_sec:.1f}秒待機... ({exc})"
                    )
                    time.sleep(wait_sec)
            except Exception as exc:
                last_err = exc
                if attempt < retries:
                    wait_sec = retry_backoff_sec * attempt
                    print_step(
                        f"    翻訳リトライ {attempt}/{retries}: "
                        f"{wait_sec:.1f}秒待機... ({exc})"
                    )
                    time.sleep(wait_sec)

        raise PlamoTranslateError(f"翻訳失敗(リトライ枯渇): {last_err}")


# =========================================================
# セグメント翻訳
# =========================================================


def _new_segment_en_only(seg: Segment) -> Segment:
    """英語テキストのみを保持したセグメントを生成する（翻訳再開用）。"""
    return replace(seg, text_ja="")


def translate_segment_safely(client: PlamoTranslateClient, text_en: str) -> str:
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
    client: PlamoTranslateClient,
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
