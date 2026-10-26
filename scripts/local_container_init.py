"""Initialize only the local Compose profile's named volumes and staged keys."""

import os
from pathlib import Path


def main():
    os.umask(0o077)
    for name, owner in [("/home", 1000), ("/frontend-cache", 1000), ("/nginx-cache", 101)]:
        path = Path(name)
        os.chown(path, owner, owner)
        path.chmod(0o700)
    target = Path("/worker-credentials")
    os.chown(target, 1000, 1000)
    target.chmod(0o700)
    for name in ("client.key", "known_hosts", "api.token"):
        path = target / name
        path.write_bytes((Path("/stage/credentials") / name).read_bytes())
        path.chmod(0o600)
        os.chown(path, 1000, 1000)


if __name__ == "__main__":
    main()
