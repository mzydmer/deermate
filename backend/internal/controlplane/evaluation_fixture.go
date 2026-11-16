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

func (s *Server) evaluationAdmitted(owner, inbox string) {
	if os.Getenv("DEERMATE_EVALUATION_MODE") == "" {
		return
	}
	_, _ = s.Store.DB.Exec("INSERT OR IGNORE INTO deermate_evaluation_timings(owner,inbox,admitted_ns) VALUES(?,?,?)", owner, inbox, evaluationClock())
}

func (s *Server) evaluationVisible(owner string, items []workRecord) {
	if os.Getenv("DEERMATE_EVALUATION_MODE") == "" {
		return
	}
	for _, item := range items {
		if item.State == "settled" && workString(item, "reply") != "" {
			stamp := evaluationClock()
			_, _ = s.Store.DB.Exec("UPDATE deermate_evaluation_timings SET first_visible_ns=?,complete_ns=? WHERE owner=? AND inbox=? AND first_visible_ns IS NULL", stamp, stamp, owner, item.ID)
		}
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
		respond(w, 200, map[string]any{"accepted": true, "clock_domain": domain, "clock_ns": evaluationClock()})
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
		respond(w, 200, map[string]any{"mode": mode, "clock_domain": domain, "clock_ns": evaluationClock(), "items": items})
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
