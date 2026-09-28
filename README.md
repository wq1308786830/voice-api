# 文案转语音 API

让程序发送中文文案，接收完整 WAV 文件。调用程序可运行在 macOS、Windows 或 Linux；推荐将 CosyVoice 模型服务部署在 Linux + NVIDIA GPU，Windows 可使用 WSL2。操作系统本身不提升音质，主要区别是依赖兼容性、可用加速和生成速度。

本项目包含服务代码、跨平台命令行客户端、测试、短参考录音与实际生成的试听文件，不包含模型权重。`samples/` 中的参考音色试听通过官方 CosyVoice3 在线演示生成；本地 API 测试使用测试替身，本地模型部署和 GPU 性能仍未验证。运行本地服务需要配置模型、参考录音和逐字稿。

先听效果和复现在线生成，请看 [试听说明](samples/README.md)；参考录音来源见 [来源记录](reference/SOURCE.md)。本地服务部署步骤如下。

## 调用方式

`POST /v1/audio/speech`，请求为 JSON：

```json
{
  "input": "人生很多事情，需要慢慢体会。",
  "voice": "default",
  "speed": 0.9,
  "response_format": "wav"
}
```

成功返回 `200 audio/wav`，响应体就是音频文件，不是文件路径或 JSON。输出为单声道、16 位 PCM，采样率采用模型实际值。`voice` 目前只能是 `default`，指向服务启动时配置的参考声音；没有内置名人声音库。

- `input`：去除首尾空白后不能为空，最多 5000 字符；保持用户文案，分句由模型处理。
- `speed`：0.5–2.0，1.0 为正常语速，默认 1.0。
- `response_format`：仅支持 `wav`，默认 `wav`。
- `GET /health`：检查服务是否已加载模型；不执行一次生成，也不承诺推理一定成功。
- 参数错误返回 422；启用密钥后未授权返回 401；正在生成时返回 429；生成失败返回 500。

采用单模型、单请求推理模式。请只启动一个 worker。较长文案需要较长响应时间；本版生成完毕后一次性返回，不提供异步任务或流式播放。调用方收到 429 时，应等待响应中的 `Retry-After` 后重试。

## 1. 准备 Linux 模型环境

下列命令是部署说明，尚未在当前机器完成 GPU 实测。需要已有可用的 NVIDIA 驱动和 Conda。使用独立环境，避免影响其他项目。

```bash
git clone --recursive https://github.com/QwenAudio/CosyVoice.git
cd CosyVoice
git checkout 074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc
git submodule update --init --recursive
conda create -n voice-api python=3.10 -y
conda activate voice-api
python -m pip install -r requirements.txt
```

这里固定了本次核对接口的仓库版本。模型仓库的依赖包含 PyTorch、音频处理和 GPU 包，下载较大；安装报错时应根据实际错误处理，不建议盲目升级全部依赖。若出现 SoX 依赖问题，按官方说明安装系统 `sox` 和 `libsox-dev`。

下载模型（在 CosyVoice 目录下执行）：

```bash
python -c "from modelscope import snapshot_download; snapshot_download('FunAudioLLM/Fun-CosyVoice3-0.5B-2512', local_dir='pretrained_models/Fun-CosyVoice3-0.5B')"
```

模型下载本身并不创建目标人物的声音。随后进入本项目目录，在同一 Conda 环境安装 API 依赖：

```bash
cd /your/path/voice-api
python -m pip install -r requirements.txt
```

## 2. 配置参考声音

准备一段单人、清晰、没有背景音乐和混响的 WAV，以及这段录音准确对应的 UTF-8 逐字稿。可先用约 10–20 秒的录音试验；这是起步建议，不是效果保证。不要将待合成文案填入参考录音逐字稿。

使用具体人物的声音前，确认素材和声音使用授权范围、发布方式。项目附带的 9 秒参考录音来源和使用说明见 `reference/SOURCE.md`；输出属于合成音频，不应描述为本人原始录音。

Linux/WSL2 配置示例（替换为实际绝对路径）：

