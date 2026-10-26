package controlplane

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httputil"
	"net/url"
	"strings"
	"time"
)

// runtimeAdapter is an identity-preserving boundary, never an internal/admin principal.
type runtimeAdapter struct {
	url          *url.URL
	secret       []byte
	proxy        *httputil.ReverseProxy
	client       *http.Client
	publicScheme string
}

func newRuntime(address, secret string) (*runtimeAdapter, error) {
	u, err := url.Parse(address)
	if err != nil || u.Host == "" || u.User != nil || (u.Scheme != "http" && u.Scheme != "https") || u.Path != "" || u.RawQuery != "" || u.Fragment != "" {
		return nil, fmt.Errorf("invalid runtime origin")
	}
	// Do not retry mutations with Idempotency-Key on stale pooled connections.
	transport := &http.Transport{Proxy: nil, DisableKeepAlives: true, ResponseHeaderTimeout: 30 * time.Second}
	a := &runtimeAdapter{url: u, secret: []byte(secret), client: &http.Client{Transport: transport, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}}
	a.proxy = &httputil.ReverseProxy{Transport: transport, FlushInterval: -1, Rewrite: func(p *httputil.ProxyRequest) {
		p.SetURL(a.url)
		p.Out.Host = p.In.Host
		a.identity(p.Out, sessionOf(p.In).User, p.In)
	}, ModifyResponse: func(r *http.Response) error {
		r.Header.Del("Set-Cookie")
		r.Header.Set("Cache-Control", "no-store")
		return nil
	}, ErrorHandler: func(w http.ResponseWriter, r *http.Request, e error) {
		fail(w, 502, "runtime_unavailable", "Agent runtime unavailable; inspect task state before retrying mutations")
	}}
	return a, nil
}
func (a *runtimeAdapter) token(u User) string {
	header := base64.RawURLEncoding.EncodeToString([]byte(`{"alg":"HS256","typ":"JWT"}`))
	payload, _ := json.Marshal(map[string]any{"sub": u.ID, "iat": time.Now().Unix(), "exp": time.Now().Add(time.Minute).Unix(), "ver": u.Version})
	content := header + "." + base64.RawURLEncoding.EncodeToString(payload)
	mac := hmac.New(sha256.New, a.secret)
	_, _ = mac.Write([]byte(content))
	return content + "." + base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
}
func (a *runtimeAdapter) identity(out *http.Request, u User, in *http.Request) {
	for key := range out.Header {
		lower := strings.ToLower(key)
		if strings.HasPrefix(lower, "x-forwarded-") || strings.HasPrefix(lower, "x-deerflow-internal-") {
			out.Header.Del(key)
			continue
		}
		switch http.CanonicalHeaderKey(key) {
		case "Authorization", "Cookie", "Forwarded", "X-Forwarded-For", "X-Forwarded-Host", "X-Forwarded-Proto", "X-Deerflow-Internal-Token", "X-User-Id", "X-Owner-Id", "X-Deermate-Owner":
			out.Header.Del(key)
		}
	}
	// This scheme comes from operator configuration, never a client proxy header.
	if a.publicScheme != "" {
		out.Header.Set("X-Forwarded-Proto", a.publicScheme)
	}
	out.AddCookie(&http.Cookie{Name: "access_token", Value: a.token(u)})
	// Runtime CSRF validates its own cookie/header pair. Go has already bound it to this session.
	for _, name := range []string{"csrf_token", "deerflow_locale"} {
		if c, err := in.Cookie(name); err == nil {
			out.AddCookie(c)
		}
	}
}
func (a *runtimeAdapter) ready(ctx context.Context) bool {
	r, _ := http.NewRequestWithContext(ctx, "GET", a.url.String()+"/health/ready", nil)
	resp, err := a.client.Do(r)
	if err != nil {
		return false
	}
	defer resp.Body.Close()
	return resp.StatusCode == 200
}
func (a *runtimeAdapter) query(ctx context.Context, in *http.Request, method, path string, body []byte) (json.RawMessage, error) {
	req, err := http.NewRequestWithContext(ctx, method, a.url.String()+path, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	req.Host = in.Host
	req.Header = in.Header.Clone()
	a.identity(req, sessionOf(in).User, in)
	req.Header.Set("Content-Type", "application/json")
	if c, e := in.Cookie("csrf_token"); e == nil {
		req.Header.Set("X-CSRF-Token", c.Value)
	}
	response, err := a.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	if response.StatusCode != 200 {
		return nil, fmt.Errorf("runtime status %d", response.StatusCode)
	}
	data, err := io.ReadAll(io.LimitReader(response.Body, 2<<20))
	if err != nil || !json.Valid(data) {
		return nil, fmt.Errorf("invalid or oversized runtime response")
	}
	return json.RawMessage(data), nil
}
func (s *Server) workspace(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
	defer cancel()
	threads, err := s.engine.query(ctx, r, "POST", "/api/threads/search", []byte(`{"limit":20}`))
	if err != nil {
		fail(w, 502, "runtime_unavailable", "Could not read workspace threads")
		return
	}
	// This bounded summary intentionally excludes private message bodies and host paths.
	var records []struct {
		ID       string         `json:"thread_id"`
		Updated  string         `json:"updated_at"`
		Metadata map[string]any `json:"metadata"`
	}
	if json.Unmarshal(threads, &records) != nil {
		fail(w, 502, "runtime_contract", "Unexpected thread response")
		return
	}
	out := []map[string]any{}
	for _, thread := range records {
		if len(out) >= 20 {
			break
		}
		title, _ := thread.Metadata["title"].(string)
		out = append(out, map[string]any{"thread_id": thread.ID, "title": title, "updated_at": thread.Updated})
	}
	respond(w, 200, map[string]any{"user": sessionOf(r).User, "threads": out, "runtime": "deerflow", "execution_enabled": sessionOf(r).User.Role == "admin"})
}
