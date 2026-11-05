package controlplane

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func continuousFixture(t *testing.T, runtime http.HandlerFunc) (*Server, User, browser) {
	t.Helper()
	db := testStore(t)
	u := account(t, db, "secretary@example.com", "admin")
	s := testServer(t, db, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/models" {
			respond(w, 200, map[string]any{"models": []any{map[string]any{"name": "fixture"}}})
			return
		}
		if strings.HasSuffix(r.URL.Path, "/capabilities") {
			respond(w, 200, map[string]any{"contract_version": 1, "bounded": true})
			return
		}
		runtime(w, r)
	})
	if _, err := db.DB.Exec("CREATE TABLE IF NOT EXISTS mcp_tasks(id TEXT PRIMARY KEY,user_id TEXT,thread_id TEXT,thread_incarnation TEXT,status TEXT,created_at TEXT)"); err != nil {
		t.Fatal(err)
	}
	s.cfg.ContinuousEnabled = true
	s.cfg.GitHubRepository = "fixture/project"
	b := session(t, db, u)
	w := request(s, b, "PATCH", "/api/me/continuous-config", `{"enabled":true,"model":"fixture","native_budget":2}`, map[string]string{"X-Expected-User-Id": u.ID})
	requireStatus(t, w, 200)
	d := agentDevice{ID: "device", Owner: u.ID, Instance: "instance", Projects: []string{"demo"}, LastSeen: time.Now().Unix(), Worker: "reachable", Continuous: "work-orders-v1"}
	g := agentGrant{ID: "grant", Owner: u.ID, Device: d.ID, Instance: d.Instance, Version: 1, Active: &agentPolicy{Projects: d.Projects, Operations: []string{"submit", "continue", "cancel"}, ExpiryPolicy: "finish"}}
	raw, _ := json.Marshal(d)
	if _, err := db.DB.Exec("INSERT INTO deermate_agent_devices VALUES(?,?,?,?)", d.ID, u.ID, "token-digest", string(raw)); err != nil {
		t.Fatal(err)
	}
	raw, _ = json.Marshal(g)
	if _, err := db.DB.Exec("INSERT INTO deermate_agent_grants VALUES(?,?,?,?)", g.ID, u.ID, d.ID, string(raw)); err != nil {
		t.Fatal(err)
	}
	return s, u, b
}
func fixtureWork(t *testing.T, s *Server, u User, key string) workRecord {
	t.Helper()
	v, e := s.createWork(context.Background(), u, workBody{Operation: key, Title: "修复 fixture", Goal: "Fix the bounded fixture", Project: "demo", Grant: "grant"}, "interactive")
	if e != nil {
		t.Fatal(e)
	}
	return v
}
func TestContinuousDefaultOwnerAndIdempotency(t *testing.T) {
	db := testStore(t)
	u := account(t, db, "disabled@example.com", "admin")
	s := testServer(t, db, func(w http.ResponseWriter, r *http.Request) { t.Error("default module called runtime") })
	if _, e := s.createWork(context.Background(), u, workBody{Operation: "first", Goal: "work"}, "interactive"); e != ErrDisabled {
		t.Fatalf("default: %v", e)
	}
	s, u, b := continuousFixture(t, func(w http.ResponseWriter, r *http.Request) { t.Error("create called runtime") })
	v := fixtureWork(t, s, u, "first")
	again := fixtureWork(t, s, u, "first")
	if again.ID != v.ID {
		t.Fatal("duplicate root")
	}
	if _, e := s.createWork(context.Background(), u, workBody{Operation: "first", Goal: "different"}, "interactive"); e != ErrConflict {
		t.Fatalf("key reuse: %v", e)
	}
	other := account(t, s.Store, "other@example.com", "admin")
	w := request(s, session(t, s.Store, other), "GET", "/api/me/work-orders/"+v.ID, "", nil)
	requireStatus(t, w, 403)
	w = request(s, b, "POST", "/api/me/router/messages", `{"operation_id":"hello","text":"hello"}`, nil)
	requireStatus(t, w, 409) // expected owner required on mutations
	w = request(s, b, "POST", "/api/me/router/messages", `{"operation_id":"hello","text":"hello"}`, map[string]string{"X-Expected-User-Id": u.ID})
	requireStatus(t, w, 200)
	w = request(s, b, "POST", "/api/me/router/messages", `{"operation_id":"hello","text":"hello"}`, map[string]string{"X-Expected-User-Id": u.ID})
	requireStatus(t, w, 200)
	var count int
	_ = s.Store.DB.QueryRow("SELECT count(*) FROM deermate_work_records WHERE kind='inbox'").Scan(&count)
	if count != 1 {
		t.Fatal("inbox duplicated")
	}
}
func TestContinuousUnknownNeverReplaysAndLateReceipt(t *testing.T) {
	var posts, queries atomic.Int32
	s, u, b := continuousFixture(t, func(w http.ResponseWriter, r *http.Request) {
		if strings.HasSuffix(r.URL.Path, "/perform") {
			posts.Add(1)
			http.Error(w, "response lost", 502)
			return
		}
		queries.Add(1)
		respond(w, 200, map[string]any{"known": true, "tracking_id": "tracked", "thread_id": "", "incarnation": "one", "status": "completed", "verified": true, "native_session": "root", "preview": "validated"})
	})
	v := fixtureWork(t, s, u, "first")
	body := `{"operation_id":"run","action":"execute","expected_revision":1}`
	w := request(s, b, "POST", "/api/me/work-orders/"+v.ID+"/actions", body, map[string]string{"X-Expected-User-Id": u.ID})
	requireStatus(t, w, 200)
	w = request(s, b, "POST", "/api/me/work-orders/"+v.ID+"/actions", body, map[string]string{"X-Expected-User-Id": u.ID})
	requireStatus(t, w, 200)
	ops, e := s.Store.workList(u.ID, "operation", v.ID, 0, 20)
	if e != nil || len(ops) != 1 {
		t.Fatal("duplicate action", e)
	}
	op, e := workGet(s.Store.DB, u.ID, "operation", ops[0].ID)
	if e != nil {
		t.Fatal(e)
	}
	s.deliverWork(context.Background(), op)
	op, _ = workGet(s.Store.DB, u.ID, "operation", op.ID)
	if op.State != "uncertain" {
		t.Fatalf("lost receipt: %s", op.State)
	}
	s.deliverWork(context.Background(), op)
	s.deliverWork(context.Background(), op)
	if posts.Load() != 1 || queries.Load() != 2 {
		t.Fatalf("submit replay: posts %d queries %d", posts.Load(), queries.Load())
	}
	target, _ := workGet(s.Store.DB, u.ID, "work", v.ID)
	if workString(target, "active_operation") != "" || workString(target, "stage") != "completed" || !workBool(target, "verified") {
		t.Fatalf("late evidence: %#v", target)
	}
	inbox, _ := s.Store.workList(u.ID, "inbox", "router", 0, 20)
	if len(inbox) != 1 {
		t.Fatal("receipt wakeup duplicated")
	}
}
func TestContinuousAtomicSlotBudgetAndRevocation(t *testing.T) {
	s, u, _ := continuousFixture(t, func(w http.ResponseWriter, r *http.Request) { t.Error("unauthorized effect") })
	a := fixtureWork(t, s, u, "a")
	b := fixtureWork(t, s, u, "b")
	var op workRecord
	e := s.Store.workTransaction(context.Background(), func(tx *sql.Tx) error {
		var err error
		op, err = s.prepareWorkOperation(tx, u, a, "execute", "fix", "a", true)
		return err
	})
	if e != nil {
		t.Fatal(e)
	}
	e = s.Store.workTransaction(context.Background(), func(tx *sql.Tx) error {
		_, err := s.prepareWorkOperation(tx, u, b, "execute", "fix", "b", true)
		return err
	})
	if e != ErrConflict {
		t.Fatalf("slot %v", e)
	}
	var used int
	_ = s.Store.DB.QueryRow("SELECT used FROM deermate_work_budget WHERE kind='native'").Scan(&used)
	if used != 1 {
		t.Fatal("failed admission charged", used)
	}
	_, e = s.Store.DB.Exec("UPDATE deermate_agent_grants SET data=json_set(data,'$.revoked',1)")
	if e != nil {
		t.Fatal(e)
	}
	s.deliverWork(context.Background(), op)
	op, _ = workGet(s.Store.DB, u.ID, "operation", op.ID)
	if op.State != "prepared" {
		t.Fatal("revoked dispatched")
	}
	e = s.Store.workTransaction(context.Background(), func(tx *sql.Tx) error {
		for range 20 {
			if err := workReserve(tx, u.ID, "model", 20, time.Now()); err != nil {
				return err
			}
		}
		return nil
	})
	if e != nil {
		t.Fatal(e)
	}
	e = s.Store.workTransaction(context.Background(), func(tx *sql.Tx) error { return workReserve(tx, u.ID, "model", 20, time.Now()) })
	if !errors.Is(e, ErrConflict) {
		t.Fatal("daily model budget exceeded", e)
	}
}
func TestContinuousOwnerFTSAndReferenceBounds(t *testing.T) {
	s, u, b := continuousFixture(t, func(w http.ResponseWriter, r *http.Request) {})
	v := fixtureWork(t, s, u, "find")
	other := account(t, s.Store, "foreign@example.com", "admin")
	err := s.Store.workTransaction(context.Background(), func(tx *sql.Tx) error {
		foreign := newWork(other.ID, "work", "active", "", map[string]any{"title": "修复 fixture", "goal": "FOREIGN_SECRET"})
		if e := workPut(tx, &foreign); e != nil {
			return e
		}
		v.Data["refs"] = []any{map[string]any{"kind": "work", "id": foreign.ID}, map[string]any{"kind": "work", "id": v.ID}}
		return workPut(tx, &v)
	})
	if err != nil {
		t.Fatal(err)
	}
	w := request(s, b, "GET", "/api/me/work-orders/search?q=fixture", "", nil)
	requireStatus(t, w, 200)
	if strings.Contains(w.Body.String(), "FOREIGN") {
		t.Fatal("FTS cross-owner")
	}
	w = request(s, b, "GET", "/api/me/work-orders/"+v.ID+"/context", "", nil)
	requireStatus(t, w, 200)
	if strings.Contains(w.Body.String(), "FOREIGN") || !strings.Contains(w.Body.String(), "unavailable") {
		t.Fatal("reference privacy", w.Body.String())
	}
}

