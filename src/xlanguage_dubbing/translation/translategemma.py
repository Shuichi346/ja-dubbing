#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TranslateGemma-12b-it (GGUF) による多言語翻訳処理。
llama-cpp-python でプロセス内推論する。
55言語対応。日英以外の言語ペアに使用する。

TranslateGemma のチャットテンプレートは特殊な構造のため、
手動でプロンプトを構築して __call__ で直接推論する。
"""

from __future__ import annotations

import gc
from pathlib import Path
from typing import Optional

from xlanguage_dubbing.config import (
    TRANSLATEGEMMA_FILE,
    TRANSLATEGEMMA_N_CTX,
    TRANSLATEGEMMA_N_GPU_LAYERS,
    TRANSLATEGEMMA_REPEAT_PENALTY,
    TRANSLATEGEMMA_REPO,
)
from xlanguage_dubbing.lang_utils import LANG_CODE_TO_NAME, get_lang_name
from xlanguage_dubbing.utils import PipelineError, print_step

_GEMMA_MODEL = None


def _get_model_path() -> str:
    """TranslateGemma GGUF モデルファイルのパスを取得する。"""
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise PipelineError(
            "huggingface-hub がインストールされていません。\n"
            "  uv sync を実行してください。\n"
        ) from exc

    print_step(
        f"  TranslateGemma モデルを取得中: "
        f"{TRANSLATEGEMMA_REPO}/{TRANSLATEGEMMA_FILE}"
    )
    path = hf_hub_download(
        repo_id=TRANSLATEGEMMA_REPO,
        filename=TRANSLATEGEMMA_FILE,
    )
    print_step(f"  モデルパス: {path}")
    return path


def _get_gemma_model():
    """TranslateGemma モデルを遅延ロードする。"""
    global _GEMMA_MODEL
    if _GEMMA_MODEL is not None:
        return _GEMMA_MODEL

    try:
        from llama_cpp import Llama
    except ImportError as exc:
        raise PipelineError(
            "llama-cpp-python がインストールされていません。\n"
            "  uv sync を実行してください。\n"
        ) from exc

    model_path = _get_model_path()

    print_step("  TranslateGemma モデルをロード中...")
    _GEMMA_MODEL = Llama(
        model_path=model_path,
        n_gpu_layers=TRANSLATEGEMMA_N_GPU_LAYERS,
        n_ctx=TRANSLATEGEMMA_N_CTX,
        verbose=False,
    )
    print_step("  TranslateGemma モデルのロード完了")
    return _GEMMA_MODEL


def release_gemma_model() -> None:
    """TranslateGemma モデルを解放する。"""
    global _GEMMA_MODEL
    if _GEMMA_MODEL is not None:
        del _GEMMA_MODEL
        _GEMMA_MODEL = None
        gc.collect()
        print_step("  TranslateGemma モデルを解放しました")


def _build_translategemma_prompt(
    text: str,
    source_lang_code: str,
    target_lang_code: str,
) -> str:
    """TranslateGemma のプロンプトを手動構築する。

    TranslateGemma のチャットテンプレートは Gemma 3 ベースの特殊な形式。
    llama-cpp-python の create_chat_completion ではテンプレートの互換性問題があるため、
    プロンプトを直接構築して __call__ (completion) で推論する。
    """
    source_lang = get_lang_name(source_lang_code)
    target_lang = get_lang_name(target_lang_code)

    # TranslateGemma の公式チャットテンプレートに準拠したプロンプト
    prompt = (
        f"<start_of_turn>user\n"
        f"You are a professional {source_lang} ({source_lang_code}) to "
        f"{target_lang} ({target_lang_code}) translator. "
        f"Your goal is to accurately convey the meaning and nuances of the "
        f"original {source_lang} text while adhering to {target_lang} grammar, "
        f"vocabulary, and cultural sensitivities.\n"
        f"Produce only the {target_lang} translation, without any additional "
        f"explanations or commentary. Please translate the following "
        f"{source_lang} text into {target_lang}:\n\n\n"
        f"{text.strip()}<end_of_turn>\n"
        f"<start_of_turn>model\n"
    )
    return prompt


def translate_text_gemma(
    text: str,
    source_lang_code: str,
    target_lang_code: str,
) -> str:
    """TranslateGemma で多言語翻訳する。

    source_lang_code, target_lang_code: ISO 639-1 コード（例: "fr", "de", "zh"）
    """
    model = _get_gemma_model()

    prompt = _build_translategemma_prompt(text, source_lang_code, target_lang_code)

    # completion API で直接推論する（チャットテンプレート問題を回避）
    response = model(
        prompt,
        max_tokens=TRANSLATEGEMMA_N_CTX // 2,
        temperature=0.0,
        top_p=1.0,
        repeat_penalty=TRANSLATEGEMMA_REPEAT_PENALTY,
        stop=["<end_of_turn>", "<start_of_turn>"],
        echo=False,
    )

    choices = response.get("choices", [])
    if not choices:
        return ""

    result = choices[0].get("text", "")
    # 制御トークンの残留を除去する
    result = result.replace("<end_of_turn>", "").replace("<start_of_turn>", "")
    return result.strip()
