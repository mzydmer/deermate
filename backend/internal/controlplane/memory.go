package controlplane

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"strings"
	"time"
)

func (s *Server) memoryRoutes() {
	for _, method := range []string{"GET", "PATCH"} {
		s.mux.HandleFunc(method+" /api/me/personal-profile", s.protected(false, s.personalProfile))
	}
	s.mux.HandleFunc("GET /api/me/memories", s.protected(false, s.memories))
	s.mux.HandleFunc("POST /api/me/memories/search", s.protected(false, s.memories))
	s.mux.HandleFunc("POST /api/me/memories", s.protected(false, s.mutateMemory))
	s.mux.HandleFunc("PATCH /api/me/memories/{id}", s.protected(false, s.mutateMemory))
	s.mux.HandleFunc("DELETE /api/me/memories/{id}", s.protected(false, s.mutateMemory))
	s.mux.HandleFunc("GET /api/me/memory-operations/{id}", s.protected(false, func(w http.ResponseWriter, r *http.Request) {
		if !personalAccess(w, r) {
			return
		}
		op, err := s.Store.MemoryOperation(sessionOf(r).User.ID, r.PathValue("id"))
		if err != nil {
			storeError(w, err)
			return
		}
		respond(w, 200, op)
	}))
	s.mux.HandleFunc("/api/me/", s.protected(false, func(w http.ResponseWriter, r *http.Request) { fail(w, 404, "not_found", "Unknown personal endpoint") }))
}

func personalAccess(w http.ResponseWriter, r *http.Request) bool {
	u := sessionOf(r).User
	if u.NeedsSetup {
		fail(w, 403, "setup_required", "Complete password setup first")
		return false
	}
	expected := r.Header.Get("X-Expected-User-Id")
	if (expected != "" && expected != u.ID) || (r.Method != "GET" && r.Method != "HEAD" && expected == "") {
		fail(w, 409, "account_changed", "Account changed; reload this page")
		return false
	}
	return true
}

func memoryError(w http.ResponseWriter, err error) {
	if errors.Is(err, ErrConflict) {
		fail(w, 409, "memory_conflict", "The memory operation changed or conflicts with an existing fact; refresh to reconcile")
		return
	}
	if errors.Is(err, ErrDisabled) {
		fail(w, 409, "memory_disabled", "Enable personal memory before adding a fact")
		return
	}
	if errors.Is(err, ErrCredentials) {
		fail(w, 422, "invalid_memory", "Check the name, timezone, fact or operation ID; authentication secrets cannot be saved")
		return
	}
	storeError(w, err)
}

func (s *Server) personalProfile(w http.ResponseWriter, r *http.Request) {
	if !personalAccess(w, r) {
		return
	}
	p, err := s.Store.PersonalProfile(sessionOf(r).User.ID)
	if err != nil {
		storeError(w, err)
		return
	}
	if r.Method == "PATCH" {
		var body struct {
			DisplayName        *string `json:"display_name"`
			Timezone           *string `json:"timezone"`
			MemoryEnabled      *bool   `json:"memory_enabled"`
			AutoCaptureEnabled *bool   `json:"auto_capture_enabled"`
			ProactiveEnabled   *bool   `json:"proactive_enabled"`
			ExpectedRevision   int64   `json:"expected_revision"`
		}
		if !decode(w, r, &body) {
			return
		}
		if body.DisplayName != nil {
			p.DisplayName = *body.DisplayName
		}
		if body.Timezone != nil {
			p.Timezone = *body.Timezone
		}
		if body.MemoryEnabled != nil {
			p.MemoryEnabled = *body.MemoryEnabled
		}
		if body.AutoCaptureEnabled != nil {
			p.AutoCaptureEnabled = *body.AutoCaptureEnabled
		}
		if body.ProactiveEnabled != nil {
			p.ProactiveEnabled = *body.ProactiveEnabled
		}
		p, err = s.Store.UpdatePersonalProfile(r.Context(), p, body.ExpectedRevision)
		if err != nil {
			memoryError(w, err)
			return
		}
	}
	respond(w, 200, p)
}