func TestContinuousFollowupRequiresFreshValidation(t *testing.T) {
	s, u, _ := continuousFixture(t, func(w http.ResponseWriter, r *http.Request) {})
	v := fixtureWork(t, s, u, "completed")
	err := s.Store.workTransaction(context.Background(), func(tx *sql.Tx) error {
		v.Data["head"] = "previous-tracking"
		v.Data["stage"] = "completed"
		v.Data["verified"] = true
		v.Data["preview"] = "Previous successful round"
		if err := workPut(tx, &v); err != nil {
			return err
		}
		_, err := s.prepareWorkOperation(tx, u, v, "followup", "next step", "next", false)
		return err
	})
	if err != nil {
		t.Fatal(err)
	}
	current, err := workGet(s.Store.DB, u.ID, "work", v.ID)
	if err != nil || workBool(current, "verified") || workString(current, "preview") != "" || workString(current, "head") != "previous-tracking" {
		t.Fatal("new round reused old validation or lost its original head", current, err)
	}
}
func TestContinuousBaselineObserveAndThreadBypass(t *testing.T) {
	var calls atomic.Int32
	s, u, _ := continuousFixture(t, func(w http.ResponseWriter, r *http.Request) { calls.Add(1) })
	src := workRecord{ID: "github", Kind: "source", Owner: u.ID, State: "enabled", Data: map[string]any{"generation": 1}}
	rule := newWork(u.ID, "rule", "observe", "", map[string]any{"source_id": "github", "instruction": "Watch fixes"})
	put := func(v *workRecord) {
		t.Helper()
		if e := s.Store.workTransaction(context.Background(), func(tx *sql.Tx) error { return workPut(tx, v) }); e != nil {
			t.Fatal(e)
		}
	}
	put(&src)
	put(&rule)
	batch := []struct {
		obj  githubObject
		kind string
	}{{githubObject{ID: 1, Number: 1, Title: "first", Body: "untrusted", Updated: "2026-11-04T01:00:00Z"}, "issue"}}
	if e := s.ingestGitHub(context.Background(), src, batch, "tag", "2026-11-04T01:01:00Z"); e != nil {
		t.Fatal(e)
	}
	inbox, _ := s.Store.workList(u.ID, "inbox", "router", 0, 20)
	if len(inbox) != 0 || calls.Load() != 0 {
		t.Fatal("baseline executed")
	}
	src, _ = workGet(s.Store.DB, u.ID, "source", "github")
	batch[0].obj.Body = "edited same second"
	if e := s.ingestGitHub(context.Background(), src, batch, "tag2", "2026-11-04T01:02:00Z"); e != nil {
		t.Fatal(e)
	}
	inbox, _ = s.Store.workList(u.ID, "inbox", "router", 0, 20)
	if len(inbox) != 1 || calls.Load() != 0 {
		t.Fatal("observe dispatched native")
	}
	target := fixtureWork(t, s, u, "bound")
	target.Data["source_generation"] = int64(1)
	put(&target)
	e := s.Store.workTransaction(context.Background(), func(tx *sql.Tx) error {
		return workUnique(tx, u.ID, "subscription", "github:fixture/project:1", target.ID)
	})
	if e != nil {
		t.Fatal(e)
	}
	src, _ = workGet(s.Store.DB, u.ID, "source", "github")
	batch[0].obj.Body = "third update"
	if e = s.ingestGitHub(context.Background(), src, batch, "tag3", "2026-11-04T01:03:00Z"); e != nil {
		t.Fatal(e)
	}
	after, _ := s.Store.workList(u.ID, "inbox", "router", 0, 20)
	if len(after) != len(inbox) {
		t.Fatal("known thread rerouted")
	}
	target, _ = workGet(s.Store.DB, u.ID, "work", target.ID)
	if !workBool(target, "has_update") {
		t.Fatal("thread update missing")
	}
}

