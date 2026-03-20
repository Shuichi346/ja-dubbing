#!/bin/bash
# ================================================================
# GPT-SoVITS setup script for ja-dubbing project
#
# GPT-SoVITS を独立した conda 環境にインストールする。
# ja-dubbing 本体の uv 環境には一切触れない。
# V2ProPlus モデルをゼロショットボイスクローンで使用する。
#
# 実行方法:
#   chmod +x scripts/setup_gptsovits.sh
#   ./scripts/setup_gptsovits.sh
#
# 前提:
#   - conda (miniforge/miniconda) がインストール済み
#   - git, curl がインストール済み
#   - ffmpeg がインストール済み（brew install ffmpeg）
# ================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
GPTSOVITS_DIR="$PROJECT_ROOT/GPT-SoVITS"
CONDA_ENV_NAME="gptsovits"
PYTHON_VERSION="3.11"

echo "=== GPT-SoVITS setup (V2ProPlus / macOS Apple Silicon) ==="
echo "Project root: $PROJECT_ROOT"
echo "GPT-SoVITS dir: $GPTSOVITS_DIR"
echo "conda env: $CONDA_ENV_NAME"
echo "Python: $PYTHON_VERSION"
echo ""

if ! command -v curl &>/dev/null; then
    echo "Error: curl not found."
    exit 1
fi

if ! command -v conda &>/dev/null; then
    echo "Error: conda not found."
    echo "Install miniforge: brew install --cask miniforge"
    exit 1
fi

eval "$(conda shell.bash hook)"

download_file() {
    local url="$1"
    local output="$2"
    echo "  Downloading: $(basename "$output")"
    curl -L --retry 5 --retry-delay 3 -# -o "$output" "$url"
}

# ---- 1. Clone GPT-SoVITS ----
if [ -d "$GPTSOVITS_DIR" ]; then
    echo "1/6: GPT-SoVITS directory exists. Updating..."
    cd "$GPTSOVITS_DIR"
    git pull --ff-only || echo "  (git pull failed, continuing)"
else
    echo "1/6: Cloning GPT-SoVITS..."
    git clone https://github.com/RVC-Boss/GPT-SoVITS.git "$GPTSOVITS_DIR"
    cd "$GPTSOVITS_DIR"
fi

# ---- 2. Create conda env ----
echo ""
echo "2/6: Creating conda env ($CONDA_ENV_NAME / Python $PYTHON_VERSION)..."

if conda env list | grep -q "^${CONDA_ENV_NAME} "; then
    echo "  conda env '$CONDA_ENV_NAME' already exists."
else
    conda create -n "$CONDA_ENV_NAME" python="$PYTHON_VERSION" -y
fi

conda activate "$CONDA_ENV_NAME"

# ---- 3. Install PyTorch + dependencies ----
echo ""
echo "3/6: Installing PyTorch + dependencies..."

pip install torch torchcodec --index-url https://download.pytorch.org/whl/cpu

cd "$GPTSOVITS_DIR"
if [ -f "extra-req.txt" ]; then
    pip install -r extra-req.txt --no-deps
fi
pip install -r requirements.txt

echo "  Dependencies installed."

# ---- 4. Download NLTK data + pyopenjtalk dictionary ----
echo ""
echo "4/6: Installing NLTK data and pyopenjtalk dictionary..."

# conda 環境のプレフィックスパスを取得
PY_PREFIX=$(python -c "import sys; print(sys.prefix)")
echo "  Python prefix: $PY_PREFIX"

# NLTK データのダウンロード（GPT-SoVITS の公式 install.sh と同じ手順）
NLTK_DATA_URL="https://huggingface.co/XXXXRT/GPT-SoVITS-Pretrained/resolve/main/nltk_data.zip"
NLTK_TARGET_DIR="$PY_PREFIX/nltk_data"

if [ -d "$NLTK_TARGET_DIR/taggers/averaged_perceptron_tagger_eng" ]; then
    echo "  NLTK data already present at: $NLTK_TARGET_DIR"
