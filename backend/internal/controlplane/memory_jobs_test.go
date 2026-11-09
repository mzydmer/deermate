package controlplane

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func TestRouterMemoryRequiresCompleteDirectOwnerInbox(t *testing.T) {
	s := testStore(t)
	u := account(t, s, "inbox-memory@example.com", "admin")
	var inbox workRecord
	err := s.workTransaction(context.Background(), func(tx *sql.Tx) error {
		var e error
		inbox, e = enqueueRouter(tx, u, "inbox-pref", "以后回答先给结论", "user", "")
		return e
	})
	if err != nil {
		t.Fatal(err)
	}
	server := testServer(t, s, func(http.ResponseWriter, *http.Request) { t.Error("fast Inbox memory invoked runtime") })
	server.captureRouterMemory(context.Background(), u.ID, inbox)
	j, err := scanMemoryJob(s.DB.QueryRow("SELECT "+memoryJobColumns+" FROM deermate_memory_jobs WHERE owner=?", u.ID))
	if err != nil || !strings.HasPrefix(j.Run, "inbox:") {
		t.Fatal(j, err)
	}
	server.runMemoryJob(context.Background(), j)
	refs, err := s.MemoryReferences(u.ID)
	if err != nil || len(refs) != 1 || refs[0].Scope != "personal" {
		t.Fatal(refs, err)
	}
	source := j.memoryCapture
	if !verifyCapture(s.DB, &source) {
		t.Fatal("canonical Inbox source not verifiable")
	}
	_, _ = s.DB.Exec("DELETE FROM deermate_work_records WHERE owner=? AND kind='inbox' AND id=?", u.ID, inbox.ID)
	if verifyCapture(s.DB, &source) {
		t.Fatal("deleted Inbox source retained authorization")
	}
	for index, input := range []struct{ text, origin string }{
		{"以后回答先给结论", "event"},
		{strings.Repeat("我", 1400) + "不要记住", "user"},
		{"以后回答带上验证码123456", "user"},
	} {
		err = s.workTransaction(context.Background(), func(tx *sql.Tx) error {
			v, e := enqueueRouter(tx, u, fmt.Sprintf("blocked-inbox-%d", index), input.text, input.origin, "")
			if workBool(v, "_memory_eligible") {
				t.Error("untrusted/truncated input received memory provenance")
			}
			return e
		})
		if err != nil {
			t.Fatal(err)
		}
	}
}

func queuedMemory(t *testing.T, s *Store, u User, nonce, text string) memoryJob {
	t.Helper()
	c := captureFixture(t, s, u, nonce, text)
	id, err := s.enqueueMemoryExtraction(context.Background(), c)
	if err != nil {
		t.Fatal(err)
	}
	j, err := scanMemoryJob(s.DB.QueryRow("SELECT "+memoryJobColumns+" FROM deermate_memory_jobs WHERE id=?", id))
	if err != nil {
		t.Fatal(err)
	}
	return j
}

func TestMemoryModelBudgetIsAtomicAndSeparateFromFastPath(t *testing.T) {
	s := testStore(t)
	u := account(t, s, "model-budget@example.com", "admin")
	jobs := []memoryJob{}
	for i := range 6 {
		jobs = append(jobs, queuedMemory(t, s, u, fmt.Sprintf("budget-%d", i), "我的答复习惯是简短直接"))
	}
	var admitted atomic.Int32
	var wg sync.WaitGroup
	for _, j := range jobs {
		wg.Go(func() {
			if s.claimMemoryModel(context.Background(), j, "preferred") == nil {
				admitted.Add(1)
			}
		})
	}
	wg.Wait()
	var used int
	_ = s.DB.QueryRow("SELECT used FROM deermate_memory_model_budget WHERE owner=?", u.ID).Scan(&used)
	if admitted.Load() != 4 || used != 4 {
		t.Fatal("model admission exceeded its daily ceiling", admitted.Load(), used)
	}
	fast := queuedMemory(t, s, u, "zero-cost-pref", "以后回答先给结论")
	server := testServer(t, s, func(http.ResponseWriter, *http.Request) { t.Error("fast path called runtime/model") })
	server.runMemoryJob(context.Background(), fast)
	var state string
	_ = s.DB.QueryRow("SELECT status FROM deermate_memory_jobs WHERE id=?", fast.ID).Scan(&state)
	if state != "completed" {
		t.Fatal("model quota blocked a deterministic preference", state)
	}
}

