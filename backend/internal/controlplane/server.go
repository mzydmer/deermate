package controlplane

import (
	"context"
	"crypto/subtle"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net"
	"net/http"
	"net/url"
	"path"
	"regexp"
	"strings"
	"time"
)

type Config struct {
	RuntimeURL   string
	Origin       string
	AllowedHosts []string
	JWTSecret    string
	PasswordCost int
}
type Server struct {
	Store   *Store
	cfg     Config
	mux     *http.ServeMux
	engine  *runtimeAdapter
	dummy   string
	hashing chan struct{}
}
type sessionKey struct{}

func NewServer(store *Store, cfg Config) (*Server, error) {
	origin, err := url.Parse(cfg.Origin)
	if err != nil || origin.Host == "" || origin.User != nil || (origin.Scheme != "http" && origin.Scheme != "https") || origin.Path != "" || origin.RawQuery != "" {
		return nil, errors.New("invalid canonical origin")
	}
	if len(cfg.JWTSecret) < 32 {
		return nil, errors.New("runtime JWT secret must have at least 32 characters")
	}
	if cfg.PasswordCost == 0 {
		cfg.PasswordCost = 12
	}
	if len(cfg.AllowedHosts) == 0 {
		cfg.AllowedHosts = []string{origin.Host}
	}
	engine, err := newRuntime(cfg.RuntimeURL, cfg.JWTSecret)
	if err != nil {
		return nil, err
	}
	engine.publicScheme = origin.Scheme
	dummy, err := hashPassword(opaque(), cfg.PasswordCost)
	if err != nil {
		return nil, err
	}
	s := &Server{Store: store, cfg: cfg, mux: http.NewServeMux(), engine: engine, dummy: dummy, hashing: make(chan struct{}, 4)}
	s.routes()
	return s, nil
}

func respond(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if value != nil {
		_ = json.NewEncoder(w).Encode(value)
	}
}
func fail(w http.ResponseWriter, status int, code, message string) {
	respond(w, status, map[string]any{"detail": map[string]string{"code": code, "message": message}})
}
func storeError(w http.ResponseWriter, err error) {
	switch {
	case errors.Is(err, ErrNotFound):
		fail(w, 404, "not_found", "Record not found")
	case errors.Is(err, ErrConflict):
		fail(w, 409, "conflict", "The account already exists or changed")
	case errors.Is(err, ErrLastAdmin):
		fail(w, 409, "last_active_admin", "Keep at least one active administrator")
	case errors.Is(err, ErrCredentials):
		fail(w, 422, "invalid_input", "Check email, role and password (12–1024 bytes)")
	default:
		slog.Error("control plane persistence failed", "error", err)
		fail(w, 503, "storage_unavailable", "Account storage unavailable")
	}
}
func decode(w http.ResponseWriter, r *http.Request, dst any) bool {
	r.Body = http.MaxBytesReader(w, r.Body, 65536)
	d := json.NewDecoder(r.Body)
	d.DisallowUnknownFields()
	if err := d.Decode(dst); err != nil {
		fail(w, 422, "invalid_input", "Invalid JSON request")
		return false
	}
	var rest any
	if !errors.Is(d.Decode(&rest), io.EOF) {
		fail(w, 422, "invalid_input", "Expected one JSON object")
		return false
	}
	return true
}
func sessionOf(r *http.Request) Session { return r.Context().Value(sessionKey{}).(Session) }

func (s *Server) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("X-Content-Type-Options", "nosniff")
	w.Header().Set("X-DeerMate-Backend", "go")
	w.Header().Set("X-Request-ID", uuid())
	allowed := false
	for _, host := range s.cfg.AllowedHosts {
		if strings.EqualFold(host, r.Host) {
			allowed = true
		}
	}
	if !allowed {
		fail(w, 403, "host_rejected", "Unrecognized request host")
		return
	}
	p := r.URL.Path
	raw := strings.ToLower(r.URL.RawPath)
	if strings.ContainsAny(p, "\\\x00") || strings.Contains(raw, "%2f") || strings.Contains(raw, "%5c") || (p != "/" && path.Clean(p) != strings.TrimSuffix(p, "/")) {
		fail(w, 400, "invalid_path", "Noncanonical request path")
		return
	}
	if origin := r.Header.Get("Origin"); origin != "" {
		u, err := url.Parse(origin)
		canonical, _ := url.Parse(s.cfg.Origin)
		if err != nil || u.User != nil || u.Host != r.Host || u.Scheme != canonical.Scheme || u.Path != "" || u.RawQuery != "" || u.Fragment != "" {
			fail(w, 403, "origin_rejected", "Cross-origin requests are not allowed")
			return
		}
	}
	if r.Header.Get("Sec-Fetch-Site") == "cross-site" {
		fail(w, 403, "origin_rejected", "Cross-site requests are not allowed")
		return
	}
	s.mux.ServeHTTP(w, r)
}

