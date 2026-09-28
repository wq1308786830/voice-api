from types import SimpleNamespace

import pytest

import local_app


@pytest.fixture
def wetext_assets(tmp_path, monkeypatch):
    for language in ("en", "zh"):
        folder = tmp_path / language / "tn"
        folder.mkdir(parents=True)
        for name in ("tagger.fst", "verbalizer.fst"):
            (folder / name).write_bytes(b"fst")
    monkeypatch.setenv("WETEXT_MODEL_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def fake_wetext(monkeypatch):
    def original_resolver(*_args, **_kwargs):
        raise AssertionError("original resolver should not be called during startup")

    wetext = SimpleNamespace(snapshot_download=original_resolver)

    def import_module(name):
        assert name == "wetext.wetext"
        return wetext

    monkeypatch.setattr(local_app.importlib, "import_module", import_module)
    return wetext, original_resolver


def test_missing_fst_stops_before_model_load(tmp_path, monkeypatch):
    monkeypatch.setenv("WETEXT_MODEL_DIR", str(tmp_path))

    def forbidden_load():
        pytest.fail("model must not load when an FST is missing")

    monkeypatch.setattr(local_app, "_load_backend", forbidden_load)
    with pytest.raises(RuntimeError, match="Missing local wetext asset"):
        local_app.load_local_backend()


def test_resolver_only_serves_local_wetext_during_model_load(
    wetext_assets, fake_wetext, monkeypatch
):
    wetext, original_resolver = fake_wetext
    model = SimpleNamespace(frontend=SimpleNamespace(text_frontend="wetext"))

    def load():
        assert wetext.snapshot_download("pengzhendong/wetext", revision="pinned") == str(wetext_assets)
        with pytest.raises(RuntimeError, match="Unexpected wetext model"):
            wetext.snapshot_download("somebody/other-model")
        return model

    monkeypatch.setattr(local_app, "_load_backend", load)
    assert local_app.load_local_backend() is model
    assert wetext.snapshot_download is original_resolver


def test_resolver_restored_when_model_load_raises(wetext_assets, fake_wetext, monkeypatch):
    wetext, original_resolver = fake_wetext

    def load():
        assert wetext.snapshot_download("pengzhendong/wetext") == str(wetext_assets)
        raise RuntimeError("model loading failed")

    monkeypatch.setattr(local_app, "_load_backend", load)
    with pytest.raises(RuntimeError, match="model loading failed"):
        local_app.load_local_backend()
    assert wetext.snapshot_download is original_resolver


def test_silent_wetext_disable_is_rejected(wetext_assets, fake_wetext, monkeypatch):
    wetext, original_resolver = fake_wetext
    model = SimpleNamespace(frontend=SimpleNamespace(text_frontend="none"))
    monkeypatch.setattr(local_app, "_load_backend", lambda: model)
    with pytest.raises(RuntimeError, match="Local wetext initialization failed"):
        local_app.load_local_backend()
    assert wetext.snapshot_download is original_resolver
