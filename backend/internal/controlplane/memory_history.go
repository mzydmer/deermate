package controlplane

import (
	"context"
	"database/sql"
	"encoding/json"
	"net/http"
	"strings"
	"time"
)

// A one-off, bounded import. The watermark and item ledger survive restarts;
// ordinary home reads never schedule extraction or native execution.
func (s *Store) initializeMemoryHistory() error {
	_, err := s.DB.Exec(`CREATE TABLE IF NOT EXISTS deermate_memory_history (
 owner TEXT PRIMARY KEY REFERENCES users(id),status TEXT NOT NULL,started_at INTEGER NOT NULL,
 cutoff INTEGER NOT NULL,topics INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS deermate_memory_history_items (
 owner TEXT NOT NULL,job_id TEXT NOT NULL,PRIMARY KEY(owner,job_id));`)
	if err != nil {
		return err
	}
	return s.initializeWorkspaceSnapshot()
}

func (s *Store) scheduleMemoryHistory(ctx context.Context, owner string) error {
	p, err := s.PersonalProfile(owner)
	if err != nil || !p.AutoCaptureEnabled || p.PolicyVersion < 2 {
		return err
	}
	now := time.Now().Unix()
	// Do not claim the import before the pinned runtime database is available.
	rows, err := s.DB.Query(`SELECT t.thread_id FROM threads_meta t JOIN runs r ON r.thread_id=t.thread_id AND r.user_id=t.user_id
 WHERE t.user_id=? AND t.project_id IS NULL AND coalesce(t.incarnation,'')!=''
 AND coalesce(json_extract(t.metadata_json,'$.deerflow_archived'),0)=0
 AND r.evidence_origin='interactive' AND r.origin_kind IS NULL AND r.operation_kind='run'
 AND CAST(strftime('%s',r.created_at) AS INTEGER)>=?
 GROUP BY t.thread_id ORDER BY max(r.created_at) DESC,t.thread_id LIMIT 10`, owner, now-7*86400)
	if err != nil {
		return err
	}
	threads := []string{}
	for rows.Next() {
		var id string
		if err = rows.Scan(&id); err != nil {
			rows.Close()
			return err
		}
		threads = append(threads, id)
	}
	err = rows.Err()
	rows.Close()
	if err != nil {
		return err
	}
	result, err := s.DB.ExecContext(ctx, `INSERT OR IGNORE INTO deermate_memory_history(owner,status,started_at,cutoff,topics) VALUES(?,'processing',?,?,?)`, owner, now, now-7*86400, len(threads))
	if err != nil {
		return err
	}
	if n, _ := result.RowsAffected(); n == 0 {
		return nil
	}
	return s.fillMemoryHistory(ctx, owner, threads)
}

func (s *Store) fillMemoryHistory(ctx context.Context, owner string, threads []string) error {
	p, err := s.PersonalProfile(owner)
	if err != nil {
		return err
	}
	var forgotten int64
	_ = s.DB.QueryRow("SELECT coalesce(max(created_at),0) FROM deermate_memory_barriers WHERE owner=?", owner).Scan(&forgotten)
	for _, thread := range threads {
		if !captureAllowed(s.DB, owner, thread) {
			continue
		}
		rows, e := s.DB.Query(`SELECT run_id,kwargs_json,CAST(strftime('%s',created_at) AS INTEGER) FROM runs
   WHERE user_id=? AND thread_id=? AND evidence_origin='interactive' AND origin_kind IS NULL AND operation_kind='run'
   AND CAST(strftime('%s',created_at) AS INTEGER)>=(SELECT cutoff FROM deermate_memory_history WHERE owner=?)
   ORDER BY created_at DESC,run_id DESC LIMIT 5`, owner, thread, owner)
		if e != nil {
			return e
		}
		sources := []memoryCapture{}
		for rows.Next() {
			var run, raw string
			var observed int64
			if e = rows.Scan(&run, &raw, &observed); e != nil {
				break
			}
			var b struct {
				Input json.RawMessage `json:"input"`
			}
			if json.Unmarshal([]byte(raw), &b) != nil {
				continue
			}
			message, text, ok := captureText(b.Input)
			if !ok || !automaticMemorySafe(text) {
				continue
			}
			if observed <= forgotten {
				continue
			}
			sources = append(sources, memoryCapture{Owner: owner, Thread: thread, Run: run, Message: message, Hash: digest(text), Policy: p.PolicyRevision, Deleted: p.DeletionRevision, Observed: observed, Historical: true})
		}
		rows.Close()
		if e != nil {
			return e
		}
		for _, source := range sources {
			var status string
			if s.DB.QueryRow("SELECT status FROM deermate_memory_history WHERE owner=?", owner).Scan(&status) != nil || status != "processing" {
				return nil
			}
			_, _ = s.enqueueMemoryExtraction(ctx, source)
		}
	}
	_, err = s.DB.ExecContext(ctx, "UPDATE deermate_memory_history SET status='queued' WHERE owner=? AND status='processing'", owner)
	return err
}

