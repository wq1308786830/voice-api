# 文案转语音 API

让程序发送中文文案，接收完整 WAV 文件。调用程序可运行在 macOS、Windows 或 Linux。当前机器使用 Windows + WSL2 Ubuntu 的 CPU 部署；Linux + NVIDIA GPU 也可按下文通用步骤部署，但该路径尚未实测。操作系统本身不提升音质，主要区别是依赖兼容性、可用加速和生成速度。

本项目包含服务代码、跨平台命令行客户端、测试、短参考录音与实际生成的试听文件，不包含模型权重。`samples/` 中的参考音色试听通过官方 CosyVoice3 在线演示生成；25 项本地测试（14 项 API、4 项 Windows 离线入口、7 项 Mac 适配）及 HTTP/CLI 联调使用测试替身。当前 Windows + WSL2 CPU 已完成真实模型加载和 HTTP 语音生成；GPU 性能未验证。运行本地服务需要配置模型、参考录音和逐字稿。

先听效果和复现在线生成，请看 [试听说明](samples/README.md)；参考录音来源见 [来源记录](reference/SOURCE.md)。当前机器的本地启动方法见下一节；通用部署步骤随后给出。

## MacBook M5 / 32GB 部署包

Mac 版使用社区 [mlx-audio-plus](https://github.com/DePasqualeOrg/mlx-audio-plus/tree/4c9ec6a8489e790b5ba8964ab1f1d63150476f9f) 的 CosyVoice3 移植，通过 MLX 使用 Apple Metal GPU。采用 [CosyVoice3 的 MLX 4bit 转换模型](https://huggingface.co/mlx-community/Fun-CosyVoice3-0.5B-2512-4bit)，其中语言模型部分量化为 4 位，其他模块并非全部 4 位。32GB 是本部署包的目标配置；**尚未在你的 M5 上运行真实模型，不能据此承诺生成速度、峰值内存或与 Windows 完全相同的音色。**

将部署 ZIP 复制到 Mac 并解压，在终端进入解压后的 `voice-api` 目录。要求 macOS 14 或更新版本、原生 arm64 终端（不要通过 Rosetta 运行）。初次安装需要访问 GitHub、PyPI 和 Hugging Face；模型与分词器约 2.2GB，连同运行环境与缓存建议预留至少 10GB 磁盘空间。

```bash
# 在解压后的 voice-api 目录执行；无需先安装 Python、Homebrew 或 CUDA。
bash scripts/setup-mac.sh
bash scripts/run-mac.sh
```

安装脚本把 uv、Python 3.11、独立环境和模型放在项目的 `.runtime-mac/`，不需要 sudo。保留该目录即可复用下载。运行脚本保持前台运行；看到 `Application startup complete` 后，在另一个终端进入同一项目目录执行：

```bash
# 生成与 Windows 实测相同文案，输出音频和耗时 JSON。
.runtime-mac/venv/bin/python scripts/benchmark-local.py
afplay generated/mac-smoke.wav

# 程序调用：输入自己的文案，输出 WAV。
.runtime-mac/venv/bin/python client.py --text "这是一段人工智能合成语音。做事情，先想清楚，再一步一步去完成。" --output generated/result.wav
# 或读取 UTF-8 文案文件。
.runtime-mac/venv/bin/python client.py --text-file input.txt --output generated/result.wav --timeout 1200
```

接口与 Windows 相同：`POST http://127.0.0.1:8000/v1/audio/speech` 返回 WAV；健康检查为 `GET /health`。停止时在服务终端按 `Ctrl+C`，下次只需重新运行 `bash scripts/run-mac.sh`；本包不配置开机自启。`benchmark-local.py` 需要接口已经就绪，计时不含模型启动耗时。`samples/` 内原有音频来自在线演示，不是 M5 实测结果。

Mac 入口为 `mac_app:app`。所有 MLX 加载、生成和清理在同一个专用工作线程执行。模型与 S3TokenizerV3 的版本固定在 `mac-models.json`，安装时分别下载到本地；启动时启用 Hugging Face / Transformers 离线模式，并显式加载本地 S3 权重。使用包内的 `reference/reference.wav` 与对应逐字稿进行参考音色生成；合成音频不代表本人原始录音。

此固定移植会忽略原始 `speed` 参数，因此 Mac 适配层用 librosa 对整段音频做保留音高的时间伸缩，实现接口的 0.5–2.0 倍速；与 Windows 的模型内部调速方法不同。Mac 文本规范化也不同于 Windows 的 wetext，对日期、金额、多音字等建议写明期望读法并试听。`requirements-mac.txt` 是针对 macOS 14 ARM64 / Python 3.11 解析的固定依赖清单；不要替换为同名 PyPI `mlx-audio-plus==0.1.8`，其依赖与这里固定的源码版本不同。

目前已完成依赖解析与二进制包可用性检查、Shell 语法检查以及不依赖 MLX 的替身测试。**Apple GPU 加载、真实语音、耗时和内存仍需在 Mac 上通过上述命令验收。** 下载中断可重跑安装脚本；启动失败时保留终端报错，并确认未占用本机 8000 端口。

## 当前 Windows + WSL2 CPU 部署

运行时已安装在 WSL Ubuntu 的 `/opt/voice-api-runtime`，使用 Python 3.10、PyTorch 2.3.1 CPU 版和固定到提交 `074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc` 的 CosyVoice。模型为 `Fun-CosyVoice3-0.5B-2512`，固定 revision `29e01c4e8d000f4bcd70751be16fa94bf3d85a18`，文件位于 Windows 工作目录 `work/local-model`，在 WSL 中对应 `/mnt/c/Users/Administrator/Documents/Codex/2026-09-28/wo-xi/work/local-model`。服务配置在 `/opt/voice-api-runtime/service.env`，由 systemd 的 `voice-api.service` 读取；其中的密钥如已配置，请勿复制到日志或文档。此机服务使用 `local_app:app` 作为入口。

离线文本规范化资源目录由 `WETEXT_MODEL_DIR=/opt/voice-api-runtime/wetext` 指定。目录内需要 `en/tn` 和 `zh/tn` 各自的 `tagger.fst`、`verbalizer.fst`，共四个非空 FST 文件。这些资源来自 [wetext 官方 ModelScope Git 仓库](https://www.modelscope.cn/pengzhendong/wetext.git) 的 revision `030bb1febce0bd0168549a03e181cd9c1d70c799`；本次 ModelScope 下载遇到 HTTP 403，改由该 Git 仓库获取。`local_app.py` 仅在模型构造期间将 wetext 的资源解析器定向到本地目录，构造结束或报错后都会恢复原解析器；未修改第三方源码。

在本项目目录的 Windows PowerShell 中手动控制服务：

```powershell
.\scripts\local-service.ps1 start
.\scripts\local-service.ps1 status
.\scripts\local-service.ps1 restart
.\scripts\local-service.ps1 stop
```

服务设置为**不随开机自动启动**；重启 Windows 或 WSL 后需重新执行 `start`。`start` 和 `restart` 会启动一个隐藏的 `wsl sleep infinity` 进程，让 WSL 在空闲时保持运行；`stop` 会停止服务及脚本创建的保活进程，不会关闭整个 Ubuntu 发行版。服务只监听 `127.0.0.1:8000`，本机请求地址为 `http://127.0.0.1:8000`。首次启动需要加载模型，`start` 命令返回后可用 `status` 和 `GET /health` 检查准备状态；真实语音生成仍需按下文调用并试听。服务启停和 Windows 端 `/health` 已验证。模型权重仍在上述 `work/local-model` 目录，运行此服务时请保留该目录。

如需在另一个 WSL Ubuntu 环境重建 CPU 依赖，项目提供 `requirements-local-cpu.txt` 与 `build-constraints-local-cpu.txt`。运行时固定 `setuptools==80.9.0`，因为当前 Lightning 依赖其中的 `pkg_resources`；构建约束另固定 `setuptools==80.9.0`、`numpy==1.26.4`。构建前还需安装系统包 `python3.10-dev`。这些文件用于当前 CPU 路径；下文 Linux + NVIDIA GPU 是单独的通用说明。

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

## 1. 准备 Linux + NVIDIA GPU 模型环境（未实测）

下列命令是通用部署说明，尚未在当前机器完成 GPU 实测。需要已有可用的 NVIDIA 驱动和 Conda。使用独立环境，避免影响其他项目。

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

Windows 原生模型推理未验证；Mac 的 MLX 部署方式见前文，尚待真机验收。跨平台调用远程 Linux 服务不需要安装 CUDA、PyTorch 或 CosyVoice。

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

Node.js、Java、Go 等语言也按同一 HTTP 协议调用。当前 WSL2 部署使用上述本机地址；其他部署需替换为实际服务地址。

## 验证与限制

轻量接口测试不需要模型或 GPU：

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

本次在 Windows / Python 3.12.14 验证：25 项测试通过，其中 14 项覆盖接口、4 项覆盖 Windows 离线入口、7 项覆盖 Mac 适配与线程生命周期；另通过真实本地 HTTP + 命令行客户端联调，检查了带 BOM 的中文 UTF-8 文件输入、24 kHz WAV 输出、鉴权失败时保留原文件。这些验证均使用测试替身，未加载 CosyVoice 权重，测试音频不作为语音效果样本。测试出现一条第三方 Starlette/AnyIO 弃用警告，不影响本次通过结果。WSL2 CPU 的真实模型验证结果见下文；GPU 路径未实测。

2026-09-28 在当前 Windows + WSL2 机器完成真实模型验证：

- 服务使用 CPU、8 个计算线程；本机 HTTP 健康检查和语音生成均成功。
- 文案：“这是一段在本地电脑生成的人工智能语音。遇到事情，先让自己静下来，再慢慢找到解决的方法。”
- 模型已加载后的首次请求耗时 **34.664 秒**，输出 **10.64 秒**语音，RTF **3.258**（生成时间 / 音频时间）；这是单条样本，不能代表所有文案速度，也不含服务启动时间。
- WAV 为 24 kHz、单声道、16 位 PCM，完整解码通过、音频非静音。试听位于项目上级输出目录的 `本地CPU_AI合成试听.wav`，属于 AI 合成录音。
- 本地 wetext 实测将 `2026年9月28日` 转成“二零二六年九月二十八日”，将 `$12.50` 转成 `twelve point five dollars`；模型及这些文本规则从本机加载。

还需用目标文案验证：中文多音字和数字、漏读与重复、短句与长段落、语速、音色一致性、耗时和显存峰值。不能仅凭 HTTP 200 判断声音已经符合预期。

## 依据

- [CosyVoice 官方部署与模型说明](https://github.com/QwenAudio/CosyVoice)
- [CosyVoice3 参考音频调用示例](https://github.com/QwenAudio/CosyVoice/blob/074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc/example.py)
- [模型推理参数与采样率来源](https://github.com/QwenAudio/CosyVoice/blob/074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc/cosyvoice/cli/cosyvoice.py)
