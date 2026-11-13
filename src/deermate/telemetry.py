"""Optional, content-free OpenTelemetry. No vendor SDK or execution authority."""

import atexit
import contextvars
import functools
import inspect
import json
import logging
import os
import re
import sqlite3
from collections.abc import Mapping
from contextlib import contextmanager
from urllib.parse import urlsplit

_provider = None
_configured = False
_export_failures = 0
_refs = contextvars.ContextVar("deermate_trace_refs", default=None)
_id = re.compile(r"[A-Za-z0-9_.:-]{1,160}\Z")
_parent = re.compile(r"00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}\Z")
REFS = {"operation_id", "work_id", "conversation_id", "incarnation", "task_id", "instance_id"}
ATTRS = {
    *("deermate." + k for k in REFS),
    "deermate.native_session_id",
    "deermate.native_turn_id",
    "deermate.native_item_id",
    "deermate.status",
    "deermate.kind",
    "deermate.attempt",
    "deermate.recovery",
    "deermate.validation_status",
    "deermate.item_type",
    "deermate.tool_name",
    "http.request.method",
    "http.response.status_code",
    "gen_ai.operation.name",
    "gen_ai.request.model",
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.output_tokens",
    "error.type",
}
METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "CONNECT", "TRACE"}


def resource_attributes(service):
    result = {"service.name": service}
    for entry in os.getenv("OTEL_RESOURCE_ATTRIBUTES", "").split(","):
        key, _, value = entry.partition("=")
        if key in {"service.version", "service.namespace", "deployment.environment.name"}:
            if _id.fullmatch(value):
                result[key] = value
    return result


def mark_error(target=None):
    if _provider is not None:
        from opentelemetry import trace
        from opentelemetry.trace import Status, StatusCode

        (target if target is not None else trace.get_current_span()).set_status(
            Status(StatusCode.ERROR)
        )


def safe_refs(value):
    if not isinstance(value, dict):
        return {}
    return {k: v for k, v in value.items() if k in REFS and isinstance(v, str) and _id.fullmatch(v)}


def carrier(value):
    """Only W3C IDs and bounded tracestate; never baggage or arbitrary headers."""
    if not isinstance(value, dict):
        return {}
    parent = value.get("traceparent", "")
    if not isinstance(parent, str) or not _parent.fullmatch(parent):
        return {}
    if parent[3:35] == "0" * 32 or parent[36:52] == "0" * 16:
        return {}
    result = {"traceparent": parent}
    state = value.get("tracestate", "")
    if isinstance(state, str) and 0 < len(state) <= 512:
        parts = state.split(",")
        if len(parts) <= 32 and all(
            re.fullmatch(r"[a-z0-9_@*/-]{1,256}=[\x21-\x2b\x2d-\x3c\x3e-\x7e ]{1,256}", p.strip())
            for p in parts
        ):
            result["tracestate"] = state
    return result


def set_attributes(target, values):
    for key, value in values.items():
        if key not in ATTRS:
            continue
        if isinstance(value, (bool, int)) or (isinstance(value, str) and _id.fullmatch(value)):
            target.set_attribute(key, value)


def exporter_session():
    """Use the explicitly configured endpoint, without ambient system proxy routing."""
    import requests

    session = requests.Session()
    session.trust_env = False
    # HTTP exporter internals vary by SDK version and may log credential URLs.
    logger = logging.getLogger("opentelemetry.exporter.otlp")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return session


def configure(service="deermate-worker", *, provider=None):
    """A missing/invalid exporter degrades to disabled tracing, not failed work."""
    global _provider, _configured
    if provider is not None:  # Standard SDK providers also support offline verification.
        _provider = provider
        return
    if _configured:
        return
    _configured = True
    if os.getenv("DEERMATE_TELEMETRY_ENABLED", "false").lower() != "true":
        return
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            SpanExporter,
            SpanExportResult,
        )

        endpoint = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
        if not endpoint:
            base = os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"].rstrip("/")
            endpoint = base + "/v1/traces"
        url = urlsplit(endpoint)
        if url.username or url.password or url.fragment or not url.hostname:
            raise ValueError("invalid telemetry endpoint")
        if url.scheme != "https" and not (
            url.scheme == "http"
            and (
                url.hostname in {"localhost", "127.0.0.1", "::1"}
                or os.getenv("DEERMATE_TELEMETRY_ALLOW_INSECURE") == "true"
            )
        ):
            raise ValueError("telemetry endpoint requires TLS")
        # Exporters may include credential-bearing URLs in their error logs.
        logging.getLogger("opentelemetry.exporter.otlp.proto.http.trace_exporter").disabled = True
        delegate = OTLPSpanExporter(endpoint=endpoint, timeout=1, session=exporter_session())

        class QuietExporter(SpanExporter):
            def export(self, spans):
                global _export_failures
                try:
                    result = delegate.export(spans)
                except Exception:
                    result = SpanExportResult.FAILURE
                if result == SpanExportResult.FAILURE:
                    _export_failures += 1
                    if _export_failures == 1:
                        logging.getLogger(__name__).warning(
                            "Telemetry export failed; task execution continues"
                        )
                return result

            def shutdown(self):
                delegate.shutdown()

        name = os.getenv("OTEL_SERVICE_NAME", service)
        if not _id.fullmatch(name):
            raise ValueError("invalid service name")
        _provider = TracerProvider(resource=Resource(resource_attributes(name)))
        _provider.add_span_processor(
            BatchSpanProcessor(
                QuietExporter(),
                max_queue_size=512,
                max_export_batch_size=64,
                schedule_delay_millis=500,
                export_timeout_millis=1500,
            )
        )
        atexit.register(shutdown)
    except Exception:
        _provider = None
        logging.getLogger(__name__).warning("Telemetry unavailable; task execution is unchanged")


