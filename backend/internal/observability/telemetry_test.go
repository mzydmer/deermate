package observability

import (
	"context"
	"go.opentelemetry.io/otel"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/sdk/trace/tracetest"
	collect "go.opentelemetry.io/proto/otlp/collector/trace/v1"
	"google.golang.org/protobuf/proto"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func recorder(t *testing.T) *tracetest.InMemoryExporter {
	previous := otel.GetTracerProvider()
	exporter := tracetest.NewInMemoryExporter()
	provider := sdktrace.NewTracerProvider(sdktrace.WithSyncer(exporter))
	otel.SetTracerProvider(provider)
	t.Cleanup(func() { _ = provider.Shutdown(context.Background()); otel.SetTracerProvider(previous) })
	return exporter
}
func TestMetadataAndHTTPPropagation(t *testing.T) {
	exporter := recorder(t)
	var incoming http.Header
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { incoming = r.Header.Clone(); w.WriteHeader(204) }))
	defer server.Close()
	ctx, root := Start(context.Background(), "root", map[string]string{"operation_id": "op-one", "password": "SYNTHETIC_SECRET"})
	client := http.Client{Transport: Transport{}}
	req, _ := http.NewRequestWithContext(ctx, "GET", server.URL+"/private?api_key=SYNTHETIC_SECRET", nil)
	req.Header.Set("Baggage", "SYNTHETIC_SECRET")
	resp, err := client.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	resp.Body.Close()
	root.End()
	value := FromHeaders(incoming)
	if value.Traceparent == "" || value.Refs["operation_id"] != "op-one" || incoming.Get("Baggage") != "" {
		t.Fatal("missing or unsafe context")
	}
	spans := exporter.GetSpans()
	if len(spans) != 2 || spans[0].SpanContext.TraceID() != spans[1].SpanContext.TraceID() || spans[0].Parent.SpanID() != spans[1].SpanContext.SpanID() {
		t.Fatal("broken parentage")
	}
	for _, span := range spans {
		for _, attr := range span.Attributes {
			if strings.Contains(attr.Value.Emit(), "SYNTHETIC_SECRET") {
				t.Fatal("content leaked")
			}
		}
	}
	if Clean(Context{Traceparent: "bad"}).Traceparent != "" {
		t.Fatal("invalid context accepted")
	}
	if Clean(Context{Traceparent: "00-" + strings.Repeat("0", 32) + "-" + strings.Repeat("1", 16) + "-01"}).Traceparent != "" {
		t.Fatal("zero trace accepted")
	}
}

func TestPythonRandomTraceFlagPreservesIDs(t *testing.T) {
	recorder(t)
	value := Context{Traceparent: "00-11111111111111111111111111111111-2222222222222222-03"}
	ctx, span := Start(Restore(context.Background(), value), "python.child", nil)
	defer span.End()
	if got := Capture(ctx); got.Traceparent[3:35] != value.Traceparent[3:35] {
		t.Fatal("Python random-ID flag broke cross-language parentage")
	}
}
func TestRealOTLPHTTPAndDisabledExport(t *testing.T) {
	previous := otel.GetTracerProvider()
	t.Cleanup(func() { otel.SetTracerProvider(previous) })
	received := make(chan *collect.ExportTraceServiceRequest, 4)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		raw, _ := io.ReadAll(io.LimitReader(r.Body, 2_000_000))
		payload := new(collect.ExportTraceServiceRequest)
		if err := proto.Unmarshal(raw, payload); err != nil {
			t.Error(err)
		}
		received <- payload
		w.Header().Set("Content-Type", "application/x-protobuf")
		w.WriteHeader(200)
	}))
	defer server.Close()
	t.Setenv("DEERMATE_TELEMETRY_ENABLED", "false")
	t.Setenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", server.URL+"/v1/traces")
	_ = Setup(context.Background())(context.Background())
	select {
	case <-received:
		t.Fatal("disabled exporter made a request")
	default:
	}
	t.Setenv("DEERMATE_TELEMETRY_ENABLED", "true")
	t.Setenv("OTEL_SERVICE_NAME", "deermate-test")
	stop := Setup(context.Background())
	_, span := Start(context.Background(), "wire.test", map[string]string{"operation_id": "wire-op"})
	span.End()
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	if err := stop(ctx); err != nil {
		t.Fatal(err)
	}
	select {
	case p := <-received:
		if len(p.ResourceSpans) != 1 || len(p.ResourceSpans[0].ScopeSpans[0].Spans) != 1 {
			t.Fatal("missing actual span")
		}
	case <-time.After(2 * time.Second):
		t.Fatal("no actual OTLP payload")
	}
}
