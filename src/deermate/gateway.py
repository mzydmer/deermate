"""Portable ASGI entrypoint around the unchanged pinned DeerFlow application."""

from . import telemetry

telemetry.configure("deermate-gateway")

from app.gateway.app import app  # noqa: E402

app.add_middleware(telemetry.TraceASGI)
