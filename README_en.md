<table>
  <thead>
    <tr>
      <th style="text-align:center"><a href="README_en.md">English</a></th>
      <th style="text-align:center"><a href="README.md">日本語</a></th>
    </tr>
  </thead>
</table>

# ja-dubbing

A tool to convert English videos into Japanese-dubbed videos while maintaining the original speaker's voice characteristics.

## Features

- **Two ASR engines**: Switchable between whisper.cpp + Silero VAD (fast, English-focused, hallucination suppression) and VibeVoice-ASR (multilingual, built-in speaker diarization)
- **Speaker diarization**: Identify who is speaking using pyannote.audio (Whisper mode), VibeVoice-ASR has built-in speaker diarization
- **Two TTS engines**: Switchable between MioTTS-Inference (speaker cloning support, high quality) and Kokoro TTS (fast, lightweight, no server required)
- **High-quality translation**: English-to-Japanese translation using plamo-translate-cli (PLaMo-2-Translate, MLX)
- **Video speed adjustment**: Achieves natural dubbing by stretching/compressing video while keeping audio speed unchanged

## System Requirements

- macOS (Apple Silicon) — Tested on Mac mini M4 (24GB)
- Python 3.13+
- ffmpeg / ffprobe
- CMake (required for building whisper.cpp)
- Ollama (for MioTTS LLM backend, MioTTS mode only)

> **Note**: Linux compatibility is currently unverified. The translation engine (plamo-translate-cli) uses MLX, so Apple Silicon Mac is required.

## Prerequisites Installation

Before setup, ensure the following tools are installed:

### Homebrew (if not already installed)

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### ffmpeg

```bash
brew install ffmpeg
```

### CMake (required for building whisper.cpp and plamo-translate-cli dependency sentencepiece)

```bash
brew install cmake
```

### uv (Python package manager)

```bash
brew install uv
```

> uv is a fast Python package manager that replaces pip. This tool uses it for all Python operations.

### Ollama (required for MioTTS mode only)

Download and install the macOS version from https://ollama.com/download.

> Ollama is used as the LLM backend for MioTTS. It's not used for translation. Not required for Kokoro TTS mode.

## Setup

### 1. Clone Repository

```bash
git clone https://github.com/Shuichi346/ja-dubbing.git
cd ja-dubbing
```

### 2. HuggingFace Preparation

The pyannote.audio speaker diarization model is a gated model that requires agreement to terms of use. **If using Whisper mode (`ASR_ENGINE=whisper`)**, complete the following steps in advance. This step is not required if using only VibeVoice mode.

1. Create an access token at https://huggingface.co/settings/tokens (`Read` permission is sufficient)
2. Open the following two model pages and **agree to the terms of use** to request access:
   - https://huggingface.co/pyannote/speaker-diarization-3.1
   - https://huggingface.co/pyannote/segmentation-3.0

> Applications are typically **approved immediately**. Model download will fail if not approved.

### 3. Install Dependencies

```bash
uv sync
uv run python -m spacy download en_core_web_sm
```

> Note: VibeVoice-ASR is a large Apple Silicon-specific package (9B parameter model). The model will be automatically downloaded on first run (~5GB).

### 4. Build whisper.cpp (for Whisper mode)

If using Whisper mode (`ASR_ENGINE=whisper`), you need to build whisper.cpp from source and download Whisper and VAD models. This can be done automatically with the following script:

```bash
chmod +x scripts/setup_whisper.sh
./scripts/setup_whisper.sh
```

This script performs the following:

1. Clone `whisper.cpp` repository (built with Apple Silicon Metal GPU support)
2. Download Whisper model (`ggml-large-v3-turbo`)
3. Download Silero VAD model (`ggml-silero-v6.2.0`)

> This step is not required if using only VibeVoice mode.

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

Lightweight (82M parameters) and fast TTS. No server required, runs inference directly in-process. Does not support voice cloning but offers fast processing speed for ease of use.

Dependencies are automatically installed with `uv sync`. **Please additionally download the unidic dictionary required for Japanese normalization.**

```bash
uv run python -m unidic download
```

> **Important**: Skipping this step will result in incorrect Japanese pronunciation during text-to-speech.

### 6. Create Configuration File

```bash
cp .env.example .env
```

Open `.env` and edit the following items:

| Item | Description | Example |
|------|-------------|---------|
| `VIDEO_FOLDER` | Folder for input videos | `./input_videos` |
| `HF_AUTH_TOKEN` | HuggingFace token (required for Whisper mode) | `hf_xxxxxxxxxxxx` |
| `ASR_ENGINE` | ASR engine selection | `whisper` or `vibevoice` |
| `TTS_ENGINE` | TTS engine selection | `miotts` or `kokoro` |

Other configuration items will work with default values. See "Configuration Items" section below for details.

