# Optional OTLP tracing

DeerMate uses OpenTelemetry API/SDK and OTLP/HTTP. The application does not depend on a cloud account or vendor SDK. Tracing is off unless `DEERMATE_TELEMETRY_ENABLED=true`; removing `arms/` does not change the core library. This phase exports traces and observed token attributes, not a separate metrics/logs pipeline.

- Core design, boundaries and validation: [observability guide](../../docs/observability.md).
- First deployment target: [ARMS adapter](arms/README.md).
- Portable configuration: [otel.env.example](otel.env.example).

Install Python support with `python -m pip install -e '.[observability]'`. Packaged Gateway images include it; an independently installed Worker/MCP needs the extra. Go includes the standard SDK. No Collector is required when the target directly accepts compatible OTLP/HTTP over HTTPS. A self-hosted Collector can provide routing, buffering or a TLS boundary when required.

Use a private mode-0600 environment file. The endpoint may contain a credential. Never commit a filled profile. `scripts/observability.py check` validates configuration without contacting a backend; `probe` sends one synthetic span and records transport acceptance separately from backend indexing.

For a local receiver, use the loopback example. An endpoint on another host requires HTTPS. `DEERMATE_TELEMETRY_ALLOW_INSECURE=true` is an explicit exception for isolated test networks, not a production default. Python export uses a direct connection without ambient system proxy routing; use a local Collector if an outbound proxy is required.
