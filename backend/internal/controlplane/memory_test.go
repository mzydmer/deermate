package controlplane

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func enableMemory(t *testing.T, s *Store, u User) PersonalProfile {
	t.Helper()
	p, err := s.PersonalProfile(u.ID)
	if err != nil {
		t.Fatal(err)
	}
	p.DisplayName = "小林"
	p.Timezone = "America/Los_Angeles"
	p.MemoryEnabled = true
	p, err = s.UpdatePersonalProfile(context.Background(), p, p.Revision)
	if err != nil {
		t.Fatal(err)
	}
	return p
}

func TestPersonalProfileOptimisticUpdateAndIdentity(t *testing.T) {
	s := testStore(t)
	u := account(t, s, "memory@example.com", "user")
	b := session(t, s, u)
	server := testServer(t, s, func(w http.ResponseWriter, r *http.Request) { t.Error("profile must not call runtime") })
	w := request(server, b, "GET", "/api/me/personal-profile", "", nil)
	requireStatus(t, w, 200)
	requireStatus(t, request(server, b, "GET", "/api/me/personal-profile", "", map[string]string{"X-Expected-User-Id": "another-user"}), 409)
	var p PersonalProfile
	_ = json.Unmarshal(w.Body.Bytes(), &p)
	if !p.MemoryEnabled || !p.AutoCaptureEnabled || p.PolicyOrigin != "product_default_v2" || p.Owner != u.ID || p.Revision != 0 {
		t.Fatal(p)
	}
	body := `{"display_name":"小林","timezone":"America/Los_Angeles","memory_enabled":true,"expected_revision":0}`
	requireStatus(t, request(server, b, "PATCH", "/api/me/personal-profile", body, nil), 409)
	headers := map[string]string{"X-Expected-User-Id": u.ID}
	requireStatus(t, request(server, b, "PATCH", "/api/me/personal-profile", body, headers), 200)
	requireStatus(t, request(server, b, "PATCH", "/api/me/personal-profile", `{"proactive_enabled":true,"expected_revision":1}`, headers), 200)
	requireStatus(t, request(server, b, "PATCH", "/api/me/personal-profile", body, headers), 409)
	requireStatus(t, request(server, b, "PATCH", "/api/me/personal-profile", `{"timezone":"Local","expected_revision":1}`, headers), 422)
	requireStatus(t, request(server, b, "POST", "/api/plugins/deermate.memory/actions/apply", `{}`, headers), 403)
	requireStatus(t, request(server, b, "POST", "/api/plugins/deermate.memory/actions/extract", `{}`, headers), 403)
	requireStatus(t, request(server, b, "GET", "/api/memory", "", headers), 403)
}

func TestMemoryListPagesBeforeCanonicalRead(t *testing.T) {
	s := testStore(t)
	u := account(t, s, "memory@example.com", "admin")
	enableMemory(t, s, u)
	for i := 0; i < 55; i++ {
		id := uuid()
		_, err := s.DB.Exec(`INSERT INTO deermate_memory_refs(id,owner,category,source_id,status,revision,content_hash,updated_at) VALUES(?,?,'context','fixture','active',1,'hash',?)`, id, u.ID, i)
		if err != nil {
			t.Fatal(err)
		}
	}
	server := testServer(t, s, func(w http.ResponseWriter, r *http.Request) {
		var body struct {
			IDs []string `json:"ids"`
		}
		if json.NewDecoder(r.Body).Decode(&body) != nil {
			t.Fatal("invalid provider request")
		}
		if len(body.IDs) != 5 {
			t.Errorf("expected last-page five facts, got %d", len(body.IDs))
		}
		respond(w, 200, map[string]any{"items": []any{}})
	})
	b := session(t, s, u)
	requireStatus(t, request(server, b, "GET", "/api/me/memories?offset=50", "", nil), 200)
	requireStatus(t, request(server, b, "GET", "/api/me/memories?offset=-1", "", nil), 422)
}