func (s *Server) RunMemoryHistoryQueue(ctx context.Context) {
	ticker := time.NewTicker(15 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
		rows, err := s.Store.DB.Query(`SELECT p.owner FROM deermate_personal_profiles p JOIN users u ON u.id=p.owner
   WHERE p.auto_capture_enabled=1 AND p.policy_version>=2 AND u.disabled=0 AND u.needs_setup=0
   AND NOT EXISTS(SELECT 1 FROM deermate_memory_history h WHERE h.owner=p.owner) LIMIT 10`)
		if err != nil {
			continue
		}
		owners := []string{}
		for rows.Next() {
			var id string
			if rows.Scan(&id) == nil {
				owners = append(owners, id)
			}
		}
		rows.Close()
		for _, owner := range owners {
			_ = s.Store.scheduleMemoryHistory(ctx, owner)
		}
		// A crash in enumeration is stopped rather than replaying an unbounded scan.
		_, _ = s.Store.DB.ExecContext(ctx, "UPDATE deermate_memory_history SET status='interrupted' WHERE status='processing' AND started_at<?", time.Now().Add(-2*time.Minute).Unix())
	}
}

func (s *Server) memoryHistory(w http.ResponseWriter, r *http.Request) {
	if !personalAccess(w, r) {
		return
	}
	owner := sessionOf(r).User.ID
	if r.Method == "POST" {
		var b struct {
			Action string `json:"action"`
		}
		if !decode(w, r, &b) {
			return
		}
		if b.Action != "stop" && b.Action != "undo" {
			memoryError(w, ErrCredentials)
			return
		}
		tx, err := s.Store.DB.BeginTx(r.Context(), nil)
		if err != nil {
			storeError(w, err)
			return
		}
		defer tx.Rollback()
		_, err = tx.Exec("INSERT OR IGNORE INTO deermate_memory_history(owner,status,started_at,cutoff) VALUES(?,?,?,?)", owner, b.Action, time.Now().Unix(), time.Now().Unix())
		if err != nil {
			storeError(w, err)
			return
		}
		_, err = tx.Exec("UPDATE deermate_memory_history SET status=? WHERE owner=?", b.Action, owner)
		if err == nil {
			_, err = tx.Exec(`UPDATE deermate_memory_jobs SET status='invalidated',result='' WHERE owner=?
    AND id IN(SELECT job_id FROM deermate_memory_history_items WHERE owner=?) AND status NOT IN('completed','failed','invalidated')`, owner, owner)
		}
		if err == nil {
			err = tx.Commit()
		}
		if err != nil {
			storeError(w, err)
			return
		}
		if b.Action == "undo" {
			// Only newly created facts whose *current* provenance is still this
			// import are removed. Later personal corrections and preexisting facts stay.
			rows, e := s.Store.DB.Query(`SELECT r.id,r.revision FROM deermate_memory_refs r
    JOIN deermate_memory_operations o ON o.id=r.source_id
    JOIN deermate_memory_sources z ON z.operation_id=o.id
    JOIN deermate_memory_jobs j ON j.owner=z.owner AND j.thread_id=z.thread_id AND j.message_id=z.message_id AND j.message_hash=z.message_hash
    JOIN deermate_memory_history_items h ON h.job_id=j.id AND h.owner=j.owner
    WHERE r.owner=? AND o.kind='create' AND r.status IN('active','pending','interrupted')`, owner)
			if e != nil {
				storeError(w, e)
				return
			}
			refs := []MemoryReference{}
			for rows.Next() {
				var ref MemoryReference
				if rows.Scan(&ref.ID, &ref.Revision) == nil {
					refs = append(refs, ref)
				}
			}
			rows.Close()
			for _, ref := range refs {
				_, _ = s.Store.AdmitMemory(r.Context(), owner, "delete", ref.ID, memoryMutation{OperationID: "undo-history-" + ref.ID, ExpectedRevision: ref.Revision})
			}
		}
	}
	var status string
	var started, cutoff, topics int64
	err := s.Store.DB.QueryRow("SELECT status,started_at,cutoff,topics FROM deermate_memory_history WHERE owner=?", owner).Scan(&status, &started, &cutoff, &topics)
	if err == sql.ErrNoRows {
		status = "not_started"
	} else if err != nil {
		storeError(w, err)
		return
	}
	var total, done int
	_ = s.Store.DB.QueryRow(`SELECT count(*),coalesce(sum(CASE WHEN j.status IN('completed','failed','invalidated') THEN 1 ELSE 0 END),0)
  FROM deermate_memory_history_items h JOIN deermate_memory_jobs j ON j.id=h.job_id WHERE h.owner=?`, owner).Scan(&total, &done)
	if status == "queued" && total == done {
		status = "completed"
	}
	respond(w, 200, map[string]any{"status": status, "started_at": started, "cutoff": cutoff, "topics": topics, "total": total, "settled": done, "limits": map[string]int{"days": 7, "topics": 10, "messages_per_topic": 5}})
}

