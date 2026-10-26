package controlplane

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"golang.org/x/crypto/bcrypt"
)

const testPassword = "fixture-strong-password"

func testStore(t *testing.T) *Store {
	t.Helper()
	s, err := OpenStore(filepath.Join(t.TempDir(), "runtime.db"))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { s.DB.Close() })
	return s
}
func account(t *testing.T, s *Store, email, role string) User {
	t.Helper()
	u, err := s.CreateUser(context.Background(), email, testPassword, role, "test", false, bcrypt.MinCost)
	if err != nil {
		t.Fatal(err)
	}
	return u
}
func testServer(t *testing.T, s *Store, runtime http.HandlerFunc) *Server {
	t.Helper()
	up := httptest.NewServer(runtime)
	t.Cleanup(up.Close)
	server, err := NewServer(s, Config{RuntimeURL: up.URL, JWTSecret: strings.Repeat("secret", 8), Origin: "http://example.test", PasswordCost: bcrypt.MinCost})
	if err != nil {
		t.Fatal(err)
	}
	return server
}

type browser struct{ raw, csrf string }

func session(t *testing.T, s *Store, u User) browser {
	t.Helper()
	raw, csrf, err := s.NewSession(context.Background(), u, time.Hour)
	if err != nil {
		t.Fatal(err)
	}
	return browser{raw, csrf}
}
func request(s http.Handler, b browser, method, path, body string, headers map[string]string) *httptest.ResponseRecorder {
	r := httptest.NewRequest(method, "http://example.test"+path, strings.NewReader(body))
	r.Header.Set("Content-Type", "application/json")
	if b.raw != "" {
		r.AddCookie(&http.Cookie{Name: "access_token", Value: b.raw})
		r.AddCookie(&http.Cookie{Name: "csrf_token", Value: b.csrf})
		r.Header.Set("X-CSRF-Token", b.csrf)
	}
	for k, v := range headers {
		r.Header.Set(k, v)
	}
	w := httptest.NewRecorder()
	s.ServeHTTP(w, r)
	return w
}
func requireStatus(t *testing.T, w *httptest.ResponseRecorder, status int) {
	t.Helper()
	if w.Code != status {
		t.Fatalf("status %d != %d: %s", w.Code, status, w.Body.String())
	}
}
func TestPythonPasswordAndSessionPersistence(t *testing.T) {
	s := testStore(t)
	fixture := "$dfv2$$2b$04$2l39Ecc7LPhTXbxuQNF3G.HJ4fv9qBLKDIJhh/As9I8T8JzMJFCHu"
	if !verifyPassword("fixture-兼容-password", fixture) || verifyPassword("wrong", fixture) {
		t.Fatal("Python dfv2 incompatibility")
	}
	legacy, _ := bcrypt.GenerateFromPassword([]byte(testPassword), 4)
	for _, h := range []string{string(legacy), "$dfv1$" + string(legacy)} {
		if !verifyPassword(testPassword, h) {
			t.Fatal("legacy password rejected")
		}
	}
	u := account(t, s, "owner@example.com", "admin")
	b := session(t, s, u)
	var value string
	if err := s.DB.QueryRow("SELECT token_hash FROM deermate_sessions").Scan(&value); err != nil || value == b.raw {
		t.Fatal("raw session persisted")
	}
	var filename string
	var seq int
	var name string
	if err := s.DB.QueryRow("PRAGMA database_list").Scan(&seq, &name, &filename); err != nil {
		t.Fatal(err)
	}
	s.DB.Close()
	other, err := OpenStore(filename)
	if err != nil {
		t.Fatal(err)
	}
	defer other.DB.Close()
	current, err := other.Session(b.raw)
	if err != nil || current.User.ID != u.ID {
		t.Fatal("session lost on restart", err)
	}
	if err = other.Logout(context.Background(), current); err != nil {
		t.Fatal(err)
	}
	if _, err = other.Session(b.raw); !errors.Is(err, ErrCredentials) {
		t.Fatal("logout failed")
	}
}
func TestAtomicBootstrapAndLastAdmin(t *testing.T) {
	s := testStore(t)
	var seq int
	var name, filename string
	if err := s.DB.QueryRow("PRAGMA database_list").Scan(&seq, &name, &filename); err != nil {
		t.Fatal(err)
	}
	second, err := OpenStore(filename)
	if err != nil {
		t.Fatal(err)
	}
	defer second.DB.Close()
	var wg sync.WaitGroup
	var mu sync.Mutex
	success := 0
	for i := range 8 {
		wg.Go(func() {
			store := s
			if i%2 == 0 {
				store = second
			}
			_, err := store.CreateUser(context.Background(), strings.Repeat("a", i+1)+"@example.com", testPassword, "admin", "bootstrap", true, 4)
			if err == nil {
				mu.Lock()
				success++
				mu.Unlock()
			} else if !errors.Is(err, ErrConflict) {
				t.Error(err)
			}
		})
	}
	wg.Wait()
	if success != 1 {
		t.Fatalf("bootstrap count %d", success)
	}
	users, _ := s.Users()
	a := users[0]
	b := account(t, s, "second@example.com", "admin")
	disabled := true
	success = 0
	for _, id := range []string{a.ID, b.ID} {
		wg.Go(func() {
			_, err := s.UpdateUser(context.Background(), id, nil, &disabled, "test")
			if err == nil {
				mu.Lock()
				success++
				mu.Unlock()
			} else if !errors.Is(err, ErrLastAdmin) {
				t.Error(err)
			}
		})
	}
	wg.Wait()
	if success != 1 {
		t.Fatalf("disabled %d admins", success)
	}
}

