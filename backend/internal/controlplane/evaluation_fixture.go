//go:build deermate_evaluation && linux

package controlplane

// This file is absent from normal binaries. It seeds only the reviewed
// synthetic source fixture and calls the real ingestion/authorization paths.
import (
	"crypto/subtle"
	"database/sql"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"

	"golang.org/x/sys/unix"
)

func evaluationDirectContext() bool {
	mode := os.Getenv("DEERMATE_EVALUATION_MODE")
	return mode != "A" && mode != "B"
}

func evaluationClock() int64 {
	var stamp unix.Timespec
	if err := unix.ClockGettime(unix.CLOCK_MONOTONIC, &stamp); err != nil {
		panic(err)
	}
	return stamp.Nano()
}

func (s *Server) evaluationRoutedContext(tx *sql.Tx, op workRecord) error {
	if evaluationDirectContext() || workString(op, "origin") != "event" {
		return nil
	}
	source, _, err := s.evaluationEventBatch(tx, op)
	if err != nil {
		return nil
	}
	refs, _ := op.Data["event_batch"].([]any)
	for _, raw := range refs {
		ref, ok := raw.(map[string]any)
		if !ok {
			return ErrConflict
		}
		id, _ := ref["id"].(string)
		item, err := workGet(tx, op.Owner, "event", id)
		if err != nil {
			return err
		}
		if _, err = attachSubscriptionContext(tx, source, &item); err != nil {
			return err
		}
	}
	return nil
}

func (s *Server) evaluationEventBatch(tx *sql.Tx, op workRecord) (workRecord, string, error) {
	u, err := scanUser(tx.QueryRow("SELECT "+userColumns+" FROM users WHERE id=?", op.Owner))
	if err != nil || u.Disabled || u.NeedsSetup || u.Role != "admin" || int64(u.Version) != workInt(op, "_user_version") || !s.cfg.ContinuousEnabled || !workEnabled(tx, op.Owner) {
		return workRecord{}, "", ErrConflict
	}
	event, rule, err := assessmentInputs(tx, op.Owner, workString(op, "event_id"), workString(op, "rule_id"))
	if err != nil || event.Revision != workInt(op, "event_revision") || rule.Revision != workInt(op, "rule_revision") {
		return workRecord{}, "", ErrConflict
	}
	batch, err := assessmentBatch(tx, op.Owner, event, rule, op.Data["event_batch"])
	if err != nil {
		return workRecord{}, "", err
	}
	source, err := workGet(tx, op.Owner, "source", workString(event, "source_id"))
	return source, batch, err
}

func (s *Server) evaluationContext(w http.ResponseWriter, r *http.Request) {
	var owner string
	if s.Store.DB.QueryRow("SELECT owner FROM deermate_work_records WHERE kind='operation' AND id=?", r.PathValue("id")).Scan(&owner) != nil {
		workError(w, ErrNotFound)
		return
	}
	op, err := workGet(s.Store.DB, owner, "operation", r.PathValue("id"))
	if err != nil {
		workError(w, err)
		return
	}
	nonce := strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")
	if nonce == "" || subtle.ConstantTimeCompare([]byte(nonce), []byte(workString(op, "_nonce"))) != 1 {
		fail(w, 403, "operation_required", "Canonical operation capability required")
		return
	}
	if workString(op, "kind") != "router" || workString(op, "origin") != "event" || !slicesWorkState(op.State, "dispatching", "acknowledged", "uncertain") {
		workError(w, ErrConflict)
		return
	}
	var batch string
	err = s.Store.workTransaction(r.Context(), func(tx *sql.Tx) error { _, value, e := s.evaluationEventBatch(tx, op); batch = value; return e })
	if err != nil {
		workError(w, err)
		return
	}
	respond(w, 200, map[string]any{"context": batch, "event_refs": op.Data["event_batch"]})
}

func (s *Server) evaluationAdmitted(owner, inbox, text string) {
	if os.Getenv("DEERMATE_EVALUATION_MODE") == "" || !strings.HasPrefix(text, "EVAL_FRONT ") {
		return
	}
	_, _ = s.Store.DB.Exec("INSERT OR IGNORE INTO deermate_evaluation_timings(owner,inbox,admitted_ns) VALUES(?,?,?)", owner, inbox, evaluationClock())
}

