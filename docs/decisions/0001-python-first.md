# ADR 0001: Python-owned backend, optional Hermesh interoperability

Date: 2026-10-25. Status: accepted design direction; Python Worker/MCP/direct SSH implemented, optional Hermesh bridge pending. See [the decision index](README.md) and [current status](../STATUS.md).

## Context

DeerMate starts from a DeerFlow secretary plus remote agent execution. Hermesh closely matches the desired cross-machine handoff, but its backend is Go. The project owner wants to maintain backend services in Python.

## Decision

Maintain the DeerMate control service, worker, and session adapters in Python. Propose FastAPI, Pydantic, asyncio, and AsyncSSH, with durable local persistence to start. Reuse DeerFlow through a bounded integration instead of reimplementing its model loop, memory, and scheduler.

Use the established SSH protocol with host-key verification for the first private transport. Do not invent cryptography or label ordinary TLS termination as relay-blind end-to-end encryption.

Support existing Hermesh deployments through a future optional CLI adapter. Do not fork, port, or promise wire compatibility with Hermesh. Its independent relay remains external and is not required by the default deployment.

## Consequences

- No Go toolchain or Go service is required by the default DeerMate design.
- External native agents keep their own executable and runtime requirements.
- We must build and verify worker admission, session mapping, cancellation, and recovery rather than claiming Hermesh provides these to our default path.
- Browser-facing UI may use DeerFlow's existing TypeScript frontend; the Python constraint applies to backend services we maintain.
- Device pairing, host enrollment, NAT traversal, and key lifecycle are explicit work items, not delivered capabilities.
- Calling the project Python-first does not imply all dependencies use permissive licenses. Review dependencies and notices before shipping a runtime distribution.
