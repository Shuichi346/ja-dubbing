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
  <p align="center">A tool to convert English videos into Japanese dubbed videos.<br>It can also create dubbing that reproduces the original speaker's voice tone.</p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-5.0.0-blue" alt="Version">
  <img src="https://img.shields.io/badge/python-3.13%2B-blue" alt="Python">
  <img src="https://img.shields.io/badge/platform-macOS%20Apple%20Silicon-lightgrey" alt="Platform">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
</p>

---

## What this tool can do

- Takes English videos as input and outputs Japanese dubbed videos
- Can create dubbing that resembles the original speaker's voice (voice cloning)
- Automatically adjusts video speed to achieve natural dubbing
- Can resume from where it left off if processing is interrupted

---

## Table of Contents

- [System Requirements](#system-requirements)
- [Setup](#setup)
- [Usage](#usage)
- [Engine Combinations](#engine-combinations)
- [Configuration Options](#configuration-options)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## System Requirements

- **Mac (Apple Silicon)** — Tested on Mac mini M4 (24GB)
- **Python 3.13 or higher**
- Linux is untested

---

## Setup

### 1. Install Required Tools

First, install several tools on your Mac. Open Terminal and execute the following commands **in order**.

**Homebrew** (Mac package manager. Skip if already installed)

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

**ffmpeg・CMake・uv**

```bash
brew install ffmpeg cmake uv
```

### 2. Download the Repository

```bash
git clone https://github.com/Shuichi346/ja-dubbing.git
cd ja-dubbing
```

### 3. Install Dependencies

```bash
uv sync
uv run python -m spacy download en_core_web_sm
```

### 4. Create Configuration File

```bash
cp .env.example .env
```

Open `.env` in a text editor and **make sure to configure the following 4 items**.

| Item | Description | Example |
|------|-------------|---------|
| `VIDEO_FOLDER` | Folder to place videos you want to dub | `./input_videos` |
| `ASR_ENGINE` | Speech recognition engine | `whisper` or `vibevoice` |
| `TTS_ENGINE` | Text-to-speech engine | `kokoro`, `miotts`, or `gptsovits` |
| `HF_AUTH_TOKEN` | HuggingFace token (※conditional) | `hf_xxxxxxxxxxxx` |

> **When `HF_AUTH_TOKEN` is required**: Required when `ASR_ENGINE=whisper` AND `TTS_ENGINE=miotts` or `gptsovits`. Not needed when using only Kokoro TTS or only VibeVoice.

### 5. ASR Engine Setup

#### For Whisper mode (`ASR_ENGINE=whisper`)

Build whisper.cpp and download models.

```bash
chmod +x scripts/setup_whisper.sh
./scripts/setup_whisper.sh
```

**HuggingFace preparation** (Only required for Whisper + MioTTS/GPT-SoVITS combination)

1. Create a token at https://huggingface.co/settings/tokens (`Read` permission)
2. **Agree to terms of use** on the following 2 pages (instantly approved)
   - https://huggingface.co/pyannote/speaker-diarization-3.1
   - https://huggingface.co/pyannote/segmentation-3.0

#### For VibeVoice mode (`ASR_ENGINE=vibevoice`)

No additional setup required. Models (~5GB) will be automatically downloaded on first run.

### 6. TTS Engine Setup

#### For Kokoro TTS (`TTS_ENGINE=kokoro`) — Easiest option

No server startup required. Just run the following command.

```bash
uv run python -m unidic download
```

> **Important**: Skipping this step will cause incorrect Japanese pronunciation.

#### For MioTTS (`TTS_ENGINE=miotts`)

Requires Ollama installation and MioTTS-Inference cloning.

**Install Ollama**: Download macOS version from https://ollama.com/download

**Clone MioTTS-Inference**:

```bash
git clone https://github.com/Aratako/MioTTS-Inference.git
cd MioTTS-Inference
uv sync
cd ..
```

#### For GPT-SoVITS (`TTS_ENGINE=gptsovits`)

Requires conda and GPT-SoVITS setup.

```bash
brew install --cask miniforge
chmod +x scripts/setup_gptsovits.sh
./scripts/setup_gptsovits.sh
```

---

## Usage

### Step 1: Place Videos

Place English videos you want to dub (.mp4, .mkv, .mov, .webm, .m4v) in `VIDEO_FOLDER`.

> **Recommended**: Long videos may cause errors.

### Step 2: Start Servers (Except for Kokoro TTS)

**For Kokoro TTS**: No server startup required. Proceed to Step 3.

**For MioTTS / GPT-SoVITS**: Start servers in a separate terminal.

```bash
uv run ja-dubbing --generate-script
./start_servers.sh
```

### Step 3: Execute

```bash
uv run ja-dubbing
```

Videos in `VIDEO_FOLDER` will be processed in order, with output as `*_jaDub.mp4` in the same folder.

---

## Engine Combinations

### ASR Engines (Speech Recognition)

| | Whisper | VibeVoice |
|---|---------|-----------|
| Speed | Fast | Slow |
| Strengths | English only | Mixed multilingual audio |
| Additional Setup | Requires running `setup_whisper.sh` | Not required (auto-download on first run) |
| HuggingFace Token | Required when combined with MioTTS/GPT-SoVITS | Not required |

### TTS Engines (Text-to-Speech)

| | Kokoro | MioTTS | GPT-SoVITS |
|---|--------|--------|------------|
| Ease of Use | ★★★ Easiest | ★★ Requires server startup | ★ Requires conda environment |
| Voice Cloning | Not supported (fixed voice) | Supported (high quality) | Supported (zero-shot) |
| Speed | Fast | Slow | Medium |
| Server | Not required | Ollama + MioTTS API | conda + API server |

**If unsure**: Try `ASR_ENGINE=whisper` + `TTS_ENGINE=kokoro` combination first. It has the simplest setup and doesn't require HuggingFace tokens.

---

## Configuration Options

All settings are managed in the `.env` file. All items and default values are listed in `.env.example`.

### Basic Settings (Must check)

| Setting | Default | Description |
|---------|---------|-------------|
| `VIDEO_FOLDER` | `./input_videos` | Input video folder |
| `ASR_ENGINE` | `whisper` | Speech recognition engine (`whisper` / `vibevoice`) |
| `TTS_ENGINE` | `miotts` | Text-to-speech engine (`kokoro` / `miotts` / `gptsovits`) |
| `HF_AUTH_TOKEN` | — | HuggingFace token (conditionally required) |

### Output Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `ENGLISH_VOLUME` | `0.10` | Original English audio volume (0.0〜1.0) |
| `JAPANESE_VOLUME` | `1.00` | Japanese dubbed audio volume (0.0〜1.0) |
| `OUTPUT_SIZE` | `720` | Output video height (pixels) |
| `KEEP_TEMP` | `true` | Keep temporary files (required for resuming) |

### Whisper Settings (`ASR_ENGINE=whisper`)

| Setting | Default | Description |
|---------|---------|-------------|
| `WHISPER_MODEL` | `large-v3-turbo` | Whisper model name |
| `WHISPER_LANG` | `en` | Recognition language |
| `WHISPER_CPP_DIR` | `./whisper.cpp` | whisper.cpp installation directory |

### VibeVoice Settings (`ASR_ENGINE=vibevoice`)

| Setting | Default | Description |
|---------|---------|-------------|
| `VIBEVOICE_MODEL` | `mlx-community/VibeVoice-ASR-8bit` | Model name |
| `VIBEVOICE_MAX_TOKENS` | `32768` | Maximum generation tokens |
| `VIBEVOICE_CONTEXT` | (empty) | Hot words (proper noun recognition assistance, comma-separated) |

### Translation Settings (CAT-Translate-7b)

| Setting | Default | Description |
|---------|---------|-------------|
| `CAT_TRANSLATE_REPO` | `mradermacher/CAT-Translate-7b-GGUF` | Model repository |
| `CAT_TRANSLATE_FILE` | `CAT-Translate-7b.Q8_0.gguf` | Model file name |
| `CAT_TRANSLATE_N_GPU_LAYERS` | `-1` | GPU offload (-1 for all layers) |
| `CAT_TRANSLATE_RETRIES` | `3` | Retry count |

### Kokoro TTS Settings (`TTS_ENGINE=kokoro`)

| Setting | Default | Description |
|---------|---------|-------------|
| `KOKORO_VOICE` | `jf_alpha` | Japanese voice name |
| `KOKORO_SPEED` | `1.0` | Reading speed (0.8〜1.2 recommended) |

Available voices: `jf_alpha` (female・recommended), `jf_gongitsune` (female), `jf_nezumi` (female), `jf_tebukuro` (female), `jm_kumo` (male)

### MioTTS Settings (`TTS_ENGINE=miotts`)

| Setting | Default | Description |
|---------|---------|-------------|
| `MIOTTS_API_URL` | `http://localhost:8001` | MioTTS API URL |
| `MIOTTS_LLM_TEMPERATURE` | `0.5` | Temperature (lower = more stable, 0.1〜0.8) |
| `MIOTTS_LLM_REPETITION_PENALTY` | `1.1` | Repetition penalty (1.0〜1.3 recommended) |
| `MIOTTS_LLM_FREQUENCY_PENALTY` | `0.3` | High-frequency token penalty (0.0〜1.0) |
| `MIOTTS_QUALITY_RETRIES` | `1` | Retry count on quality validation failure |
| `MIOTTS_DURATION_PER_CHAR_MAX` | `0.5` | Maximum seconds per character |

### GPT-SoVITS Settings (`TTS_ENGINE=gptsovits`)

| Setting | Default | Description |
|---------|---------|-------------|
| `GPTSOVITS_API_URL` | `http://127.0.0.1:9880` | GPT-SoVITS API URL |
| `GPTSOVITS_CONDA_ENV` | `gptsovits` | conda environment name |
| `GPTSOVITS_DIR` | `./GPT-SoVITS` | Installation directory |
| `GPTSOVITS_SPEED_FACTOR` | `1.0` | Reading speed |
| `GPTSOVITS_REFERENCE_TARGET_SEC` | `5.0` | Target reference audio duration in seconds |

---

## About Resume Function

Processing saves checkpoints at each step, so if interrupted, you can resume by re-running `uv run ja-dubbing`.

**To start from the beginning**: Delete the `temp/<video_name>/` folder before re-running.

**To restart after switching engines**: Also delete the `temp/<video_name>/` folder.

## License

MIT License

External models and libraries used by this tool (MioTTS, CAT-Translate-7b, pyannote.audio, whisper.cpp, Kokoro TTS, GPT-SoVITS, etc.) have their own respective licenses. Please check them when using.