func (s *Server) evaluationVisible(w http.ResponseWriter, owner string, items []workRecord) {
	if os.Getenv("DEERMATE_EVALUATION_MODE") == "" {
		return
	}
	// Polling already-visible replies must remain read-only. Even a zero-row
	// UPDATE obtains writer intent and can starve Gateway admission on this
	// shared WAL database. Only the first actual foreground projection writes.
	rows, err := s.Store.DB.Query("SELECT inbox FROM deermate_evaluation_timings WHERE owner=? AND first_visible_ns IS NULL", owner)
	if err != nil {
		return
	}
	pending := map[string]bool{}
	for rows.Next() {
		var id string
		if rows.Scan(&id) == nil {
			pending[id] = true
		}
	}
	rows.Close()
	visible := []string{}
	for _, item := range items {
		if pending[item.ID] && item.State == "settled" && workString(item, "reply") != "" {
			visible = append(visible, item.ID)
		}
	}
	if len(visible) == 0 {
		return
	}
	// The JSON body has already been written by routerView. Bypass our tracing
	// wrapper's void Flush method so a real transport flush error stays visible.
	writer := w
	if traced, ok := w.(*tracedResponse); ok {
		writer = traced.ResponseWriter
	}
	if http.NewResponseController(writer).Flush() != nil {
		return
	}
	stamp := evaluationClock()
	for _, id := range visible {
		_, _ = s.Store.DB.Exec("UPDATE deermate_evaluation_timings SET first_visible_ns=?,complete_ns=? WHERE owner=? AND inbox=? AND first_visible_ns IS NULL", stamp, stamp, owner, id)
	}
}