func (s *Server) memories(w http.ResponseWriter, r *http.Request) {
	if !personalAccess(w, r) {
		return
	}
	query := r.URL.Query().Get("q")
	requestedOffset := r.URL.Query().Get("offset")
	if r.Method == "POST" {
		var body struct {
			Query  string `json:"query"`
			Offset int    `json:"offset"`
		}
		if !decode(w, r, &body) {
			return
		}
		query = body.Query
		requestedOffset = strconv.Itoa(body.Offset)
	}
	if len(query) > 512 {
		memoryError(w, ErrCredentials)
		return
	}
	refs, err := s.Store.MemoryReferences(sessionOf(r).User.ID)
	if err != nil {
		storeError(w, err)
		return
	}
	ids := []string{}
	for _, ref := range refs {
		if ref.Status == "active" {
			ids = append(ids, ref.ID)
		}
	}
	total := len(ids)
	offset := 0
	if value := requestedOffset; value != "" {
		var parseErr error
		offset, parseErr = strconv.Atoi(value)
		if parseErr != nil || offset < 0 || offset > 2000 {
			memoryError(w, ErrCredentials)
			return
		}
	}
	if query == "" {
		if offset < total {
			ids = ids[offset:]
		} else {
			ids = []string{}
		}
		if len(ids) > 50 {
			ids = ids[:50]
		}
	}
	items := json.RawMessage(`{"items":[]}`)
	if len(ids) > 0 {
		body, _ := json.Marshal(map[string]any{"ids": ids, "query": query})
		ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
		defer cancel()
		items, err = s.engine.query(ctx, r, "POST", "/api/plugins/deermate.memory/actions/read", body)
		if err != nil {
			fail(w, 503, "memory_unavailable", "Memory storage is unavailable; saved references are preserved")
			return
		}
	}
	var data struct {
		Items []json.RawMessage `json:"items"`
	}
	if json.Unmarshal(items, &data) != nil || data.Items == nil {
		fail(w, 502, "memory_contract", "Unexpected memory response")
		return
	}
	respond(w, 200, map[string]any{"items": data.Items, "references": refs, "total_active": total, "offset": offset, "limit": 50})
}

func (s *Server) mutateMemory(w http.ResponseWriter, r *http.Request) {
	if !personalAccess(w, r) {
		return
	}
	var body memoryMutation
	if !decode(w, r, &body) {
		return
	}
	body.Content = strings.TrimSpace(body.Content)
	kind := map[string]string{"POST": "create", "PATCH": "update", "DELETE": "delete"}[r.Method]
	op, err := s.Store.AdmitMemory(r.Context(), sessionOf(r).User.ID, kind, r.PathValue("id"), body)
	if err != nil {
		memoryError(w, err)
		return
	}
	if op.Status == "pending" {
		s.deliverMemory(r.Context(), r, op)
	}
	op, err = s.Store.MemoryOperation(sessionOf(r).User.ID, op.ID)
	if err != nil {
		storeError(w, err)
		return
	}
	respond(w, http.StatusAccepted, op)
}

func (s *Server) deliverMemory(ctx context.Context, r *http.Request, op MemoryOperation) {
	select {
	case s.memoryDelivery <- struct{}{}:
		defer func() { <-s.memoryDelivery }()
	default:
		return
	}
	op, err := s.Store.claimMemory(ctx, op.Owner, op.ID)
	if err != nil {
		return
	}
	ctx, cancel := context.WithTimeout(ctx, 25*time.Second)
	defer cancel()
	body, _ := json.Marshal(map[string]string{"operation_id": op.ID})
	raw, err := s.engine.query(ctx, r, "POST", "/api/plugins/deermate.memory/actions/apply", body)
	var result struct {
		Revision int64  `json:"revision"`
		Category string `json:"category"`
	}
	if err == nil {
		err = json.Unmarshal(raw, &result)
		if err == nil && op.Kind != "delete" && result.Revision < 1 {
			err = errors.New("invalid memory receipt")
		}
	}
	// The delivery caller may have gone away after a provider commit.
	finish, cancelFinish := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancelFinish()
	_ = s.Store.finishMemory(finish, op, result.Revision, result.Category, err)
}

// RunMemoryQueue reclaims deterministic deliveries after restart. It never invokes
// a model or native task; uncertain provider writes are reconciled by operation ID.
func (s *Server) RunMemoryQueue(ctx context.Context) {
	ticker := time.NewTicker(3 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
		rows, err := s.Store.DB.QueryContext(ctx, `SELECT o.owner,o.id FROM deermate_memory_operations o
JOIN users u ON u.id=o.owner AND u.disabled=0 AND u.needs_setup=0
WHERE o.status='pending' OR (o.status IN ('processing','uncertain') AND o.lease_until<?)
ORDER BY o.created_at,o.id LIMIT 1`, time.Now().Unix())
		if err != nil {
			continue
		}
		var owner, id string
		if rows.Next() {
			err = rows.Scan(&owner, &id)
		}
		rows.Close()
		if err != nil || id == "" {
			continue
		}
		u, err := s.Store.User(owner)
		if err != nil || u.Disabled || u.NeedsSetup {
			continue
		}
		op, err := s.Store.MemoryOperation(owner, id)
		if err != nil {
			continue
		}
		r, _ := http.NewRequestWithContext(context.WithValue(ctx, sessionKey{}, Session{User: u}), "POST", s.cfg.Origin+"/api/me/memories", nil)
		csrf := opaque()
		r.AddCookie(&http.Cookie{Name: "csrf_token", Value: csrf})
		r.Header.Set("X-CSRF-Token", csrf)
		s.deliverMemory(ctx, r, op)
	}
}