func TestRuntimeReadAllowlistAndEmailCompatibility(t *testing.T) {
	for _, p := range []string{"/api/threads/a/browser", "/api/threads/a/browser/stream", "/api/threads/a/runs", "/api/threads/a/files/secrets", "/api/v1/auth/me"} {
		if regularRead(httptest.NewRequest("GET", p, nil)) {
			t.Error("unexpected regular-user route", p)
		}
	}
	for _, email := range []string{"a@example.invalid", "a@localhost", "a@host.test", "a@-example.com", "a..b@example.com"} {
		if validEmail(email) {
			t.Error("accepted runtime-incompatible email", email)
		}
	}
	for _, email := range []string{"a@example.com", "owner+deermate@example.org"} {
		if !validEmail(email) {
			t.Error("rejected email", email)
		}
	}
}

func TestRevokedSessionClosesStream(t *testing.T) {
	s := testStore(t)
	u := account(t, s, "owner@example.com", "admin")
	b := session(t, s, u)
	server := testServer(t, s, func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		io.WriteString(w, "data: started\n\n")
		w.(http.Flusher).Flush()
		<-r.Context().Done()
	})
	public := httptest.NewServer(server)
	defer public.Close()
	req, _ := http.NewRequest("GET", public.URL+"/api/threads/a/stream", nil)
	req.Host = "example.test"
	req.AddCookie(&http.Cookie{Name: "access_token", Value: b.raw})
	client := &http.Client{Timeout: 8 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	buffer := make([]byte, 15)
	if _, err = io.ReadFull(resp.Body, buffer); err != nil {
		t.Fatal(err)
	}
	if err = s.RevokeSession(u.ID, digest(b.raw)); err != nil {
		t.Fatal(err)
	}
	started := time.Now()
	_, _ = io.ReadAll(resp.Body)
	if time.Since(started) > 7*time.Second {
		t.Fatal("revoked stream did not close")
	}
}
func TestAuthCSRFAndAdminLifecycle(t *testing.T) {
	s := testStore(t)
	owner := account(t, s, "owner@example.com", "admin")
	b := session(t, s, owner)
	server := testServer(t, s, func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(200) })
	requireStatus(t, request(server, b, "GET", "/api/v1/auth/me", "", nil), 200)
	requireStatus(t, request(server, b, "GET", "/api/v1/auth/me", "", map[string]string{"Origin": "http://evil.test"}), 403)
	requireStatus(t, request(server, b, "GET", "/api/v1/auth/me", "", map[string]string{"Authorization": "Bearer forged"}), 401)
	requireStatus(t, request(server, b, "POST", "/api/v1/admin/users", `{"email":"reader@example.com","password":"fixture-strong-password"}`, map[string]string{"X-CSRF-Token": "wrong"}), 403)
	created := request(server, b, "POST", "/api/v1/admin/users", `{"email":"reader@example.com","password":"fixture-strong-password"}`, nil)
	requireStatus(t, created, 201)
	if strings.Contains(created.Body.String(), "password") {
		t.Fatal("hash leaked")
	}
	var reader User
	json.Unmarshal(created.Body.Bytes(), &reader)
	r := session(t, s, reader)
	requireStatus(t, request(server, r, "GET", "/api/v1/admin/users", "", nil), 403)
	requireStatus(t, request(server, r, "POST", "/api/threads", `{}`, nil), 403)
	requireStatus(t, request(server, r, "GET", "/api/mcp/servers", "", nil), 403)
	requireStatus(t, request(server, b, "PATCH", "/api/v1/admin/users/"+owner.ID, `{"disabled":true}`, nil), 409)
	requireStatus(t, request(server, b, "PATCH", "/api/v1/admin/users/"+reader.ID, `{"disabled":true}`, nil), 200)
	requireStatus(t, request(server, r, "GET", "/api/v1/auth/me", "", nil), 401)
	requireStatus(t, request(server, b, "PATCH", "/api/v1/admin/users/"+reader.ID, `{"disabled":false}`, nil), 200)
	reader, _ = s.User(reader.ID)
	r = session(t, s, reader)
	requireStatus(t, request(server, b, "POST", "/api/v1/admin/users/"+reader.ID+"/password", `{"password":"replacement-strong-pass"}`, nil), 200)
	requireStatus(t, request(server, r, "GET", "/api/v1/auth/me", "", nil), 401)
	requireStatus(t, request(server, b, "GET", "/api/v1/auth/preferences", "", map[string]string{"X-Expected-User-Id": "wrong"}), 409)
	requireStatus(t, request(server, b, "PATCH", "/api/v1/auth/preferences", `{"locale":"zh-CN"}`, map[string]string{"X-Expected-User-Id": owner.ID}), 204)
	requireStatus(t, request(server, b, "POST", "/api/v1/auth/logout", `{}`, nil), 200)
	requireStatus(t, request(server, b, "GET", "/api/v1/auth/me", "", nil), 401)
}
func TestProxyIdentityStreamingAndNoCredentialLeak(t *testing.T) {
	s := testStore(t)
	owner := account(t, s, "owner@example.com", "admin")
	b := session(t, s, owner)
	calls := 0
	server := testServer(t, s, func(w http.ResponseWriter, r *http.Request) {
		calls++
		if r.Header.Get("X-DeerFlow-Internal-Token") != "" || r.Header.Get("Authorization") != "" || r.Header.Get("X-User-Id") != "" {
			t.Error("forged identity reached runtime")
		}
		c, err := r.Cookie("access_token")
		if err != nil || c.Value == b.raw {
			t.Error("bridge credential missing")
		}
		parts := strings.Split(c.Value, ".")
		payload, _ := base64Decode(parts[1])
		var claims map[string]any
		json.Unmarshal(payload, &claims)
		if claims["sub"] != owner.ID || claims["ver"] != float64(owner.Version) {
			t.Error("wrong runtime identity")
		}
		if r.Host != "example.test" {
			t.Error("host not preserved")
		}
		http.SetCookie(w, &http.Cookie{Name: "access_token", Value: "engine-secret"})
		w.Header().Set("Content-Type", "text/event-stream")
		io.WriteString(w, "data: first\n\n")
		w.(http.Flusher).Flush()
		io.WriteString(w, "data: second\n\n")
	})
	response := request(server, b, "GET", "/api/threads/a/runs/stream", "", map[string]string{"X-DeerFlow-Internal-Token": "forged", "X-User-Id": "internal"})
	requireStatus(t, response, 200)
	if response.Header().Get("Set-Cookie") != "" || !strings.Contains(response.Body.String(), "second") {
		t.Fatal("stream or credential boundary broken")
	}
	requireStatus(t, request(server, b, "GET", "/api/../api/v1/admin/users", "", nil), 400)
	if calls != 1 {
		t.Fatal("path bypass reached runtime")
	}
}
func base64Decode(v string) ([]byte, error) { return base64.RawURLEncoding.DecodeString(v) }
func TestLoginThrottleAndPasswordChange(t *testing.T) {
	s := testStore(t)
	owner := account(t, s, "owner@example.com", "admin")
	server := testServer(t, s, func(w http.ResponseWriter, r *http.Request) {})
	login := func(password string) *httptest.ResponseRecorder {
		return request(server, browser{}, "POST", "/api/v1/auth/login/local", url.Values{"username": {owner.Email}, "password": {password}}.Encode(), map[string]string{"Content-Type": "application/x-www-form-urlencoded"})
	}
	ok := login(testPassword)
	requireStatus(t, ok, 200)
	var b browser
	for _, c := range ok.Result().Cookies() {
		if c.Name == "access_token" {
			b.raw = c.Value
		}
		if c.Name == "csrf_token" {
			b.csrf = c.Value
		}
	}
	requireStatus(t, request(server, b, "POST", "/api/v1/auth/change-password", `{"old_password":"fixture-strong-password","new_password":"new-strong-fixture-password"}`, nil), 200)
	requireStatus(t, request(server, b, "GET", "/api/v1/auth/me", "", nil), 401)
	for range 7 {
		requireStatus(t, login("incorrect"), 401)
	}
	requireStatus(t, login("new-strong-fixture-password"), 429)
}