func (s *Server) evaluationFixtureRoutes() {
	mode := os.Getenv("DEERMATE_EVALUATION_MODE")
	if mode == "" {
		return
	}
	origin, _ := url.Parse(s.cfg.Origin)
	key := os.Getenv("DEERMATE_EVALUATION_KEY")
	if !slicesWorkState(mode, "A", "B", "C") || len(key) < 32 || s.cfg.GitHubRepository != "fixture/project" || (origin.Hostname() != "localhost" && origin.Hostname() != "127.0.0.1") {
		panic("evaluation binary requires the isolated loopback fixture profile")
	}
	boot, err := os.ReadFile("/proc/sys/kernel/random/boot_id")
	if err != nil {
		panic(err)
	}
	domain := "linux-monotonic:" + strings.TrimSpace(string(boot))
	_, err = s.Store.DB.Exec("CREATE TABLE IF NOT EXISTS deermate_evaluation_timings(owner TEXT,inbox TEXT,admitted_ns INTEGER,first_visible_ns INTEGER,complete_ns INTEGER,PRIMARY KEY(owner,inbox))")
	if err != nil {
		panic(err)
	}
	guard := func(next http.HandlerFunc) http.HandlerFunc {
		return s.protected(true, func(w http.ResponseWriter, r *http.Request) {
			if subtle.ConstantTimeCompare([]byte(r.Header.Get("X-DeerMate-Evaluation")), []byte(key)) != 1 {
				fail(w, 403, "evaluation_fixture_required", "Explicit isolated fixture required")
				return
			}
			if !s.workAccess(w, r) {
				return
			}
			next(w, r)
		})
	}
	s.mux.HandleFunc("POST /internal/deermate/evaluation-context/{id}", s.evaluationContext)
	s.mux.HandleFunc("POST /__deermate_evaluation/setup", guard(func(w http.ResponseWriter, r *http.Request) {
		var body struct {
			Work string `json:"work_id"`
		}
		if !decode(w, r, &body) {
			return
		}
		owner := sessionOf(r).User.ID
		err := s.Store.workTransaction(r.Context(), func(tx *sql.Tx) error {
			var count int
			if tx.QueryRow("SELECT count(*) FROM deermate_work_records WHERE owner=? AND kind='source'", owner).Scan(&count) != nil || count != 0 {
				return ErrConflict
			}
			work, e := workGet(tx, owner, "work", body.Work)
			if e != nil || work.State != "active" || workString(work, "head") != "" {
				return ErrConflict
			}
			source := workRecord{ID: "github", Owner: owner, Kind: "source", State: "enabled", Data: map[string]any{"repository": "fixture/project", "generation": 1, "baseline": true, "last_poll_at": time.Now().Unix(), "cursor": time.Now().UTC().Format(time.RFC3339)}}
			if e = workPut(tx, &source); e != nil {
				return e
			}
			work.Data["source_id"] = "github"
			work.Data["source_generation"] = 1
			work.Data["thread_key"] = "github:fixture/project:7"
			work.Data["number"] = 7
			if e = workPut(tx, &work); e != nil {
				return e
			}
			return workUnique(tx, owner, "subscription", "github:fixture/project:7", work.ID)
		})
		if err != nil {
			workError(w, err)
			return
		}
		respond(w, 200, map[string]any{"mode": mode, "clock_domain": domain, "clock_ns": evaluationClock(), "direct_context": evaluationDirectContext()})
	}))
	s.mux.HandleFunc("POST /__deermate_evaluation/events", guard(func(w http.ResponseWriter, r *http.Request) {
		var body struct {
			ID       int64  `json:"id"`
			Number   int    `json:"number"`
			Text     string `json:"text"`
			Revision string `json:"revision"`
		}
		if !decode(w, r, &body) {
			return
		}
		if body.ID <= 0 || (body.Number != 7 && body.Number != 8) || len(body.Text) > 2000 || !workOperationID.MatchString(body.Revision) {
			workError(w, ErrCredentials)
			return
		}
		owner := sessionOf(r).User.ID
		source, err := workGet(s.Store.DB, owner, "source", "github")
		if err != nil {
			workError(w, err)
			return
		}
		objects := []struct {
			obj  githubObject
			kind string
		}{{githubObject{ID: body.ID, Number: body.Number, Title: "Synthetic evaluation event", Body: body.Text, Updated: body.Revision, URL: fmt.Sprintf("https://api.github.com/repos/fixture/project/issues/%d", body.Number)}, "comment"}}
		if err = s.ingestGitHub(r.Context(), source, objects, "", time.Now().UTC().Format(time.RFC3339)); err != nil {
			workError(w, err)
			return
		}
		items, err := s.Store.workList(sessionOf(r).User.ID, "event", "", 0, 20)
		if err != nil {
			workError(w, err)
			return
		}
		for _, item := range items {
			if workInt(item, "remote_id") == body.ID {
				respond(w, 200, map[string]any{"accepted": true, "clock_domain": domain, "clock_ns": evaluationClock(), "event": map[string]any{"id": item.ID, "state": item.State, "parent_id": item.Parent, "revision": item.Revision, "remote_id": body.ID}})
				return
			}
		}
		fail(w, 503, "fixture_event_evidence_missing", "The original event was not found after ingestion")
	}))
	s.mux.HandleFunc("GET /__deermate_evaluation/evidence", guard(func(w http.ResponseWriter, r *http.Request) {
		rows, err := s.Store.DB.Query("SELECT inbox,admitted_ns,first_visible_ns,complete_ns FROM deermate_evaluation_timings WHERE owner=? ORDER BY admitted_ns", sessionOf(r).User.ID)
		if err != nil {
			storeError(w, err)
			return
		}
		defer rows.Close()
		items := []map[string]any{}
		for rows.Next() {
			var inbox string
			var admitted int64
			var first, complete sql.NullInt64
			if rows.Scan(&inbox, &admitted, &first, &complete) != nil {
				continue
			}
			var f, c any
			if first.Valid {
				f = first.Int64
			}
			if complete.Valid {
				c = complete.Int64
			}
			items = append(items, map[string]any{"inbox": inbox, "admitted_ns": admitted, "first_visible_ns": f, "complete_ns": c})
		}
		respond(w, 200, map[string]any{"mode": mode, "clock_domain": domain, "clock_ns": evaluationClock(), "items": items,
			"observation_boundary":  "successful flush of actual settled JSON reply after response body write; clock sampled before persistence, not before response write",
			"visibility_limit":      "server flush is a lower bound on client JSON/UI visibility; client complete-read clock is separately recorded and never subtracted from service clock",
			"first_equals_complete": "one complete reply projection; not streaming tokens"})
	}))
	// The response contains only static synthetic source data; no external
	// credential is used or network contacted by the fixture transport.
	s.githubTransport = evaluationEmptyGitHub{}
}

type evaluationEmptyGitHub struct{}

func (evaluationEmptyGitHub) RoundTrip(r *http.Request) (*http.Response, error) {
	if r.URL.Host != "api.github.com" || !strings.HasPrefix(r.URL.Path, "/repos/fixture/project/") {
		return nil, fmt.Errorf("non-fixture source refused")
	}
	return &http.Response{StatusCode: 200, Header: http.Header{}, Body: io.NopCloser(strings.NewReader("[]")), Request: r}, nil
}