func TestContinuousRevokedSourceCannotReindexLateResult(t *testing.T) {
	s, u, _ := continuousFixture(t, func(w http.ResponseWriter, r *http.Request) {})
	err := s.Store.workTransaction(context.Background(), func(tx *sql.Tx) error {
		src := newWork(u.ID, "source", "enabled", "", map[string]any{"generation": 1})
		if err := workPut(tx, &src); err != nil {
			return err
		}
		v := newWork(u.ID, "work", "active", "", map[string]any{"source_id": src.ID, "source_generation": 1, "title": "private source"})
		if err := workPut(tx, &v); err != nil {
			return err
		}
		table := "deermate_work_fts_" + digest(u.ID)[:24]
		count := func(want int) error {
			var n int
			if err := tx.QueryRow("SELECT count(*) FROM " + table).Scan(&n); err != nil {
				return err
			}
			if n != want {
				t.Errorf("indexed records = %d; want %d", n, want)
			}
			return nil
		}
		if err := count(1); err != nil {
			return err
		}
		src.Data["error"] = "unreadable"
		if err := workPut(tx, &src); err != nil {
			return err
		}
		v.Data["stage"] = "completed"
		if err := workPut(tx, &v); err != nil {
			return err
		}
		if err := count(0); err != nil {
			return err
		}
		src.Data["error"] = ""
		if err := workPut(tx, &src); err != nil {
			return err
		}
		if err := count(1); err != nil {
			return err
		}
		src.State = "disabled"
		if err := workPut(tx, &src); err != nil {
			return err
		}
		if err := workPut(tx, &v); err != nil {
			return err
		}
		return count(0)
	})
	if err != nil {
		t.Fatal(err)
	}
}

