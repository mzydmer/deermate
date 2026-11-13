"""Bounded, loopback-only actual OTLP/protobuf receiver for offline acceptance."""

import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest


class Receiver:
    def __init__(self, host="127.0.0.1", port=0, output_dir=None):
        self.payloads = []
        self.lock = threading.RLock()
        self.changed = threading.Condition(self.lock)
        receiver = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                length = int(self.headers.get("content-length", "0"))
                if self.path != "/v1/traces" or not 0 < length <= 4_000_000:
                    self.send_error(400)
                    return
                payload = ExportTraceServiceRequest.FromString(self.rfile.read(length))
                with receiver.lock:
                    receiver.payloads.append(payload)
                    if output_dir is not None:
                        path = output_dir / f"{len(receiver.payloads):06d}.pb"
                        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                        with os.fdopen(fd, "wb") as file:
                            file.write(payload.SerializeToString())
                    receiver.changed.notify_all()
                self.send_response(200)
                self.send_header("Content-Type", "application/x-protobuf")
                self.end_headers()

        self.server = ThreadingHTTPServer((host, port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def endpoint(self):
        return f"http://127.0.0.1:{self.server.server_port}/v1/traces"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def spans(self):
        with self.lock:
            return [
                span
                for p in self.payloads
                for r in p.resource_spans
                for s in r.scope_spans
                for span in s.spans
            ]

    def wait_for_span(self, name, timeout=8):
        with self.changed:
            return self.changed.wait_for(
                lambda: any(span.name == name for span in self.spans()), timeout=timeout
            )


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4318)
    parser.add_argument("--output-dir", type=Path, required=True)
    options = parser.parse_args()
    options.output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    with Receiver(options.host, options.port, options.output_dir):
        threading.Event().wait()
