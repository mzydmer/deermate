#!/usr/bin/env python3
"""Prepare generic OTLP configuration and verify ingestion without running an agent."""

import argparse
import json
import os
import re
import stat
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

ENV_KEYS = {
    "DEERMATE_TELEMETRY_ENABLED",
    "DEERMATE_TELEMETRY_ALLOW_INSECURE",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
    "OTEL_EXPORTER_OTLP_HEADERS",
    "OTEL_EXPORTER_OTLP_TRACES_HEADERS",
    "OTEL_SERVICE_NAME",
    "OTEL_RESOURCE_ATTRIBUTES",
    "OTEL_TRACES_SAMPLER",
    "OTEL_TRACES_SAMPLER_ARG",
}


def read_env(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_size > 65536:
        raise ValueError("Use a regular private environment file with mode 0600")
    result = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep or key.strip() not in ENV_KEYS:
            raise ValueError("Environment file contains an unsupported setting")
        value = value.strip()
        if value.startswith("'"):
            if len(value) < 2 or not value.endswith("'"):
                raise ValueError("Unclosed environment value")
            value = value[1:-1].replace("\\'", "'")
        elif value.startswith('"'):
            value = json.loads(value)
        if not isinstance(value, str) or "\n" in value or "\r" in value:
            raise ValueError("Environment values must be single-line strings")
        result[key.strip()] = value
    return result


def validate(values):
    endpoint = values.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
    if not endpoint:
        base = values.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").rstrip("/")
        endpoint = base + "/v1/traces" if base else ""
    url = urlsplit(endpoint)
    if not url.hostname or url.username or url.password or url.fragment or "replace" in endpoint:
        raise ValueError("Replace the endpoint placeholder with the console-provided OTLP endpoint")
    if url.scheme != "https" and not (
        url.scheme == "http"
        and (
            url.hostname in {"127.0.0.1", "localhost", "::1"}
            or values.get("DEERMATE_TELEMETRY_ALLOW_INSECURE") == "true"
        )
    ):
        raise ValueError("Non-local telemetry requires HTTPS")
    if values.get("DEERMATE_TELEMETRY_ENABLED") != "true":
        raise ValueError("Set DEERMATE_TELEMETRY_ENABLED=true for this profile")
    for key in ("OTEL_EXPORTER_OTLP_HEADERS", "OTEL_EXPORTER_OTLP_TRACES_HEADERS"):
        if "replace" in values.get(key, ""):
            raise ValueError("Replace the write-credential placeholder")
    return endpoint


def private_write(path, content, *, replace=False):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("Configuration destination must be a regular file")
    fd, temporary = tempfile.mkstemp(prefix=".deermate-telemetry-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as file:
            os.fchmod(file.fileno(), 0o600)
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def patch_mcp(path, values):
    """Operator-only configuration; preserve other servers, secrets and grants."""
    validate(values)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("MCP configuration must be a regular file")
    config = json.loads(path.read_text())
    if not isinstance(config, dict) or not isinstance(config.get("mcpServers", {}), dict):
        raise ValueError("Invalid MCP server configuration")
    updated = 0
    for server in config.get("mcpServers", {}).values():
        if not isinstance(server, dict):
            raise ValueError("Invalid MCP server configuration")
        args = server.get("args", [])
        if (
            server.get("type", "stdio") != "stdio"
            or not isinstance(args, list)
            or args[:2] != ["-m", "deermate.cli"]
            or args[-1:] != ["mcp"]
            or not re.fullmatch(r"python(?:3(?:\.\d+)?)?", Path(server.get("command", "")).name)
        ):
            continue
        env = server.setdefault("env", {})
        if not isinstance(env, dict):
            raise ValueError("Invalid MCP environment configuration")
        env.update({k: v for k, v in values.items() if k in ENV_KEYS})
        env["OTEL_SERVICE_NAME"] = "deermate-mcp"
        updated += 1
    interceptors = config.get("mcpInterceptors", [])
    if isinstance(interceptors, str):
        interceptors = [interceptors]
    if not isinstance(interceptors, list) or not all(isinstance(v, str) for v in interceptors):
        raise ValueError("Invalid MCP interceptor configuration")
    config["mcpInterceptors"] = interceptors
    name = "deermate.observability_middleware:build_mcp_interceptor"
    if name not in interceptors:
        interceptors.append(name)
    private_write(path, json.dumps(config, indent=2) + "\n", replace=True)
    return updated


def configure_bundle(bundle, values):
    import shutil

    import yaml

    validate(values)
    info = json.loads((bundle / "bundle.json").read_text())
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,62}", info["project"]):
        raise ValueError("Unrecognized bundle")
    path = bundle / "compose.yaml"
    config = yaml.safe_load(path.read_text())
    if not {"control", "gateway"} <= set(config.get("services", {})):
        raise ValueError("Expected the single-host control and Gateway services")
    shared = {k: v for k, v in values.items() if k != "OTEL_SERVICE_NAME"}
    destination = bundle / "observability.env"
    # Operator explicitly runs this configuration command; existing app secrets are untouched.
    private_write(
        destination,
        "".join(k + "='" + v.replace("'", "\\'") + "'\n" for k, v in sorted(shared.items())),
        replace=True,
    )
    for service in ("control", "gateway"):
        entry = config["services"][service]
        files = entry.setdefault("env_file", [])
        if "observability.env" not in files:
            files.append("observability.env")
        entry.setdefault("environment", {})["OTEL_SERVICE_NAME"] = "deermate-" + service
    private_write(path, yaml.safe_dump(config, sort_keys=False), replace=True)
    shutil.copyfile(Path(__file__), bundle / "runtime/observability.py")
    seed = bundle / "runtime/extensions_config.json"
    if seed.exists():
        patch_mcp(seed, values)


def probe(values, receipt):
    """Transport acceptance only; a successful export does not prove indexing."""
    endpoint = validate(values)
    os.environ.update(values)
    # Suppress exporter diagnostics that can contain an endpoint write credential.
    import logging

    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult

    from deermate import telemetry

    logging.getLogger("opentelemetry.exporter.otlp.proto.http.trace_exporter").disabled = True
    delegate = OTLPSpanExporter(endpoint=endpoint, timeout=2, session=telemetry.exporter_session())
    outcomes = []

    class Exporter(SpanExporter):
        def export(self, spans):
            try:
                outcome = delegate.export(spans)
            except Exception:
                outcome = SpanExportResult.FAILURE
            outcomes.append(outcome == SpanExportResult.SUCCESS)
            return outcome

        def shutdown(self):
            delegate.shutdown()

    provider = TracerProvider(resource=Resource({"service.name": "deermate-observability-probe"}))
    provider.add_span_processor(SimpleSpanProcessor(Exporter()))
    telemetry.configure(provider=provider)
    with telemetry.span(
        "deermate.observability.probe", attributes={"deermate.kind": "synthetic_probe"}
    ):
        parent = telemetry.capture()["traceparent"]
    provider.shutdown()
    result = {
        "schema_version": 1,
        "trace_id": parent[3:35],
        "span_id": parent[36:52],
        "export_accepted": outcomes == [True],
        "indexed_verified": False,
        "scope": "Synthetic OTLP transport probe; no agent, model or Native execution",
    }
    private_write(receipt, json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
    if not result["export_accepted"]:
        raise ValueError("Telemetry endpoint did not accept the probe; credentials are not printed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "probe", "configure-bundle", "configure-mcp"):
        command = commands.add_parser(name)
        command.add_argument("--env-file", type=Path)
        if name == "probe":
            command.add_argument("--receipt", type=Path, required=True)
        if name == "configure-bundle":
            command.add_argument("--bundle", type=Path, required=True)
        if name == "configure-mcp":
            command.add_argument("--mcp-config", type=Path, required=True)
    args = parser.parse_args()
    try:
        values = (
            read_env(args.env_file)
            if args.env_file
            else {k: v for k, v in os.environ.items() if k in ENV_KEYS}
        )
        validate(values)
        if args.command == "probe":
            probe(values, args.receipt)
        elif args.command == "configure-bundle":
            configure_bundle(args.bundle.resolve(), values)
            print(
                "Configured OTLP for control/Gateway. Apply the bundle, then configure "
                "the active MCP profile and restart Gateway."
            )
        elif args.command == "configure-mcp":
            count = patch_mcp(args.mcp_config, values)
            print(
                f"Configured {count} DeerMate MCP profiles; "
                "restart Gateway to refresh pooled sessions."
            )
        else:
            print("OTLP configuration is valid. No network request was made.")
    except (OSError, ValueError, KeyError, ImportError):
        parser.exit(
            1,
            "Observability configuration or probe failed; check private configuration "
            "and the receipt. No credentials are printed.\n",
        )


if __name__ == "__main__":
    main()
