package observability

import (
	"context"
	"errors"
	"io"
	"net/http"
	"sync"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
)

// Transport never records URLs, query strings, bodies, headers or exception text.
type Transport struct{ Base http.RoundTripper }

func (t Transport) RoundTrip(r *http.Request) (*http.Response, error) {
	ctx, span := Start(r.Context(), "http.client", nil)
	var once sync.Once
	end := func(err error, errorType string) {
		once.Do(func() {
			if err != nil {
				switch {
				case errors.Is(err, context.Canceled):
					errorType = "request_cancelled"
				case errors.Is(err, context.DeadlineExceeded):
					errorType = "request_timeout"
				}
				span.SetAttributes(attribute.String("error.type", errorType))
				span.SetStatus(codes.Error, "")
			}
			span.End()
		})
	}
	handedOff := false
	defer func() {
		// Covers empty responses, transport errors and a propagating panic.
		if !handedOff {
			end(nil, "")
		}
	}()
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
		end(err, "transport_error")
		return response, err
	}
	if response == nil || response.Body == nil || response.Body == http.NoBody || !span.IsRecording() {
		return response, nil
	}
	// RoundTrip returns at headers. Keep the span alive for the response stream,
	// including cancellation when the caller never reads/closes the body.
	stop := context.AfterFunc(ctx, func() { end(ctx.Err(), "request_cancelled") })
	body := &tracedBody{ReadCloser: response.Body, finish: func(err error, kind string) {
		stop()
		end(err, kind)
	}}
	if writer, ok := response.Body.(io.Writer); ok {
		// net/http promises io.Writer for upgraded (101) response bodies.
		response.Body = &tracedDuplexBody{tracedBody: body, writer: writer}
	} else {
		response.Body = body
	}
	handedOff = true
	return response, nil
}

type tracedBody struct {
	io.ReadCloser
	finish func(error, string)
}

func (b *tracedBody) Read(p []byte) (int, error) {
	n, err := b.ReadCloser.Read(p)
	if err == io.EOF {
		b.finish(nil, "")
	} else if err != nil {
		b.finish(err, "response_read_error")
	}
	return n, err
}

func (b *tracedBody) Close() error {
	err := b.ReadCloser.Close()
	b.finish(err, "response_close_error")
	return err
}

type tracedDuplexBody struct {
	*tracedBody
	writer io.Writer
}

func (b *tracedDuplexBody) Write(p []byte) (int, error) {
	n, err := b.writer.Write(p)
	if err != nil {
		b.finish(err, "response_write_error")
	}
	return n, err
}
