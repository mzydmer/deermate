"""Prepare verified public BPE data in a test image; never invokes a model."""

import hashlib
import importlib.metadata
import json
import os
import urllib.request
from pathlib import Path

metadata = json.loads(Path("/tmp/tokenizer-cache.json").read_text())
if importlib.metadata.version(metadata["package"]) != metadata["version"]:
    raise RuntimeError("Review the changed tokenizer dependency before rebuilding this fixture")
with urllib.request.urlopen(metadata["url"], timeout=30) as source:
    data = source.read(4 * 1024 * 1024 + 1)
if len(data) > 4 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != metadata["sha256"]:
    raise RuntimeError("Official tokenizer artifact checksum mismatch")
root = Path(os.environ["TIKTOKEN_CACHE_DIR"])
root.mkdir(parents=True, mode=0o755, exist_ok=True)
path = root / hashlib.sha1(metadata["url"].encode()).hexdigest()
path.write_bytes(data)
path.chmod(0o644)
print(
    json.dumps(
        {
            "encoding": metadata["encoding"],
            "sha256": metadata["sha256"],
            "bytes": len(data),
            "model_requests": 0,
        }
    )
)
