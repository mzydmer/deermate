package observability

import (
	"bytes"
	"context"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/sdk/trace/tracetest"
	"go.opentelemetry.io/otel/trace/noop"
)

type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

type responseBody struct {
	read  func([]byte) (int, error)
	close func() error
}

func (b responseBody) Read(p []byte) (int, error) { return b.read(p) }
func (b responseBody) Close() error               { return b.close() }

func tracedResponse(t *testing.T, ctx context.Context, body io.ReadCloser) *http.Response {
	t.Helper()
	transport := Transport{Base: roundTripFunc(func(*http.Request) (*http.Response, error) {
		return &http.Response{StatusCode: http.StatusOK, Body: body}, nil
	})}
	req, _ := http.NewRequestWithContext(ctx, "GET", "http://localhost/stream", nil)
	response, err := transport.RoundTrip(req)
	if err != nil {
		t.Fatal(err)
	}
	return response
}

func TestHTTPStreamSpanWaitsForResponseBody(t *testing.T) {
	exporter := recorder(t)
	finish := make(chan struct{})
	var release sync.Once
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, child := Start(Restore(r.Context(), FromHeaders(r.Header)), "gateway.stream", nil)
		defer child.End()
		w.Header().Set("Content-Type", "text/event-stream")
		_, _ = io.WriteString(w, "data: first\n\n")
		w.(http.Flusher).Flush()
		<-finish
		_, _ = io.WriteString(w, "data: last\n\n")
	}))
	defer server.Close()
	defer release.Do(func() { close(finish) })
	client := http.Client{Transport: Transport{}}
	response, err := client.Get(server.URL)
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	if len(exporter.GetSpans()) != 0 {
		t.Fatal("client span ended at response headers while SSE is still open")
	}
	first := make([]byte, len("data: first\n\n"))
	if _, err := io.ReadFull(response.Body, first); err != nil || string(first) != "data: first\n\n" {
		t.Fatal("streaming bytes changed", err)
	}
	firstRead := time.Now()
	if len(exporter.GetSpans()) != 0 {
		t.Fatal("client span ended after a chunk, before stream completion")
	}
	release.Do(func() { close(finish) })
	last, err := io.ReadAll(response.Body)
	if err != nil || string(last) != "data: last\n\n" {
		t.Fatal("streaming tail changed", err)
	}
	spans := exporter.GetSpans()
	if len(spans) != 2 || spans[0].Name != "gateway.stream" || spans[1].Name != "http.client" {
		t.Fatal("missing completed stream spans")
	}
	child, parent := spans[0], spans[1]
	if parent.EndTime.Before(firstRead) || parent.EndTime.Before(child.EndTime) || parent.StartTime.After(child.StartTime) {
		t.Fatal("client span does not cover the downstream stream lifetime")
	}
	if child.Parent.SpanID() != parent.SpanContext.SpanID() || child.SpanContext.TraceID() != parent.SpanContext.TraceID() {
		t.Fatal("stream parentage changed")
	}
}

func TestHTTPBodyTerminalEvents(t *testing.T) {
	secretError := errors.New("SYNTHETIC_RESPONSE_SECRET")
	for _, test := range []struct {
		name, errorType string
		readError       error
		closeError      error
		closeOnly       bool
	}{
		{name: "eof", readError: io.EOF},
		{name: "read failure", readError: secretError, errorType: "response_read_error"},
		{name: "truncated stream", readError: io.ErrUnexpectedEOF, errorType: "response_read_error"},
		{name: "cancelled read", readError: context.Canceled, errorType: "request_cancelled"},
		{name: "timed out read", readError: context.DeadlineExceeded, errorType: "request_timeout"},
		{name: "close without reading", closeOnly: true},
		{name: "close failure", closeOnly: true, closeError: secretError, errorType: "response_close_error"},
	} {
		t.Run(test.name, func(t *testing.T) {
			exporter := recorder(t)
			var closes int
			response := tracedResponse(t, context.Background(), responseBody{
				read:  func(p []byte) (int, error) { return copy(p, "x"), test.readError },
				close: func() error { closes++; return test.closeError },
			})
			if len(exporter.GetSpans()) != 0 {
				t.Fatal("span completed before the caller consumed or closed the body")
			}
			if !test.closeOnly {
				p := make([]byte, 3)
				n, err := response.Body.Read(p)
				if n != 1 || p[0] != 'x' || err != test.readError {
					t.Fatal("body read result changed")
				}
			}
			if err := response.Body.Close(); err != test.closeError || closes != 1 {
				t.Fatal("body close result changed")
			}
			spans := exporter.GetSpans()
			if len(spans) != 1 {
				t.Fatal("stream must end exactly once", len(spans))
			}
			assertHTTPError(t, spans[0], test.errorType)
		})
	}
}

func assertHTTPError(t *testing.T, span tracetest.SpanStub, errorType string) {
	t.Helper()
	if (span.Status.Code == codes.Error) != (errorType != "") {
		t.Fatal("incorrect stream error status", span.Status)
	}
	got := ""
	for _, attr := range span.Attributes {
		if strings.Contains(attr.Value.Emit(), "SYNTHETIC_RESPONSE_SECRET") {
			t.Fatal("body error text leaked")
		}
		if string(attr.Key) == "error.type" {
			got = attr.Value.AsString()
		}
	}
	if got != errorType {
		t.Fatal("incorrect fixed error classification", got, errorType)
	}
}