else
    echo "  Downloading NLTK data..."
    cd "$GPTSOVITS_DIR"
    download_file "$NLTK_DATA_URL" "nltk_data.zip"
    echo "  Extracting NLTK data to: $PY_PREFIX"
    unzip -q -o nltk_data.zip -d "$PY_PREFIX"
    rm -f nltk_data.zip
    echo "  NLTK data installed."

    # フォールバック: zip の中身にデータが不足していた場合は Python で直接ダウンロード
    if [ ! -d "$NLTK_TARGET_DIR/taggers/averaged_perceptron_tagger_eng" ]; then
        echo "  NLTK zip にデータが不足。Python から追加ダウンロード中..."
        python -c "
import nltk
nltk.download('averaged_perceptron_tagger_eng', download_dir='$NLTK_TARGET_DIR')
nltk.download('punkt_tab', download_dir='$NLTK_TARGET_DIR')
nltk.download('cmudict', download_dir='$NLTK_TARGET_DIR')
"
        echo "  NLTK 追加データダウンロード完了。"
    fi
fi

# ユーザーホームの nltk_data にもシンボリックリンクを作成（GPT-SoVITS がここも探すため）
USER_NLTK_DIR="$HOME/nltk_data"
if [ ! -d "$USER_NLTK_DIR/taggers/averaged_perceptron_tagger_eng" ]; then
    echo "  Downloading NLTK data to user home as fallback..."
    python -c "
import nltk
nltk.download('averaged_perceptron_tagger_eng')
nltk.download('punkt_tab')
nltk.download('cmudict')
"
    echo "  User home NLTK data installed."
else
    echo "  User home NLTK data already present."
fi

# pyopenjtalk 辞書のインストール（日本語テキストフロントエンドに必要）
PYOPENJTALK_URL="https://huggingface.co/XXXXRT/GPT-SoVITS-Pretrained/resolve/main/open_jtalk_dic_utf_8-1.11.tar.gz"
PYOPENJTALK_PREFIX=$(python -c "import os, pyopenjtalk; print(os.path.dirname(pyopenjtalk.__file__))" 2>/dev/null || echo "")

if [ -n "$PYOPENJTALK_PREFIX" ]; then
    if [ -d "$PYOPENJTALK_PREFIX/open_jtalk_dic_utf_8-1.11" ]; then
        echo "  pyopenjtalk dictionary already present."
    else
        echo "  Downloading pyopenjtalk dictionary..."
        cd "$GPTSOVITS_DIR"
        download_file "$PYOPENJTALK_URL" "open_jtalk_dic_utf_8-1.11.tar.gz"
        tar -xzf open_jtalk_dic_utf_8-1.11.tar.gz -C "$PYOPENJTALK_PREFIX"
        rm -f open_jtalk_dic_utf_8-1.11.tar.gz
        echo "  pyopenjtalk dictionary installed."
    fi
else
    echo "  Warning: pyopenjtalk not found. Skipping dictionary install."
    echo "  (Japanese text frontend may not work correctly)"
fi

# ---- 5. Download pretrained models ----
echo ""
echo "5/6: Downloading pretrained models..."

PRETRAINED_DIR="$GPTSOVITS_DIR/GPT_SoVITS/pretrained_models"
mkdir -p "$PRETRAINED_DIR"

if [ ! -d "$PRETRAINED_DIR/chinese-roberta-wwm-ext-large" ]; then
    echo "  Downloading base models (large file, please wait)..."
    cd "$GPTSOVITS_DIR"
    download_file \
        "https://huggingface.co/XXXXRT/GPT-SoVITS-Pretrained/resolve/main/pretrained_models.zip" \
        "pretrained_models.zip"
    echo "  Extracting..."
    unzip -q -o pretrained_models.zip -d GPT_SoVITS
    rm -f pretrained_models.zip
    echo "  Base models downloaded."
