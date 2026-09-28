#!/bin/bash
set -euo pipefail

if [ "$(uname -s)" != Darwin ] || [ "$(uname -m)" != arm64 ]; then
    echo '请在 Apple 芯片 Mac 的原生终端运行。' >&2
    exit 1
fi
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RUNTIME="$ROOT/.runtime-mac"
PYTHON="$RUNTIME/venv/bin/python"
if [ ! -x "$PYTHON" ]; then
    echo '请先执行 bash scripts/setup-mac.sh。' >&2
    exit 1
fi

export MLX_MODEL_DIR="$RUNTIME/models/model"
export MLX_TOKENIZER_DIR="$RUNTIME/models/tokenizer"
export REFERENCE_WAV="${REFERENCE_WAV:-$ROOT/reference/reference.wav}"
export REFERENCE_TEXT_FILE="${REFERENCE_TEXT_FILE:-$ROOT/reference/reference.txt}"
export HF_HOME="$RUNTIME/cache/huggingface"
export XDG_CACHE_HOME="$RUNTIME/cache"
export NUMBA_CACHE_DIR="$RUNTIME/cache/numba"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export HF_HUB_DISABLE_TELEMETRY=1
export TOKENIZERS_PARALLELISM=false
export DO_NOT_TRACK=1
cd "$ROOT"
echo '正在加载本地 MLX 模型；看到 Application startup complete 后即可调用。'
echo 'API: http://127.0.0.1:8000 ，按 Ctrl+C 停止服务。'
exec "$PYTHON" -m uvicorn mac_app:app --host 127.0.0.1 --port 8000 --workers 1
