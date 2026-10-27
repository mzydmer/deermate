"""Initialize fresh named volumes without changing an existing account or MCP seed."""

import os
from pathlib import Path

os.umask(0o077)
for name, uid in [("/home", 1000), ("/frontend-cache", 1000), ("/nginx-cache", 101)]:
    path = Path(name)
    os.chown(path, uid, uid)
    path.chmod(0o700)
extensions = Path("/home/extensions_config.json")
if not extensions.exists():
    extensions.write_bytes(Path("/stage/extensions_config.json").read_bytes())
    extensions.chmod(0o600)
    os.chown(extensions, 1000, 1000)
