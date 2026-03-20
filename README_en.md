<table>
  <thead>
    <tr>
      <th style="text-align:center"><a href="README_en.md">English</a></th>
      <th style="text-align:center"><a href="README.md">日本語</a></th>
    </tr>
  </thead>
</table>

<p align="center">
  <h1 align="center">ja-dubbing</h1>
  <p align="center">A tool to convert English videos into Japanese dubbed videos while maintaining the original speaker's voice characteristics</p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-5.0.0-blue" alt="Version">
  <img src="https://img.shields.io/badge/python-3.13%2B-blue" alt="Python">
  <img src="https://img.shields.io/badge/platform-macOS%20Apple%20Silicon-lightgrey" alt="Platform">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
</p>

---

## Table of Contents

- [Features](#features)
- [System Requirements](#system-requirements)
- [Installing Prerequisites](#installing-prerequisites)
- [Setup](#setup)
- [ASR Engine Selection](#asr-engine-selection)
- [TTS Engine Selection](#tts-engine-selection)
- [Starting Servers](#starting-servers)
- [Execution](#execution)
- [Processing Flow](#processing-flow)
- [Resume Feature](#resume-feature)
- [Configuration Items](#configuration-items)
- [Known Limitations](#known-limitations)
- [Troubleshooting](#troubleshooting)
- [License](#license)

## Features

- **Two ASR engines**: Switch between whisper.cpp + Silero VAD (fast, English-focused, hallucination suppression) and VibeVoice-ASR (multilingual, built-in speaker separation)
- **Speaker separation**: Identify who speaks what using pyannote.audio (Whisper mode), VibeVoice-ASR has built-in speaker separation
- **Three TTS engines**: Switch between MioTTS-Inference (speaker cloning support, high quality), GPT-SoVITS V2ProPlus (zero-shot voice cloning), and Kokoro TTS (fast, lightweight, no server required)
- **High-quality translation**: In-process English-to-Japanese translation using CAT-Translate-7b (GGUF, llama-cpp-python) without server requirements
- **Video speed adjustment**: Stretch/compress video to match TTS audio length while maintaining natural dubbing, without changing audio speed
- **Resume feature**: Save checkpoints at each step, allowing resumption from interruption points

## System Requirements

- macOS (Apple Silicon) — Tested on Mac mini M4 (24GB)
- Python 3.13+
- ffmpeg / ffprobe
- CMake (required for whisper.cpp build)
- Ollama (for MioTTS LLM backend, MioTTS mode only)
- conda (GPT-SoVITS mode only)

> **Note**: Linux compatibility is currently unverified. Apple Silicon Mac is recommended as ASR (whisper.cpp, VibeVoice-ASR) and translation (CAT-Translate-7b) utilize MLX / Apple Silicon GPU.

## Installing Prerequisites

Before setup, ensure the following tools are installed.

### Homebrew (if not installed)

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### ffmpeg

```bash
brew install ffmpeg
```

### CMake (required for whisper.cpp build and dependency library builds)

```bash
brew install cmake
```

### uv (Python package manager)

```bash
brew install uv
```

> uv is a fast Python package manager that replaces pip. This tool uses it for all Python operations.

### Ollama (MioTTS mode only)

Download and install the macOS version from https://ollama.com/download.

> Ollama is used as the LLM backend for MioTTS. It's not used for translation. Not required for Kokoro TTS and GPT-SoVITS modes.

### conda (GPT-SoVITS mode only)

GPT-SoVITS runs in an isolated conda environment. We recommend installing miniforge.

```bash
brew install --cask miniforge
```

## Setup

### 1. Clone Repository

```bash
git clone https://github.com/Shuichi346/ja-dubbing.git
cd ja-dubbing
```

### 2. HuggingFace Preparation

pyannote.audio's speaker separation model is a gated model requiring agreement to terms of use. **If using Whisper mode (`ASR_ENGINE=whisper`)**, complete the following beforehand. This step is unnecessary if using VibeVoice mode only, or if using only Kokoro TTS (no speaker separation required).

1. Create an access token at https://huggingface.co/settings/tokens (`Read` permission is sufficient)
2. Open the following two model pages and **agree to terms of use** to request access:
   - https://huggingface.co/pyannote/speaker-diarization-3.1
   - https://huggingface.co/pyannote/segmentation-3.0

> Requests are typically **approved immediately**. Model downloads will fail without approval.

### 3. Install Dependencies

```bash
uv sync
uv run python -m spacy download en_core_web_sm
```

> Note: VibeVoice-ASR is a large Apple Silicon-specific package (9B parameter model). The model will be automatically downloaded on first run (~5GB). The CAT-Translate-7b GGUF model is also automatically downloaded via huggingface_hub on first run.

### 4. Build whisper.cpp (when using Whisper mode)

If using Whisper mode (`ASR_ENGINE=whisper`), you need to build whisper.cpp from source and download Whisper and VAD models. This can be done automatically with the following script:

```bash
chmod +x scripts/setup_whisper.sh
./scripts/setup_whisper.sh
```

This script performs:

1. Clone `whisper.cpp` repository (build with Apple Silicon Metal GPU support)
2. Download Whisper model (`ggml-large-v3-turbo`)
3. Download Silero VAD model (`ggml-silero-v6.2.0`)

> This step is unnecessary if using VibeVoice mode only.

### 5. TTS Engine Setup

Set up the TTS engine according to the `TTS_ENGINE` setting in `.env`.

#### MioTTS Mode (`TTS_ENGINE=miotts`)

High-quality TTS with speaker cloning support. Requires Ollama + MioTTS-Inference server.

```bash
git clone https://github.com/Aratako/MioTTS-Inference.git
cd MioTTS-Inference
uv sync
cd ..
```

#### Kokoro TTS Mode (`TTS_ENGINE=kokoro`)

Lightweight (82M parameters) and fast TTS. No server required, runs in-process inference. Does not support voice cloning but offers fast processing speed for easy use.

Dependencies are automatically installed with `uv sync`. **Please additionally download the unidic dictionary required for Japanese normalization.**

```bash
uv run python -m unidic download
```

> **Important**: Skipping this step will result in incorrect Japanese pronunciation.

#### GPT-SoVITS Mode (`TTS_ENGINE=gptsovits`)

Zero-shot voice cloning TTS using V2ProPlus model. Runs in an isolated conda environment and accessed via API server.

```bash
chmod +x scripts/setup_gptsovits.sh
./scripts/setup_gptsovits.sh
```

This script performs:

1. Clone GPT-SoVITS repository
2. Create conda environment `gptsovits` (Python 3.11)
3. Install PyTorch + dependencies
4. Download NLTK data and pyopenjtalk dictionary
5. Download pre-trained model (V2ProPlus)
6. Generate `tts_infer.yaml` configuration file

> **Prerequisite**: conda (miniforge/miniconda) must be installed. GPT-SoVITS runs in CPU mode.

### 6. Create Configuration File

```bash
cp .env.example .env
```

Open `.env` and edit the following items:

| Item | Description | Example |
|------|-------------|---------|
| `VIDEO_FOLDER` | Folder for input videos | `./input_videos` |
| `HF_AUTH_TOKEN` | HuggingFace token (required for Whisper mode + MioTTS/GPT-SoVITS) | `hf_xxxxxxxxxxxx` |
| `ASR_ENGINE` | ASR engine selection | `whisper` or `vibevoice` |
| `TTS_ENGINE` | TTS engine selection | `miotts`, `kokoro`, or `gptsovits` |

Other configuration items work with default values. See "Configuration Items" section for details.

Place English video files (.mp4, .mkv, .mov, .webm, .m4v) in `VIDEO_FOLDER`.

## ASR Engine Selection

Switch audio recognition engines with `ASR_ENGINE` in `.env`.

| Item | `whisper` | `vibevoice` |
|------|-----------|-------------|
| Engine | whisper.cpp CLI + Silero VAD | VibeVoice-ASR (Microsoft, mlx-audio) |
| Speaker separation | pyannote.audio (separate step) | Built-in (single pass) |
| Speed | Fast | Slow (several times slower than Whisper) |
| VAD | Built-in Silero VAD (hallucination suppression) | None |
| Languages | English-focused | Strong with multilingual mixing |
| Audio limit | No limit | Memory optimization supports long audio |
| Additional setup | Requires `scripts/setup_whisper.sh` | `mlx-audio[stt]>=0.3.0` |
| HuggingFace token | Required (for pyannote) | Not required |

### Whisper Mode (Default)

```env
ASR_ENGINE=whisper
```

Combines whisper.cpp with Silero VAD for fast, high-quality transcription, with speaker separation using pyannote.audio. VAD suppresses hallucination (phantom text) in silent sections. Optimal for English audio processing.

### VibeVoice Mode

```env
ASR_ENGINE=vibevoice
```

Microsoft's VibeVoice-ASR outputs transcription, speaker separation, and timestamps in a single pass. Strong with multilingual mixed audio (English + local languages) but slower than Whisper.

Built-in memory optimization through encoder chunking allows processing long audio on 24GB unified memory Macs. Chunk size is automatically determined based on available memory, requiring no special user configuration.

VibeVoice mode does not require pyannote.audio or HuggingFace tokens. Steps 3 (speaker separation) and 4 (speaker ID assignment) are automatically skipped.

#### VibeVoice-ASR Specific Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `VIBEVOICE_MODEL` | `mlx-community/VibeVoice-ASR-8bit` | Model to use |
| `VIBEVOICE_MAX_TOKENS` | `32768` | Maximum generation tokens |
| `VIBEVOICE_CONTEXT` | (empty) | Hot words (proper noun recognition assistance, comma-separated) |

Hot word example:

```env
VIBEVOICE_CONTEXT=MLX, Apple Silicon, PyTorch, Transformer
```

## TTS Engine Selection

Switch text-to-speech engines with `TTS_ENGINE` in `.env`.

| Item | `miotts` | `gptsovits` | `kokoro` |
|------|----------|-------------|----------|
| Engine | MioTTS-Inference | GPT-SoVITS V2ProPlus | Kokoro TTS (82M parameters) |
| Voice cloning | Supported (segment-level reference) | Supported (zero-shot, speaker representative reference) | Not supported (fixed voice) |
| Processing speed | Slow | Medium | Fast |
| Server | Required (Ollama + MioTTS API) | Required (conda environment + API server) | Not required (in-process inference) |
| Additional setup | MioTTS-Inference clone + Ollama | `scripts/setup_gptsovits.sh` + conda | `uv run python -m unidic download` |
| Audio quality | High quality with different voice per speaker | Zero-shot voice reproduction | Natural speech with fixed voice |
| Speaker separation | Required | Required | Not required (same voice for all speakers) |

### MioTTS Mode (Default)

```env
TTS_ENGINE=miotts
```

Speaker cloning TTS using MioTTS-Inference. Generates Japanese audio reproducing original speaker voice characteristics. Prioritizes segment-level reference audio, reflecting emotion and tempo. Requires Ollama (LLM backend) and MioTTS API server startup.

### GPT-SoVITS Mode

```env
TTS_ENGINE=gptsovits
```

Zero-shot voice cloning TTS using GPT-SoVITS V2ProPlus. Extracts voice quality from 3-10 second reference audio and reuses speaker representative references. Reference audio transcription text (prompt_text) is automatically generated by ASR engine. Runs in isolated conda environment without affecting ja-dubbing main Python environment.

### Kokoro TTS Mode

```env
TTS_ENGINE=kokoro
```

Kokoro is a lightweight 82M parameter open-weight TTS model. Does not support voice cloning but generates Japanese audio quickly. No server startup required, translation also completes in-process. Speaker separation is also omitted, making it the most convenient to use.

#### Kokoro TTS Specific Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `KOKORO_MODEL` | `kokoro` | Model name |
| `KOKORO_VOICE` | `jf_alpha` | Japanese voice name |
| `KOKORO_SPEED` | `1.0` | Speech speed (0.8-1.2 recommended) |

#### Available Japanese Voices

| Voice Name | Gender | Grade | Description |
|------------|--------|-------|-------------|
| `jf_alpha` | Female | C+ | Standard Japanese female voice (recommended) |
| `jf_gongitsune` | Female | C | "Gon the Fox" voice database |
| `jf_nezumi` | Female | C- | "The Mouse's Wedding" voice database |
| `jf_tebukuro` | Female | C | "Buying Gloves" voice database |
| `jm_kumo` | Male | C- | "The Spider's Thread" voice database |

#### GPT-SoVITS Specific Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `GPTSOVITS_API_URL` | `http://127.0.0.1:9880` | GPT-SoVITS API URL |
| `GPTSOVITS_CONDA_ENV` | `gptsovits` | conda environment name |
| `GPTSOVITS_DIR` | `./GPT-SoVITS` | Installation directory |
| `GPTSOVITS_TEXT_LANG` | `ja` | Synthesis text language |
| `GPTSOVITS_PROMPT_LANG` | `en` | Reference audio language |
| `GPTSOVITS_SPEED_FACTOR` | `1.0` | Speech speed |
| `GPTSOVITS_REPETITION_PENALTY` | `1.35` | Repetition suppression penalty |
| `GPTSOVITS_REFERENCE_MIN_SEC` | `3.0` | Minimum reference audio duration |
| `GPTSOVITS_REFERENCE_MAX_SEC` | `10.0` | Maximum reference audio duration |
| `GPTSOVITS_REFERENCE_TARGET_SEC` | `5.0` | Target reference audio duration |

## Starting Servers

Required servers vary by TTS engine. Translation uses CAT-Translate-7b for in-process inference, so no server is required.

### For Kokoro TTS Mode

**No external server startup required.** Both translation (CAT-Translate-7b) and TTS (Kokoro) run in-process.

```bash
uv run ja-dubbing
```

### For MioTTS Mode

#### Method A: Using startup script (recommended)

```bash
uv run ja-dubbing --generate-script
./start_servers.sh
```

MioTTS Ollama + API server will be started. Ollama model is automatically downloaded on first run.

#### Method B: Manual startup (2 terminals)

**Terminal 1: MioTTS LLM Backend (Port 8000)**

```bash
OLLAMA_HOST=localhost:8000 ollama serve
# First time only: OLLAMA_HOST=localhost:8000 ollama pull hf.co/Aratako/MioTTS-GGUF:MioTTS-1.7B-Q8_0.gguf
```

**Terminal 2: MioTTS API Server (Port 8001)**

```bash
cd MioTTS-Inference
uv run python run_server.py \
    --llm-base-url http://localhost:8000/v1 \
    --device mps \
    --max-text-length 500 \
    --port 8001
```

### For GPT-SoVITS Mode

#### Method A: Using startup script (recommended)

```bash
uv run ja-dubbing --generate-script
./start_servers.sh
```

GPT-SoVITS API server will be started in conda environment.

#### Method B: Manual startup (1 terminal)

```bash
conda activate gptsovits
cd GPT-SoVITS
python api_v2.py -a 127.0.0.1 -p 9880 -c GPT_SoVITS/configs/tts_infer.yaml
```

## Execution

For TTS engines requiring servers, run from another terminal with servers already started.

```bash
uv run ja-dubbing
```

Automatically detects videos in `VIDEO_FOLDER` and processes them sequentially. Output is saved as `*_jaDub.mp4` in the same folder as input videos. Specify any `VIDEO_FOLDER` path in `.env`.

### Generating Startup Script

```bash
uv run ja-dubbing --generate-script
```

Automatically generates appropriate server startup script `start_servers.sh` based on TTS engine settings.

## Processing Flow

### Whisper Mode + MioTTS (`ASR_ENGINE=whisper`, `TTS_ENGINE=miotts`)

1. Extract 16kHz mono WAV from video using ffmpeg
2. English transcription with whisper.cpp + Silero VAD (suppress hallucination in silent sections)
3. Speaker separation with pyannote.audio
4. Assign speaker IDs to Whisper segments
5. Segment merging → spaCy sentence splitting → translation unit merging (maintain speaker boundaries)
6. Extract speaker representative reference audio + segment-level reference audio from original video
7. English-to-Japanese translation with CAT-Translate-7b (GGUF, llama-cpp-python) in-process inference
8. Generate speaker-cloned Japanese audio with MioTTS-Inference (prioritize segment-level reference)
9. Speed-adjust original video sections to match TTS audio length
10. Combine video + Japanese audio (+ lightly mixed English audio) for output

### Whisper Mode + GPT-SoVITS (`ASR_ENGINE=whisper`, `TTS_ENGINE=gptsovits`)

1. Extract 16kHz mono WAV from video using ffmpeg
2. English transcription with whisper.cpp + Silero VAD
3. Speaker separation with pyannote.audio
4. Assign speaker IDs to Whisper segments
5. Segment merging → spaCy sentence splitting → translation unit merging
6. Extract speaker representative reference audio (3-10 seconds) + ASR transcription
7. English-to-Japanese translation with CAT-Translate-7b (GGUF, llama-cpp-python) in-process inference
8. Generate zero-shot voice-cloned Japanese audio with GPT-SoVITS V2ProPlus
9. Speed-adjust original video sections to match TTS audio length
10. Combine video + Japanese audio (+ lightly mixed English audio) for output

### Whisper Mode + Kokoro (`ASR_ENGINE=whisper`, `TTS_ENGINE=kokoro`)

1. Extract 16kHz mono WAV from video using ffmpeg
2. English transcription with whisper.cpp + Silero VAD (suppress hallucination in silent sections)
3. Speaker separation: Skipped (Kokoro doesn't support cloning, pyannote not used)
4. Assign unified speaker ID to all segments
5. Segment merging → spaCy sentence splitting → translation unit merging
6. Reference audio extraction skipped (Kokoro doesn't support cloning)
7. English-to-Japanese translation with CAT-Translate-7b (GGUF, llama-cpp-python) in-process inference
8. Generate Japanese audio quickly with Kokoro TTS
9. Speed-adjust original video sections to match TTS audio length
10. Combine video + Japanese audio (+ lightly mixed English audio) for output

### VibeVoice Mode (`ASR_ENGINE=vibevoice`)

1. Extract 16kHz mono WAV from video using ffmpeg
2. Transcription + speaker separation + timestamp acquisition with VibeVoice-ASR (single pass, memory optimization through chunk encoding)
3. (Skipped: built-in to VibeVoice-ASR)
4. (Skipped: built-in to VibeVoice-ASR)
5. Segment merging → spaCy sentence splitting → translation unit merging (maintain speaker boundaries)
6. MioTTS: Extract speaker reference audio from original video / GPT-SoVITS: Extract representative reference (3-10 seconds) / Kokoro: Skip
7. English-to-Japanese translation with CAT-Translate-7b (GGUF, llama-cpp-python) in-process inference
8. MioTTS: Generate speaker-cloned Japanese audio / GPT-SoVITS: Generate zero-shot cloned audio / Kokoro: Generate Japanese audio quickly
9. Speed-adjust original video sections to match TTS audio length
10. Combine video + Japanese audio (+ lightly mixed English audio) for output

## Resume Feature

Processing saves checkpoints at each step. If interrupted, re-execution resumes from where it left off. Checkpoints are saved in `temp/<video_name>/progress.json`.

To restart from the beginning, delete the corresponding `temp/<video_name>/` folder before re-execution.

> **Note when switching ASR or TTS engines**: To redo a partially processed video with different engines, delete the `temp/<video_name>/` folder before re-execution.

## Configuration Items

All settings are managed in the `.env` file. `.env.example` contains all configuration items and default values. Main configuration items are as follows:

### Basic Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `VIDEO_FOLDER` | `./input_videos` | Input video folder |
| `TEMP_ROOT` | `./temp` | Temporary files folder |
| `ASR_ENGINE` | `whisper` | ASR engine (`whisper` or `vibevoice`) |
| `TTS_ENGINE` | `miotts` | TTS engine (`miotts`, `kokoro`, or `gptsovits`) |
| `HF_AUTH_TOKEN` | (Required for Whisper mode + cloning-capable TTS) | HuggingFace token |

### ASR Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `WHISPER_MODEL` | `large-v3-turbo` | Whisper model name |
| `WHISPER_LANG` | `en` | Whisper recognition language |
| `VAD_MODEL` | `silero-v6.2.0` | VAD model name |
| `WHISPER_CPP_DIR` | `./whisper.cpp` | whisper.cpp installation directory |
| `VIBEVOICE_MODEL` | `mlx-community/VibeVoice-ASR-8bit` | VibeVoice-ASR model name |
| `VIBEVOICE_MAX_TOKENS` | `32768` | VibeVoice-ASR maximum tokens |
| `VIBEVOICE_CONTEXT` | (empty) | VibeVoice-ASR hot words |

### Translation Settings (CAT-Translate-7b)

| Setting | Default | Description |
|---------|---------|-------------|
| `CAT_TRANSLATE_REPO` | `mradermacher/CAT-Translate-7b-GGUF` | GGUF model HuggingFace repository |
| `CAT_TRANSLATE_FILE` | `CAT-Translate-7b.Q8_0.gguf` | GGUF file name |
| `CAT_TRANSLATE_N_GPU_LAYERS` | `-1` | GPU offload layer count (-1 for all layers) |
| `CAT_TRANSLATE_N_CTX` | `4096` | Context window size |
| `CAT_TRANSLATE_RETRIES` | `3` | Translation retry count |
| `CAT_TRANSLATE_REPEAT_PENALTY` | `1.2` | Repetition suppression penalty |

### TTS Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `MIOTTS_API_URL` | `http://localhost:8001` | MioTTS API URL |
| `MIOTTS_DEVICE` | `mps` | MioTTS codec device |
| `MIOTTS_REFERENCE_MAX_SEC` | `20.0` | MioTTS reference audio limit (seconds) |
| `KOKORO_MODEL` | `kokoro` | Kokoro model name |
| `KOKORO_VOICE` | `jf_alpha` | Kokoro Japanese voice |
| `KOKORO_SPEED` | `1.0` | Kokoro speech speed |
| `GPTSOVITS_API_URL` | `http://127.0.0.1:9880` | GPT-SoVITS API URL |
| `GPTSOVITS_SPEED_FACTOR` | `1.0` | GPT-SoVITS speech speed |

### Translation Anomaly Detection Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `OUTPUT_REPEAT_THRESHOLD` | `3` | Translation output repetition detection threshold |
| `INPUT_REPEAT_THRESHOLD` | `4` | Translation input repetition detection threshold |
| `INPUT_UNIQUE_RATIO_THRESHOLD` | `0.3` | Translation input unique ratio threshold |

### Output Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `ENGLISH_VOLUME` | `0.10` | English audio volume (0.0-1.0) |
| `JAPANESE_VOLUME` | `1.00` | Japanese audio volume (0.0-1.0) |
| `OUTPUT_SIZE` | `720` | Output video height (pixels) |
| `KEEP_TEMP` | `true` | Whether to keep temporary files |

## Known Limitations

- **English-Japanese mixing**: When English words are mixed like "utilize simulation tools such as Omniverse and ISACsim", TTS may not read correctly.
- **Processing time**: Even 3-minute videos take tens of minutes. Long videos may cause errors, so **pre-splitting to about 8 minutes** is recommended.
- **Translation quality**: Local LLM (CAT-Translate-7b) translation varies in accuracy compared to cloud APIs.
- **Kokoro TTS**: Does not support voice cloning, so all speakers have the same voice. Suitable when prioritizing speed or when voice reproduction is unnecessary.
- **GPT-SoVITS**: Runs in CPU mode, slower inference compared to MPS/CUDA environments. Reference audio only extracts voice quality (timbre), not reflecting intonation or tempo.
- **VibeVoice-ASR processing speed**: Takes several times longer than Whisper.
- **VibeVoice-ASR memory usage**: 9B parameter model uses about 5GB memory even with 8bit quantization. Built-in memory optimization through chunk encoding, verified on 24GB unified memory Mac.

## Troubleshooting

### whisper-cli not found

Run `scripts/setup_whisper.sh` to build whisper.cpp.

```bash
chmod +x scripts/setup_whisper.sh
./scripts/setup_whisper.sh
```

If CMake is not installed, run `brew install cmake` first.

### Out of memory

Tested on Mac mini M4 with 24GB unified memory. For memory conservation, ASR models (Whisper/VibeVoice-ASR) and pyannote pipeline are released after use. VibeVoice mode uses encoder chunk processing to suppress memory spikes even with long audio. MLX and PyTorch MPS caches are also cleared after each step. For long videos, set `KEEP_TEMP=true` and use interruption/resume functionality.

### MioTTS text too long error

MioTTS default maximum text length is 300 characters. This tool specifies `--max-text-length 500` when starting the server and also performs truncation processing at punctuation positions on the pipeline side.

### Kokoro TTS Japanese pronunciation issues

unidic dictionary may not be downloaded. Run the following:

```bash
uv run python -m unidic download
```

### VibeVoice-ASR "mlx-audio not installed" error

Run the following:

```bash
uv pip install 'mlx-audio[stt]>=0.3.0'
```

### VibeVoice-ASR empty transcription results

Audio file may not contain speech or audio may be too short. Try increasing `VIBEVOICE_MAX_TOKENS` or switch to Whisper mode.

### CAT-Translate-7b model download failure

Automatically downloaded via huggingface_hub. Check network connection and re-execute. Model is downloaded from `mradermacher/CAT-Translate-7b-GGUF`.

### Cannot connect to GPT-SoVITS API server

Check if conda environment is properly set up.

```bash
conda activate gptsovits
cd GPT-SoVITS
python api_v2.py -a 127.0.0.1 -p 9880 -c GPT_SoVITS/configs/tts_infer.yaml
```

If not set up, run `scripts/setup_gptsovits.sh` first.

## License

MIT License

Note: External models and libraries used by this tool have their own respective licenses.

- MioTTS default presets
- CAT-Translate-7b
- pyannote.audio
- whisper.cpp
- Silero VAD
- VibeVoice-ASR
- mlx-audio
- Kokoro TTS (Kokoro-82M)
- misaki (G2P)
- GPT-SoVITS
- llama-cpp-python