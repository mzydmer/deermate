#!/usr/bin/env python3
"""Convert a fresh synthetic single-host bundle to a network-isolated Fake fixture."""

import argparse
import json
import re
import secrets
import shutil
from pathlib import Path

import yaml

from deermate.tooling import runtime_config

ROOT = Path(__file__).resolve().parents[1]


def prepare(bundle):
    info = json.loads((bundle / "bundle.json").read_text())
    if (
        not re.fullmatch(r"deermate-[a-z0-9-]+-(check|fixture)", info["project"])
        or info["port"] == 2026
        or info["worker_enabled"]
        or info["models_preconfigured"]
        or (bundle / "owner.json").exists()
    ):
        raise ValueError("Use a fresh named synthetic bundle; personal deployments are refused")
    config_path = bundle / "runtime/config.yaml"
    config = yaml.safe_load(config_path.read_text())
    if config.get("models") or config["extensions"].get("mcpServers"):
        raise ValueError("The fixture cannot contain models or Worker credentials")
    additions = runtime_config()
    for key in ("tools", "tool_groups", "plugins"):
        config[key] = additions[key]
    config["extensions"]["middlewares"] = additions["extensions"]["middlewares"]
    middlewares = config["extensions"]["middlewares"]
    index = middlewares.index("deermate.continuous_middleware:ContinuousMiddleware")
    middlewares[index] = "continuous_fixture_model:FixtureMiddleware"
    config["plugins"][0]["use"] = "continuous_fixture_model:install"
    config["models"] = [
        {
            "name": "continuous-fixture",
            "model": "offline-only",
            "use": "continuous_fixture_model:FixtureModel",
            "supports_thinking": False,
        }
    ]
    config_path.write_text(yaml.safe_dump(config, sort_keys=False))
    shutil.copyfile(
        ROOT / "tests/continuous_fixture_model.py", bundle / "runtime/continuous_fixture_model.py"
    )
    path = bundle / "compose.yaml"
    compose = yaml.safe_load(path.read_text())
    compose["services"]["control"]["environment"]["DEERMATE_CONTINUOUS_ENABLED"] = "true"
    compose["services"]["gateway"]["environment"]["PYTHONPATH"] = "/etc/deermate:/app/backend"
    compose["networks"] = {"default": {"internal": True}, "edge": {}}
    compose["services"]["nginx"]["networks"] = ["default", "edge"]
    path.write_text(yaml.safe_dump(compose, sort_keys=False))
    owner = bundle / "owner.json"
    owner.write_text(
        json.dumps(
            {"email": "continuous-fixture@example.com", "password": secrets.token_urlsafe(24)}
        )
    )
    owner.chmod(0o600)
    info.update(fixture_profile="continuous-v1", models_preconfigured=True)
    (bundle / "bundle.json").write_text(json.dumps(info, indent=2) + "\n")
    print("Prepared isolated continuous fixture; no real Provider or Native credentials")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    prepare(parser.parse_args().bundle.resolve())
