# 试听文件

| 文件 | 内容与来源 |
|---|---|
| 中文男声试听.mp3 | Edge 在线 TTS 的 `zh-TW-YunJheNeural` 通用男声，语速 `-12%`，约 34.6 秒；不是曾仕强参考音色。 |
| 试听文案.txt | 本项目生成的原创文案。 |
| 曾仕强音色参考_AI合成试听.wav | 用 `reference/` 中的公开讲座片段作为声音参考，通过官方 CosyVoice3 在线演示合成，约 37.04 秒、24 kHz、单声道、16 位 PCM。 |
| 曾仕强音色参考_AI合成试听.mp3 | 上述 WAV 的 128 kbps MP3 版本，元数据标注 AI 合成。 |
| AI合成试听文案.txt | 参考音色试听的实际输入文案，开头包含人工智能合成提示。 |

参考音色生成服务：[FunAudioLLM/Fun-CosyVoice3-0.5B](https://huggingface.co/spaces/FunAudioLLM/Fun-CosyVoice3-0.5B)，`zero_shot` 模式，随机种子 42；生成日期 2026-09-28。

这些是 AI 合成音频，文案不是曾仕强本人原话。在线生成已成功，解码和语音转写核对已完成；相似度和自然度仍需人工试听评价。本地 API 的模型部署尚未完成，不能将在线结果当成本地 GPU 推理验收。

## 重新生成

在项目根目录运行（需要联网，会向上述官方演示上传参考音频和输入文案；该公共服务可能排队、限额或变更接口）：

```bash
python -m pip install -r requirements-sample.txt
python scripts/generate_sample.py
```

默认读取项目中的参考声音和原创文案，输出到被 Git 忽略的 `generated/ai-sample.wav`。也可用 `--reference`、`--transcript`、`--text-file`、`--output`、`--seed` 指定参数。服务限制参考 WAV 最长 10 秒、采样率不低于 16 kHz，文案加合成提示最长 200 字符。没有稳定性或输出逐字节一致的保证。

通用男声示例：

```bash
python -m edge_tts --voice zh-TW-YunJheNeural --rate=-12% --file samples/试听文案.txt --write-media generated/stock-voice.mp3
```

执行通用男声命令前，请先创建 `generated` 目录。