Place English video files (.mp4, .mkv, .mov, .webm, .m4v) that you want to dub in the `VIDEO_FOLDER`.

## ASR Engine Selection

Switch between speech recognition engines using `ASR_ENGINE` in `.env`.

| Item | `whisper` | `vibevoice` |
|------|-----------|-------------|
| Engine | whisper.cpp CLI + Silero VAD | VibeVoice-ASR (Microsoft, mlx-audio) |
| Speaker diarization | pyannote.audio (separate step) | Built-in (single pass) |
| Speed | Fast | Slow (several times slower than Whisper) |
| VAD | Built-in Silero VAD (hallucination suppression) | None |
| Language support | English-focused | Strong with multilingual mixed content |
| Audio length limit | No limit | Supports long audio through memory optimization |
| Additional setup | Requires running `scripts/setup_whisper.sh` | `mlx-audio[stt]>=0.3.0` |
| HuggingFace token | Required (for pyannote) | Not required |

### Whisper Mode (Default)

```env
ASR_ENGINE=whisper
```

Performs fast and high-quality transcription using whisper.cpp combined with Silero VAD, and speaker diarization using pyannote.audio. VAD suppresses hallucination text in silent sections. Optimal for English audio processing.

### VibeVoice Mode

```env
ASR_ENGINE=vibevoice
```

Microsoft's VibeVoice-ASR outputs transcription, speaker diarization, and timestamps in a single pass. Strong with multilingual mixed audio (English + local language, etc.) but processing speed is slower than Whisper.

Features built-in memory optimization through encoder chunking, allowing processing of long audio on 24GB unified memory Mac. Chunk size is automatically determined based on available memory, requiring no special user configuration.

VibeVoice mode does not require pyannote.audio or HuggingFace token. Steps 3 (speaker diarization) and 4 (speaker ID assignment) are automatically skipped.

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

Switch between text-to-speech engines using `TTS_ENGINE` in `.env`.

