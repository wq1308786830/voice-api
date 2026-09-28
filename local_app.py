"""Offline deployment entry point for the pinned CosyVoice / wetext runtime."""

import importlib

from app import _load_backend, _required_path, create_app


def load_local_backend():
    root = _required_path("WETEXT_MODEL_DIR", directory=True)
    for language in ("en", "zh"):
        for name in ("tagger.fst", "verbalizer.fst"):
            path = root / language / "tn" / name
            if not path.is_file() or path.stat().st_size == 0:
                raise RuntimeError(f"Missing local wetext asset: {path}")

    wetext = importlib.import_module("wetext.wetext")
    original = wetext.snapshot_download

    def local_snapshot(model_id, *args, **kwargs):
        if model_id != "pengzhendong/wetext":
            raise RuntimeError(f"Unexpected wetext model: {model_id}")
        return str(root)

    # wetext 0.0.4 has no offline environment switch. Limit this override to
    # its own resolver during the single-worker application's model startup.
    wetext.snapshot_download = local_snapshot
    try:
        model = _load_backend()
    finally:
        wetext.snapshot_download = original
    if model.frontend.text_frontend != "wetext":
        raise RuntimeError("Local wetext initialization failed")
    return model


app = create_app(backend_factory=load_local_backend)