func TestUnknownExtractionDoesNotSelectOrInvokeModelAgain(t *testing.T) {
	s := testStore(t)
	u := account(t, s, "unknown-extraction@example.com", "admin")
	j := queuedMemory(t, s, u, "unknown-job", "我的答复习惯是简短直接")
	var catalogs, models atomic.Int32
	server := testServer(t, s, func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/api/models":
			catalogs.Add(1)
			respond(w, 200, map[string]any{"models": []any{map[string]string{"name": "original"}}})
		case strings.HasSuffix(r.URL.Path, "/capabilities"):
			respond(w, 200, map[string]any{"contract_version": 1, "bounded": true})
		case strings.HasSuffix(r.URL.Path, "/extract"):
			models.Add(1)
			http.Error(w, "synthetic lost response", 502)
		default:
			t.Error("unexpected runtime call", r.URL.Path)
		}
	})
	server.runMemoryJob(context.Background(), j)
	j, _ = scanMemoryJob(s.DB.QueryRow("SELECT "+memoryJobColumns+" FROM deermate_memory_jobs WHERE id=?", j.ID))
	if j.Status != "uncertain" || j.Model != "original" {
		t.Fatal(j.Status, j.Model)
	}
	for range 3 {
		server.runMemoryJob(context.Background(), j)
	}
	if catalogs.Load() != 1 || models.Load() != 1 {
		t.Fatal("unknown result caused fresh model selection or a second invocation", catalogs.Load(), models.Load())
	}
	var used int
	_ = s.DB.QueryRow("SELECT used FROM deermate_memory_model_budget WHERE owner=?", u.ID).Scan(&used)
	if used != 1 {
		t.Fatal(used)
	}
	result, _ := json.Marshal(map[string]any{"candidates": []memoryCandidate{{Content: "答复简短直接", Category: "preference", Scope: "personal", Evidence: "我的答复习惯是简短直接"}}})
	_, _ = s.DB.Exec("UPDATE deermate_memory_jobs SET provider_state='completed',result=? WHERE id=?", string(result), j.ID)
	j, _ = scanMemoryJob(s.DB.QueryRow("SELECT "+memoryJobColumns+" FROM deermate_memory_jobs WHERE id=?", j.ID))
	server.runMemoryJob(context.Background(), j)
	j, _ = scanMemoryJob(s.DB.QueryRow("SELECT "+memoryJobColumns+" FROM deermate_memory_jobs WHERE id=?", j.ID))
	if j.Status != "completed" || j.Result != "" || catalogs.Load() != 1 || models.Load() != 1 {
		t.Fatal("cached receipt did not settle without provider I/O", j.Status)
	}
}

func TestMemorySourceRevocationAndPauseFenceCachedExtraction(t *testing.T) {
	for _, change := range []string{"pause", "source", "disable"} {
		t.Run(change, func(t *testing.T) {
			s := testStore(t)
			u := account(t, s, "late-result@example.com", "admin")
			j := queuedMemory(t, s, u, "late-result", "我的答复习惯是简短直接")
			result := `{"candidates":[{"content":"答复简短直接","category":"preference","scope":"personal","evidence":"我的答复习惯是简短直接"}]}`
			_, _ = s.DB.Exec("UPDATE deermate_memory_jobs SET provider_state='completed',result=? WHERE id=?", result, j.ID)
			switch change {
			case "pause":
				p, _ := s.PersonalProfile(u.ID)
				p.AutoCaptureEnabled = false
				if _, err := s.UpdatePersonalProfile(context.Background(), p, p.Revision); err != nil {
					t.Fatal(err)
				}
			case "source":
				_, _ = s.DB.Exec("DELETE FROM runs WHERE run_id=?", j.Run)
			case "disable":
				_, _ = s.DB.Exec("UPDATE users SET disabled=1 WHERE id=?", u.ID)
			}
			j, _ = scanMemoryJob(s.DB.QueryRow("SELECT "+memoryJobColumns+" FROM deermate_memory_jobs WHERE id=?", j.ID))
			server := testServer(t, s, func(http.ResponseWriter, *http.Request) { t.Error("late result invoked model") })
			server.runMemoryJob(context.Background(), j)
			var count int
			_ = s.DB.QueryRow("SELECT count(*) FROM deermate_memory_refs WHERE owner=?", u.ID).Scan(&count)
			if count != 0 {
				t.Fatal("revoked job produced a fact", count)
			}
		})
	}
}

