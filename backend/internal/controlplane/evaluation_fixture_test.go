//go:build deermate_evaluation && linux

package controlplane

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
)

func evaluationRoutingFixture(t *testing.T, mode string) (*Server, User, browser, workRecord, *atomic.Int64) {
	t.Helper()
	t.Setenv("DEERMATE_EVALUATION_MODE", "")
	calls := &atomic.Int64{}
	s, u, b := continuousFixture(t, func(w http.ResponseWriter, r *http.Request) {
		calls.Add(1)
		respond(w, 200, map[string]any{"known": true, "accepted": true, "run_id": "synthetic-router-run", "status": "completed", "preview": "Synthetic reference received"})
	})
	t.Setenv("DEERMATE_EVALUATION_MODE", mode)
	t.Setenv("DEERMATE_EVALUATION_KEY", strings.Repeat("k", 40))
	s.cfg.Origin = "http://localhost:2026"
	s.cfg.AllowedHosts = []string{"localhost:2026", "control:8080"}
	s.evaluationFixtureRoutes()
	v := fixtureWork(t, s, u, "evaluation-work")
	headers := map[string]string{"X-Expected-User-Id": u.ID, "X-DeerMate-Evaluation": strings.Repeat("k", 40)}
	w := evaluationRequest(s, b, "POST", "/__deermate_evaluation/setup", fmt.Sprintf(`{"work_id":%q}`, v.ID), headers)
	requireStatus(t, w, 200)
	rule := newWork(u.ID, "rule", "observe", "", map[string]any{"source_id": "github", "instruction": "Read synthetic updates only", "event_kinds": []any{"comment"}})
	if err := s.Store.workTransaction(context.Background(), func(tx *sql.Tx) error { return workPut(tx, &rule) }); err != nil {
		t.Fatal(err)
	}
	return s, u, b, v, calls
}

func evaluationRequest(s http.Handler, b browser, method, path, body string, headers map[string]string) *httptest.ResponseRecorder {
	r := httptest.NewRequest(method, "http://localhost:2026"+path, strings.NewReader(body))
	r.Header.Set("Content-Type", "application/json")
	if b.raw != "" {
		r.AddCookie(&http.Cookie{Name: "access_token", Value: b.raw})
		r.AddCookie(&http.Cookie{Name: "csrf_token", Value: b.csrf})
		r.Header.Set("X-CSRF-Token", b.csrf)
	}
	for key, value := range headers {
		r.Header.Set(key, value)
	}
	w := httptest.NewRecorder()
	s.ServeHTTP(w, r)
	return w
}

func TestEvaluationBoundContextOnlyChangesRouterHop(t *testing.T) {
	for _, mode := range []string{"B", "C"} {
		t.Run(mode, func(t *testing.T) {
			s, u, b, target, calls := evaluationRoutingFixture(t, mode)
			headers := map[string]string{"X-Expected-User-Id": u.ID, "X-DeerMate-Evaluation": strings.Repeat("k", 40)}
			for i := 1; i <= 6; i++ {
				body := fmt.Sprintf(`{"id":%d,"number":7,"text":"Synthetic bound update %d","revision":"r%d"}`, i, i, i)
				requireStatus(t, evaluationRequest(s, b, "POST", "/__deermate_evaluation/events", body, headers), 200)
			}
			events, err := s.Store.workList(u.ID, "event", "", 0, 20)
			if err != nil {
				t.Fatal(err)
			}
			if len(events) != 6 {
				t.Fatal("lost an input event", len(events))
			}
			inbox, _ := s.Store.workList(u.ID, "inbox", "router", 0, 20)
			if mode == "C" && len(inbox) != 0 {
				t.Fatal("C rerouted a bound event")
			}
			if mode == "B" {
				if len(inbox) != 1 {
					t.Fatal("B changed coalescing", len(inbox))
				}
				for _, event := range events {
					if event.State == "context" {
						t.Fatal("B bypassed Router")
					}
				}
				s.pumpContinuousLane(context.Background(), "router")
				if calls.Load() != 1 {
					t.Fatal("B did not traverse actual runtime adapter", calls.Load())
				}
			}
			events, _ = s.Store.workList(u.ID, "event", "", 0, 20)
			for _, event := range events {
				if event.State != "context" || event.Parent != target.ID {
					t.Fatal("wrong final work association", event)
				}
			}
			if mode == "C" && calls.Load() != 0 {
				t.Fatal("C called the Router runtime")
			}
		})
	}
}

func TestEvaluationCannotAttachAfterSourceRevocationOrForgeOwner(t *testing.T) {
	s, u, b, _, calls := evaluationRoutingFixture(t, "B")
	headers := map[string]string{"X-Expected-User-Id": u.ID, "X-DeerMate-Evaluation": strings.Repeat("k", 40)}
	body := `{"id":1,"number":7,"text":"Synthetic bound update","revision":"r1"}`
	requireStatus(t, evaluationRequest(s, b, "POST", "/__deermate_evaluation/events", body, headers), 200)
	headers["X-Expected-User-Id"] = "other-owner"
	requireStatus(t, evaluationRequest(s, b, "POST", "/__deermate_evaluation/events", `{"id":2,"number":7,"text":"forged","revision":"r2"}`, headers), 409)
	if err := s.Store.workTransaction(context.Background(), func(tx *sql.Tx) error {
		source, err := workGet(tx, u.ID, "source", "github")
		if err != nil {
			return err
		}
		source.State = "disabled"
		return workPut(tx, &source)
	}); err != nil {
		t.Fatal(err)
	}
	s.pumpContinuousLane(context.Background(), "router")
	events, _ := s.Store.workList(u.ID, "event", "", 0, 20)
	if len(events) != 1 || events[0].State == "context" || calls.Load() != 0 {
		t.Fatal("revoked/forged input gained routing", events, calls.Load())
	}
}

