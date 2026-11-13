// Package observability implements optional, vendor-neutral, content-free tracing.
package observability

import (
	"context"
	"encoding/json"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/trace"
	"log/slog"
	"net/http"
	"net/url"
	"os"
	"regexp"
	"strconv"
	"strings"
	"sync/atomic"
	"time"
)

type refsKey struct{}
type Context struct {
	Traceparent string            `json:"traceparent,omitempty"`
	Tracestate  string            `json:"tracestate,omitempty"`
	Refs        map[string]string `json:"refs,omitempty"`
}

var identity = regexp.MustCompile(`^[A-Za-z0-9_.:-]{1,160}$`)
var parent = regexp.MustCompile(`^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$`)
var refKeys = map[string]bool{"operation_id": true, "work_id": true, "conversation_id": true, "incarnation": true, "task_id": true, "instance_id": true}
var exportFailures atomic.Uint64

func Method(value string) string {
	switch value {
	case "GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "CONNECT", "TRACE":
		return value
	default:
		return "_OTHER"
	}
}

func Clean(value Context) Context {
	if !parent.MatchString(value.Traceparent) || value.Traceparent[3:35] == strings.Repeat("0", 32) || value.Traceparent[36:52] == strings.Repeat("0", 16) {
		return Context{}
	}
	result := Context{Traceparent: value.Traceparent, Refs: map[string]string{}}
	if len(value.Tracestate) <= 512 {
		if state, err := trace.ParseTraceState(value.Tracestate); err == nil {
			result.Tracestate = state.String()
		}
	}
	for k, v := range value.Refs {
		if refKeys[k] && identity.MatchString(v) {
			result.Refs[k] = v
		}
	}
	return result
}
func WithRefs(ctx context.Context, refs map[string]string) context.Context {
	merged := map[string]string{}
	if previous, ok := ctx.Value(refsKey{}).(map[string]string); ok {
		for k, v := range previous {
			merged[k] = v
		}
	}
	for k, v := range refs {
		if refKeys[k] && identity.MatchString(v) {
			merged[k] = v
		}
	}
	return context.WithValue(ctx, refsKey{}, merged)
}
func Capture(ctx context.Context) Context {
	c := propagation.MapCarrier{}
	propagation.TraceContext{}.Inject(ctx, c)
	refs, _ := ctx.Value(refsKey{}).(map[string]string)
	return Clean(Context{Traceparent: c.Get("traceparent"), Tracestate: c.Get("tracestate"), Refs: refs})
}
func Restore(ctx context.Context, value Context) context.Context {
	value = Clean(value)
	if value.Traceparent == "" {
		return ctx
	}
	// Python SDKs may set the W3C random-ID flag (03). Older Go propagators
	// reject it: retain the supported sampling bit without changing either ID.
	flags, _ := strconv.ParseUint(value.Traceparent[53:], 16, 8)
	value.Traceparent = value.Traceparent[:53] + "0" + strconv.FormatUint(flags&1, 16)
	ctx = propagation.TraceContext{}.Extract(ctx, propagation.MapCarrier{"traceparent": value.Traceparent, "tracestate": value.Tracestate})
	return WithRefs(ctx, value.Refs)
}
func FromHeaders(h http.Header) Context {
	refs := map[string]string{}
	if raw := h.Get("X-Deermate-Trace-Refs"); len(raw) <= 2048 {
		_ = json.Unmarshal([]byte(raw), &refs)
	}
	return Clean(Context{Traceparent: h.Get("Traceparent"), Tracestate: h.Get("Tracestate"), Refs: refs})
}
func Inject(ctx context.Context, h http.Header) {
	for _, k := range []string{"Traceparent", "Tracestate", "Baggage", "X-Deermate-Trace-Refs"} {
		h.Del(k)
	}
	value := Capture(ctx)
	if value.Traceparent == "" {
		return
	}
	h.Set("Traceparent", value.Traceparent)
	if value.Tracestate != "" {
		h.Set("Tracestate", value.Tracestate)
	}
	if len(value.Refs) > 0 {
		raw, _ := json.Marshal(value.Refs)
		h.Set("X-Deermate-Trace-Refs", string(raw))
	}
}
func Start(ctx context.Context, name string, refs map[string]string) (context.Context, trace.Span) {
	ctx = WithRefs(ctx, refs)
	kind := trace.SpanKindInternal
	switch name {
	case "http.server", "device.relay":
		kind = trace.SpanKindServer
	case "http.client":
		kind = trace.SpanKindClient
	case "operation.deliver":
		kind = trace.SpanKindProducer
	}
	ctx, span := otel.Tracer("deermate").Start(ctx, name, trace.WithSpanKind(kind))
	if refs, ok := ctx.Value(refsKey{}).(map[string]string); ok {
		for k, v := range refs {
			span.SetAttributes(attribute.String("deermate."+k, v))
		}
	}
	return ctx, span
}