func (s *Server) protected(admin bool, h http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "" {
			fail(w, 401, "token_invalid", "Bearer credentials are not supported on this browser API")
			return
		}
		cookie, err := r.Cookie("access_token")
		if err != nil {
			fail(w, 401, "not_authenticated", "Sign in required")
			return
		}
		session, err := s.Store.Session(cookie.Value)
		if err != nil {
			if errors.Is(err, ErrDisabled) {
				fail(w, 401, "account_disabled", "Account disabled")
			} else if errors.Is(err, ErrCredentials) || errors.Is(err, ErrNotFound) {
				fail(w, 401, "token_invalid", "Session expired or revoked")
			} else {
				storeError(w, err)
			}
			return
		}
		if admin && session.User.Role != "admin" {
			fail(w, 403, "admin_required", "Administrator permission required")
			return
		}
		if r.Method != "GET" && r.Method != "HEAD" && r.Method != "OPTIONS" {
			csrf, e := r.Cookie("csrf_token")
			header := r.Header.Get("X-CSRF-Token")
			if e != nil || len(header) != 43 || subtle.ConstantTimeCompare([]byte(header), []byte(csrf.Value)) != 1 || subtle.ConstantTimeCompare([]byte(digest(header)), []byte(session.CSRFHash)) != 1 {
				fail(w, 403, "csrf_rejected", "Session-bound CSRF token required")
				return
			}
		}
		h(w, r.WithContext(context.WithValue(r.Context(), sessionKey{}, session)))
	}
}

func (s *Server) routes() {
	s.mux.HandleFunc("GET /health/live", func(w http.ResponseWriter, r *http.Request) {
		respond(w, 200, map[string]string{"status": "ok", "backend": "go"})
	})
	s.mux.HandleFunc("GET /health/ready", s.ready)
	s.mux.HandleFunc("GET /health", s.ready)
	s.mux.HandleFunc("GET /api/v1/auth/setup-status", s.setup)
	s.mux.HandleFunc("GET /api/v1/auth/providers", func(w http.ResponseWriter, r *http.Request) { respond(w, 200, map[string]any{"providers": []any{}}) })
	s.mux.HandleFunc("POST /api/v1/auth/initialize", s.initialize)
	s.mux.HandleFunc("POST /api/v1/auth/login/local", s.login)
	s.mux.HandleFunc("POST /api/v1/auth/register", func(w http.ResponseWriter, r *http.Request) {
		fail(w, 403, "registration_disabled", "Ask an administrator to create an account")
	})
	s.mux.HandleFunc("GET /api/v1/auth/me", s.protected(false, func(w http.ResponseWriter, r *http.Request) { respond(w, 200, sessionOf(r).User) }))
	s.mux.HandleFunc("POST /api/v1/auth/logout", s.protected(false, s.logout))
	s.mux.HandleFunc("POST /api/v1/auth/change-password", s.protected(false, s.changePassword))
	s.mux.HandleFunc("GET /api/v1/auth/preferences", s.protected(false, s.preferences))
	s.mux.HandleFunc("PATCH /api/v1/auth/preferences", s.protected(false, s.preferences))
	s.mux.HandleFunc("GET /api/v1/auth/sessions", s.protected(false, func(w http.ResponseWriter, r *http.Request) {
		items, err := s.Store.SessionList(sessionOf(r).User.ID)
		if err != nil {
			storeError(w, err)
			return
		}
		respond(w, 200, items)
	}))
	s.mux.HandleFunc("DELETE /api/v1/auth/sessions/{id}", s.protected(false, func(w http.ResponseWriter, r *http.Request) {
		if err := s.Store.RevokeSession(sessionOf(r).User.ID, r.PathValue("id")); err != nil {
			storeError(w, err)
			return
		}
		respond(w, 200, map[string]string{"message": "Session revoked"})
	}))
	s.mux.HandleFunc("GET /api/v1/admin/users", s.protected(true, func(w http.ResponseWriter, r *http.Request) {
		users, err := s.Store.Users()
		if err != nil {
			storeError(w, err)
			return
		}
		respond(w, 200, users)
	}))
	s.mux.HandleFunc("POST /api/v1/admin/users", s.protected(true, s.createUser))
	s.mux.HandleFunc("PATCH /api/v1/admin/users/{id}", s.protected(true, s.updateUser))
	s.mux.HandleFunc("POST /api/v1/admin/users/{id}/password", s.protected(true, s.resetPassword))
	s.mux.HandleFunc("GET /api/v1/admin/audit", s.protected(true, func(w http.ResponseWriter, r *http.Request) {
		items, err := s.Store.Audits()
		if err != nil {
			storeError(w, err)
			return
		}
		respond(w, 200, items)
	}))
	s.mux.HandleFunc("GET /api/deermate/v1/info", s.protected(false, func(w http.ResponseWriter, r *http.Request) {
		respond(w, 200, map[string]any{"backend": "go", "version": "0.2.0-dev", "admin_url": "/admin", "agent_runtime": "deerflow-python", "worker": "python-codex", "regular_user_execution": false})
	}))
	s.mux.HandleFunc("GET /api/deermate/v1/workspace", s.protected(false, s.workspace))
	s.mux.HandleFunc("/api/v1/auth/", func(w http.ResponseWriter, r *http.Request) {
		fail(w, 501, "auth_feature_unavailable", "This authentication feature is not enabled in the Go control plane")
	})
	s.mux.HandleFunc("/api/v1/admin/", s.protected(true, func(w http.ResponseWriter, r *http.Request) { fail(w, 404, "not_found", "Unknown management endpoint") }))
	s.mux.HandleFunc("GET /admin", s.protected(true, s.adminPage))
	s.mux.HandleFunc("/api/", s.protected(false, s.proxy))
	s.mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		fail(w, 404, "not_found", "Unknown control-plane endpoint")
	})
}