type continuousHTTP func(*http.Request) (*http.Response, error)

func (f continuousHTTP) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }
func TestContinuousGitHubHTTPBoundsAndCursorFailure(t *testing.T) {
	s, u, _ := continuousFixture(t, func(w http.ResponseWriter, r *http.Request) { t.Error("poll called model") })
	s.cfg.GitHubSecretHome = t.TempDir()
	if e := os.WriteFile(filepath.Join(s.cfg.GitHubSecretHome, "github-read-token"), []byte("synthetic-read-token"), 0600); e != nil {
		t.Fatal(e)
	}
	src := workRecord{ID: "github", Kind: "source", Owner: u.ID, State: "enabled", Data: map[string]any{"repository": "fixture/project", "generation": 1, "baseline": true, "cursor": "2026-11-04T01:00:00Z"}}
	if e := s.Store.workTransaction(context.Background(), func(tx *sql.Tx) error { return workPut(tx, &src) }); e != nil {
		t.Fatal(e)
	}
	var calls int
	s.githubTransport = continuousHTTP(func(r *http.Request) (*http.Response, error) {
		calls++
		if r.Method != "GET" || r.URL.Host != "api.github.com" || !strings.HasPrefix(r.URL.Path, "/repos/fixture/project/") {
			t.Fatal("widened read scope", r.Method, r.URL)
		}
		if !strings.Contains(r.URL.RawQuery, "since=") {
			t.Fatal("missing overlap")
		}
		code := 200
		body := `[{"id":1,"number":1,"title":"same second","body":"first","updated_at":"2026-11-04T01:00:00Z"}]`
		if strings.Contains(r.URL.Path, "comments") {
			code = 429
			body = `{"message":"rate limited"}`
		}
		return &http.Response{StatusCode: code, Header: make(http.Header), Body: io.NopCloser(strings.NewReader(body)), Request: r}, nil
	})
	if e := s.pollGitHub(context.Background(), src); e == nil {
		t.Fatal("failed poll accepted")
	}
	current, _ := workGet(s.Store.DB, u.ID, "source", src.ID)
	if current.Revision != src.Revision || workString(current, "cursor") != workString(src, "cursor") {
		t.Fatal("cursor advanced before full poll committed")
	}
	var events int
	_ = s.Store.DB.QueryRow("SELECT count(*) FROM deermate_work_records WHERE kind='event'").Scan(&events)
	if events != 0 || calls != 2 {
		t.Fatal("partial poll leaked events", events, calls)
	}
	s.githubTransport = continuousHTTP(func(r *http.Request) (*http.Response, error) {
		return &http.Response{StatusCode: 302, Header: http.Header{"Location": []string{"https://outside.invalid/steal"}}, Body: io.NopCloser(strings.NewReader("")), Request: r}, nil
	})
	_, _, code, e := s.githubRead(context.Background(), "/issues?per_page=50", "")
	if e == nil || code != 302 {
		t.Fatal("redirect accepted", e, code)
	}
}