else
    echo "  Base models already present."
fi

V2PRO_DIR="$PRETRAINED_DIR/v2Pro"
mkdir -p "$V2PRO_DIR"

if [ ! -f "$V2PRO_DIR/s2Gv2ProPlus.pth" ]; then
    download_file \
        "https://huggingface.co/lj1995/GPT-SoVITS/resolve/main/v2Pro/s2Gv2ProPlus.pth" \
        "$V2PRO_DIR/s2Gv2ProPlus.pth"
else
    echo "  s2Gv2ProPlus.pth already present."
fi

if [ ! -f "$V2PRO_DIR/s2Dv2ProPlus.pth" ]; then
    download_file \
        "https://huggingface.co/lj1995/GPT-SoVITS/resolve/main/v2Pro/s2Dv2ProPlus.pth" \
        "$V2PRO_DIR/s2Dv2ProPlus.pth"
else
    echo "  s2Dv2ProPlus.pth already present."
fi

if [ ! -f "$PRETRAINED_DIR/s1v3.ckpt" ]; then
    download_file \
        "https://huggingface.co/lj1995/GPT-SoVITS/resolve/main/s1v3.ckpt" \
        "$PRETRAINED_DIR/s1v3.ckpt"
else
    echo "  s1v3.ckpt already present."
fi

SV_DIR="$PRETRAINED_DIR/sv"
mkdir -p "$SV_DIR"

if [ ! -f "$SV_DIR/pretrained_eres2netv2w24s4ep4.ckpt" ]; then
    download_file \
        "https://huggingface.co/lj1995/GPT-SoVITS/resolve/main/sv/pretrained_eres2netv2w24s4ep4.ckpt" \
        "$SV_DIR/pretrained_eres2netv2w24s4ep4.ckpt"
else
    echo "  Speaker verification model already present."
fi

# ---- 6. Configure tts_infer.yaml for V2ProPlus ----
echo ""
echo "6/6: Writing tts_infer.yaml for V2ProPlus + CPU..."

CONFIG_DIR="$GPTSOVITS_DIR/GPT_SoVITS/configs"
mkdir -p "$CONFIG_DIR"
CONFIG_FILE="$CONFIG_DIR/tts_infer.yaml"

cat > "$CONFIG_FILE" << 'YAMLEOF'
custom:
  bert_base_path: GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large
  cnhuhbert_base_path: GPT_SoVITS/pretrained_models/chinese-hubert-base
  device: cpu
  is_half: false
  t2s_weights_path: GPT_SoVITS/pretrained_models/s1v3.ckpt
  version: v2ProPlus
  vits_weights_path: GPT_SoVITS/pretrained_models/v2Pro/s2Gv2ProPlus.pth
v2ProPlus:
  bert_base_path: GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large
  cnhuhbert_base_path: GPT_SoVITS/pretrained_models/chinese-hubert-base
  device: cpu
  is_half: false
  t2s_weights_path: GPT_SoVITS/pretrained_models/s1v3.ckpt
  version: v2ProPlus
  vits_weights_path: GPT_SoVITS/pretrained_models/v2Pro/s2Gv2ProPlus.pth
YAMLEOF

echo "  tts_infer.yaml configured."

conda deactivate

echo ""
echo "=== Setup complete ==="
echo ""
echo "GPT-SoVITS dir: $GPTSOVITS_DIR"
echo "conda env: $CONDA_ENV_NAME"
echo "Model: V2ProPlus (zero-shot voice clone)"
echo ""
echo "Start API server:"
echo "  conda activate $CONDA_ENV_NAME"
echo "  cd $GPTSOVITS_DIR"
echo "  python api_v2.py -a 127.0.0.1 -p 9880 -c GPT_SoVITS/configs/tts_infer.yaml"
echo ""
echo "Usage from ja-dubbing:"
echo "  Set TTS_ENGINE=gptsovits in .env"