| Item | `miotts` | `kokoro` |
|------|----------|----------|
| Engine | MioTTS-Inference | Kokoro TTS (82M parameters) |
| Voice cloning | Supported (reproduces original speaker's voice) | Not supported (fixed voice) |
| Processing speed | Slow | Fast |
| Server | Required (Ollama + MioTTS API) | Not required (in-process inference) |
| Additional setup | MioTTS-Inference clone + Ollama | `uv run python -m unidic download` |
| Audio quality | High quality with different voice per speaker | Natural speech with fixed voice |

### MioTTS Mode (Default)

```env
TTS_ENGINE=miotts
```

Speaker cloning TTS using MioTTS-Inference. Generates Japanese audio that reproduces the original speaker's voice characteristics. Requires starting Ollama (LLM backend) and MioTTS API server.

### Kokoro TTS Mode

```env
TTS_ENGINE=kokoro
```

Kokoro is a lightweight 82M parameter open-weight TTS model. Does not support voice cloning but can generate Japanese audio quickly. No server startup required like MioTTS, operates with only the translation server (plamo-translate-cli).

#### Kokoro TTS Specific Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `KOKORO_MODEL` | `kokoro` | Model name |
| `KOKORO_VOICE` | `jf_alpha` | Japanese voice name |
| `KOKORO_HTTP_TIMEOUT` | `300.0` | HTTP timeout (seconds) |
| `KOKORO_SPEED` | `1.0` | Speech speed (0.8-1.2 recommended) |

#### Available Japanese Voices

| Voice name | Gender | Grade | Description |
|------------|--------|-------|-------------|
| `jf_alpha` | Female | C+ | Standard Japanese female voice (recommended) |
| `jf_gongitsune` | Female | C | "Gon the Fox" voice database |
| `jf_nezumi` | Female | C- | "Mouse's Wedding" voice database |
| `jf_tebukuro` | Female | C | "Buying Gloves" voice database |
| `jm_kumo` | Male | C- | "Spider's Thread" voice database |

## Server Startup

This tool uses plamo-translate-cli server for translation. Required servers differ depending on the TTS engine. **Servers must be started before pipeline execution.**

### Method A: Use Startup Script (Recommended)

```bash
uv run ja-dubbing --generate-script
./start_servers.sh
```

Appropriate startup script is automatically generated according to TTS engine settings.

- **Kokoro TTS mode**: Starts only plamo-translate-cli
- **MioTTS mode**: Starts all three: plamo-translate-cli + Ollama + MioTTS-Inference

PLaMo-2-Translate MLX model is automatically downloaded on first run. For MioTTS mode, Ollama model is also automatically downloaded.

### Method B: Manual Startup

#### For Kokoro TTS Mode (1 terminal)

```bash
# plamo-translate-cli translation server (MLX, 8bit)
uv run plamo-translate server --precision 8bit
```

#### For MioTTS Mode (3 terminals)

**Terminal 1: plamo-translate-cli translation server (MLX, 8bit)**

```bash
uv run plamo-translate server --precision 8bit
```

> The `mlx-community/plamo-2-translate-8bit` model is automatically downloaded on first startup. Wait for download completion before running `uv run ja-dubbing` below.

**Terminal 2: MioTTS LLM backend (port 8000)**

```bash
OLLAMA_HOST=localhost:8000 ollama serve
# First time only: OLLAMA_HOST=localhost:8000 ollama pull hf.co/Aratako/MioTTS-GGUF:MioTTS-1.7B-Q8_0.gguf
```

**Terminal 3: MioTTS API server (port 8001)**

```bash
cd MioTTS-Inference
uv run python run_server.py \
    --llm-base-url http://localhost:8000/v1 \
    --device mps \
    --max-text-length 500 \
    --port 8001
```

> **Port configuration**: Translation uses plamo-translate-cli with automatic port management via MCP protocol. MioTTS LLM Ollama (8000) port is specified via `OLLAMA_HOST` environment variable.

## Execution

Run from a separate terminal while servers are running.

```bash
uv run ja-dubbing
```

Automatically detects videos in `VIDEO_FOLDER` and processes them sequentially. Output is saved as `*_jaDub.mp4` in the same folder as input videos. Specify any `VIDEO_FOLDER` path in `.env`.

## Processing Flow

### Whisper Mode + MioTTS (`ASR_ENGINE=whisper`, `TTS_ENGINE=miotts`)

1. Extract 16kHz mono WAV from video using ffmpeg
2. English transcription using whisper.cpp + Silero VAD (suppress hallucinations in silent sections)
3. Speaker diarization using pyannote.audio
4. Assign speaker IDs to Whisper segments
5. Segment combination → spaCy sentence splitting → translation unit combination (maintaining speaker boundaries)
6. Extract reference audio for each speaker from original video
7. English-to-Japanese translation using plamo-translate-cli (PLaMo-2-Translate, MLX 8bit)
8. Generate speaker-cloned Japanese audio using MioTTS-Inference
9. Speed-adjust each section of original video to match TTS audio length
10. Combine video + Japanese audio (+ lightly mixed English audio) for output

### Whisper Mode + Kokoro (`ASR_ENGINE=whisper`, `TTS_ENGINE=kokoro`)

1. Extract 16kHz mono WAV from video using ffmpeg
2. English transcription using whisper.cpp + Silero VAD (suppress hallucinations in silent sections)
3. Speaker diarization using pyannote.audio
4. Assign speaker IDs to Whisper segments
5. Segment combination → spaCy sentence splitting → translation unit combination (maintaining speaker boundaries)
6. Skip reference audio extraction (Kokoro doesn't support cloning)
7. English-to-Japanese translation using plamo-translate-cli (PLaMo-2-Translate, MLX 8bit)
8. Generate Japanese audio quickly using Kokoro TTS
9. Speed-adjust each section of original video to match TTS audio length
10. Combine video + Japanese audio (+ lightly mixed English audio) for output

### VibeVoice Mode (`ASR_ENGINE=vibevoice`)

1. Extract 16kHz mono WAV from video using ffmpeg
2. Transcription + speaker diarization + timestamp acquisition using VibeVoice-ASR (single pass, memory optimization through chunk encoding)
3. (Skipped: built into VibeVoice-ASR)
4. (Skipped: built into VibeVoice-ASR)
5. Segment combination → spaCy sentence splitting → translation unit combination (maintaining speaker boundaries)
6. MioTTS: Extract reference audio for each speaker from original video / Kokoro: Skip
7. English-to-Japanese translation using plamo-translate-cli (PLaMo-2-Translate, MLX 8bit)
8. MioTTS: Generate speaker-cloned Japanese audio / Kokoro: Generate Japanese audio quickly
9. Speed-adjust each section of original video to match TTS audio length
10. Combine video + Japanese audio (+ lightly mixed English audio) for output

## Resume Functionality

Processing saves checkpoints at each step. If interrupted, re-running will resume from where it left off. Checkpoints are saved in `temp/<video_name>/progress.json`.

To start from scratch, delete the corresponding `temp/<video_name>/` folder before re-running.

> **Note when switching ASR or TTS engines**: To restart a partially processed video with a different engine, delete the `temp/<video_name>/` folder before re-running.

## Configuration Items

All settings are managed in the `.env` file. `.env.example` contains all configuration items and default values. Main configuration items are as follows:

### Basic Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `VIDEO_FOLDER` | `./input_videos` | Input video folder |
| `TEMP_ROOT` | `./temp` | Temporary files folder |
| `ASR_ENGINE` | `whisper` | ASR engine (`whisper` or `vibevoice`) |
| `TTS_ENGINE` | `miotts` | TTS engine (`miotts` or `kokoro`) |
| `HF_AUTH_TOKEN` | (Required for Whisper mode) | HuggingFace token |

### ASR Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `WHISPER_MODEL` | `large-v3-turbo` | Whisper model name |
| `VAD_MODEL` | `silero-v6.2.0` | VAD model name |
| `WHISPER_CPP_DIR` | `./whisper.cpp` | whisper.cpp installation directory |
| `VIBEVOICE_MODEL` | `mlx-community/VibeVoice-ASR-8bit` | VibeVoice-ASR model name |
| `VIBEVOICE_MAX_TOKENS` | `32768` | VibeVoice-ASR maximum tokens |
| `VIBEVOICE_CONTEXT` | (empty) | VibeVoice-ASR hot words |

### TTS Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `MIOTTS_API_URL` | `http://localhost:8001` | MioTTS API URL |
| `MIOTTS_DEVICE` | `mps` | MioTTS codec device |
| `KOKORO_MODEL` | `kokoro` | Kokoro model name |
| `KOKORO_VOICE` | `jf_alpha` | Kokoro Japanese voice |
| `KOKORO_HTTP_TIMEOUT` | `300.0` | Kokoro HTTP timeout (seconds) |
| `KOKORO_SPEED` | `1.0` | Kokoro speech speed |

### Translation & Output Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `PLAMO_TRANSLATE_PRECISION` | `8bit` | Translation model precision (4bit / 8bit / bf16) |
| `ENGLISH_VOLUME` | `0.10` | English audio volume (0.0-1.0) |
| `JAPANESE_VOLUME` | `1.00` | Japanese audio volume (0.0-1.0) |
| `OUTPUT_SIZE` | `720` | Output video height (pixels) |
| `KEEP_TEMP` | `true` | Whether to keep temporary files |

## Known Limitations

- **English-Japanese mixed content**: When English words are mixed like "utilizing simulation tools such as Omniverse and ISACsim", TTS may not read correctly.
- **Processing time**: Even a 3-minute video can take tens of minutes. Long videos may cause errors, so **splitting to about 8 minutes beforehand** is recommended.
- **Translation quality**: Local LLM translation may have quality variations compared to cloud APIs.
- **Kokoro TTS**: Does not support voice cloning, so all speakers will have the same voice. Suitable when prioritizing speed or when voice reproduction is not required.
- **VibeVoice-ASR processing speed**: Takes several times longer compared to Whisper.
- **VibeVoice-ASR memory usage**: Uses about 5GB of memory even with 8bit quantization due to 9B parameter model. Features built-in memory optimization through chunk encoding, tested on 24GB unified memory Mac.

## Troubleshooting

### whisper-cli not found

Run `scripts/setup_whisper.sh` to build whisper.cpp.

```bash
chmod +x scripts/setup_whisper.sh
./scripts/setup_whisper.sh
```

If CMake is not installed, run `brew install cmake` first.

### Out of memory

Tested on Mac mini M4 with 24GB unified memory. To save memory, ASR models (Whisper / VibeVoice-ASR) and pyannote pipeline are released after use. VibeVoice mode suppresses memory spikes during long audio processing through encoder chunking. For long videos, set `KEEP_TEMP=true` and utilize interruption/resume functionality.

### MioTTS text too long error

MioTTS default maximum text length is 300 characters. This tool specifies `--max-text-length 500` during server startup and also performs truncation processing at punctuation marks on the pipeline side.

### Kokoro TTS Japanese pronunciation issues

The unidic dictionary may not be downloaded. Run the following:

```bash
uv run python -m unidic download
```

### VibeVoice-ASR "mlx-audio not installed" error

Run the following:

```bash
uv pip install 'mlx-audio[stt]>=0.3.0'
```

### VibeVoice-ASR empty transcription results

The audio file may not contain speech or the audio may be too short. Try increasing `VIBEVOICE_MAX_TOKENS` or switch to Whisper mode.

> plamo-translate-cli automatically manages ports using MCP protocol. Configuration file is saved to `$TMPDIR/plamo-translate-config.json`.

## License

MIT License

Note: External models and libraries used by this tool have their own respective licenses.

- MioTTS default presets: Use audio generated by T5Gemma-TTS / Gemini TTS, commercial use not permitted
- PLaMo-2-Translate: PLaMo Community License (commercial use requires application)
- plamo-translate-cli: Apache-2.0 License
- pyannote.audio: MIT License (models are gated, requires agreement to terms of use on HuggingFace)
- whisper.cpp: MIT License
- Silero VAD: MIT License
- VibeVoice-ASR: MIT License
- mlx-audio: MIT License
- Kokoro TTS (Kokoro-82M): Apache-2.0 License
- misaki (G2P): MIT License