// Transport never records URLs, query strings, bodies, headers or exception text.
type Transport struct{ Base http.RoundTripper }

func (t Transport) RoundTrip(r *http.Request) (*http.Response, error) {
	ctx, span := Start(r.Context(), "http.client", nil)
	defer span.End()
	req := r.Clone(ctx)
	Inject(ctx, req.Header)
	span.SetAttributes(attribute.String("http.request.method", Method(r.Method)))
	base := t.Base
	if base == nil {
		base = http.DefaultTransport
	}
	response, err := base.RoundTrip(req)
	if response != nil {
		span.SetAttributes(attribute.Int("http.response.status_code", response.StatusCode))
		if response.StatusCode >= 500 {
			span.SetStatus(codes.Error, "")
		}
	}
	if err != nil {
		span.SetAttributes(attribute.String("error.type", "transport_error"))
		span.SetStatus(codes.Error, "")
	}
	return response, err
}
func Setup(ctx context.Context) func(context.Context) error {
	noop := func(context.Context) error { return nil }
	if os.Getenv("DEERMATE_TELEMETRY_ENABLED") != "true" {
		return noop
	}
	endpoint := os.Getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
	if endpoint == "" {
		endpoint = os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
	}
	u, err := url.Parse(endpoint)
	if err != nil || u.Hostname() == "" || u.User != nil || u.Fragment != "" || (u.Scheme != "https" && !(u.Scheme == "http" && (u.Hostname() == "localhost" || u.Hostname() == "127.0.0.1" || u.Hostname() == "::1" || os.Getenv("DEERMATE_TELEMETRY_ALLOW_INSECURE") == "true"))) {
		slog.Warn("Telemetry unavailable; task execution is unchanged")
		return noop
	}
	// Exporter errors can include credential-bearing endpoint URLs.
	otel.SetErrorHandler(otel.ErrorHandlerFunc(func(error) {
		if exportFailures.Add(1) == 1 {
			slog.Warn("Telemetry export failed; task execution continues")
		}
	}))
	exporter, err := otlptracehttp.New(ctx, otlptracehttp.WithTimeout(time.Second))
	if err != nil {
		slog.Warn("Telemetry unavailable; task execution is unchanged")
		return noop
	}
	name := os.Getenv("OTEL_SERVICE_NAME")
	if !identity.MatchString(name) {
		name = "deermate-control"
	}
	attrs := []attribute.KeyValue{attribute.String("service.name", name)}
	for _, entry := range strings.Split(os.Getenv("OTEL_RESOURCE_ATTRIBUTES"), ",") {
		key, value, _ := strings.Cut(entry, "=")
		if (key == "service.version" || key == "service.namespace" || key == "deployment.environment.name") && identity.MatchString(value) {
			attrs = append(attrs, attribute.String(key, value))
		}
	}
	provider := sdktrace.NewTracerProvider(sdktrace.WithResource(resource.NewSchemaless(attrs...)), sdktrace.WithBatcher(exporter, sdktrace.WithMaxQueueSize(512), sdktrace.WithMaxExportBatchSize(64), sdktrace.WithBatchTimeout(500*time.Millisecond), sdktrace.WithExportTimeout(time.Second)))
	otel.SetTracerProvider(provider)
	return provider.Shutdown
}