```bash
export COSYVOICE_REPO=/your/path/CosyVoice
export COSYVOICE_MODEL_DIR=/your/path/CosyVoice/pretrained_models/Fun-CosyVoice3-0.5B
export REFERENCE_WAV=/your/path/voice/reference.wav
export REFERENCE_TEXT_FILE=/your/path/voice/reference.txt
# 如果其他机器需要访问，建议配置此密钥，并使用受控内网或 HTTPS 反向代理。
export TTS_API_KEY='replace-with-your-own-key'
python -m uvicorn app:app --host 127.0.0.1 --port 8000 --workers 1
```

默认仅本机访问。需要供其他机器调用时，将 `--host` 改成 `0.0.0.0`，调用方使用服务器实际地址。WSL2 的端口访问还取决于 Windows 的网络和防火墙配置。

如果自行在 Windows 原生环境安装好了模型依赖，可以用 PowerShell 设置相同变量：

```powershell
$env:COSYVOICE_REPO = 'D:\models\CosyVoice'
$env:COSYVOICE_MODEL_DIR = 'D:\models\CosyVoice\pretrained_models\Fun-CosyVoice3-0.5B'
$env:REFERENCE_WAV = 'D:\voices\reference.wav'
$env:REFERENCE_TEXT_FILE = 'D:\voices\reference.txt'
$env:TTS_API_KEY = 'replace-with-your-own-key'
python -m uvicorn app:app --host 127.0.0.1 --port 8000 --workers 1
```

macOS 和 Windows 的原生模型推理未验证，尤其不承诺 Apple GPU 加速。跨平台调用远程 Linux 服务不需要安装 CUDA、PyTorch 或 CosyVoice。

## 3. 从任意系统调用

客户端仅使用 Python 标准库，不需要安装第三方包。服务端启用密钥时，客户端也设置同一个 `TTS_API_KEY` 环境变量。

```bash
python client.py --url http://127.0.0.1:8000 --text "人生很多事情，需要慢慢体会。" --speed 0.9 --output result.wav
python client.py --url http://127.0.0.1:8000 --text-file input.txt --output result.wav
```

客户端默认等待最多 600 秒，可用 `--timeout 1200` 调整。若服务返回错误或音频格式不正确，客户端报错退出并保留原有输出文件。

也可以直接在现有程序中发送 HTTP 请求，例如 Python 标准库：

```python
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

payload = {"input": "这里放你的文案。", "voice": "default", "speed": 0.9}
headers = {"Content-Type": "application/json"}
if os.getenv("TTS_API_KEY"):
    headers["Authorization"] = "Bearer " + os.environ["TTS_API_KEY"]
request = Request(
    "http://127.0.0.1:8000/v1/audio/speech",
    data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
    headers=headers,
    method="POST",
)
with urlopen(request, timeout=600) as response:
    audio = response.read()
Path("result.wav").write_bytes(audio)
```

Node.js、Java、Go 等语言也按同一 HTTP 协议调用。示例地址均为占位的本机服务地址；项目交付不表示该地址已有模型服务运行。

## 验证与限制

轻量接口测试不需要模型或 GPU：

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

本次在 Windows / Python 3.12.14 验证：14 项接口测试通过；另通过真实本地 HTTP + 命令行客户端联调，检查了带 BOM 的中文 UTF-8 文件输入、24 kHz WAV 输出、鉴权失败时保留原文件。两类验证均使用测试替身，未加载 CosyVoice 权重，测试音频不作为语音效果样本。测试出现一条第三方 Starlette/AnyIO 弃用警告，不影响本次通过结果。

接入真实模型后还需用目标文案验证：中文多音字和数字、漏读与重复、短句与长段落、语速、音色一致性、耗时和显存峰值。不能仅凭 HTTP 200 判断声音已经符合预期。

## 依据

- [CosyVoice 官方部署与模型说明](https://github.com/QwenAudio/CosyVoice)
- [CosyVoice3 参考音频调用示例](https://github.com/QwenAudio/CosyVoice/blob/074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc/example.py)
- [模型推理参数与采样率来源](https://github.com/QwenAudio/CosyVoice/blob/074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc/cosyvoice/cli/cosyvoice.py)
