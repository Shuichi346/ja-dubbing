#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
サーバーヘルスチェック・起動スクリプト生成。
TTSエンジンに応じて MioTTS のチェックをスキップする。
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from ja_dubbing.config import MIOTTS_API_URL, TTS_ENGINE
from ja_dubbing.utils import PipelineError, print_step


def check_health(url: str, timeout: float = 5.0) -> bool:
    """URLにGETリクエストを送り応答があるか確認する。"""
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def wait_for_server(
    name: str,
    url: str,
    timeout: float = 120.0,
    interval: float = 3.0,
) -> None:
    """サーバーが応答するまで待機する。"""
    print_step(f"  {name} の応答を待機中: {url}")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check_health(url):
            print_step(f"  {name} 応答確認")
            return
        time.sleep(interval)
    raise PipelineError(f"{name} が {timeout}秒以内に応答しません: {url}")


def check_plamo_translate_server() -> bool:
    """plamo-translate-cliサーバーが起動しているか確認する。"""
    try:
        from plamo_translate.servers.utils import update_config, verify_mcp_server_ready
        import asyncio

        config = update_config()
        if "port" not in config:
            return False
        port = config["port"]
        tools = asyncio.run(verify_mcp_server_ready(port))
        return "plamo-translate" in tools
    except Exception:
        return False


def _get_tts_engine() -> str:
    """現在選択されている TTS エンジン名を返す。"""
    return TTS_ENGINE.strip().lower()


def preflight_server_checks() -> None:
    """全サーバーのヘルスチェックを実行する。"""
    if not check_plamo_translate_server():
        raise PipelineError(
            "plamo-translate-cli サーバーに接続できません。\n"
            "  以下を別ターミナルで実行してください:\n"
            "  uv run plamo-translate server --precision 8bit"
        )

    tts_engine = _get_tts_engine()

    if tts_engine == "kokoro":
        # Kokoro はプロセス内で直接推論するためサーバー不要
        print_step("  TTS エンジン: Kokoro（サーバー不要）")
        return

    # MioTTS の場合はサーバーチェック
    miotts_health = f"{MIOTTS_API_URL.rstrip('/')}/health"
    if not check_health(miotts_health):
        raise PipelineError(
            f"MioTTS APIサーバーに接続できません: {MIOTTS_API_URL}\n"
            "  MioTTS-Inference の run_server.py を起動してください。"
        )


