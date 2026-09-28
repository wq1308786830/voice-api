"""Download only the pinned MLX weights and tokenizer needed by this service."""

import json
import sys
from pathlib import Path

from huggingface_hub import snapshot_download


def main():
    root = Path(__file__).resolve().parents[1]
    runtime = Path(sys.argv[1]).resolve()
    manifest = json.loads((root / "mac-models.json").read_text(encoding="utf-8"))
    for name, asset in manifest.items():
        target = runtime / "models" / name
        snapshot_download(
            repo_id=asset["repo_id"],
            revision=asset["revision"],
            allow_patterns=asset["files"],
            local_dir=target,
            max_workers=2,
        )
        for filename in asset["files"]:
            path = target / filename
            if not path.is_file() or not path.stat().st_size:
                raise RuntimeError(f"Missing downloaded asset: {path}")
        print(f"Ready: {name} at {target}", flush=True)


if __name__ == "__main__":
    main()
