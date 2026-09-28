"""Cross-platform standard-library client for the local TTS HTTP API."""

import argparse
import io
import json
import math
import os
import sys
import tempfile
import urllib.error
import urllib.request
import wave
from pathlib import Path


def synthesize(
    input_text: str, output: Path, url: str, speed: float, api_key: str | None, timeout: float = 600
) -> None:
    payload = json.dumps(
        {"input": input_text, "voice": "default", "speed": speed, "response_format": "wav"},
        ensure_ascii=False,
    ).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.headers.get_content_type() != "audio/wav":
                raise RuntimeError("server did not return audio/wav")
            audio = response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"server returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"connection failed: {exc.reason}") from exc
    try:
        with wave.open(io.BytesIO(audio), "rb") as wav:
            if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getnframes() == 0:
                raise wave.Error("unsupported or empty WAV")
            if len(wav.readframes(wav.getnframes())) != wav.getnframes() * 2:
                raise wave.Error("truncated WAV")
    except (EOFError, wave.Error) as exc:
        raise RuntimeError("server returned invalid WAV data") from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, suffix=".wav", delete=False) as file:
            temporary = Path(file.name)
            file.write(audio)
        os.replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate WAV speech with a CosyVoice3 API")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="Chinese text to speak")
    source.add_argument("--text-file", type=Path, help="UTF-8 text file to speak")
    parser.add_argument("--output", required=True, type=Path, help="output WAV path")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="API base URL")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=600, help="request timeout in seconds")
    parser.add_argument("--api-key", default=os.getenv("TTS_API_KEY"))
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be a positive finite number")
    try:
        input_text = args.text if args.text is not None else args.text_file.read_text(encoding="utf-8-sig")
        synthesize(
            input_text,
            args.output,
            args.url.rstrip("/") + "/v1/audio/speech",
            args.speed,
            args.api_key,
            args.timeout,
        )
    except (OSError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
