import io
import sys
import threading
import types
import wave

import numpy as np
import pytest
from fastapi.testclient import TestClient

import mac_app
from app import create_app


class FakeModel:
    sample_rate = 24000

    def __init__(self, events, *, output_rate=24000):
        self.events = events
        self.output_rate = output_rate

    def generate(self, **kwargs):
        self.events.append(("generate", threading.get_ident(), kwargs))
        for audio in ([0.0, 0.5, -0.5, 1.0], [0.25, -0.25]):
            yield types.SimpleNamespace(audio=np.array(audio, dtype=np.float32), sample_rate=self.output_rate)

    def close(self):
        self.events.append(("close", threading.get_ident()))


def make_backend(tmp_path, monkeypatch, events, *, model=None, reference_loader=None):
    monkeypatch.setattr(mac_app, "_check_platform", lambda: object())
    reference = tmp_path / "reference.wav"
    reference.write_bytes(b"reference")
    tokenizer = tmp_path / "s3"
    tokenizer.mkdir()
    (tokenizer / "model.safetensors").write_bytes(b"weights")
    model = model or FakeModel(events)

    def load_model(_model_dir, _tokenizer_dir, _mx):
        events.append(("load", threading.get_ident()))
        return model

    def load_reference(path, sample_rate):
        events.append(("reference", threading.get_ident(), path, sample_rate))
        return np.zeros(24000, dtype=np.float32)

    backend = mac_app.MacBackend(
        tmp_path, tokenizer, reference, model_loader=load_model,
        reference_loader=reference_loader or load_reference,
    )
    return backend, reference


def test_full_http_wav_and_single_worker_thread(tmp_path, monkeypatch):
    events = []
    backend, reference = make_backend(tmp_path, monkeypatch, events)
    app = create_app(
        backend_factory=lambda: backend,
        reference_wav=str(reference),
        reference_text="准确逐字稿",
    )
    with TestClient(app) as http:
        assert http.get("/health").json() == {"ready": True}
        response = http.post("/v1/audio/speech", json={"input": "你好", "speed": 1.0})
    assert response.status_code == 200
    with wave.open(io.BytesIO(response.content), "rb") as wav:
        assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth(), wav.getnframes()) == (24000, 1, 2, 6)
    work_events = [event for event in events if event[0] in {"load", "reference", "generate", "close"}]
    assert [event[0] for event in work_events] == ["load", "reference", "generate", "close"]
    assert len({event[1] for event in work_events}) == 1
    generate_kwargs = work_events[2][2]
    assert generate_kwargs["text"] == "你好"
    assert generate_kwargs["ref_text"] == "准确逐字稿"
    assert generate_kwargs["stream"] is False
    assert generate_kwargs["verbose"] is False
    assert generate_kwargs["ref_audio"].shape == (24000,)


def test_speed_change_stretches_combined_audio(tmp_path, monkeypatch):
    events = []
    backend, reference = make_backend(tmp_path, monkeypatch, events)
    calls = []

    def stretch(audio, *, rate):
        calls.append((audio.copy(), rate, threading.get_ident()))
        return audio[::2]

    monkeypatch.setitem(sys.modules, "librosa", types.SimpleNamespace(effects=types.SimpleNamespace(time_stretch=stretch)))
    try:
        output = backend.inference_zero_shot("你好", mac_app.PROMPT_PREFIX + "逐字稿", reference, speed=1.5)
        assert len(output) == 1
        assert output[0]["tts_speech"].shape == (3,)
        assert calls[0][0].shape == (6,)
        assert calls[0][1] == 1.5
        assert calls[0][2] == events[0][1]
    finally:
        backend.close()


def test_alternating_references_keep_audio_and_transcript_paired_on_worker(tmp_path, monkeypatch):
    events = []
    loaded = {}

    def load_reference(path, sample_rate):
        events.append(("reference", threading.get_ident(), path, sample_rate))
        audio = np.full(24000, len(loaded) + 1, dtype=np.float32)
        loaded[path] = audio
        return audio

    backend, first = make_backend(tmp_path, monkeypatch, events, reference_loader=load_reference)
    second = tmp_path / "academic.wav"
    second.write_bytes(b"other reference")
    requests = [(first, "曾仕强逐字稿"), (second, "学术音色逐字稿"),
                (first, "曾仕强逐字稿"), (second, "更新的学术逐字稿")]
    try:
        for path, transcript in requests:
            backend.inference_zero_shot("待生成文案", mac_app.PROMPT_PREFIX + transcript, path)
        generate_events = [event for event in events if event[0] == "generate"]
        for event, (path, transcript) in zip(generate_events, requests, strict=True):
            assert event[2]["ref_audio"] is loaded[path.resolve()]
            assert event[2]["ref_text"] == transcript
        assert [event[2] for event in events if event[0] == "reference"] == [first.resolve(), second.resolve()]
        assert len([event for event in events if event[0] == "load"]) == 1
    finally:
        backend.close()
    backend.close()
    assert len({event[1] for event in events}) == 1
    assert len([event for event in events if event[0] == "close"]) == 1
    assert not backend._reference_cache
    with pytest.raises(RuntimeError, match="closed"):
        backend.inference_zero_shot("待生成文案", mac_app.PROMPT_PREFIX + "逐字稿", first)


