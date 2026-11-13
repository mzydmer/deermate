# ARMS deployment adapter

This directory contains configuration and operator instructions only. Core Go/Python code uses the same standard OTLP exporter with ARMS or another compatible backend. No Alibaba SDK, AK/SK or LicenseKey is embedded in the application.

## Obtain a profile

In CloudMonitor 2.0, select the intended workspace and region, open **Integration Center → server application → OpenTelemetry**, and obtain the endpoint and write headers from its configuration. These are the settings described in [Alibaba's custom SDK integration guide](https://help.aliyun.com/zh/agentloop/go-llm-application-custom-burial-best-practices). For the existing Singapore deployment, confirm the workspace actually accepts data in that region; do not infer a URL from a hostname list.

Copy `arms.env.example` to a private location, set mode 0600, then replace the placeholders with the exact OTLP/HTTP HTTPS endpoint and headers. `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` is a complete traces URL; it is not a gRPC address. If the console supplies a base `OTEL_EXPORTER_OTLP_ENDPOINT`, use that variable instead and let the SDK append `/v1/traces`. Do not set both unless intentionally overriding the traces endpoint. Endpoint paths and authentication formats vary by product/workspace generation.

If the account only supplies HTTP or gRPC, use an explicitly configured Collector/TLS route or obtain a supported HTTPS endpoint. Do not guess a new scheme or path. [Official preparation instructions](https://www.alibabacloud.com/help/zh/arms/tracing-analysis/before-you-begin) cover supported regions and reporting protocols. Confirm service activation, quota, retention and billing in the actual account before enabling reporting; this repository does not create or purchase cloud resources.

## Check, probe, apply

Run in the repository environment with the `observability` extra installed:

```bash
python scripts/observability.py check --env-file /private/path/arms.env
python scripts/observability.py probe --env-file /private/path/arms.env \
  --receipt /private/path/arms-probe.json
```

`check` makes no network request. `probe` emits one synthetic span; it does not run an agent or consume model quota. A receipt with `export_accepted=true` means the receiver accepted the export. `indexed_verified` remains false: search the receipt's `trace_id` in the same ARMS workspace/region and check the actual span before recording cloud verification. Both stdout and the receipt omit credentials.

Apply an updated single-host bundle using the [generic deployment steps](../../../docs/observability.md#single-host-compose). Configure each execution device independently; the cloud bundle does not install or authorize a local Worker. Existing device authorization and native login remain required.

## Cloud acceptance still required

1. Confirm the synthetic trace is searchable and its service is `deermate-observability-probe`.
2. Run an already authorized task and a follow-up. Check Go → runtime/MCP → relay → Worker → native turn → independent validation against the operation/task identifiers.
3. Confirm two turns share the existing native root and have distinct task/turn identifiers. Check actual tool events only where the native protocol provided a start and completion.
4. Check privacy and error classification; never upload prompt, commands, diffs or credentials merely to improve a dashboard.
5. Keep the original task ledger authoritative. A missing sampled/exported span does not establish that an operation did not execute.

Current local evidence uses a generic OTLP receiver and a synthetic native protocol. ARMS ingestion, cloud querying, AI dashboard presentation and automatic native/Pilot subtrace joining have not been verified. Standard spans being searchable does not prove every vendor-specific AI view is populated. AgentLoop evaluations and optimization are outside this phase.

To stop reporting, set `DEERMATE_TELEMETRY_ENABLED=false` on control, Gateway, each active MCP profile and Worker, then restart the affected processes. Disable any separately installed native probe as well. Delete/rotate the cloud write credential independently; stopping export does not delete data retained by ARMS.