func evaluationPendingEvent(t *testing.T, s *Server, u User, b browser) workRecord {
	t.Helper()
	headers := map[string]string{"X-Expected-User-Id": u.ID, "X-DeerMate-Evaluation": strings.Repeat("k", 40)}
	requireStatus(t, evaluationRequest(s, b, "POST", "/__deermate_evaluation/events", `{"id":1,"number":7,"text":"Actual bounded source text","revision":"r1"}`, headers), 200)
	s.pumpRouter(context.Background())
	ops, err := s.Store.workList(u.ID, "operation", "", 0, 20)
	if err != nil || len(ops) != 1 {
		t.Fatal("missing original operation", ops, err)
	}
	op, err := workGet(s.Store.DB, u.ID, "operation", ops[0].ID)
	if err != nil {
		t.Fatal(err)
	}
	op.State = "dispatching"
	if err = s.Store.workTransaction(context.Background(), func(tx *sql.Tx) error { return workPut(tx, &op) }); err != nil {
		t.Fatal(err)
	}
	return op
}

func TestEvaluationModelContextAndAttachmentRecheckOriginalRevisions(t *testing.T) {
	for _, change := range []string{"rule", "event", "generation", "pause"} {
		t.Run(change, func(t *testing.T) {
			s, u, b, _, _ := evaluationRoutingFixture(t, "B")
			op := evaluationPendingEvent(t, s, u, b)
			path := "/internal/deermate/evaluation-context/" + op.ID
			headers := map[string]string{"Authorization": "Bearer " + workString(op, "_nonce")}
			w := evaluationRequest(s, browser{}, "POST", path, "", headers)
			requireStatus(t, w, 200)
			if !strings.Contains(w.Body.String(), "Actual bounded source text") {
				t.Fatal("model did not receive actual input", w.Body.String())
			}
			requireStatus(t, evaluationRequest(s, browser{}, "POST", path, "", map[string]string{"Authorization": "Bearer wrong"}), 403)
			if err := s.Store.workTransaction(context.Background(), func(tx *sql.Tx) error {
				kind, id := "rule", workString(op, "rule_id")
				if change == "event" {
					kind, id = "event", workString(op, "event_id")
				}
				if change == "generation" {
					kind, id = "source", "github"
				}
				if change == "pause" {
					kind, id = "settings", "settings"
				}
				v, err := workGet(tx, u.ID, kind, id)
				if err != nil {
					return err
				}
				switch change {
				case "rule":
					v.Data["instruction"] = "Changed policy"
				case "event":
					v.Data["preview"] = "Changed source"
				case "generation":
					v.Data["generation"] = 2
				case "pause":
					v.Data["enabled"] = false
				}
				return workPut(tx, &v)
			}); err != nil {
				t.Fatal(err)
			}
			requireStatus(t, evaluationRequest(s, browser{}, "POST", path, "", headers), 409)
			if err := s.Store.workTransaction(context.Background(), func(tx *sql.Tx) error { return s.evaluationRoutedContext(tx, op) }); err != nil {
				t.Fatal(err)
			}
			events, _ := s.Store.workList(u.ID, "event", "", 0, 20)
			if len(events) != 1 || events[0].State == "context" {
				t.Fatal("stale input attached", events)
			}
		})
	}
}

func TestEvaluationReadContextDoesNotAcquireNativeGrantRequirement(t *testing.T) {
	s, u, b, target, _ := evaluationRoutingFixture(t, "B")
	op := evaluationPendingEvent(t, s, u, b)
	var raw string
	if err := s.Store.DB.QueryRow("SELECT data FROM deermate_agent_grants WHERE id='grant'").Scan(&raw); err != nil {
		t.Fatal(err)
	}
	var grant agentGrant
	if err := json.Unmarshal([]byte(raw), &grant); err != nil {
		t.Fatal(err)
	}
	grant.Revoked = true
	data, _ := json.Marshal(grant)
	if _, err := s.Store.DB.Exec("UPDATE deermate_agent_grants SET data=? WHERE id='grant'", string(data)); err != nil {
		t.Fatal(err)
	}
	headers := map[string]string{"Authorization": "Bearer " + workString(op, "_nonce")}
	requireStatus(t, evaluationRequest(s, browser{}, "POST", "/internal/deermate/evaluation-context/"+op.ID, "", headers), 200)
	if err := s.Store.workTransaction(context.Background(), func(tx *sql.Tx) error { return s.evaluationRoutedContext(tx, op) }); err != nil {
		t.Fatal(err)
	}
	events, _ := s.Store.workList(u.ID, "event", "", 0, 20)
	if len(events) != 1 || events[0].State != "context" || events[0].Parent != target.ID {
		t.Fatal("legitimate read context blocked", events)
	}
	if _, err := s.workGrant(s.Store.DB, u.ID, "grant", "demo", "execute"); err == nil {
		t.Fatal("revoked Native authority accepted")
	}
}