func TestCrashedModelClaimRemainsUnknownWithoutReplay(t *testing.T) {
	s := testStore(t)
	u := account(t, s, "crashed-extractor@example.com", "admin")
	j := queuedMemory(t, s, u, "crash-before-http", "我的答复习惯是简短直接")
	if err := s.claimMemoryModel(context.Background(), j, "original"); err != nil {
		t.Fatal(err)
	}
	_, _ = s.DB.Exec("UPDATE deermate_memory_jobs SET lease_until=? WHERE id=?", time.Now().Add(-time.Minute).Unix(), j.ID)
	j, _ = scanMemoryJob(s.DB.QueryRow("SELECT "+memoryJobColumns+" FROM deermate_memory_jobs WHERE id=?", j.ID))
	server := testServer(t, s, func(http.ResponseWriter, *http.Request) { t.Error("restart replayed model admission") })
	server.runMemoryJob(context.Background(), j)
	j, _ = scanMemoryJob(s.DB.QueryRow("SELECT "+memoryJobColumns+" FROM deermate_memory_jobs WHERE id=?", j.ID))
	if j.Status != "uncertain" || j.Model != "original" {
		t.Fatal(j.Status, j.Model)
	}
}

func TestAcknowledgedBackgroundExtractionWaitsWithoutReinvocation(t *testing.T) {
	s := testStore(t)
	u := account(t, s, "scheduled-extraction@example.com", "admin")
	j := queuedMemory(t, s, u, "background-model", "我的答复习惯是简短直接")
	var calls atomic.Int32
	server := testServer(t, s, func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/api/models":
			respond(w, 200, map[string]any{"models": []any{map[string]string{"name": "original"}}})
		case strings.HasSuffix(r.URL.Path, "/capabilities"):
			respond(w, 200, map[string]any{"contract_version": 1, "bounded": true})
		case strings.HasSuffix(r.URL.Path, "/extract"):
			calls.Add(1)
			respond(w, 200, map[string]any{"known": false, "state": "scheduled"})
		default:
			t.Error("unexpected runtime call", r.URL.Path)
		}
	})
	server.runMemoryJob(context.Background(), j)
	j, err := scanMemoryJob(s.DB.QueryRow("SELECT "+memoryJobColumns+" FROM deermate_memory_jobs WHERE id=?", j.ID))
	if err != nil || j.Status != "processing" {
		t.Fatal("known background admission marked unknown", j.Status, err)
	}
	for range 3 {
		server.runMemoryJob(context.Background(), j)
	}
	if calls.Load() != 1 {
		t.Fatal("background call repeated", calls.Load())
	}
	result := `{"candidates":[{"content":"答复简短直接","category":"preference","scope":"personal","evidence":"我的答复习惯是简短直接"}]}`
	_, _ = s.DB.Exec("UPDATE deermate_memory_jobs SET provider_state='completed',result=? WHERE id=?", result, j.ID)
	j, _ = scanMemoryJob(s.DB.QueryRow("SELECT "+memoryJobColumns+" FROM deermate_memory_jobs WHERE id=?", j.ID))
	server.runMemoryJob(context.Background(), j)
	j, _ = scanMemoryJob(s.DB.QueryRow("SELECT "+memoryJobColumns+" FROM deermate_memory_jobs WHERE id=?", j.ID))
	if j.Status != "completed" || j.Result != "" || calls.Load() != 1 {
		t.Fatal(j.Status, calls.Load())
	}
}
