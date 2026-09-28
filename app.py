"""Small HTTP wrapper around a local CosyVoice3 zero-shot model."""

import hmac
import io
import logging
import os
import sys
import threading
import wave
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable

import numpy as np
from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, field_validator


LOG = logging.getLogger(__name__)
PROMPT_PREFIX = "You are a helpful assistant.<|endofprompt|>"


class SpeechRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    input: str
    voice: str = "default"
    speed: float = 1.0
    response_format: str = "wav"

    @field_validator("input")
    @classmethod
    def validate_input(cls, value: str) -> str:
        value = value.strip()
        if not value or len(value) > 5000:
            raise ValueError("input must contain 1 to 5000 characters after trimming")
        return value

    @field_validator("voice")
    @classmethod
    def validate_voice(cls, value: str) -> str:
        if value != "default":
            raise ValueError("only voice=default is supported")
        return value

    @field_validator("response_format")
    @classmethod
    def validate_format(cls, value: str) -> str:
        if value != "wav":
            raise ValueError("only response_format=wav is supported")
        return value

    @field_validator("speed")
    @classmethod
    def validate_speed(cls, value: float) -> float:
        if not 0.5 <= value <= 2.0:
            raise ValueError("speed must be between 0.5 and 2.0")
        return value


def _required_path(name: str, *, directory: bool) -> Path:
    raw = os.getenv(name)
    if not raw:
        raise RuntimeError(f"{name} must be set")
    path = Path(raw)
    if not path.is_absolute() or not (path.is_dir() if directory else path.is_file()):
        kind = "existing absolute directory" if directory else "existing absolute file"
        raise RuntimeError(f"{name} must name an {kind}")
    return path


def _load_backend():
    repo = _required_path("COSYVOICE_REPO", directory=True)
    model_dir = _required_path("COSYVOICE_MODEL_DIR", directory=True)
    for path in (repo, repo / "third_party" / "Matcha-TTS"):
        if not path.is_dir():
            raise RuntimeError("COSYVOICE_REPO is missing third_party/Matcha-TTS")
        sys.path.insert(0, str(path))
    from cosyvoice.cli.cosyvoice import AutoModel

    model = AutoModel(model_dir=str(model_dir))
    if model.__class__.__name__ != "CosyVoice3":
        raise RuntimeError("COSYVOICE_MODEL_DIR must contain a CosyVoice3 model")
    return model


def _wav_bytes(segments, sample_rate: int) -> bytes:
    if not isinstance(sample_rate, int) or sample_rate <= 0:
        raise ValueError("invalid model sample rate")
    samples = []
    for segment in segments:
        tensor = segment["tts_speech"]
        array = tensor if isinstance(tensor, np.ndarray) else np.asarray(tensor.detach().cpu().numpy())
        if array.ndim == 2 and array.shape[0] == 1:
            array = array[0]
        if array.ndim != 1 or not array.size or not np.issubdtype(array.dtype, np.floating):
            raise ValueError("invalid model audio shape")
        if not np.isfinite(array).all():
            raise ValueError("nonfinite model audio")
        pcm = np.rint(np.clip(array, -1.0, 1.0) * 32767).astype("<i2")
        samples.append(pcm.tobytes())
    if not samples:
        raise ValueError("model returned no audio")
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"".join(samples))
    return output.getvalue()


def create_app(
    *,
    backend_factory: Callable | None = None,
    reference_wav: str | None = None,
    reference_text: str | None = None,
    api_key: str | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        wav = reference_wav or str(_required_path("REFERENCE_WAV", directory=False))
        if reference_text is None:
            transcript_path = _required_path("REFERENCE_TEXT_FILE", directory=False)
            transcript = transcript_path.read_text(encoding="utf-8-sig").strip()
        else:
            transcript = reference_text.strip()
        if not transcript:
            raise RuntimeError("reference transcript must not be empty")
        app.state.reference_wav = wav
        app.state.prompt_text = PROMPT_PREFIX + transcript
        app.state.api_key = api_key if api_key is not None else os.getenv("TTS_API_KEY")
        app.state.lock = threading.Lock()
        app.state.model = (backend_factory or _load_backend)()
        try:
            yield
        finally:
            try:
                close = getattr(app.state.model, "close", None)
                if close is not None:
                    close()
            finally:
                del app.state.model

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health")
    async def health():
        return {"ready": True}

    @app.post("/v1/audio/speech")
    def speech(request: SpeechRequest, authorization: str | None = Header(default=None)):
        expected = app.state.api_key
        if expected and not hmac.compare_digest(
            (authorization or "").encode("utf-8"), f"Bearer {expected}".encode("utf-8")
        ):
            raise HTTPException(status_code=401, detail="Unauthorized", headers={"WWW-Authenticate": "Bearer"})
        if not app.state.lock.acquire(blocking=False):
            raise HTTPException(status_code=429, detail="Synthesis busy", headers={"Retry-After": "1"})
        try:
            model = app.state.model
            audio = _wav_bytes(
                model.inference_zero_shot(
                    request.input,
                    app.state.prompt_text,
                    app.state.reference_wav,
                    stream=False,
                    speed=request.speed,
                ),
                model.sample_rate,
            )
            return Response(content=audio, media_type="audio/wav")
        except Exception:
            LOG.exception("CosyVoice synthesis failed")
            raise HTTPException(status_code=500, detail="Synthesis failed") from None
        finally:
            app.state.lock.release()

    return app


app = create_app()