func (s *Server) ready(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 3*time.Second)
	defer cancel()
	if s.Store.DB.PingContext(ctx) != nil || !s.engine.ready(ctx) {
		fail(w, 503, "not_ready", "Control plane or runtime not ready")
		return
	}
	respond(w, 200, map[string]string{"status": "ok", "backend": "go", "runtime": "deerflow"})
}
func (s *Server) setup(w http.ResponseWriter, r *http.Request) {
	initialized, err := s.Store.Initialized()
	if err != nil {
		storeError(w, err)
		return
	}
	respond(w, 200, map[string]bool{"needs_setup": !initialized, "registration_enabled": false})
}
func (s *Server) hashingSlot(w http.ResponseWriter, r *http.Request) bool {
	select {
	case s.hashing <- struct{}{}:
		return true
	case <-r.Context().Done():
		return false
	default:
		fail(w, 429, "busy", "Authentication busy; retry shortly")
		return false
	}
}

func (s *Server) cookies(w http.ResponseWriter, raw, csrf string, remember bool) {
	secure := strings.HasPrefix(s.cfg.Origin, "https://")
	age := 0
	if remember {
		age = 7 * 86400
	}
	for _, cookie := range []*http.Cookie{{Name: "access_token", Value: raw, HttpOnly: true}, {Name: "csrf_token", Value: csrf}, {Name: "deerflow_session_persistent", Value: map[bool]string{true: "1", false: "0"}[remember], HttpOnly: true}} {
		cookie.Path = "/"
		cookie.SameSite = http.SameSiteLaxMode
		cookie.Secure = secure
		cookie.MaxAge = age
		http.SetCookie(w, cookie)
	}
}
func (s *Server) clearCookies(w http.ResponseWriter) {
	for _, name := range []string{"access_token", "csrf_token", "deerflow_session_persistent"} {
		http.SetCookie(w, &http.Cookie{Name: name, Value: "", Path: "/", HttpOnly: name != "csrf_token", Secure: strings.HasPrefix(s.cfg.Origin, "https://"), SameSite: http.SameSiteLaxMode, MaxAge: -1})
	}
}

