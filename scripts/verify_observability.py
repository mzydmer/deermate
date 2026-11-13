#!/usr/bin/env python3
"""Verify actual OTLP protobuf ancestry from an isolated two-round fixture."""

import argparse
import hashlib
import json
import stat
from collections import Counter
from pathlib import Path

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

ROOT = Path(__file__).resolve().parents[1]


def verify(payload_dir, native_receipt, output, secrets_file):
    info = secrets_file.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
        raise ValueError("Use a private synthetic-value file")
    forbidden = json.loads(secrets_file.read_text())
    if not isinstance(forbidden, list) or not all(isinstance(v, str) and v for v in forbidden):
        raise ValueError("Expected synthetic private markers")
    native = json.loads(native_receipt.read_text())
    assert native["passed"] and native["native_rounds"] == 2
    assert native["real_provider_calls"] == native["real_codex_turns"] == 0
    paths = sorted(payload_dir.glob("*.pb"))
    assert 0 < len(paths) <= 4096
    assert sum(p.stat().st_size for p in paths) <= 64_000_000
    rows = {}
    for path in paths:
        payload = ExportTraceServiceRequest.FromString(path.read_bytes())
        assert not any(value in str(payload) for value in forbidden), "Private marker in payload"
        for resource in payload.resource_spans:
            service = next(
                (
                    a.value.string_value
                    for a in resource.resource.attributes
                    if a.key == "service.name"
                ),
                "",
            )
            for scope in resource.scope_spans:
                for span in scope.spans:
                    rows[span.trace_id, span.span_id] = (span, service)
    names = Counter(s.name for s, _ in rows.values())
    assert {
        "operation.deliver",
        "agent.operation",
        "agent.model",
        "memory.retrieve",
        "mcp.client",
        "mcp.server",
        "device.relay",
        "worker.execute",
        "codex.turn",
        "worker.validation",
    } <= names.keys()
    workers = [s for s, _ in rows.values() if s.name == "worker.execute"]
    assert len(workers) == names["worker.validation"] == names["codex.turn"] == 2
    native_roots, turns, trace_ids, operations = set(), set(), set(), set()
    rounds = []
    for worker in workers:
        attrs = {a.key: a.value.string_value for a in worker.attributes}
        assert attrs["deermate.status"] == "completed"
        native_roots.add(attrs["deermate.native_session_id"])
        turns.add(attrs["deermate.native_turn_id"])
        operations.add(attrs["deermate.operation_id"])
        trace_ids.add(worker.trace_id)
        current, chain, seen = rows[worker.trace_id, worker.span_id], [], set()
        while current:
            span, service = current
            assert span.span_id not in seen, "Cycle in observed parent chain"
            seen.add(span.span_id)
            chain.append({"name": span.name, "service": service})
            current = rows.get((span.trace_id, span.parent_span_id))
        chain_names = {v["name"] for v in chain}
        assert {
            "http.server",
            "agent.operation",
            "mcp.client",
            "mcp.server",
            "worker.request",
            "device.relay",
            "worker.execute",
        } <= chain_names
        assert len({v["service"] for v in chain}) == 4
        same_trace = [s for s, _ in rows.values() if s.trace_id == worker.trace_id]
        assert any(s.name == "operation.deliver" for s in same_trace)
        for required in ("codex.turn", "worker.validation"):
            child = next(s for s in same_trace if s.name == required)
            assert child.parent_span_id == worker.span_id
        rounds.append(
            {
                "trace_id": worker.trace_id.hex(),
                "operation_id": attrs["deermate.operation_id"],
                "observed_ancestor_chain": chain,
            }
        )
    assert len(native_roots) == 1 and "" not in native_roots
    assert len(turns) == len(trace_ids) == len(operations) == 2
    sources = [
        *sorted((ROOT / "src/deermate").glob("*.py")),
        *sorted((ROOT / "backend/internal/observability").glob("*.go")),
        *sorted((ROOT / "backend/internal/controlplane").glob("*.go")),
        ROOT / "scripts/verify_observability.py",
    ]
    receipt = {
        "schema_version": 1,
        "passed": True,
        "scope": (
            "Actual pinned Go/Gateway/MCP/relay/Worker OTLP ancestry; "
            "Fake model and native protocol"
        ),
        "payload_count": len(paths),
        "observed_span_count": len(rows),
        "span_counts": dict(sorted(names.items())),
        "rounds": rounds,
        "native_roots": len(native_roots),
        "native_rounds": len(turns),
        "independent_validations": names["worker.validation"],
        "privacy_markers_checked": len(forbidden),
        "private_marker_matches": 0,
        "real_provider_calls": 0,
        "real_codex_turns": 0,
        "arms_export_accepted": False,
        "arms_indexed_verified": False,
        "source_sha256": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources
        },
        "limits": [
            "No live ARMS, provider or native-agent acceptance",
            "No Pilot automatic subtrace joining or dedicated metrics/logs pipeline",
            "Offline protocol events are synthetic; raw payloads and credentials stay private",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        json.dumps(
            {
                "passed": True,
                "observed_spans": len(rows),
                "rounds": 2,
                "services_per_execution_chain": 4,
                "private_marker_matches": 0,
                "arms_verified": False,
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload-dir", type=Path, required=True)
    parser.add_argument("--native-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--secrets-file", type=Path, required=True)
    args = parser.parse_args()
    verify(args.payload_dir, args.native_receipt, args.output, args.secrets_file)