func (s *Server) memorySource(w http.ResponseWriter, r *http.Request) {
	if !personalAccess(w, r) {
		return
	}
	owner, id := sessionOf(r).User.ID, r.PathValue("id")
	ref, err := scanMemoryRef(s.Store.DB.QueryRow("SELECT "+memoryRefColumns+" FROM deermate_memory_refs WHERE id=? AND owner=? AND status!='deleted'", id, owner))
	if err != nil {
		storeError(w, err)
		return
	}
	source, err := captureSource(s.Store.DB, ref.Source)
	out := map[string]any{"fact_id": id, "scope": ref.Scope, "expires_at": ref.Expires, "updated_at": ref.Updated, "kind": "manual", "state": "available"}
	if err == nil && ref.Status == "active" {
		raw, ok := canonicalMemoryInput(s.Store.DB, source)
		if !ok || source.Owner != owner {
			out["state"] = "unavailable"
		} else {
			out["kind"] = "chat"
			if strings.HasPrefix(source.Run, "inbox:") {
				out["kind"] = "inbox"
			}
			out["text"], out["thread_id"], out["message_id"], out["observed_at"] = raw, source.Thread, source.Message, source.Observed
		}
	} else if err != nil && err != sql.ErrNoRows {
		storeError(w, err)
		return
	} else if ref.Status != "active" {
		out["state"] = "unavailable"
	}
	usages := []map[string]any{}
	rows, err := s.Store.DB.Query("SELECT thread_id,last_used FROM deermate_memory_usage WHERE owner=? AND fact_id=? ORDER BY last_used DESC LIMIT 10", owner, id)
	if err != nil {
		storeError(w, err)
		return
	}
	type usage struct {
		thread string
		at     int64
	}
	uses := []usage{}
	for rows.Next() {
		var v usage
		if rows.Scan(&v.thread, &v.at) == nil {
			uses = append(uses, v)
		}
	}
	rows.Close()
	for _, v := range uses {
		if topic, e := ownedTopicSource(s.Store.DB, owner, v.thread); e == nil && topic.Project == "" && !topic.Archived {
			usages = append(usages, map[string]any{"thread_id": v.thread, "title": topic.Title, "included_at": v.at})
		}
	}
	out["uses"] = usages
	respond(w, 200, out)
}