func (s *Server) initialize(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Email    string `json:"email"`
		Password string `json:"password"`
	}
	if !decode(w, r, &body) || !s.hashingSlot(w, r) {
		return
	}
	defer func() { <-s.hashing }()
	u, err := s.Store.CreateUser(r.Context(), body.Email, body.Password, "admin", "bootstrap", true, s.cfg.PasswordCost)
	if err != nil {
		storeError(w, err)
		return
	}
	raw, csrf, err := s.Store.NewSession(r.Context(), u, 7*24*time.Hour)
	if err != nil {
		storeError(w, err)
		return
	}
	s.cookies(w, raw, csrf, true)
	respond(w, 201, u)
}
func (s *Server) login(w http.ResponseWriter, r *http.Request) {
	r.Body = http.MaxBytesReader(w, r.Body, 65536)
	if err := r.ParseForm(); err != nil {
		fail(w, 422, "invalid_input", "Invalid login form")
		return
	}
	email := strings.ToLower(strings.TrimSpace(r.PostForm.Get("username")))
	password := r.PostForm.Get("password")
	if len(email) > 320 || len(password) > 1024 {
		fail(w, 401, "invalid_credentials", "Incorrect email or password")
		return
	}
	ip, _, _ := net.SplitHostPort(r.RemoteAddr)
	key := digest(ip + "\x00" + email)
	allowed, err := s.Store.LoginAllowed(key)
	if err != nil {
		storeError(w, err)
		return
	}
	if !allowed {
		w.Header().Set("Retry-After", "600")
		fail(w, 429, "rate_limited", "Too many failed sign-in attempts")
		return
	}
	if !s.hashingSlot(w, r) {
		return
	}
	defer func() { <-s.hashing }()
	u, err := s.Store.UserByEmail(email)
	valid := false
	if err == nil && !u.Disabled && u.Password != "" {
		valid = verifyPassword(password, u.Password)
	} else {
		_ = verifyPassword(password, s.dummy)
	}
	if !valid {
		if e := s.Store.LoginFailure(key); e != nil {
			storeError(w, e)
			return
		}
		fail(w, 401, "invalid_credentials", "Incorrect email or password")
		return
	}
	remember := r.PostForm.Get("remember_me") == "true" || r.PostForm.Get("remember_me") == "1"
	lifetime := 8 * time.Hour
	if remember {
		lifetime = 7 * 24 * time.Hour
	}
	raw, csrf, err := s.Store.NewSession(r.Context(), u, lifetime)
	if err != nil {
		storeError(w, err)
		return
	}
	if err = s.Store.LoginSuccess(key); err != nil {
		storeError(w, err)
		return
	}
	s.cookies(w, raw, csrf, remember)
	respond(w, 200, map[string]any{"expires_in": int(lifetime.Seconds()), "needs_setup": u.NeedsSetup})
}
func (s *Server) logout(w http.ResponseWriter, r *http.Request) {
	if err := s.Store.Logout(r.Context(), sessionOf(r)); err != nil {
		storeError(w, err)
		return
	}
	s.clearCookies(w)
	respond(w, 200, map[string]string{"message": "Signed out"})
}
func (s *Server) changePassword(w http.ResponseWriter, r *http.Request) {
	var b struct {
		Old   string  `json:"old_password"`
		New   string  `json:"new_password"`
		Email *string `json:"new_email"`
	}
	if !decode(w, r, &b) || !s.hashingSlot(w, r) {
		return
	}
	defer func() { <-s.hashing }()
	u := sessionOf(r).User
	if b.Email != nil && strings.ToLower(*b.Email) != u.Email {
		fail(w, 422, "email_change_unavailable", "Email changes are not enabled in this migration")
		return
	}
	if !verifyPassword(b.Old, u.Password) {
		fail(w, 401, "invalid_credentials", "Incorrect current password")
		return
	}
	if err := s.Store.SetPassword(r.Context(), u.ID, b.New, u.ID, u.Version, s.cfg.PasswordCost); err != nil {
		storeError(w, err)
		return
	}
	s.clearCookies(w)
	respond(w, 200, map[string]string{"message": "Password changed; sign in again"})
}
func (s *Server) createUser(w http.ResponseWriter, r *http.Request) {
	var b struct {
		Email    string `json:"email"`
		Password string `json:"password"`
		Role     string `json:"system_role"`
	}
	if !decode(w, r, &b) || !s.hashingSlot(w, r) {
		return
	}
	defer func() { <-s.hashing }()
	if b.Role == "" {
		b.Role = "user"
	}
	u, err := s.Store.CreateUser(r.Context(), b.Email, b.Password, b.Role, sessionOf(r).User.ID, false, s.cfg.PasswordCost)
	if err != nil {
		storeError(w, err)
		return
	}
	respond(w, 201, u)
}
func (s *Server) updateUser(w http.ResponseWriter, r *http.Request) {
	var b struct {
		Role     *string `json:"system_role"`
		Disabled *bool   `json:"disabled"`
	}
	if !decode(w, r, &b) {
		return
	}
	u, err := s.Store.UpdateUser(r.Context(), r.PathValue("id"), b.Role, b.Disabled, sessionOf(r).User.ID)
	if err != nil {
		storeError(w, err)
		return
	}
	respond(w, 200, u)
}
func (s *Server) resetPassword(w http.ResponseWriter, r *http.Request) {
	var b struct {
		Password string `json:"password"`
	}
	if !decode(w, r, &b) || !s.hashingSlot(w, r) {
		return
	}
	defer func() { <-s.hashing }()
	if err := s.Store.SetPassword(r.Context(), r.PathValue("id"), b.Password, sessionOf(r).User.ID, -1, s.cfg.PasswordCost); err != nil {
		storeError(w, err)
		return
	}
	respond(w, 200, map[string]string{"message": "Password reset; sessions revoked"})
}