def test_failed_reference_load_is_not_cached_and_other_voice_still_works(tmp_path, monkeypatch):
    events = []
    attempts = []

    def load_reference(path, sample_rate):
        attempts.append(path)
        if path.name == "missing.wav":
            raise ValueError("invalid reference audio")
        return np.zeros(sample_rate, dtype=np.float32)

    backend, reference = make_backend(tmp_path, monkeypatch, events, reference_loader=load_reference)
    missing = tmp_path / "missing.wav"
    try:
        for _ in range(2):
            with pytest.raises(ValueError, match="invalid reference audio"):
                backend.inference_zero_shot("你好", mac_app.PROMPT_PREFIX + "逐字稿", missing)
        assert attempts.count(missing.resolve()) == 2
        assert backend.inference_zero_shot("你好", mac_app.PROMPT_PREFIX + "逐字稿", reference)
    finally:
        backend.close()


def test_output_rate_mismatch_rejected_and_worker_remains_usable(tmp_path, monkeypatch):
    events = []
    model = FakeModel(events, output_rate=16000)
    backend, reference = make_backend(tmp_path, monkeypatch, events, model=model)
    try:
        with pytest.raises(ValueError, match="sample rate changed"):
            backend.inference_zero_shot("你好", mac_app.PROMPT_PREFIX + "逐字稿", reference)
        model.output_rate = 24000
        assert backend.inference_zero_shot("你好", mac_app.PROMPT_PREFIX + "逐字稿", reference)
    finally:
        backend.close()


def test_startup_failure_closes_model_on_worker(tmp_path, monkeypatch):
    events = []
    model = FakeModel(events)
    model.sample_rate = 16000
    with pytest.raises(RuntimeError, match="24000 Hz"):
        make_backend(tmp_path, monkeypatch, events, model=model)
    assert [event[0] for event in events] == ["load", "close"]
    assert events[0][1] == events[1][1]


def test_reference_loader_resamples_mono_audio(tmp_path, monkeypatch):
    source = tmp_path / "reference.wav"
    source.write_bytes(b"wav")
    calls = []

    def read(path, *, dtype):
        calls.append((path, dtype))
        return np.ones(16000, dtype=np.float32), 16000

    def resample(audio, *, orig_sr, target_sr):
        calls.append((orig_sr, target_sr))
        return np.ones(24000, dtype=np.float32)

    monkeypatch.setitem(sys.modules, "soundfile", types.SimpleNamespace(read=read))
    monkeypatch.setitem(sys.modules, "librosa", types.SimpleNamespace(resample=resample))
    output = mac_app._load_reference(source, 24000)
    assert output.shape == (24000,)
    assert calls == [(str(source), "float32"), (16000, 24000)]


def test_rejects_non_apple_platform(monkeypatch):
    monkeypatch.setattr(mac_app.sys, "platform", "win32")
    with pytest.raises(RuntimeError, match="macOS on Apple Silicon"):
        mac_app._check_platform()


def test_local_s3_weights_are_loaded_without_upstream_downloader(tmp_path, monkeypatch):
    calls = []
    model = types.SimpleNamespace(
        model_type=lambda: "cosyvoice3",
        _ensure_model_loaded=lambda: calls.append("model_ready"),
        _ensure_tokenizers_loaded=lambda: calls.append("tokenizers_ready"),
        _model=types.SimpleNamespace(parameters=lambda: "tts_parameters"),
        _speaker_encoder=types.SimpleNamespace(model=types.SimpleNamespace(parameters=lambda: "speaker_parameters")),
    )

    class S3:
        def __init__(self, name):
            calls.append(("s3", name))

        def load_weights(self, weights):
            calls.append(("weights", weights))

        def parameters(self):
            return "parameters"

        @classmethod
        def from_pretrained(cls, *_args, **_kwargs):
            pytest.fail("network-capable upstream downloader must not be called")

    def package(name):
        module = types.ModuleType(name)
        module.__path__ = []
        return module

    for name in ("mlx_audio", "mlx_audio.codec", "mlx_audio.codec.models", "mlx_audio.tts"):
        monkeypatch.setitem(sys.modules, name, package(name))
    s3_module = types.ModuleType("mlx_audio.codec.models.s3tokenizer")
    s3_module.S3TokenizerV3 = S3
    monkeypatch.setitem(sys.modules, s3_module.__name__, s3_module)
    utils_module = types.ModuleType("mlx_audio.tts.utils")
    utils_module.load_model = lambda path: model
    monkeypatch.setitem(sys.modules, utils_module.__name__, utils_module)
    mx = types.SimpleNamespace(
        load=lambda path, *, format: {"weight": np.array([1.0])},
        eval=lambda value: calls.append(("eval", value)),
    )
    result = mac_app._load_model(tmp_path, tmp_path, mx)
    assert result is model
    assert isinstance(model._s3_tokenizer, S3)
    assert calls[0] == ("s3", "speech_tokenizer_v3")
    assert calls[1][0] == "weights"
    assert calls[2:] == [("eval", "parameters"), "model_ready", "tokenizers_ready",
                         ("eval", "tts_parameters"), ("eval", "speaker_parameters")]