func TestContinuousRuleChangeInvalidatesQueuedEventAndSourcePreview(t *testing.T) {
	s, u, b := continuousFixture(t, func(w http.ResponseWriter, r *http.Request) { t.Error("stale event called model") })
	src := workRecord{ID: "github", Kind: "source", Owner: u.ID, State: "enabled", Data: map[string]any{"generation": 1, "baseline": true}}
	rule := newWork(u.ID, "rule", "observe", "", map[string]any{"source_id": "github", "instruction": "Watch changes"})
	e := s.Store.workTransaction(context.Background(), func(tx *sql.Tx) error {
		if e := workPut(tx, &src); e != nil {
			return e
		}
		return workPut(tx, &rule)
	})
	if e != nil {
		t.Fatal(e)
	}
	batch := []struct {
		obj  githubObject
		kind string
	}{{githubObject{ID: 2, Number: 2, Title: "sensitive preview", Body: "OLD_SOURCE_PREVIEW", Updated: "2026-11-04T01:00:00Z"}, "issue"}}
	if e = s.ingestGitHub(context.Background(), src, batch, "", "2026-11-04T01:01:00Z"); e != nil {
		t.Fatal(e)
	}
	e = s.Store.workTransaction(context.Background(), func(tx *sql.Tx) error { rule.State = "off"; return workPut(tx, &rule) })
	if e != nil {
		t.Fatal(e)
	}
	s.pumpRouter(context.Background())
	inbox, _ := s.Store.workList(u.ID, "inbox", "router", 0, 20)
	if len(inbox) != 1 || inbox[0].State != "stale" {
		t.Fatal("old rule event replayed", inbox)
	}
	e = s.Store.workTransaction(context.Background(), func(tx *sql.Tx) error {
		src, _ = workGet(tx, u.ID, "source", "github")
		src.State = "disabled"
		return workPut(tx, &src)
	})
	if e != nil {
		t.Fatal(e)
	}
	w := request(s, b, "GET", "/api/me/work-orders/search?q=OLD_SOURCE_PREVIEW", "", nil)
	requireStatus(t, w, 200)
	if strings.Contains(w.Body.String(), "OLD_SOURCE_PREVIEW") {
		t.Fatal("disabled source remained searchable")
	}
}

func TestContinuousBatchCoalescesSameThreadAndKeepsScope(t *testing.T) {
	s, u, _ := continuousFixture(t, func(w http.ResponseWriter, r *http.Request) { t.Error("ingestion invoked a model") })
	src := workRecord{ID: "github", Kind: "source", Owner: u.ID, State: "enabled", Data: map[string]any{"generation": 1, "baseline": true}}
	rule := newWork(u.ID, "rule", "observe", "", map[string]any{"source_id": "github", "instruction": "Watch changes"})
	if e := s.Store.workTransaction(context.Background(), func(tx *sql.Tx) error {
		if e := workPut(tx, &src); e != nil {
			return e
		}
		return workPut(tx, &rule)
	}); e != nil {
		t.Fatal(e)
	}
	objects := []struct {
		obj  githubObject
		kind string
	}{}
	for i := 1; i <= 3; i++ {
		objects = append(objects, struct {
			obj  githubObject
			kind string
		}{githubObject{ID: int64(i), URL: "https://api.github.com/repos/fixture/project/issues/7", Body: "bounded reference", Updated: "2026-11-04T01:00:00Z"}, "comment"})
	}
	if e := s.ingestGitHub(context.Background(), src, objects, "", "2026-11-04T01:01:00Z"); e != nil {
		t.Fatal(e)
	}
	inbox, _ := s.Store.workList(u.ID, "inbox", "router", 0, 20)
	if len(inbox) != 1 {
		t.Fatal("same Thread was fanned out", len(inbox))
	}
	refs, _ := inbox[0].Data["event_batch"].([]any)
	if len(refs) != 3 {
		t.Fatal("batch lost events", refs)
	}
	s.pumpRouter(context.Background())
	ops, _ := s.Store.workList(u.ID, "operation", "", 0, 20)
	if len(ops) != 1 {
		t.Fatal("batch produced several Router operations")
	}
	if e := s.Store.workTransaction(context.Background(), func(tx *sql.Tx) error {
		event, rule, e := assessmentInputs(tx, u.ID, workString(inbox[0], "event_id"), rule.ID)
		if e != nil {
			return e
		}
		prompt, e := assessmentBatch(tx, u.ID, event, rule, inbox[0].Data["event_batch"])
		if e != nil {
			return e
		}
		if len(prompt) > 32768 {
			t.Fatal("unbounded batch")
		}
		return nil
	}); e != nil {
		t.Fatal(e)
	}
}

