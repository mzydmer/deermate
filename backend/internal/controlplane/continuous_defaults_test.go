package controlplane

import (
	"context"
	"database/sql"
	"encoding/json"
	"net/http"
	"strings"
	"sync/atomic"
	"testing"
)

func TestSecretaryAvailableWithoutSeparateSetup(t *testing.T) {
	db := testStore(t)
	u := account(t, db, "default-secretary@example.com", "admin")
	var calls atomic.Int32
	s := testServer(t, db, func(w http.ResponseWriter, r *http.Request) {
		calls.Add(1)
		t.Error("reading the desk must not invoke runtime")
	})
	s.cfg.ContinuousEnabled = true
	b := session(t, db, u)
	response := request(s, b, "GET", "/api/me/continuous-config", "", nil)
	requireStatus(t, response, 200)
	var config map[string]any
	_ = json.Unmarshal(response.Body.Bytes(), &config)
	if config["interactive_available"] != true || calls.Load() != 0 {
		t.Fatal("secretary needs setup or reads call runtime")
	}
	work, err := s.createWork(context.Background(), u, workBody{Operation: "create-default", Goal: "A manually requested goal"}, "interactive")
	if err != nil || work.ID == "" {
		t.Fatalf("manual work blocked: %v", err)
	}
	response = request(s, b, "POST", "/api/me/router/messages", `{"operation_id":"first-message","text":"Help me plan my work"}`, map[string]string{"X-Expected-User-Id": u.ID})
	requireStatus(t, response, 200)
	if workEnabled(db.DB, u.ID) {
		t.Fatal("interactive use enabled background monitoring")
	}
	var reserved int
	_ = db.DB.QueryRow("SELECT count(*) FROM deermate_work_budget").Scan(&reserved)
	if reserved != 0 || calls.Load() != 0 {
		t.Fatal("admission caused model work or budget reservation")
	}
	other := account(t, db, "other-owner@example.com", "admin")
	response = request(s, session(t, db, other), "GET", "/api/me/router", "", nil)
	requireStatus(t, response, 403)
}

func TestSecretaryInheritsConversationModelAndFreezesUnknownOperation(t *testing.T) {
	db := testStore(t)
	u := account(t, db, "model-default@example.com", "admin")
	var catalog, perform, queries atomic.Int32
	s := testServer(t, db, func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/api/models":
			catalog.Add(1)
			respond(w, 200, map[string]any{"models": []any{map[string]any{"name": "first"}, map[string]any{"name": "preferred"}}})
		case strings.HasSuffix(r.URL.Path, "/capabilities"):
			respond(w, 200, map[string]any{"contract_version": 1, "bounded": true})
		case strings.HasSuffix(r.URL.Path, "/perform"):
			perform.Add(1)
			var body struct {
				Operation string `json:"operation_id"`
			}
			_ = json.NewDecoder(r.Body).Decode(&body)
			op, e := workGet(db.DB, u.ID, "operation", body.Operation)
			if e != nil || workString(op, "model") != "preferred" {
				t.Errorf("model selection was not inherited: %v", e)
			}
			http.Error(w, "lost reply", 502)
		default:
			queries.Add(1)
			respond(w, 200, map[string]any{"known": true, "run_id": "original-router-run", "status": "completed", "preview": "Original reply"})
		}
	})
	s.cfg.ContinuousEnabled = true
	b := session(t, db, u)
	if e := db.SetPreferences(context.Background(), u.ID, map[string]any{"model_name": "preferred"}); e != nil {
		t.Fatal(e)
	}
	response := request(s, b, "POST", "/api/me/router/messages", `{"operation_id":"default-message","text":"Plan the next step"}`, map[string]string{"X-Expected-User-Id": u.ID})
	requireStatus(t, response, 200)
	s.pumpRouter(context.Background())
	ops, e := db.workList(u.ID, "operation", "", 0, 20)
	if e != nil || len(ops) != 1 {
		t.Fatal("router operation missing", e)
	}
	s.deliverWork(context.Background(), ops[0])
	op, _ := workGet(db.DB, u.ID, "operation", ops[0].ID)
	if op.State != "uncertain" || workString(op, "model") != "preferred" {
		t.Fatal("lost receipt did not freeze model", op.State)
	}
	_ = db.SetPreferences(context.Background(), u.ID, map[string]any{"model_name": "first"})
	s.deliverWork(context.Background(), op)
	if catalog.Load() != 1 || perform.Load() != 1 || queries.Load() != 1 {
		t.Fatalf("retry selected or sent again: %d/%d/%d", catalog.Load(), perform.Load(), queries.Load())
	}
	var used int
	_ = db.DB.QueryRow("SELECT used FROM deermate_work_budget WHERE kind='model'").Scan(&used)
	if used != 1 {
		t.Fatal("retry reserved another model request", used)
	}
}

func TestSecretaryMissingModelWaitsWithoutSpending(t *testing.T) {
	db := testStore(t)
	u := account(t, db, "no-model@example.com", "admin")
	s := testServer(t, db, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/models" {
			t.Error("missing model attempted execution")
		}
		respond(w, 200, map[string]any{"models": []any{}})
	})
	s.cfg.ContinuousEnabled = true
	b := session(t, db, u)
	w := request(s, b, "POST", "/api/me/router/messages", `{"operation_id":"wait-for-model","text":"Plan a task"}`, map[string]string{"X-Expected-User-Id": u.ID})
	requireStatus(t, w, 200)
	s.pumpRouter(context.Background())
	ops, _ := db.workList(u.ID, "operation", "", 0, 20)
	s.deliverWork(context.Background(), ops[0])
	inbox, _ := db.workList(u.ID, "inbox", "router", 0, 20)
	if len(inbox) != 1 || inbox[0].State != "waiting_model" {
		t.Fatal("missing model not actionable")
	}
	var n int
	_ = db.DB.QueryRow("SELECT count(*) FROM deermate_work_budget").Scan(&n)
	if n != 0 {
		t.Fatal("missing model charged budget")
	}
}

func TestLegacyPauseStillBlocksAutomaticButNotManualWork(t *testing.T) {
	s, u, b := continuousFixture(t, func(w http.ResponseWriter, r *http.Request) { t.Error("unexpected runtime execution") })
	w := request(s, b, "PATCH", "/api/me/continuous-config", `{"enabled":false,"model":"fixture","native_budget":2,"expected_revision":1}`, map[string]string{"X-Expected-User-Id": u.ID})
	requireStatus(t, w, 200)
	work := fixtureWork(t, s, u, "legacy-pause")
	err := s.Store.workTransaction(context.Background(), func(tx *sql.Tx) error {
		_, e := s.prepareWorkOperation(tx, u, work, "execute", "Explicitly execute", "manual", false)
		return e
	})
	if err != nil {
		t.Fatal("manual work still gated by old setup", err)
	}
	second := fixtureWork(t, s, u, "automatic-pause")
	err = s.Store.workTransaction(context.Background(), func(tx *sql.Tx) error {
		_, e := s.prepareWorkOperation(tx, u, second, "execute", "Automatic work", "automatic", true)
		return e
	})
	if err != ErrDisabled {
		t.Fatalf("legacy background pause bypassed: %v", err)
	}
	if workEnabled(s.Store.DB, u.ID) {
		t.Fatal("manual work resumed background")
	}
}
