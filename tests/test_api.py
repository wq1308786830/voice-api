import io
import wave
from pathlib import Path
from urllib.error import HTTPError

import numpy as np
import pytest
from fastapi.testclient import TestClient

import client
from app import PROMPT_PREFIX, create_app


class Tensor:
    def __init__(self, values):
        self.values = np.array(values)

    def detach(self):
        return self

    def cpu(self):
        return self

    def numpy(self):
        return self.values


class Backend:
    sample_rate = 22050

    def __init__(self, segments=None):
        self.segments = segments if segments is not None else [[[0.0, 0.5]], [[-1.0, 1.5]]]
        self.calls = []

    def inference_zero_shot(self, text, prompt, wav, *, stream, speed):
        self.calls.append((text, prompt, wav, stream, speed))
        for item in self.segments:
            yield {"tts_speech": Tensor(item)}


@pytest.fixture
def backend():
    return Backend()


@pytest.fixture
def app(backend):
    return create_app(
        backend_factory=lambda: backend,
        reference_wav="reference.wav",
        reference_text="示例参考文本",
        api_key="secret",
    )


def post(http, **payload):
    return http.post(
        "/v1/audio/speech",
        json={"input": "  你好，世界！  ", **payload},
        headers={"Authorization": "Bearer secret"},
    )


def test_wav_uses_model_sample_rate_and_all_segments(app, backend):
    with TestClient(app) as http:
        assert http.get("/health").json() == {"ready": True}
        response = post(http, speed=0.8)
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    with wave.open(io.BytesIO(response.content), "rb") as wav:
        assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth(), wav.getnframes()) == (22050, 1, 2, 4)
        assert np.frombuffer(wav.readframes(4), dtype="<i2").tolist() == [0, 16384, -32767, 32767]
    assert backend.calls == [("你好，世界！", PROMPT_PREFIX + "示例参考文本", "reference.wav", False, 0.8)]


@pytest.mark.parametrize(
    "payload",
    [
        {"input": "   "},
        {"input": "中" * 5001},
        {"input": 123},
        {"speed": 0.49},
        {"speed": 2.01},
        {"speed": "fast"},
        {"voice": "another"},
        {"response_format": "mp3"},
        {"unsupported": 1},
    ],
)
def test_rejects_invalid_requests(app, backend, payload):
    with TestClient(app) as http:
        assert post(http, **payload).status_code == 422
    assert backend.calls == []


def test_auth_busy_and_failure(app, backend):
    with TestClient(app) as http:
        assert http.post("/v1/audio/speech", json={"input": "你好"}).status_code == 401
        app.state.api_key = "密钥"
        assert post(http).status_code == 401
        app.state.api_key = "secret"
        app.state.lock.acquire()
        try:
            response = post(http)
            assert response.status_code == 429
            assert response.headers["retry-after"] == "1"
            assert http.get("/health").status_code == 200
        finally:
            app.state.lock.release()
        backend.segments = [[[float("nan")]]]
        response = post(http)
        assert response.status_code == 500
        assert response.json() == {"detail": "Synthesis failed"}
        backend.segments = []
        assert post(http).status_code == 500


def test_reference_text_reads_windows_bom(tmp_path, monkeypatch, backend):
    wav = tmp_path / "reference.wav"
    wav.write_bytes(b"reference")
    transcript = tmp_path / "reference.txt"
    transcript.write_text("\ufeff示例文本", encoding="utf-8")
    monkeypatch.setenv("REFERENCE_WAV", str(wav))
    monkeypatch.setenv("REFERENCE_TEXT_FILE", str(transcript))
    app = create_app(backend_factory=lambda: backend)
    with TestClient(app) as http:
        assert http.post("/v1/audio/speech", json={"input": "你好"}).status_code == 200
    assert backend.calls[0][1] == PROMPT_PREFIX + "示例文本"


def test_client_preserves_output_on_http_error(tmp_path, monkeypatch):
    output = tmp_path / "result.wav"
    output.write_bytes(b"original")

    def fail(*_args, **_kwargs):
        raise HTTPError("http://localhost", 500, "failure", None, None)

    monkeypatch.setattr(client.urllib.request, "urlopen", fail)
    with pytest.raises(RuntimeError, match="HTTP 500"):
        client.synthesize("你好", output, "http://localhost/v1/audio/speech", 1.0, None)
    assert output.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [output]


def test_client_rejects_non_wav(tmp_path, monkeypatch):
    class Response:
        headers = type("Headers", (), {"get_content_type": lambda self: "audio/wav"})()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def read(self):
            return b"not a wave"

    monkeypatch.setattr(client.urllib.request, "urlopen", lambda *_args, **_kwargs: Response())
    output = tmp_path / "result.wav"
    with pytest.raises(RuntimeError, match="invalid WAV"):
        client.synthesize("你好", output, "http://localhost/v1/audio/speech", 1.0, None)
    assert not output.exists()