var effortPattern = regexp.MustCompile(`^[A-Za-z0-9_.-]{1,32}$`)

func (s *Server) preferences(w http.ResponseWriter, r *http.Request) {
	id := sessionOf(r).User.ID
	if r.Header.Get("X-Expected-User-Id") != id {
		fail(w, 409, "account_changed", "The signed-in account changed; reload")
		return
	}
	if r.Method == "GET" {
		values, err := s.Store.Preferences(id)
		if err != nil {
			storeError(w, err)
			return
		}
		respond(w, 200, values)
		return
	}
	var values map[string]any
	if !decode(w, r, &values) {
		return
	}
	for k, v := range values {
		valid := false
		if v == nil {
			valid = map[string]bool{"notification_enabled": true, "model_name": true, "mode": true, "reasoning_effort": true, "locale": true}[k]
		} else {
			switch k {
			case "notification_enabled":
				_, valid = v.(bool)
			case "model_name":
				str, ok := v.(string)
				valid = ok && len(str) <= 200
			case "mode":
				str, ok := v.(string)
				valid = ok && map[string]bool{"flash": true, "thinking": true, "pro": true, "ultra": true}[str]
			case "reasoning_effort":
				str, ok := v.(string)
				valid = ok && effortPattern.MatchString(str)
			case "locale":
				valid = v == "zh-CN" || v == "en-US"
			}
		}
		if !valid {
			fail(w, 422, "invalid_input", "Invalid preference key or value")
			return
		}
	}
	if err := s.Store.SetPreferences(r.Context(), id, values); err != nil {
		storeError(w, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (s *Server) proxy(w http.ResponseWriter, r *http.Request) {
	u := sessionOf(r).User
	if u.NeedsSetup {
		fail(w, 403, "setup_required", "Complete password setup first")
		return
	}
	if u.Role != "admin" && !regularRead(r) {
		fail(w, 403, "permission_denied", "This account has read-only runtime access; execution/configuration requires an administrator")
		return
	}
	r.Body = http.MaxBytesReader(w, r.Body, 64<<20)
	// Revoke existing streams within five seconds. This closes access; it does
	// not assert that an already-admitted native task has stopped.
	ctx, cancel := context.WithCancel(r.Context())
	defer cancel()
	raw, _ := r.Cookie("access_token")
	go func() {
		ticker := time.NewTicker(5 * time.Second)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				if _, err := s.Store.Session(raw.Value); err != nil {
					cancel()
					return
				}
			}
		}
	}()
	s.engine.proxy.ServeHTTP(w, r.WithContext(ctx))
}
func regularRead(r *http.Request) bool {
	p := r.URL.Path
	if r.Method == "POST" && p == "/api/threads/search" {
		return true
	}
	if r.Method != "GET" && r.Method != "HEAD" {
		return false
	}
	if p == "/api/models" || p == "/api/features" || p == "/api/agents" {
		return true
	}
	if !strings.HasPrefix(p, "/api/threads/") {
		return false
	}
	parts := strings.Split(strings.TrimPrefix(p, "/api/threads/"), "/")
	if !resourceID.MatchString(parts[0]) {
		return false
	}
	if len(parts) == 1 {
		return true
	}
	if len(parts) == 2 {
		return parts[1] == "state" || parts[1] == "goal" || parts[1] == "mcp-tasks"
	}
	return len(parts) == 3 && parts[1] == "mcp-tasks" && resourceID.MatchString(parts[2])
}

var resourceID = regexp.MustCompile(`^[A-Za-z0-9_-]{1,64}$`)
