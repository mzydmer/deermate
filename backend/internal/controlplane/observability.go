package controlplane

import (
	"context"
	"database/sql"
	"encoding/json"
	obs "github.com/mzydmer/deermate/backend/internal/observability"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
	"net/http"
)

type tracedResponse struct {
	http.ResponseWriter
	status int
}

func (w *tracedResponse) WriteHeader(status int) {
	if w.status == 0 {
		w.status = status
	}
	w.ResponseWriter.WriteHeader(status)
}
func (w *tracedResponse) Write(body []byte) (int, error) {
	if w.status == 0 {
		w.status = http.StatusOK
	}
	return w.ResponseWriter.Write(body)
}
func (w *tracedResponse) Unwrap() http.ResponseWriter { return w.ResponseWriter }
func (w *tracedResponse) Flush() {
	if w.status == 0 {
		w.WriteHeader(http.StatusOK)
	}
	_ = http.NewResponseController(w.ResponseWriter).Flush()
}
func finishHTTP(span trace.Span, r *http.Request, w *tracedResponse) {
	status := w.status
	if status == 0 {
		status = http.StatusOK
	}
	span.SetAttributes(attribute.Int("http.response.status_code", status))
	// Pattern is registered server code, not an untrusted request URL.
	if r.Pattern != "" && len(r.Pattern) <= 256 {
		span.SetAttributes(attribute.String("http.route", r.Pattern))
	}
	if status >= 500 {
		span.SetStatus(codes.Error, "")
	}
	span.End()
}

func (s *Server) initTraceBindings() error {
	_, err := s.Store.DB.Exec(`CREATE TABLE IF NOT EXISTS deermate_operation_trace(owner TEXT NOT NULL,record TEXT NOT NULL,context TEXT NOT NULL,PRIMARY KEY(owner,record))`)
	return err
}
func bindTrace(tx *sql.Tx, owner, record string, ctx context.Context) {
	value := obs.Capture(ctx)
	if value.Traceparent == "" {
		return
	}
	raw, err := json.Marshal(value)
	if err == nil {
		_, _ = tx.Exec("INSERT OR IGNORE INTO deermate_operation_trace VALUES(?,?,?)", owner, record, string(raw))
	}
}
func restoreTrace(ctx context.Context, q memoryReader, owner, record string) context.Context {
	var raw string
	var value obs.Context
	if q.QueryRow("SELECT context FROM deermate_operation_trace WHERE owner=? AND record=?", owner, record).Scan(&raw) == nil && json.Unmarshal([]byte(raw), &value) == nil {
		return obs.Restore(ctx, value)
	}
	return ctx
}

// Public callers cannot choose an internal Trace ID or sampling decision.
func publicTrace(r *http.Request) (*http.Request, trace.Span) {
	ctx := trace.ContextWithSpanContext(r.Context(), trace.SpanContext{})
	ctx, span := obs.Start(ctx, "http.server", nil)
	span.SetAttributes(attribute.String("http.request.method", obs.Method(r.Method)))
	return r.WithContext(ctx), span
}
