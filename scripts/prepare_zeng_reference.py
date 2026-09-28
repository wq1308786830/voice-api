"""Reproduce the speech-only excerpt from the preserved CCTV reference."""

from pathlib import Path
import wave

import numpy as np


def main():
    root = Path(__file__).resolve().parents[1] / "reference"
    with wave.open(str(root / "reference.wav"), "rb") as source:
        assert (source.getframerate(), source.getnchannels(), source.getsampwidth()) == (24000, 1, 2)
        samples = np.frombuffer(source.readframes(source.getnframes()), dtype="<i2")
    # VAD plus transcript review: exclude the leading background and the next
    # utterance at the very end, retaining roughly 100 ms around the target speech.
    samples = samples[round(2.9 * 24000):round(8.14 * 24000)].copy()
    # A 5 ms edge fade prevents a click without fading the actual syllables.
    fade = np.linspace(0, 1, 120)
    samples[:120] = np.rint(samples[:120] * fade).astype("<i2")
    samples[-120:] = np.rint(samples[-120:] * fade[::-1]).astype("<i2")
    with wave.open(str(root / "zeng_voice.wav"), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(24000)
        target.writeframes(samples.tobytes())
    (root / "zeng_voice.txt").write_text(
        (root / "reference.txt").read_text(encoding="utf-8-sig").strip() + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