func TestHTTPCancellationEndsUnreadBody(t *testing.T) {
	exporter := recorder(t)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	response := tracedResponse(t, ctx, io.NopCloser(strings.NewReader("unread")))
	cancel()
	deadline := time.NewTimer(2 * time.Second)
	defer deadline.Stop()
	tick := time.NewTicker(time.Millisecond)
	defer tick.Stop()
	for len(exporter.GetSpans()) == 0 {
		select {
		case <-deadline.C:
			t.Fatal("cancelled unread response left its span open")
		case <-tick.C:
		}
	}
	assertHTTPError(t, exporter.GetSpans()[0], "request_cancelled")
	_ = response.Body.Close()
	if len(exporter.GetSpans()) != 1 {
		t.Fatal("close duplicated a cancelled span")
	}
}

func TestHTTPBodyConcurrentCompletion(t *testing.T) {
	exporter := recorder(t)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	var closes atomic.Int32
	response := tracedResponse(t, ctx, responseBody{
		read:  func([]byte) (int, error) { return 0, io.EOF },
		close: func() error { closes.Add(1); return nil },
	})
	var group sync.WaitGroup
	for range 20 {
		group.Go(func() { _, _ = response.Body.Read(make([]byte, 1)) })
		group.Go(func() { _ = response.Body.Close() })
	}
	group.Go(cancel)
	group.Wait()
	if len(exporter.GetSpans()) != 1 || closes.Load() != 20 {
		t.Fatal("completion duplicated spans or changed caller close operations")
	}
}

type duplexBody struct{ bytes.Buffer }

func (*duplexBody) Close() error { return nil }

func TestHTTPPreservesOptionalDuplexBody(t *testing.T) {
	exporter := recorder(t)
	duplex := &duplexBody{}
	response := tracedResponse(t, context.Background(), duplex)
	writer, ok := response.Body.(io.Writer)
	if !ok {
		t.Fatal("upgraded HTTP response lost io.Writer")
	}
	if n, err := writer.Write([]byte("upgrade bytes")); n != 13 || err != nil || duplex.String() != "upgrade bytes" {
		t.Fatal("duplex write changed", n, err)
	}
	if len(exporter.GetSpans()) != 0 {
		t.Fatal("upgrade span ended before close")
	}
	_ = response.Body.Close()
	plain := tracedResponse(t, context.Background(), io.NopCloser(strings.NewReader("plain")))
	if _, ok := plain.Body.(io.Writer); ok {
		t.Fatal("read-only response incorrectly advertises io.Writer")
	}
	_ = plain.Body.Close()
	if len(exporter.GetSpans()) != 2 {
		t.Fatal("duplex/plain spans not completed")
	}
}

func TestHTTPEmptyAndFailedResponse(t *testing.T) {
	for _, test := range []struct {
		name string
		body io.ReadCloser
		err  error
	}{
		{name: "NoBody", body: http.NoBody},
		{name: "nil body"},
		{name: "transport failure", err: errors.New("SYNTHETIC_RESPONSE_SECRET")},
	} {
		t.Run(test.name, func(t *testing.T) {
			exporter := recorder(t)
			transport := Transport{Base: roundTripFunc(func(*http.Request) (*http.Response, error) {
				if test.err != nil {
					return nil, test.err
				}
				return &http.Response{StatusCode: http.StatusNoContent, Body: test.body}, nil
			})}
			req, _ := http.NewRequest("HEAD", "http://localhost/empty", nil)
			response, err := transport.RoundTrip(req)
			if err != test.err || (err == nil && response.Body != test.body) {
				t.Fatal("empty/failed response contract changed")
			}
			spans := exporter.GetSpans()
			if len(spans) != 1 {
				t.Fatal("empty/failed response did not end immediately")
			}
			want := ""
			if test.err != nil {
				want = "transport_error"
			}
			assertHTTPError(t, spans[0], want)
		})
	}
}

func TestHTTPKeepsStatusErrorAndFirstCompletion(t *testing.T) {
	exporter := recorder(t)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	transport := Transport{Base: roundTripFunc(func(*http.Request) (*http.Response, error) {
		return &http.Response{StatusCode: http.StatusBadGateway, Body: responseBody{
			read:  func([]byte) (int, error) { return 0, io.EOF },
			close: func() error { return errors.New("SYNTHETIC_RESPONSE_SECRET") },
		}}, nil
	})}
	req, _ := http.NewRequestWithContext(ctx, "GET", "http://localhost/failure", nil)
	response, err := transport.RoundTrip(req)
	if err != nil {
		t.Fatal(err)
	}
	_, _ = response.Body.Read(make([]byte, 1))
	if len(exporter.GetSpans()) != 1 || exporter.GetSpans()[0].Status.Code != codes.Error {
		t.Fatal("body completion cleared the HTTP error")
	}
	ended := exporter.GetSpans()[0].EndTime
	_ = response.Body.Close()
	cancel()
	spans := exporter.GetSpans()
	if len(spans) != 1 || !spans[0].EndTime.Equal(ended) {
		t.Fatal("later close/cancel changed the completed span")
	}
	for _, attr := range spans[0].Attributes {
		if string(attr.Key) == "error.type" || strings.Contains(attr.Value.Emit(), "SYNTHETIC_RESPONSE_SECRET") {
			t.Fatal("late cleanup changed first-completion error metadata")
		}
	}
}

func TestHTTPDisabledTracingPreservesBody(t *testing.T) {
	previous := otel.GetTracerProvider()
	otel.SetTracerProvider(noop.NewTracerProvider())
	t.Cleanup(func() { otel.SetTracerProvider(previous) })
	body := io.NopCloser(strings.NewReader("unchanged"))
	response := tracedResponse(t, context.Background(), body)
	defer response.Body.Close()
	if response.Body != body {
		t.Fatal("disabled tracing wrapped the response body")
	}
}
