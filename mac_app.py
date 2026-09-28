"""Apple Silicon MLX entry point for the pinned CosyVoice3 conversion."""

import logging
import platform
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from app import PROMPT_PREFIX, _required_path, create_app


LOG = logging.getLogger(__name__)


def _check_platform():
    if sys.platform != "darwin" or platform.machine() != "arm64":
        raise RuntimeError("MLX CosyVoice3 requires macOS on Apple Silicon")
    import mlx.core as mx

    if not mx.metal.is_available():
        raise RuntimeError("MLX Metal backend is unavailable")
    mx.set_default_device(mx.gpu)
    return mx


def _load_reference(path: Path, sample_rate: int) -> np.ndarray:
    import soundfile as sf

    audio, source_rate = sf.read(str(path), dtype="float32")
    if audio.ndim != 1 or not audio.size:
        raise ValueError("reference WAV must be nonempty mono audio")
    if source_rate != sample_rate:
        import librosa

        audio = librosa.resample(audio, orig_sr=source_rate, target_sr=sample_rate)
    if not np.isfinite(audio).all() or len(audio) > 30 * sample_rate:
        raise ValueError("reference WAV must be finite and no longer than 30 seconds")
    return np.asarray(audio, dtype=np.float32)


def _load_model(model_dir: Path, tokenizer_dir: Path, mx):
    from mlx_audio.codec.models.s3tokenizer import S3TokenizerV3
    from mlx_audio.tts.utils import load_model

    model = load_model(model_dir)
    if model.model_type() != "cosyvoice3":
        raise RuntimeError("MLX_MODEL_DIR must contain a CosyVoice3 model")
    weights = mx.load(str(tokenizer_dir / "model.safetensors"), format="safetensors")
    s3 = S3TokenizerV3("speech_tokenizer_v3")
    s3.load_weights(list(weights.items()))
    mx.eval(s3.parameters())
    model._s3_tokenizer = s3
    # This pinned wrapper defers loading until generate(); finish it before /health is ready.
    model._ensure_model_loaded()
    model._ensure_tokenizers_loaded()
    mx.eval(model._model.parameters())
    mx.eval(model._speaker_encoder.model.parameters())
    return model


class MacBackend:
    def __init__(
        self,
        model_dir: Path,
        tokenizer_dir: Path,
        reference_wav: Path,
        *,
        model_loader=_load_model,
        reference_loader=_load_reference,
    ):
        self.reference_wav = reference_wav.resolve()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mlx-cosyvoice3")
        self._closed = False
        self._model_loader = model_loader
        self._reference_loader = reference_loader
        try:
            self.sample_rate = self._executor.submit(self._initialize, model_dir, tokenizer_dir).result()
        except Exception:
            try:
                self.close()
            except Exception:
                LOG.exception("MLX backend cleanup failed after startup error")
            raise

    def _initialize(self, model_dir: Path, tokenizer_dir: Path) -> int:
        mx = _check_platform()
        if not (tokenizer_dir / "model.safetensors").is_file():
            raise RuntimeError("MLX_TOKENIZER_DIR is missing model.safetensors")
        self._model = self._model_loader(model_dir, tokenizer_dir, mx)
        sample_rate = self._model.sample_rate
        if type(sample_rate) is not int or sample_rate != 24000:
            raise RuntimeError("CosyVoice3 MLX model must use 24000 Hz audio")
        self._reference_audio = self._reference_loader(self.reference_wav, sample_rate)
        return sample_rate

    def inference_zero_shot(self, text, prompt_text, prompt_wav, *, stream=False, speed=1.0):
        if self._closed:
            raise RuntimeError("MLX backend is closed")
        return self._executor.submit(
            self._infer, text, prompt_text, prompt_wav, stream, speed
        ).result()

    def _infer(self, text, prompt_text, prompt_wav, stream, speed):
        if stream or Path(prompt_wav).resolve() != self.reference_wav:
            raise ValueError("unsupported stream mode or reference WAV")
        if not prompt_text.startswith(PROMPT_PREFIX):
            raise ValueError("missing CosyVoice3 reference prompt prefix")
        transcript = prompt_text[len(PROMPT_PREFIX) :]
        if not transcript:
            raise ValueError("reference transcript is empty")
        segments = []
        for result in self._model.generate(
            text=text,
            ref_audio=self._reference_audio,
            ref_text=transcript,
            stream=False,
            verbose=False,
        ):
            if result.sample_rate != self.sample_rate:
                raise ValueError("MLX output sample rate changed")
            audio = np.asarray(result.audio, dtype=np.float32)
            if audio.ndim != 1 or not audio.size or not np.isfinite(audio).all():
                raise ValueError("invalid MLX audio")
            segments.append(audio.copy())
        if not segments:
            raise ValueError("MLX model returned no audio")
        audio = np.concatenate(segments)
        if speed != 1.0:
            import librosa

            audio = librosa.effects.time_stretch(audio, rate=speed)
        if audio.ndim != 1 or not audio.size or not np.isfinite(audio).all():
            raise ValueError("invalid time-stretched audio")
        return [{"tts_speech": np.asarray(audio, dtype=np.float32)}]

    def _dispose(self):
        model = getattr(self, "_model", None)
        if model is not None:
            close = getattr(model, "close", None)
            if callable(close):
                close()
            del self._model
        if hasattr(self, "_reference_audio"):
            del self._reference_audio

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self._executor.submit(self._dispose).result()
        finally:
            self._executor.shutdown(wait=True)


def load_mac_backend():
    return MacBackend(
        _required_path("MLX_MODEL_DIR", directory=True),
        _required_path("MLX_TOKENIZER_DIR", directory=True),
        _required_path("REFERENCE_WAV", directory=False),
    )


app = create_app(backend_factory=load_mac_backend)