def generate_start_script(output_path: Path) -> None:
    """サーバー起動用シェルスクリプトを生成する。"""
    from ja_dubbing.config import (
        MIOTTS_CODEC_MODEL,
        MIOTTS_DEVICE,
        MIOTTS_INFERENCE_DIR,
        MIOTTS_LLM_MODEL,
        MIOTTS_LLM_PORT,
        MIOTTS_MAX_TEXT_LENGTH,
        PLAMO_TRANSLATE_PRECISION,
    )

    parsed = urlparse(MIOTTS_API_URL)
    miotts_api_port = parsed.port or 8001

    tts_engine = _get_tts_engine()

    if tts_engine == "kokoro":
        # Kokoro モードでは翻訳サーバーのみ必要
        script = f"""#!/bin/bash
# === ja-dubbing サーバー起動スクリプト（Kokoro TTSモード） ===
# .env の設定値に基づいて自動生成されたスクリプトです。
# Kokoro TTS はプロセス内で動作するため、MioTTS サーバーは不要です。

echo "=== ja-dubbing サーバー起動（Kokoro TTSモード） ==="

PIDS=()

cleanup() {{
    echo ""
    echo "=== 全サーバーを停止します ==="
    for pid in "${{PIDS[@]}}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null
            echo "  停止: PID=$pid"
        fi
    done
    wait 2>/dev/null
    echo "=== 停止完了 ==="
    exit 1
}}

trap cleanup INT TERM

check_process() {{
    local pid=$1
    local name=$2
    if ! kill -0 "$pid" 2>/dev/null; then
        echo "エラー: $name が起動に失敗しました (PID=$pid)"
        cleanup
    fi
}}

echo "1/1: plamo-translate-cli 翻訳サーバー起動 (MLX {PLAMO_TRANSLATE_PRECISION})"
uv run plamo-translate server --precision {PLAMO_TRANSLATE_PRECISION} &
PLAMO_PID=$!
PIDS+=("$PLAMO_PID")

echo "  plamo-translate 起動待機中（15秒）..."
sleep 15
check_process "$PLAMO_PID" "plamo-translate"
echo "  plamo-translate サーバー起動完了"

echo ""
echo "=== サーバー起動完了（Kokoro TTSモード） ==="
echo "  plamo-translate:  PID=$PLAMO_PID (MLX {PLAMO_TRANSLATE_PRECISION})"
echo "  MioTTS:           不要（Kokoro TTS 使用）"
echo ""
echo "停止するには: Ctrl+C"
wait
"""
    else:
        # MioTTS モード（従来と同じ）
        script = f"""#!/bin/bash
# === ja-dubbing サーバー起動スクリプト ===
# .env の設定値に基づいて自動生成されたスクリプトです。

echo "=== ja-dubbing サーバー起動 ==="

PIDS=()

cleanup() {{
    echo ""
    echo "=== 全サーバーを停止します ==="
    for pid in "${{PIDS[@]}}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null
            echo "  停止: PID=$pid"
        fi
    done
    wait 2>/dev/null
    echo "=== 停止完了 ==="
    exit 1
}}

trap cleanup INT TERM

check_process() {{
    local pid=$1
    local name=$2
    if ! kill -0 "$pid" 2>/dev/null; then
        echo "エラー: $name が起動に失敗しました (PID=$pid)"
        cleanup
    fi
}}

echo "1/3: plamo-translate-cli 翻訳サーバー起動 (MLX {PLAMO_TRANSLATE_PRECISION})"
uv run plamo-translate server --precision {PLAMO_TRANSLATE_PRECISION} &
PLAMO_PID=$!
PIDS+=("$PLAMO_PID")

echo "  plamo-translate 起動待機中（15秒）..."
sleep 15
check_process "$PLAMO_PID" "plamo-translate"
echo "  plamo-translate サーバー起動完了"

echo "2/3: MioTTS LLMバックエンド起動 (ポート{MIOTTS_LLM_PORT})"
OLLAMA_HOST=localhost:{MIOTTS_LLM_PORT} ollama serve &
MIOTTS_LLM_PID=$!
PIDS+=("$MIOTTS_LLM_PID")

echo "  Ollama 起動待機中（5秒）..."
sleep 5
check_process "$MIOTTS_LLM_PID" "Ollama (MioTTS LLM)"

echo "  MioTTS LLMモデルをプル中..."
if ! OLLAMA_HOST=localhost:{MIOTTS_LLM_PORT} ollama pull {MIOTTS_LLM_MODEL}; then
    echo "エラー: MioTTS LLMモデルのプルに失敗しました"
    cleanup
fi
echo "  MioTTS LLMモデル準備完了: {MIOTTS_LLM_MODEL}"

echo "3/3: MioTTS APIサーバー起動 (ポート{miotts_api_port})"
cd {MIOTTS_INFERENCE_DIR} || {{ echo "エラー: {MIOTTS_INFERENCE_DIR} ディレクトリが見つかりません"; cleanup; }}
uv run python run_server.py \\
    --llm-base-url http://localhost:{MIOTTS_LLM_PORT}/v1 \\
    --device {MIOTTS_DEVICE} \\
    --codec-model {MIOTTS_CODEC_MODEL} \\
    --max-text-length {MIOTTS_MAX_TEXT_LENGTH} \\
    --port {miotts_api_port} &
MIOTTS_API_PID=$!
PIDS+=("$MIOTTS_API_PID")
cd -

echo "  MioTTS API 起動待機中（10秒）..."
sleep 10
check_process "$MIOTTS_API_PID" "MioTTS API"

echo ""
echo "=== 全サーバー起動完了 ==="
echo "  plamo-translate:  PID=$PLAMO_PID (MLX {PLAMO_TRANSLATE_PRECISION})"
echo "  MioTTS LLM:       PID=$MIOTTS_LLM_PID (ポート{MIOTTS_LLM_PORT})"
echo "  MioTTS API:       PID=$MIOTTS_API_PID (ポート{miotts_api_port})"
echo ""
echo "停止するには: Ctrl+C"
echo "または: pkill -f 'plamo-translate' && pkill -f 'ollama serve' && pkill -f 'run_server.py'"
wait
"""
    output_path.write_text(script, encoding="utf-8")
    output_path.chmod(0o755)
    print_step(f"  起動スクリプト生成: {output_path}")
