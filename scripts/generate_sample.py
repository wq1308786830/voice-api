"""Generate an AI-labelled sample using the official CosyVoice3 Space."""

import argparse
from pathlib import Path
import shutil
import wave

from gradio_client import Client, handle_file


ROOT = Path(__file__).resolve().parents[1]
SPACE = "FunAudioLLM/Fun-CosyVoice3-0.5B"
AI_NOTICE = "这是一段人工智能合成的声音示例。"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=ROOT / "reference/reference.wav")
    parser.add_argument("--transcript", type=Path, default=ROOT / "reference/reference.txt")
    parser.add_argument("--text-file", type=Path, default=ROOT / "samples/试听文案.txt")
    parser.add_argument("--output", type=Path, default=ROOT / "generated/ai-sample.wav")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    transcript = args.transcript.read_text(encoding="utf-8-sig").strip()
    text = args.text_file.read_text(encoding="utf-8-sig").strip()
    if not transcript or not text:
        parser.error("reference transcript and input text must not be empty")
    if not text.startswith(AI_NOTICE):
        text = AI_NOTICE + text
    if len(text) > 200:
        parser.error("input including the AI notice must not exceed 200 characters")
    with wave.open(str(args.reference), "rb") as reference:
        if reference.getframerate() < 16000 or not 0 < reference.getnframes() / reference.getframerate() <= 10:
            parser.error("reference must be a nonempty WAV at >=16 kHz and at most 10 seconds")

    cache = ROOT / ".cache/cosyvoice"
    cache.mkdir(parents=True, exist_ok=True)
    client = Client(SPACE, verbose=False, download_files=str(cache))
    result = client.predict(
        tts_text=text,
        mode_value="zero_shot",
        prompt_text=transcript,
        prompt_wav_upload=handle_file(str(args.reference.resolve())),
        prompt_wav_record=None,
        # Gradio validates this dropdown even though zero_shot mode ignores it.
        instruct_text="You are a helpful assistant. 请用尽可能慢地语速说一句话。<|endofprompt|>",
        seed=args.seed,
        stream=False,
        ui_lang="Zh",
        api_name="/generate_audio",
    )
    source = Path(result)
    with wave.open(str(source), "rb") as audio:
        if not audio.getnframes():
            raise RuntimeError("The service returned empty audio")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, args.output)
    print(args.output.resolve())


if __name__ == "__main__":
    main()
