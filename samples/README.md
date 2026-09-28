# 试听文件

| 文件 | 内容与来源 |
|---|---|
| 中文男声试听.mp3 | Edge 在线 TTS 的 `zh-TW-YunJheNeural` 通用男声，语速 `-12%`，约 34.6 秒；不是曾仕强参考音色。 |
| 试听文案.txt | 本项目生成的原创文案。 |
| 曾仕强音色参考_AI合成试听.wav | 用 `reference/` 中的公开讲座片段作为声音参考，通过官方 CosyVoice3 在线演示合成，约 37.04 秒、24 kHz、单声道、16 位 PCM。 |
| 曾仕强音色参考_AI合成试听.mp3 | 上述 WAV 的 128 kbps MP3 版本，元数据标注 AI 合成。 |
| AI合成试听文案.txt | 参考音色试听的实际输入文案，开头包含人工智能合成提示。 |

参考音色生成服务：[FunAudioLLM/Fun-CosyVoice3-0.5B](https://huggingface.co/spaces/FunAudioLLM/Fun-CosyVoice3-0.5B)，`zero_shot` 模式，随机种子 42；生成日期 2026-09-28。

这些是历史 AI 合成音频，文案不是曾仕强本人原话。在线生成已成功，解码和语音转写核对已完成；相似度和自然度仍需人工试听评价。Windows 本地 CPU 部署现已完成，但本目录的在线结果不能当成本地 GPU 推理验收。当前默认使用清理后的曾仕强参考（`reference/zeng_voice.wav`），学术理法派仍可手动选择；这里保留旧试听以说明其真实来源。

## 重新生成

在项目根目录运行（需要联网，会向上述官方演示上传参考音频和输入文案；该公共服务可能排队、限额或变更接口）：

```bash
python -m pip install -r requirements-sample.txt
python scripts/generate_sample.py
```

在线示例脚本现默认读取去除头尾背景的 `reference/zeng_voice.wav`、`reference/zeng_voice.txt` 和原创文案，输出到被 Git 忽略的 `generated/ai-sample.wav`。本目录既有样本仍是旧参考生成的历史结果；若需复现原参考条件，可用 `--reference reference/reference.wav --transcript reference/reference.txt` 明确指定。也可用 `--text-file`、`--output`、`--seed` 指定其他参数。在线服务限制参考 WAV 最长 10 秒、采样率不低于 16 kHz，文案加合成提示最长 200 字符，因此不应直接给它传入约 22.7 秒的当前学术理法派参考。没有稳定性或输出逐字节一致的保证。

通用男声示例：

```bash
python -m edge_tts --voice zh-TW-YunJheNeural --rate=-12% --file samples/试听文案.txt --write-media generated/stock-voice.mp3
```

执行通用男声命令前，请先创建 `generated` 目录。