func TestMemoryAdmissionIdempotencyOwnershipAndSecretExclusion(t *testing.T) {
	s := testStore(t)
	u := account(t, s, "memory@example.com", "admin")
	other := account(t, s, "other@example.com", "admin")
	ctx := context.Background()
	body := memoryMutation{OperationID: "save-1", Content: "控制端使用 Go", Category: "preference"}
	p, _ := s.PersonalProfile(u.ID)
	p.MemoryEnabled, p.AutoCaptureEnabled, p.PolicyOrigin = false, false, "user_choice"
	if _, err := s.UpdatePersonalProfile(ctx, p, p.Revision); err != nil {
		t.Fatal(err)
	}
	if _, err := s.AdmitMemory(ctx, u.ID, "create", "", body); !errors.Is(err, ErrDisabled) {
		t.Fatal(err)
	}
	enableMemory(t, s, u)
	op, err := s.AdmitMemory(ctx, u.ID, "create", "", body)
	if err != nil {
		t.Fatal(err)
	}
	duplicate, err := s.AdmitMemory(ctx, u.ID, "create", "", body)
	if err != nil || duplicate.ID != op.ID {
		t.Fatal(err, duplicate)
	}
	body.Content = "a different intent"
	if _, err = s.AdmitMemory(ctx, u.ID, "create", "", body); !errors.Is(err, ErrConflict) {
		t.Fatal(err)
	}
	if _, err = s.MemoryOperation(other.ID, op.ID); !errors.Is(err, ErrNotFound) {
		t.Fatal("cross-owner read", err)
	}
	for _, text := range []string{"sk-fixture-do-not-save", "password=fixture", "-----BEGIN PRIVATE KEY-----"} {
		body.OperationID = "secret"
		body.Content = text
		if _, err = s.AdmitMemory(ctx, u.ID, "create", "", body); !errors.Is(err, ErrCredentials) {
			t.Fatal("secret admitted", err)
		}
	}
	body.OperationID = "invalid-kind"
	body.Content = "ordinary"
	body.Category = "preference|goal"
	if _, err = s.AdmitMemory(ctx, u.ID, "create", "", body); !errors.Is(err, ErrCredentials) {
		t.Fatal("invalid category", err)
	}
}

func TestMemoryDeletionBlocksLateDeliveryAndErasesPayload(t *testing.T) {
	s := testStore(t)
	u := account(t, s, "memory@example.com", "admin")
	enableMemory(t, s, u)
	ctx := context.Background()
	op, err := s.AdmitMemory(ctx, u.ID, "create", "", memoryMutation{OperationID: "old", Content: "记住这个项目", Category: "goal"})
	if err != nil {
		t.Fatal(err)
	}
	op, err = s.claimMemory(ctx, u.ID, op.ID)
	if err != nil {
		t.Fatal(err)
	}
	del, err := s.AdmitMemory(ctx, u.ID, "delete", op.FactID, memoryMutation{OperationID: "forget"})
	if err != nil {
		t.Fatal(err)
	}
	if err = s.finishMemory(ctx, op, 1, "goal", nil); err != nil {
		t.Fatal(err)
	}
	saved, _ := s.MemoryOperation(u.ID, op.ID)
	if saved.Status != "invalidated" || saved.Payload != "" {
		t.Fatal("old delivery revived", saved)
	}
	refs, _ := s.MemoryReferences(u.ID)
	if refs[0].Status != "suppressed" {
		t.Fatal(refs)
	}
	claimed, err := s.claimMemory(ctx, u.ID, del.ID)
	if err != nil {
		t.Fatal(err)
	}
	if err = s.finishMemory(ctx, claimed, 0, "goal", nil); err != nil {
		t.Fatal(err)
	}
	refs, _ = s.MemoryReferences(u.ID)
	if len(refs) != 0 {
		t.Fatal(refs)
	}
}

func TestForgettingOneFactDoesNotCancelAnIndependentExplicitSave(t *testing.T) {
	s := testStore(t)
	u := account(t, s, "memory@example.com", "admin")
	enableMemory(t, s, u)
	ctx := context.Background()
	a, err := s.AdmitMemory(ctx, u.ID, "create", "", memoryMutation{OperationID: "first", Content: "第一项背景", Category: "context"})
	if err != nil {
		t.Fatal(err)
	}
	a, err = s.claimMemory(ctx, u.ID, a.ID)
	if err != nil {
		t.Fatal(err)
	}
	if err = s.finishMemory(ctx, a, 1, "context", nil); err != nil {
		t.Fatal(err)
	}
	b, err := s.AdmitMemory(ctx, u.ID, "create", "", memoryMutation{OperationID: "independent", Content: "另一项背景", Category: "context"})
	if err != nil {
		t.Fatal(err)
	}
	if _, err = s.AdmitMemory(ctx, u.ID, "delete", a.FactID, memoryMutation{OperationID: "forget-first", ExpectedRevision: 1}); err != nil {
		t.Fatal(err)
	}
	b, err = s.claimMemory(ctx, u.ID, b.ID)
	if err != nil {
		t.Fatal(err)
	}
	if err = s.finishMemory(ctx, b, 1, "context", nil); err != nil {
		t.Fatal(err)
	}
	current, err := s.MemoryOperation(u.ID, b.ID)
	if err != nil || current.Status != "completed" {
		t.Fatal(current, err)
	}
}

