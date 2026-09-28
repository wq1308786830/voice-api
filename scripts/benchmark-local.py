"""Generate one real sample through the HTTP client and report wall-clock RTF."""

import argparse
import json
import os
from pathlib import Path
import sys
import time
from urllib.request import urlopen
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from client import synthesize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, default=Path("generated/mac-smoke.wav"))
    parser.add_argument("--text", default="这是一段在本地电脑生成的人工智能语音。遇到事情，先让自己静下来，再慢慢找到解决的方法。")
    args = parser.parse_args()
    base = args.url.rstrip("/")
    with urlopen(base + "/health", timeout=10) as response:
        if not json.load(response).get("ready"):
            raise RuntimeError("Model is not ready")
    started = time.perf_counter()
    synthesize(args.text, args.output, base + "/v1/audio/speech", 1.0, os.getenv("TTS_API_KEY"), timeout=1200)
    elapsed = time.perf_counter() - started
    with wave.open(str(args.output)) as audio:
        duration = audio.getnframes() / audio.getframerate()
        result = {
            "text": args.text,
            "audio_file": str(args.output.resolve()),
            "sample_rate": audio.getframerate(),
            "audio_seconds": round(duration, 3),
            "request_seconds": round(elapsed, 3),
            "rtf": round(elapsed / duration, 3),
            "note": "Request time excludes service startup; audio is AI-generated.",
        }
    args.output.with_suffix(".json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
