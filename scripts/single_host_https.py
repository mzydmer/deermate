"""Opt in an existing portable bundle to public IP HTTPS; never starts services."""

import argparse
import ipaddress
from pathlib import Path

import yaml

CADDY_IMAGE = "caddy@sha256:5e5286cb37d44086d651a5363f05f43a692ce4d649d88fb1bd844579f45fa9e8"


def configure(bundle: Path, public_ip: str) -> None:
    address = ipaddress.ip_address(public_ip)
    if address.version != 4 or not address.is_global:
        raise ValueError("Use the assigned public IPv4 address of this deployment")
    source = bundle / "compose.yaml"
    original = source.read_text()
    config = yaml.safe_load(original)
    services = config["services"]
    if "edge" in services or (bundle / "compose.before-https.yaml").exists():
        raise ValueError("HTTPS already configured: inspect before changing or replaying")
    if services["nginx"].get("ports") != ["127.0.0.1:2027:2026"]:
        raise ValueError("Expected the private single-host nginx listener on loopback 2027")
    env = services["control"]["environment"]
    if env.get("DEERMATE_ORIGIN") != "http://localhost:2027":
        raise ValueError("Unexpected existing origin: inspect before modifying")
    env["DEERMATE_ORIGIN"] = f"https://{address}"
    env["DEERMATE_ALLOWED_HOSTS"] = (
        f"{address},{address}:443,localhost:2027,127.0.0.1:2027,"
        "nginx:2026,127.0.0.1:8080,control:8080"
    )
    services["edge"] = {
        "image": CADDY_IMAGE,
        "pull_policy": "never",
        "network_mode": "host",
        "user": "0:0",
        "cap_drop": ["ALL"],
        "cap_add": ["NET_BIND_SERVICE"],
        "security_opt": ["no-new-privileges:true"],
        "read_only": True,
        "restart": "unless-stopped",
        "depends_on": {"nginx": {"condition": "service_healthy"}},
        "volumes": [
            "./edge/Caddyfile:/etc/caddy/Caddyfile:ro",
            "edge-data:/data",
            "edge-config:/config",
        ],
        "tmpfs": ["/tmp:size=16m,noexec,nosuid,nodev"],
        "mem_limit": "128m",
        "memswap_limit": "128m",
        "cpus": 0.2,
        "pids_limit": 64,
        "logging": {"driver": "json-file", "options": {"max-size": "10m", "max-file": "3"}},
    }
    config["volumes"].update({"edge-data": None, "edge-config": None})
    caddyfile = f"""{{
    admin 127.0.0.1:2019
    default_sni {address}
    servers {{
        protocols h1 h2
    }}
}}

https://{address}, :443 {{
    bind 0.0.0.0
    @unknown_host not host {address}
    respond @unknown_host 421
    tls {{
        issuer acme {{
            dir https://acme-v02.api.letsencrypt.org/directory
            profile shortlived
        }}
    }}
    reverse_proxy 127.0.0.1:2027 {{
        flush_interval -1
    }}
}}
"""
    edge = bundle / "edge"
    edge.mkdir(mode=0o700)
    (edge / "Caddyfile").write_text(caddyfile)
    (edge / "Caddyfile").chmod(0o644)  # Nonsecret; readable by the capability-limited edge.
    backup = bundle / "compose.before-https.yaml"
    backup.write_text(original)
    backup.chmod(0o600)
    source.write_text(yaml.safe_dump(config, sort_keys=False))
    source.chmod(0o600)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--public-ip", required=True)
    args = parser.parse_args()
    configure(args.bundle, args.public_ip)
    print("Prepared HTTPS files. Migrate the owner database before starting the public edge.")


if __name__ == "__main__":
    main()
