package controlplane

import (
	"context"
	"encoding/json"
	obs "github.com/mzydmer/deermate/backend/internal/observability"
	"go.opentelemetry.io/otel"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/sdk/trace/tracetest"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"testing"
)

func TestTraceBindingRejectsOverwriteAndForeignOwner(t *testing.T) {
	previous := otel.GetTracerProvider()
	provider := sdktrace.NewTracerProvider(sdktrace.WithSyncer(tracetest.NewInMemoryExporter()))
	otel.SetTracerProvider(provider)
	defer otel.SetTracerProvider(previous)
	defer provider.Shutdown(context.Background())
	store := testStore(t)
	server := testServer(t, store, func(w http.ResponseWriter, r *http.Request) {})
	ctx, span := obs.Start(context.Background(), "accept", map[string]string{"operation_id": "one"})
	original := obs.Capture(ctx)
	span.End()
	tx, _ := store.DB.Begin()
	bindTrace(tx, "owner", "one", ctx)
	tx.Commit()
	other, second := obs.Start(context.Background(), "duplicate", nil)
	tx, _ = store.DB.Begin()
	bindTrace(tx, "owner", "one", other)
	tx.Commit()
	second.End()
	raw := obs.Capture(restoreTrace(context.Background(), server.Store.DB, "owner", "one"))
	if raw.Traceparent != original.Traceparent {
		t.Fatal("original context overwritten")
	}
	if obs.Capture(restoreTrace(context.Background(), store.DB, "different-owner", "one")).Traceparent != "" {
		t.Fatal("cross-owner context exposed")
	}
	if server.initTraceBindings() != nil {
		t.Fatal("upgrade not idempotent")
	}
	req := httptest.NewRequest("POST", "http://localhost/api/me/router/messages", nil)
	req.Header.Set("Traceparent", original.Traceparent)
	_, public := publicTrace(req)
	if public.SpanContext().TraceID().String() == original.Traceparent[3:35] {
		t.Fatal("public context injected")
	}
	public.End()
	var value obs.Context
	encoded, _ := json.Marshal(raw)
	if json.Unmarshal(encoded, &value) != nil {
		t.Fatal("invalid persistence")
	}
}

func TestTraceBindingSurvivesDatabaseCloseAndReopen(t *testing.T) {
	filename := filepath.Join(t.TempDir(), "trace.db")
	store, err := OpenStore(filename)
	if err != nil {
		t.Fatal(err)
	}
	server := &Server{Store: store}
	if err = server.initTraceBindings(); err != nil {
		t.Fatal(err)
	}
	original := obs.Context{Traceparent: "00-11111111111111111111111111111111-2222222222222222-01", Refs: map[string]string{"operation_id": "persisted-operation"}}
	tx, err := store.DB.Begin()
	if err != nil {
		t.Fatal(err)
	}
	bindTrace(tx, "owner", "operation", obs.Restore(context.Background(), original))
	if err = tx.Commit(); err != nil {
		t.Fatal(err)
	}
	if err = store.DB.Close(); err != nil {
		t.Fatal(err)
	}
	reopened, err := OpenStore(filename)
	if err != nil {
		t.Fatal(err)
	}
	defer reopened.DB.Close()
	value := obs.Capture(restoreTrace(context.Background(), reopened.DB, "owner", "operation"))
	if value.Traceparent != original.Traceparent || value.Refs["operation_id"] != "persisted-operation" {
		t.Fatal("original durable binding lost after reopening the database")
	}
}
