package controlplane

import (
	"context"
	"fmt"
	"net/http"
	"testing"
	"time"
)

func TestHistoryIsBoundedIdempotentAndKeepsCurrentPreferences(t *testing.T) {
	s := testStore(t)
	u := account(t, s, "history@example.com", "admin")
	current := captureFixture(t, s, u, "current", "以后回答先给结论")
	op, e := s.admitNaturalMemory(context.Background(), current, naturalMemories("以后回答先给结论")[0], 0)
	if e != nil {
		t.Fatal(e)
	}
	completeNatural(t, s, op, 1)
	for i := range 12 {
		c := captureFixture(t, s, u, fmt.Sprintf("old-%d", i), "以后回答先列事实")
		_, _ = s.DB.Exec("UPDATE runs SET created_at=? WHERE run_id=?", time.Now().Add(-time.Hour).UTC().Format("2006-01-02 15:04:05.999999"), c.Run)
	}
	if e = s.scheduleMemoryHistory(context.Background(), u.ID); e != nil {
		t.Fatal(e)
	}
	var topics, count int
	_ = s.DB.QueryRow("SELECT topics FROM deermate_memory_history WHERE owner=?", u.ID).Scan(&topics)
	_ = s.DB.QueryRow("SELECT count(*) FROM deermate_memory_history_items WHERE owner=?", u.ID).Scan(&count)
	if topics != 10 || count != 10 {
		t.Fatal(topics, count)
	}
	if e = s.scheduleMemoryHistory(context.Background(), u.ID); e != nil {
		t.Fatal(e)
	}
	var again int
	_ = s.DB.QueryRow("SELECT count(*) FROM deermate_memory_history_items WHERE owner=?", u.ID).Scan(&again)
	if count != again {
		t.Fatal("history repeated")
	}
	server := testServer(t, s, func(http.ResponseWriter, *http.Request) { t.Error("fast history called model") })
	rows, e := s.DB.Query("SELECT "+memoryJobColumns+" FROM deermate_memory_jobs WHERE owner=?", u.ID)
	if e != nil {
		t.Fatal(e)
	}
	jobs := []memoryJob{}
	for rows.Next() {
		j, e := scanMemoryJob(rows)
		if e != nil {
			t.Fatal(e)
		}
		jobs = append(jobs, j)
	}
	rows.Close()
	for _, j := range jobs {
		server.runMemoryJob(context.Background(), j)
	}
	ref, e := scanMemoryRef(s.DB.QueryRow("SELECT "+memoryRefColumns+" FROM deermate_memory_refs WHERE id=?", op.FactID))
	if e != nil || ref.Source != op.ID || ref.Revision != 1 {
		t.Fatal("old import overwrote current preference", ref, e)
	}
}

func TestNaturalForgetUsesUniqueCurrentConversationFact(t *testing.T) {
	s := testStore(t)
	u := account(t, s, "forget-current@example.com", "admin")
	c := captureFixture(t, s, u, "unique", "以后回答先给结论")
	op, e := s.admitNaturalMemory(context.Background(), c, naturalMemories("以后回答先给结论")[0], 0)
	if e != nil {
		t.Fatal(e)
	}
	completeNatural(t, s, op, 1)
	server := testServer(t, s, func(http.ResponseWriter, *http.Request) { t.Error("forget invoked model") })
	server.settleMemoryControl(context.Background(), memoryJob{ID: "memory-123456789012345678901234567890123456789012345678", memoryCapture: memoryCapture{Owner: u.ID, Thread: "unrelated"}})
	ref, _ := scanMemoryRef(s.DB.QueryRow("SELECT "+memoryRefColumns+" FROM deermate_memory_refs WHERE id=?", op.FactID))
	if ref.Status != "active" {
		t.Fatal("cross topic forgetting")
	}
	server.settleMemoryControl(context.Background(), memoryJob{ID: "memory-123456789012345678901234567890123456789012345678", memoryCapture: memoryCapture{Owner: u.ID, Thread: c.Thread}})
	ref, _ = scanMemoryRef(s.DB.QueryRow("SELECT "+memoryRefColumns+" FROM deermate_memory_refs WHERE id=?", op.FactID))
	if ref.Status != "suppressed" {
		t.Fatal(ref)
	}
}
