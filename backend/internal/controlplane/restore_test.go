package controlplane

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func TestRestoreQuarantinePreservesAuthenticatedReadsAndBlocksDispatch(t *testing.T) {
	store := testStore(t)
	owner := account(t, store, "restore@example.com", "admin")
	var calls atomic.Int32
	server := testServer(t, store, func(w http.ResponseWriter, r *http.Request) {
		calls.Add(1)
		w.WriteHeader(http.StatusOK)
	})
	server.cfg.RestoreQuarantine = true
	b := session(t, store, owner)
	read := request(server, b, "GET", "/api/v1/auth/me", "", nil)
	if read.Code != 200 || !strings.Contains(read.Body.String(), owner.ID) || read.Header().Get("X-DeerMate-Restore-Quarantine") != "true" {
		t.Fatalf("restored owner must remain readable: %d %s", read.Code, read.Body)
	}
	for _, path := range []string{"/api/threads", "/api/me/router/messages", "/api/agent-devices/poll", "/api/me/memories", "/api/agent-relay/fixture/requests"} {
		response := request(server, b, "POST", path, `{}`, nil)
		if response.Code != 503 || !strings.Contains(response.Body.String(), "restore_quarantine") {
			t.Errorf("%s admitted during restoration: %d", path, response.Code)
		}
	}
	if calls.Load() != 0 {
		t.Fatal("restore guard called runtime for a blocked operation")
	}
	requireStatus(t, request(server, browser{}, "POST", "/api/agent-authorizations/missing/revocations", `{"expected_version":1}`, nil), 401)
	requireStatus(t, request(server, b, "POST", "/api/agent-authorizations/missing/revocations", `{"expected_version":1}`, map[string]string{"X-CSRF-Token": "wrong"}), 403)
	requireStatus(t, request(server, b, "POST", "/api/agent-authorizations/missing/revocations", `{"expected_version":1}`, nil), 404)
	login := request(server, browser{}, "POST", "/api/v1/auth/login/local", "username=restore%40example.com&password="+testPassword, map[string]string{"Content-Type": "application/x-www-form-urlencoded"})
	if login.Code != 200 {
		t.Fatalf("owner must be able to sign in during review: %d %s", login.Code, login.Body)
	}
}

func TestRestoreQuarantineDoesNotStartAnyBackgroundQueue(t *testing.T) {
	server := testServer(t, testStore(t), func(w http.ResponseWriter, r *http.Request) {
		t.Error("background queue reached runtime in quarantine")
	})
	server.cfg.RestoreQuarantine = true
	for _, queue := range []func(context.Context){server.RunMemoryQueue, server.RunMemoryExtractionQueue, server.RunMemoryHistoryQueue, server.RunContinuousQueue} {
		ctx, cancel := context.WithCancel(context.Background())
		done := make(chan struct{})
		go func() { defer close(done); queue(ctx) }()
		select {
		case <-done:
		case <-time.After(time.Second):
			t.Error("quarantined queue did not return before polling")
		}
		cancel()
	}
}

func TestRestoreSafetyDeletionRetainsOwnerCSRFRevisionAndNoOtherDelivery(t *testing.T) {
	store := testStore(t)
	owner := account(t, store, "restore-delete@example.com", "admin")
	other := account(t, store, "restore-other@example.com", "admin")
	enableMemory(t, store, owner)
	op, err := store.AdmitMemory(context.Background(), owner.ID, "create", "", memoryMutation{OperationID: "before-snapshot", Category: "preference", Content: "synthetic retained preference"})
	if err != nil {
		t.Fatal(err)
	}
	op, err = store.claimMemory(context.Background(), owner.ID, op.ID)
	if err != nil {
		t.Fatal(err)
	}
	if err = store.finishMemory(context.Background(), op, 1, "preference", nil); err != nil {
		t.Fatal(err)
	}
	var calls atomic.Int32
	server := testServer(t, store, func(w http.ResponseWriter, r *http.Request) {
		calls.Add(1)
		if r.URL.Path != "/api/plugins/deermate.memory/actions/apply" {
			t.Errorf("unexpected maintenance call: %s", r.URL.Path)
		}
		var body struct {
			Operation string `json:"operation_id"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Fatal(err)
		}
		deletion, err := store.MemoryOperation(owner.ID, body.Operation)
		if err != nil || deletion.Kind != "delete" {
			t.Fatalf("non-delete delivery: %+v %v", deletion, err)
		}
		respond(w, 200, map[string]any{"revision": 2, "category": "preference"})
	})
	server.cfg.RestoreQuarantine = true
	b := session(t, store, owner)
	headers := map[string]string{"X-Expected-User-Id": owner.ID}
	path := "/api/me/memories/" + op.FactID
	body := `{"operation_id":"post-snapshot-forget","expected_revision":1}`
	requireStatus(t, request(server, browser{}, "DELETE", path, body, headers), 401)
	requireStatus(t, request(server, b, "DELETE", path, body, map[string]string{"X-Expected-User-Id": owner.ID, "X-CSRF-Token": "wrong"}), 403)
	requireStatus(t, request(server, session(t, store, other), "DELETE", path, body, map[string]string{"X-Expected-User-Id": other.ID}), 404)
	requireStatus(t, request(server, b, "DELETE", path, `{"operation_id":"stale-forget","expected_revision":99}`, headers), 409)
	if calls.Load() != 0 {
		t.Fatal("invalid deletion reached storage")
	}
	requireStatus(t, request(server, b, "DELETE", path, body, headers), 202)
	requireStatus(t, request(server, b, "DELETE", path, body, headers), 202)
	if calls.Load() != 1 {
		t.Fatal("duplicate delete replayed storage effect", calls.Load())
	}
	refs, err := store.MemoryReferences(owner.ID)
	if err != nil || len(refs) != 0 {
		t.Fatalf("forget not applied: %+v %v", refs, err)
	}
	var deleted string
	if err = store.DB.QueryRow("SELECT status FROM deermate_memory_refs WHERE owner=? AND id=?", owner.ID, op.FactID).Scan(&deleted); err != nil || deleted != "deleted" {
		t.Fatal("canonical deletion missing", deleted, err)
	}
	requireStatus(t, request(server, b, "POST", "/api/me/memories", `{}`, headers), 503)
	requireStatus(t, request(server, b, "PATCH", path, `{}`, headers), 503)
	requireStatus(t, request(server, b, "POST", "/api/agent-devices/poll", `{}`, headers), 503)
	if calls.Load() != 1 {
		t.Fatal("quarantine admitted other work")
	}
}