func TestContinuousCancelBeforeDispatchAndProtocolFailClosed(t *testing.T) {
	s, u, b := continuousFixture(t, func(w http.ResponseWriter, r *http.Request) { t.Error("locally cancelled operation reached runtime") })
	v := fixtureWork(t, s, u, "cancel")
	var op workRecord
	e := s.Store.workTransaction(context.Background(), func(tx *sql.Tx) error {
		var e error
		op, e = s.prepareWorkOperation(tx, u, v, "execute", "fix", "execute", false)
		return e
	})
	if e != nil {
		t.Fatal(e)
	}
	v, _ = workGet(s.Store.DB, u.ID, "work", v.ID)
	body, _ := json.Marshal(workBody{Operation: "cancel", Action: "cancel", Expected: v.Revision})
	w := request(s, b, "POST", "/api/me/work-orders/"+v.ID+"/actions", string(body), map[string]string{"X-Expected-User-Id": u.ID})
	requireStatus(t, w, 200)
	s.deliverWork(context.Background(), op)
	original, _ := workGet(s.Store.DB, u.ID, "operation", op.ID)
	if original.State != "settled" || workString(original, "status") != "cancelled_before_dispatch" {
		t.Fatal("local cancellation not retained")
	}
	_, e = s.Store.DB.Exec("UPDATE deermate_agent_devices SET data=json_remove(data,'$.continuous_protocol')")
	if e != nil {
		t.Fatal(e)
	}
	e = s.Store.workTransaction(context.Background(), func(tx *sql.Tx) error {
		_, e := s.prepareWorkOperation(tx, u, v, "execute", "fix", "new", false)
		return e
	})
	if !errors.Is(e, ErrConflict) {
		t.Fatal("old Worker accepted continuous work", e)
	}
}

func TestContinuousAutoBudgetAndRuleRecheck(t *testing.T) {
	s, u, _ := continuousFixture(t, func(w http.ResponseWriter, r *http.Request) {})
	src := workRecord{ID: "github", Kind: "source", Owner: u.ID, State: "enabled", Data: map[string]any{"generation": 1, "baseline": true}}
	rule := newWork(u.ID, "rule", "auto", "", map[string]any{"source_id": "github", "project": "demo", "grant_id": "grant", "native_budget": 1})
	event := newWork(u.ID, "event", "candidate", "", map[string]any{"source_id": "github", "source_generation": 1, "thread_key": "github:fixture/project:8"})
	var d workRecord
	e := s.Store.workTransaction(context.Background(), func(tx *sql.Tx) error {
		for _, v := range []*workRecord{&src, &rule, &event} {
			if e := workPut(tx, v); e != nil {
				return e
			}
		}
		d = newWork(u.ID, "decision", "suggested", "", map[string]any{"event_id": event.ID, "event_revision": event.Revision, "source_id": src.ID, "source_generation": 1, "rule_id": rule.ID, "rule_revision": rule.Revision, "goal": "Fix the authorized issue", "title": "Fixture", "scope": "in_scope", "project": "demo", "grant_id": "grant"})
		if e := workPut(tx, &d); e != nil {
			return e
		}
		_, e := s.acceptWorkDecision(tx, u, d, "", "", true)
		return e
	})
	if e != nil {
		t.Fatal(e)
	}
	var used int
	_ = s.Store.DB.QueryRow("SELECT used FROM deermate_work_budget WHERE kind='native'").Scan(&used)
	if used != 1 {
		t.Fatal("auto did not reserve quota")
	}
	d, _ = workGet(s.Store.DB, u.ID, "decision", d.ID)
	if d.State != "accepted" {
		t.Fatal("auto did not retain decision")
	}
	e = s.Store.workTransaction(context.Background(), func(tx *sql.Tx) error { rule.State = "off"; return workPut(tx, &rule) })
	if e != nil {
		t.Fatal(e)
	}
	e = s.Store.workTransaction(context.Background(), func(tx *sql.Tx) error { _, _, e := assessmentInputs(tx, u.ID, event.ID, rule.ID); return e })
	if !errors.Is(e, ErrConflict) {
		t.Fatal("disabled rule accepted", e)
	}
	now := time.Date(2026, 11, 4, 23, 59, 59, 0, time.UTC)
	e = s.Store.workTransaction(context.Background(), func(tx *sql.Tx) error {
		if e := workReserve(tx, u.ID, "boundary", 1, now); e != nil {
			return e
		}
		return workReserve(tx, u.ID, "boundary", 1, now.Add(time.Second))
	})
	if e != nil {
		t.Fatal("UTC boundary did not reset", e)
	}
}

