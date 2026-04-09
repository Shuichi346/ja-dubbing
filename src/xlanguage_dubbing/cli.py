#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLIエントリーポイント。
"""

from __future__ import annotations

import multiprocessing
import sys
from pathlib import Path

from xlanguage_dubbing.config import (
    INPUT_LANG,
    OUTPUT_LANG,
    TEMP_ROOT,
    VIDEO_EXTS,
    VIDEO_FOLDER,
)
from xlanguage_dubbing.core.pipeline import process_one_video
from xlanguage_dubbing.segments.spacy_split import initialize_spacy
from xlanguage_dubbing.servers.health import generate_start_script
from xlanguage_dubbing.translation.cat_translate import CatTranslateClient
from xlanguage_dubbing.tts.reference import SpeakerReferenceCache
from xlanguage_dubbing.utils import (
    PipelineError,
    ensure_dir,
    force_memory_cleanup,
    print_step,
    which_or_raise,
)


def _normalize_user_path(raw: str) -> Path:
    """ユーザー入力のパス文字列を正規化する。"""
    s = raw.strip()
    s = s.strip("'\"")
    s = s.replace("\\ ", " ")
    return Path(s).expanduser().resolve()


def _prompt_video_path() -> Path:
    """ターミナルから動画パスを入力させる。"""
    print_step("VIDEO_FOLDER に処理対象の動画がありません。")
    print_step("処理したい動画ファイルのパスを直接入力してください。")

    while True:
        try:
            raw_input = input("\n動画のパスを入力: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)

        if not raw_input:
            print("パスが空です。もう一度入力してください。")
            continue

        video_path = _normalize_user_path(raw_input)

        if not video_path.exists():
            print(f"ファイルが見つかりません: {video_path}")
            continue

        if not video_path.is_file():
            print(f"ファイルではありません: {video_path}")
            continue

        if video_path.suffix.lower() not in VIDEO_EXTS:
            supported = ", ".join(sorted(VIDEO_EXTS))
            print(f"対応していない拡張子です: {video_path.suffix}")
            print(f"対応形式: {supported}")
            continue

        return video_path


def preflight_checks() -> None:
    """事前チェック。"""
    which_or_raise("ffmpeg")
    which_or_raise("ffprobe")
    ensure_dir(TEMP_ROOT)

    print_step(f"  入力言語: {INPUT_LANG}")
    print_step(f"  出力言語: {OUTPUT_LANG}")

    try:
        import torch

        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            print_step("  推論デバイス: mps")
        else:
            print_step("  推論デバイス: cpu")
    except ImportError as exc:
        raise PipelineError(
            "torch がインストールされていません。\n"
            "  uv sync を実行してください。"
        ) from exc


def list_videos(folder: Path) -> list[Path]:
    """対象動画ファイルのリストを取得する。"""
    if not folder.exists():
        return []
    return sorted(
        p for p in folder.rglob("*")
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS
    )


def _process_single_video(video_path: Path) -> int:
    """動画1本を処理する。"""
    print_step(f"単体モード: {video_path.name}")
    client = CatTranslateClient()
    work_dir = TEMP_ROOT / video_path.stem
    ensure_dir(work_dir)
    ref_cache = SpeakerReferenceCache(work_dir / "speaker_refs")
    try:
        process_one_video(video_path, client, ref_cache)
    except Exception as exc:
        print_step(f"エラー: {video_path}\n  {exc}")
        return 2
    finally:
        del ref_cache
        force_memory_cleanup()
        print_step("メモリクリーンアップ完了")

    print_step("\n処理完了しました。")
    return 0


def _process_folder_videos(videos: list[Path]) -> int:
    """フォルダ内の動画を順次処理する。"""
    print_step(f"処理対象動画数: {len(videos)}")
    client = CatTranslateClient()

    failed: list[Path] = []
    for idx, v in enumerate(videos, start=1):
        print_step(f"\n[{idx}/{len(videos)}] 処理開始: {v.name}")
        work_dir = TEMP_ROOT / v.stem
        ensure_dir(work_dir)
        ref_cache = SpeakerReferenceCache(work_dir / "speaker_refs")
        try:
            process_one_video(v, client, ref_cache)
        except Exception as exc:
            print_step(f"エラー: {v}\n  {exc}")
            failed.append(v)
        finally:
            del ref_cache
            force_memory_cleanup()
            print_step(f"[{idx}/{len(videos)}] メモリクリーンアップ完了")

    if failed:
        print_step(f"\n失敗: {len(failed)}/{len(videos)}")
        for f in failed:
            print_step(f"  - {f}")
        return 2

    print_step("\n全て完了しました。")
    return 0


def main() -> int:
    """メインエントリーポイント。"""
    try:
        multiprocessing.set_start_method("spawn", force=False)
    except RuntimeError:
        pass

    if "--generate-script" in sys.argv:
        script_path = Path("start_servers.sh")
        generate_start_script(script_path)
        print_step(f"起動スクリプトを生成しました: {script_path}")
        return 0

    initialize_spacy()

    try:
        preflight_checks()

        videos = list_videos(VIDEO_FOLDER)

        if videos:
            return _process_folder_videos(videos)
        else:
            video_path = _prompt_video_path()
            return _process_single_video(video_path)

    except Exception as exc:
        print_step(f"致命的エラー: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