func TestMemoryProviderUnavailableKeepsDurableUnknownAndNoPlaintextInResponse(t *testing.T) {
	s := testStore(t)
	u := account(t, s, "memory@example.com", "user")
	enableMemory(t, s, u)
	b := session(t, s, u)
	var calls atomic.Int32
	server := testServer(t, s, func(w http.ResponseWriter, r *http.Request) { calls.Add(1); w.WriteHeader(503) })
	headers := map[string]string{"X-Expected-User-Id": u.ID}
	body := `{"operation_id":"save","content":"我在关注记忆首页","category":"goal","expected_revision":0}`
	w := request(server, b, "POST", "/api/me/memories", body, headers)
	requireStatus(t, w, 202)
	var op MemoryOperation
	_ = json.Unmarshal(w.Body.Bytes(), &op)
	if op.Status != "uncertain" || strings.Contains(w.Body.String(), "关注") {
		t.Fatal(w.Body.String())
	}
	w = request(server, b, "POST", "/api/me/memories", body, headers)
	requireStatus(t, w, 202)
	if calls.Load() != 1 {
		t.Fatal("request replayed without lease/reconciliation")
	}
	p, _ := s.PersonalProfile(u.ID)
	p.MemoryEnabled = false
	if _, err := s.UpdatePersonalProfile(context.Background(), p, p.Revision); err != nil {
		t.Fatal(err)
	}
	op, _ = s.MemoryOperation(u.ID, op.ID)
	if op.Status != "invalidated" || op.Payload != "" {
		t.Fatal(op)
	}
}

func TestMemoryQueueUnavailableOwnerDoesNotBlockOtherAccounts(t *testing.T) {
	s := testStore(t)
	disabled := account(t, s, "disabled-memory@example.com", "user")
	setup := account(t, s, "setup-memory@example.com", "user")
	active := account(t, s, "active-memory@example.com", "user")
	var ops []MemoryOperation
	for _, u := range []User{disabled, setup, active} {
		enableMemory(t, s, u)
		op, err := s.AdmitMemory(context.Background(), u.ID, "create", "", memoryMutation{OperationID: "queued", Content: "队列验收背景", Category: "context"})
		if err != nil {
			t.Fatal(err)
		}
		ops = append(ops, op)
	}
	if _, err := s.DB.Exec("UPDATE deermate_memory_operations SET created_at=0 WHERE owner IN (?,?)", disabled.ID, setup.ID); err != nil {
		t.Fatal(err)
	}
	if _, err := s.DB.Exec("UPDATE users SET disabled=1 WHERE id=?", disabled.ID); err != nil {
		t.Fatal(err)
	}
	if _, err := s.DB.Exec("UPDATE users SET needs_setup=1 WHERE id=?", setup.ID); err != nil {
		t.Fatal(err)
	}
	var calls atomic.Int32
	server := testServer(t, s, func(w http.ResponseWriter, r *http.Request) {
		calls.Add(1)
		var body struct {
			ID string `json:"operation_id"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil || body.ID != ops[2].ID {
			t.Error("delivery used an unavailable account")
		}
		respond(w, 200, map[string]any{"revision": 1, "category": "context"})
	})
	ctx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
	done := make(chan struct{})
	go func() { defer close(done); server.RunMemoryQueue(ctx) }()
	defer func() { cancel(); <-done }()
	tick := time.NewTicker(20 * time.Millisecond)
	defer tick.Stop()
	for {
		op, err := s.MemoryOperation(active.ID, ops[2].ID)
		if err != nil {
			t.Fatal(err)
		}
		if op.Status == "completed" {
			break
		}
		select {
		case <-ctx.Done():
			t.Fatal("unavailable owner's older operation blocked another account")
		case <-tick.C:
		}
	}
	if calls.Load() != 1 {
		t.Fatal("unexpected delivery count", calls.Load())
	}
	for i, u := range []User{disabled, setup} {
		op, err := s.MemoryOperation(u.ID, ops[i].ID)
		if err != nil || op.Status != "pending" {
			t.Fatal("unavailable owner was processed", op, err)
		}
	}
}
