#!/bin/bash
set -euo pipefail

if [ "$(uname -s)" != Darwin ] || [ "$(uname -m)" != arm64 ]; then
    echo '请在 Apple 芯片 Mac 的原生终端运行；不支持 Rosetta、Intel Mac 或 Windows。' >&2
    exit 1
fi
mac_major=$(sw_vers -productVersion | cut -d. -f1)
if [ "$mac_major" -lt 14 ]; then
    echo '本部署包需要 macOS 14 或更新版本。' >&2
    exit 1
fi

ROOT=$(cd "$(dirname "$0")/.." && pwd)
RUNTIME="$ROOT/.runtime-mac"
mkdir -p "$RUNTIME/bin" "$RUNTIME/downloads"
export UV_CACHE_DIR="$RUNTIME/cache/uv"
export UV_PYTHON_INSTALL_DIR="$RUNTIME/python"
export HF_HOME="$RUNTIME/cache/huggingface"
export XDG_CACHE_HOME="$RUNTIME/cache"
export HF_HUB_DISABLE_TELEMETRY=1
export DO_NOT_TRACK=1

# Install a pinned standalone uv inside this project, without Homebrew or sudo.
UV="$RUNTIME/bin/uv"
if [ ! -x "$UV" ]; then
    archive="$RUNTIME/downloads/uv-aarch64-apple-darwin.tar.gz"
    curl --fail --location --retry 3 \
        'https://github.com/astral-sh/uv/releases/download/0.12.5/uv-aarch64-apple-darwin.tar.gz' \
        --output "$archive"
    expected='5bb0e5fe008a773c3dbcb97ff79cd89e1241464fe9d2f986d52ad8f1b037bd62'
    actual=$(shasum -a 256 "$archive" | cut -d' ' -f1)
    if [ "$actual" != "$expected" ]; then
        echo 'uv 文件校验失败；未执行下载文件。' >&2
        exit 1
    fi
    tar -xzf "$archive" -C "$RUNTIME/downloads"
    cp "$RUNTIME/downloads/uv-aarch64-apple-darwin/uv" "$UV"
    chmod +x "$UV"
fi

"$UV" python install --no-bin 3.11
if [ ! -x "$RUNTIME/venv/bin/python" ]; then
    "$UV" venv --managed-python --python 3.11 "$RUNTIME/venv"
fi
"$UV" pip install --python "$RUNTIME/venv/bin/python" -r "$ROOT/requirements-mac.txt"
"$UV" pip check --python "$RUNTIME/venv/bin/python"
"$RUNTIME/venv/bin/python" -c 'import mlx.core as mx; assert mx.metal.is_available(), "Apple Metal GPU unavailable"; print("MLX Metal: available")'
"$RUNTIME/venv/bin/python" "$ROOT/scripts/download-mac-models.py" "$RUNTIME"
echo '安装完成。启动服务：bash scripts/run-mac.sh'
echo '首次实际生成后再判断音色和性能；本部署包尚未在 M5 真机验收。'
