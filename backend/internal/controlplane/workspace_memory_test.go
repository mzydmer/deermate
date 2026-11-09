package controlplane

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"testing"
)

func TestWorkspaceMemoryDefaultsAndConservativeLegacyMigration(t *testing.T) {
	s := testStore(t)
	u := account(t, s, "new-memory@example.com", "admin")
	p, err := s.PersonalProfile(u.ID)
	if err != nil || !p.MemoryEnabled || !p.AutoCaptureEnabled || !p.ProactiveEnabled || p.PolicyVersion != 2 || p.PolicyOrigin != "product_default_v2" {
		t.Fatal(p, err)
	}
	// Reproduce an old account without provenance, including an explicit-off value.
	if _, err = s.DB.Exec("UPDATE deermate_personal_profiles SET memory_enabled=0,auto_capture_enabled=0,policy_origin='legacy',policy_version=0 WHERE owner=?", u.ID); err != nil {
		t.Fatal(err)
	}
	if _, err = s.DB.Exec("ALTER TABLE deermate_personal_profiles DROP COLUMN policy_origin; ALTER TABLE deermate_personal_profiles DROP COLUMN policy_version;"); err != nil {
		t.Fatal(err)
	}
	if err = s.initializeWorkspaceMemory(); err != nil {
		t.Fatal(err)
	}
	p, err = s.PersonalProfile(u.ID)
	if err != nil || p.MemoryEnabled || p.AutoCaptureEnabled || p.PolicyOrigin != "legacy" {
		t.Fatal("startup re-enabled an old choice", p, err)
	}
	v := account(t, s, "new-after-upgrade@example.com", "user")
	p, err = s.PersonalProfile(v.ID)
	if err != nil || !p.MemoryEnabled || !p.AutoCaptureEnabled || p.PolicyOrigin != "product_default_v2" {
		t.Fatal(p, err)
	}
}

func TestWorkspaceOwnerMigrationIsExplicitCASAndDoesNotOverrideNewPause(t *testing.T) {
	s := testStore(t)
	u := account(t, s, "owner-migrate@example.com", "admin")
	_, _ = s.DB.Exec("UPDATE deermate_personal_profiles SET memory_enabled=0,auto_capture_enabled=0,policy_origin='legacy',policy_version=0 WHERE owner=?", u.ID)
	server := testServer(t, s, func(http.ResponseWriter, *http.Request) { t.Error("profile migration must not invoke runtime") })
	b := session(t, s, u)
	h := map[string]string{"X-Expected-User-Id": u.ID}
	path := "/api/me/workspace-memory-migration"
	requireStatus(t, request(server, b, "POST", path, `{"approve_default":false,"expected_revision":0}`, h), 409)
	requireStatus(t, request(server, b, "POST", path, `{"approve_default":true,"expected_revision":0}`, h), 200)
	p, _ := s.PersonalProfile(u.ID)
	if !p.MemoryEnabled || !p.AutoCaptureEnabled || p.PolicyOrigin != "owner_approved_v2" {
		t.Fatal(p)
	}
	requireStatus(t, request(server, b, "POST", path, `{"approve_default":true,"expected_revision":0}`, h), 409)
	requireStatus(t, request(server, b, "PATCH", "/api/me/personal-profile", `{"auto_capture_enabled":false,"expected_revision":1}`, h), 200)
	requireStatus(t, request(server, b, "POST", path, `{"approve_default":true,"expected_revision":2}`, h), 409)
	p, _ = s.PersonalProfile(u.ID)
	if p.AutoCaptureEnabled || !p.MemoryEnabled || p.PolicyOrigin != "user_choice" {
		t.Fatal("automatic collection and using old memory must be separate", p)
	}
}

func TestTemporaryPolicyReservedBeforeCreationAndSameOperationReconciles(t *testing.T) {
	s := testStore(t)
	u := account(t, s, "temporary@example.com", "user")
	id, err := s.reserveTemporary(context.Background(), u.ID, "same-intent")
	if err != nil {
		t.Fatal(err)
	}
	other := account(t, s, "other-temporary@example.com", "user")
	if captureAllowed(s.DB, u.ID, id) || !captureAllowed(s.DB, other.ID, id) {
		t.Fatal("topic mode must be owner-scoped")
	}
	var calls int
	server := testServer(t, s, func(w http.ResponseWriter, r *http.Request) {
		calls++
		mode, e := topicMemoryMode(s.DB, u.ID, id)
		if e != nil || mode != "temporary" {
			t.Error("runtime saw a topic before its negative policy", mode, e)
		}
		if r.Method == "POST" {
			respond(w, 503, map[string]string{"detail": "lost acknowledgement"})
			return
		}
		respond(w, 200, map[string]string{"thread_id": id})
	})
	b := session(t, s, u)
	h := map[string]string{"X-Expected-User-Id": u.ID}
	for range 2 {
		w := request(server, b, "POST", "/api/me/temporary-topics", `{"operation_id":"same-intent"}`, h)
		requireStatus(t, w, 200)
		var result map[string]string
		_ = json.Unmarshal(w.Body.Bytes(), &result)
		if result["thread_id"] != id || result["mode"] != "temporary" {
			t.Fatal(result)
		}
	}
	var count int
	_ = s.DB.QueryRow("SELECT count(*) FROM deermate_topic_memory WHERE owner=?", u.ID).Scan(&count)
	if calls != 4 || count != 1 {
		t.Fatal(calls, count)
	}
}

func TestTemporaryAndExcludedTopicsRejectLateCapture(t *testing.T) {
	s := testStore(t)
	u := account(t, s, "late-temporary@example.com", "admin")
	c := captureFixture(t, s, u, "temporary-policy", "请记住：我偏好简洁中文回答。")
	for _, mode := range []string{"temporary", "excluded"} {
		_, err := s.DB.Exec("INSERT OR REPLACE INTO deermate_topic_memory(owner,thread_id,mode) VALUES(?,?,?)", u.ID, c.Thread, mode)
		if err != nil {
			t.Fatal(err)
		}
		_, err = s.admitMemory(context.Background(), u.ID, "create", "", memoryMutation{OperationID: "late-" + mode, Content: c.Content, Category: c.Category}, &c)
		if !errors.Is(err, ErrConflict) {
			t.Fatal("late capture crossed a topic exclusion", mode, err)
		}
	}
}