func TestContinuousAssessorHasOneSlotAndInputDoesNotOccupyRouter(t *testing.T) {
	var admissions atomic.Int32
	s, u, b := continuousFixture(t, func(w http.ResponseWriter, r *http.Request) {
		admissions.Add(1)
		respond(w, 200, map[string]any{"known": true, "status": "running", "run_id": "assessment"})
	})
	src := workRecord{ID: "github", Kind: "source", Owner: u.ID, State: "enabled", Data: map[string]any{"generation": 1, "baseline": true}}
	rule := newWork(u.ID, "rule", "observe", "", map[string]any{"source_id": "github"})
	event := newWork(u.ID, "event", "candidate", "", map[string]any{"source_id": "github", "source_generation": 1})
	ops := []workRecord{}
	e := s.Store.workTransaction(context.Background(), func(tx *sql.Tx) error {
		for _, v := range []*workRecord{&src, &rule, &event} {
			if e := workPut(tx, v); e != nil {
				return e
			}
		}
		for range 2 {
			op := newWork(u.ID, "operation", "prepared", event.ID, map[string]any{"kind": "assessor", "thread_id": "assessor-" + uuid(), "event_id": event.ID, "event_revision": event.Revision, "rule_id": rule.ID, "rule_revision": rule.Revision, "_user_version": u.Version, "_nonce": opaque()})
			if e := workPut(tx, &op); e != nil {
				return e
			}
			ops = append(ops, op)
		}
		return nil
	})
	if e != nil {
		t.Fatal(e)
	}
	s.deliverWork(context.Background(), ops[0])
	s.deliverWork(context.Background(), ops[1])
	if admissions.Load() != 1 {
		t.Fatal("several assessments admitted concurrently", admissions.Load())
	}
	second, _ := workGet(s.Store.DB, u.ID, "operation", ops[1].ID)
	if second.State != "prepared" || workString(second, "hold_reason") != "waiting_assessor" {
		t.Fatal("assessment slot not held", second.State)
	}
	w := request(s, b, "POST", "/api/me/router/messages", `{"operation_id":"during-assessment","text":"Another owner question"}`, map[string]string{"X-Expected-User-Id": u.ID})
	requireStatus(t, w, 200)
	s.pumpRouter(context.Background())
	var router int
	_ = s.Store.DB.QueryRow("SELECT count(*) FROM deermate_work_records WHERE kind='operation' AND json_extract(data,'$.kind')='router'").Scan(&router)
	if router != 1 {
		t.Fatal("assessment blocked Router admission")
	}
}

func TestContinuousRejectedContinuationPreservesHeadAndInputRetainsSlot(t *testing.T) {
	var status atomic.Value
	status.Store("rejected")
	s, u, _ := continuousFixture(t, func(w http.ResponseWriter, r *http.Request) {
		value := status.Load().(string)
		task := ""
		if value != "rejected" {
			task = "new-head"
		}
		respond(w, 200, map[string]any{"known": true, "status": value, "tracking_id": task})
	})
	work := fixtureWork(t, s, u, "continue")
	work.Data["head"] = "old-head"
	var op workRecord
	e := s.Store.workTransaction(context.Background(), func(tx *sql.Tx) error {
		if e := workPut(tx, &work); e != nil {
			return e
		}
		var e error
		op, e = s.prepareWorkOperation(tx, u, work, "followup", "Continue", "rejected", false)
		return e
	})
	if e != nil {
		t.Fatal(e)
	}
	s.deliverWork(context.Background(), op)
	work, _ = workGet(s.Store.DB, u.ID, "work", work.ID)
	if workString(work, "head") != "old-head" || workString(work, "active_operation") != "" {
		t.Fatal("rejection erased the existing head")
	}
	status.Store("input_required")
	e = s.Store.workTransaction(context.Background(), func(tx *sql.Tx) error {
		var e error
		op, e = s.prepareWorkOperation(tx, u, work, "followup", "Continue", "input", false)
		return e
	})
	if e != nil {
		t.Fatal(e)
	}
	s.deliverWork(context.Background(), op)
	saved, _ := workGet(s.Store.DB, u.ID, "operation", op.ID)
	work, _ = workGet(s.Store.DB, u.ID, "work", work.ID)
	if saved.State != "acknowledged" || workString(work, "active_operation") != op.ID {
		t.Fatal("waiting Native input released its execution slot")
	}
}