def shutdown():
    if _provider is not None:
        try:
            _provider.force_flush(timeout_millis=1500)
            _provider.shutdown()
        except Exception:
            pass


def capture():
    if _provider is None:
        return {}
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

    result = {}
    TraceContextTextMapPropagator().inject(result)
    return carrier(result)


def metadata():
    result = capture()
    if result:
        result["refs"] = safe_refs(_refs.get())
    return result


def current_attributes(values):
    if _provider is not None:
        from opentelemetry import trace

        set_attributes(trace.get_current_span(), values)


def begin_item(attributes):
    if _provider is None:
        return None
    current = _provider.get_tracer("deermate").start_span("codex.tool")
    set_attributes(current, attributes)
    return current


def end_item(current, status="completed"):
    if current is None:
        return
    if not isinstance(status, str):
        status = "unknown"
    set_attributes(current, {"deermate.status": status})
    if status in {"failed", "incomplete"}:
        from opentelemetry.trace import Status, StatusCode

        current.set_status(Status(StatusCode.ERROR))
    current.end()


def headers(value=None):
    value = metadata() if value is None else value
    result = carrier(value)
    refs = safe_refs(value.get("refs")) if isinstance(value, dict) else {}
    if result and refs:
        result["x-deermate-trace-refs"] = json.dumps(refs, separators=(",", ":"))
    return result


def from_headers(value):
    if not isinstance(value, Mapping):
        return {}
    normalized = {k.lower(): v for k, v in value.items() if isinstance(k, str)}
    result = carrier(normalized)
    raw = normalized.get("x-deermate-trace-refs", "")
    if result and isinstance(raw, str) and len(raw) <= 2048:
        try:
            result["refs"] = safe_refs(json.loads(raw))
        except (ValueError, TypeError):
            pass
    return result


@contextmanager
def span(name, *, parent=None, refs=None, attributes=None, recovery=False):
    if _provider is None:
        yield None
        return
    from opentelemetry import context, trace
    from opentelemetry.trace import Link, Status, StatusCode
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

    inherited = safe_refs(_refs.get())
    inherited.update(safe_refs(parent.get("refs") if isinstance(parent, dict) else None))
    inherited.update(safe_refs(refs))
    token = _refs.set(inherited)
    ctx = TraceContextTextMapPropagator().extract(carrier(parent)) if carrier(parent) else None
    links = []
    if recovery and ctx is not None:
        links = [Link(trace.get_current_span(ctx).get_span_context())]
        ctx = context.Context()
    try:
        with _provider.get_tracer("deermate").start_as_current_span(
            name,
            context=ctx,
            links=links,
            record_exception=False,
            set_status_on_exception=False,
        ) as current:
            set_attributes(current, {"deermate." + k: v for k, v in inherited.items()})
            set_attributes(current, attributes or {})
            if recovery:
                current.set_attribute("deermate.recovery", True)
            try:
                yield current
            except BaseException as error:
                current.set_status(Status(StatusCode.ERROR))
                set_attributes(current, {"error.type": type(error).__name__})
                raise
    finally:
        _refs.reset(token)


def observed(name):
    def decorate(function):
        if inspect.iscoroutinefunction(function):

            @functools.wraps(function)
            async def async_call(*args, **kwargs):
                with span(name):
                    return await function(*args, **kwargs)

            return async_call

        @functools.wraps(function)
        def sync_call(*args, **kwargs):
            with span(name):
                return function(*args, **kwargs)

        return sync_call

    return decorate


def save_binding(db, key, value):
    if not carrier(value):
        return
    try:
        db.execute(
            "INSERT OR IGNORE INTO deermate_task_trace VALUES(?,?)",
            (key, json.dumps({**carrier(value), "refs": safe_refs(value.get("refs"))})),
        )
    except sqlite3.DatabaseError:
        pass


def load_binding(db, key):
    try:
        row = db.execute(
            "SELECT context FROM deermate_task_trace WHERE task_id=?", (key,)
        ).fetchone()
        return json.loads(row[0]) if row else {}
    except (sqlite3.DatabaseError, ValueError, TypeError):
        return {}


class TraceASGI:
    """Private authenticated runtime/Worker boundary, with no body/header logging."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        incoming = {k.decode("latin1"): v.decode("latin1") for k, v in scope.get("headers", [])}
        with span(
            "http.server",
            parent=from_headers(incoming),
            attributes={
                "http.request.method": scope["method"] if scope["method"] in METHODS else "_OTHER"
            },
        ) as current:

            async def traced_send(message):
                if current is not None and message["type"] == "http.response.start":
                    set_attributes(current, {"http.response.status_code": message["status"]})
                    if message["status"] >= 500:
                        mark_error(current)
                await send(message)

            await self.app(scope, receive, traced_send)