func TestContinuousContextCursorIsOwnerAndRevisionBound(t *testing.T) {
	s, u, b := continuousFixture(t, func(w http.ResponseWriter, r *http.Request) {})
	work := fixtureWork(t, s, u, "cursor")
	e := s.Store.workTransaction(context.Background(), func(tx *sql.Tx) error {
		event := newWork(u.ID, "event", "assessed", "", map[string]any{"title": "bounded"})
		if e := workPut(tx, &event); e != nil {
			return e
		}
		work.Data["refs"] = []any{map[string]any{"kind": "event", "id": event.ID, "revision": event.Revision}}
		return workPut(tx, &work)
	})
	if e != nil {
		t.Fatal(e)
	}
	path := "/api/me/work-orders/" + work.ID + "/context?limit=1"
	w := request(s, b, "GET", path, "", nil)
	requireStatus(t, w, 200)
	var page struct {
		Cursor string       `json:"next_cursor"`
		Items  []workRecord `json:"items"`
	}
	if json.Unmarshal(w.Body.Bytes(), &page) != nil || len(page.Items) != 1 || page.Cursor == "" {
		t.Fatal("missing continuation", w.Body.String())
	}
	w = request(s, b, "GET", path+"&cursor="+page.Cursor, "", nil)
	requireStatus(t, w, 200)
	w = request(s, b, "GET", path+"&cursor="+page.Cursor+"tampered", "", nil)
	requireStatus(t, w, 422)
	e = s.Store.workTransaction(context.Background(), func(tx *sql.Tx) error { work.Data["title"] = "changed"; return workPut(tx, &work) })
	if e != nil {
		t.Fatal(e)
	}
	w = request(s, b, "GET", path+"&cursor="+page.Cursor, "", nil)
	requireStatus(t, w, 409)
}

func TestContinuousRepositoryChangeDisablesSourceAndAutoRules(t *testing.T) {
	s, u, _ := continuousFixture(t, func(w http.ResponseWriter, r *http.Request) { t.Error("configuration change invoked runtime") })
	src := workRecord{ID: "github", Kind: "source", Owner: u.ID, State: "enabled", Data: map[string]any{"repository": "fixture/project", "generation": 1, "baseline": true}}
	rule := newWork(u.ID, "rule", "auto", "", map[string]any{"source_id": "github", "project": "demo", "grant_id": "grant"})
	e := s.Store.workTransaction(context.Background(), func(tx *sql.Tx) error {
		if e := workPut(tx, &src); e != nil {
			return e
		}
		return workPut(tx, &rule)
	})
	if e != nil {
		t.Fatal(e)
	}
	s.cfg.GitHubRepository = "different/project"
	if e = s.syncWorkSources(); e != nil {
		t.Fatal(e)
	}
	src, _ = workGet(s.Store.DB, u.ID, "source", src.ID)
	rule, _ = workGet(s.Store.DB, u.ID, "rule", rule.ID)
	if src.State != "disabled" || workInt(src, "generation") != 2 || rule.State != "observe" || rule.Revision != 2 {
		t.Fatal("old auto scope survived repository change")
	}
}

func TestContinuousExpiringGrantRemainsValidUntilDeadline(t *testing.T) {
	s, u, _ := continuousFixture(t, func(w http.ResponseWriter, r *http.Request) {})
	g, e := s.agentGrant("grant", u.ID)
	if e != nil {
		t.Fatal(e)
	}
	deadline := time.Now().Add(time.Minute).Unix()
	g.Active.ExpiresAt = &deadline
	g.Active.Duration = "fixed"
	raw, _ := json.Marshal(g)
	if _, e = s.Store.DB.Exec("UPDATE deermate_agent_grants SET data=? WHERE id=?", string(raw), g.ID); e != nil {
		t.Fatal(e)
	}
	if _, e = s.workGrant(s.Store.DB, u.ID, g.ID, "demo", "execute"); e != nil {
		t.Fatal("valid short grant rejected", e)
	}
	deadline = time.Now().Add(-time.Second).Unix()
	raw, _ = json.Marshal(g)
	_, e = s.Store.DB.Exec("UPDATE deermate_agent_grants SET data=? WHERE id=?", string(raw), g.ID)
	if e != nil {
		t.Fatal(e)
	}
	if _, e = s.workGrant(s.Store.DB, u.ID, g.ID, "demo", "execute"); !errors.Is(e, ErrConflict) {
		t.Fatal("expired grant admitted", e)
	}
}
