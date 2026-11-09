package controlplane

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"net/http"
)

// Existing profiles keep their exact switches. Their old boolean values cannot
// prove whether a user paused memory, so only new accounts receive V2 defaults.
func (s *Store) initializeWorkspaceMemory() error {
	rows, err := s.DB.Query("PRAGMA table_info(deermate_personal_profiles)")
	if err != nil {
		return err
	}
	columns := map[string]bool{}
	for rows.Next() {
		var cid, notnull, pk int
		var name, kind string
		var def any
		if err = rows.Scan(&cid, &name, &kind, &notnull, &def, &pk); err != nil {
			rows.Close()
			return err
		}
		columns[name] = true
	}
	err = rows.Err()
	rows.Close()
	if err != nil {
		return err
	}
	for _, col := range []struct{ name, definition string }{
		{"policy_origin", "TEXT NOT NULL DEFAULT 'legacy'"},
		{"policy_version", "INTEGER NOT NULL DEFAULT 0"},
	} {
		if !columns[col.name] {
			if _, err = s.DB.Exec("ALTER TABLE deermate_personal_profiles ADD COLUMN " + col.name + " " + col.definition); err != nil {
				return err
			}
		}
	}
	_, err = s.DB.Exec(`
INSERT OR IGNORE INTO deermate_personal_profiles(owner) SELECT id FROM users;
CREATE TABLE IF NOT EXISTS deermate_topic_memory (
 owner TEXT NOT NULL REFERENCES users(id),thread_id TEXT NOT NULL,
 mode TEXT NOT NULL CHECK(mode IN ('temporary','excluded','normal')),
 operation_id TEXT NOT NULL DEFAULT '',revision INTEGER NOT NULL DEFAULT 1,
 PRIMARY KEY(owner,thread_id));`)
	return err
}

func topicMemoryMode(q memoryReader, owner, thread string) (string, error) {
	var mode string
	err := q.QueryRow("SELECT mode FROM deermate_topic_memory WHERE owner=? AND thread_id=?", owner, thread).Scan(&mode)
	if errors.Is(err, sql.ErrNoRows) {
		return "normal", nil
	}
	return mode, err
}

func captureAllowed(q memoryReader, owner, thread string) bool {
	mode, err := topicMemoryMode(q, owner, thread)
	return err == nil && mode == "normal"
}

func (s *Store) reserveTemporary(ctx context.Context, owner, operation string) (string, error) {
	if !resourceID.MatchString(operation) {
		return "", ErrCredentials
	}
	id := "temporary-" + digest(owner + "\x00" + operation)[:32]
	_, err := s.DB.ExecContext(ctx, `INSERT OR IGNORE INTO deermate_topic_memory(owner,thread_id,mode,operation_id) VALUES(?,?,'temporary',?)`, owner, id, operation)
	if err != nil {
		return "", err
	}
	var saved string
	if err = s.DB.QueryRow("SELECT operation_id FROM deermate_topic_memory WHERE owner=? AND thread_id=? AND mode='temporary'", owner, id).Scan(&saved); err != nil || saved != operation {
		return "", ErrConflict
	}
	return id, nil
}

func (s *Server) workspaceMemoryRoutes() {
	s.mux.HandleFunc("POST /api/me/temporary-topics", s.protected(false, s.temporaryTopic))
	s.mux.HandleFunc("GET /api/me/topic-memory/{id}", s.protected(false, s.topicMemory))
	s.mux.HandleFunc("PATCH /api/me/topic-memory/{id}", s.protected(false, s.topicMemory))
	s.mux.HandleFunc("POST /api/me/workspace-memory-migration", s.protected(true, s.workspaceMemoryMigration))
}

func (s *Server) temporaryTopic(w http.ResponseWriter, r *http.Request) {
	if !personalAccess(w, r) {
		return
	}
	var body struct {
		Operation string `json:"operation_id"`
	}
	if !decode(w, r, &body) {
		return
	}
	// Reserve the negative policy BEFORE the runtime can see this conversation.
	id, err := s.Store.reserveTemporary(r.Context(), sessionOf(r).User.ID, body.Operation)
	if err != nil {
		memoryError(w, err)
		return
	}
	encoded, _ := json.Marshal(map[string]any{"thread_id": id})
	raw, err := s.engine.query(r.Context(), r, "POST", "/api/threads", encoded)
	if err != nil {
		// Creation may have committed. Reconcile this ID, never mint another one.
		raw, err = s.engine.query(r.Context(), r, "GET", "/api/threads/"+id, nil)
	}
	var result struct {
		Thread string `json:"thread_id"`
	}
	if err != nil || json.Unmarshal(raw, &result) != nil || result.Thread != id {
		fail(w, 503, "temporary_topic_pending", "Temporary conversation creation is unconfirmed; reconcile the same operation")
		return
	}
	respond(w, 200, map[string]any{"thread_id": id, "mode": "temporary"})
}

func (s *Server) topicMemory(w http.ResponseWriter, r *http.Request) {
	if !personalAccess(w, r) {
		return
	}
	owner, id := sessionOf(r).User.ID, r.PathValue("id")
	if _, err := ownedTopicSource(s.Store.DB, owner, id); err != nil {
		storeError(w, err)
		return
	}
	mode, err := topicMemoryMode(s.Store.DB, owner, id)
	if err != nil {
		storeError(w, err)
		return
	}
	if r.Method == "PATCH" {
		var b struct {
			Excluded bool `json:"excluded"`
		}
		if !decode(w, r, &b) {
			return
		}
		if mode == "temporary" {
			fail(w, 409, "temporary_topic_immutable", "This entire conversation is temporary")
			return
		}
		mode = "normal"
		if b.Excluded {
			mode = "excluded"
		}
		tx, e := s.Store.DB.BeginTx(r.Context(), nil)
		if e != nil {
			storeError(w, e)
			return
		}
		defer tx.Rollback()
		_, e = tx.Exec(`INSERT INTO deermate_topic_memory(owner,thread_id,mode) VALUES(?,?,?) ON CONFLICT(owner,thread_id) DO UPDATE SET mode=excluded.mode,revision=revision+1`, owner, id, mode)
		if e == nil {
			_, e = tx.Exec("UPDATE deermate_personal_profiles SET policy_revision=policy_revision+1,revision=revision+1 WHERE owner=?", owner)
		}
		if e == nil {
			_, e = tx.Exec("UPDATE deermate_memory_refs SET status='interrupted' WHERE owner=? AND status IN ('pending','updating')", owner)
		}
		if e == nil {
			_, e = tx.Exec("UPDATE deermate_memory_operations SET status='invalidated',payload='' WHERE owner=? AND kind!='delete' AND status IN ('pending','processing','uncertain')", owner)
		}
		if e == nil {
			e = tx.Commit()
		}
		if e != nil {
			storeError(w, e)
			return
		}
	}
	respond(w, 200, map[string]string{"thread_id": id, "mode": mode})
}

// Called explicitly for this installation's owner during the approved upgrade.
// Visiting the homepage or starting the server never opts old users back in.
func (s *Server) workspaceMemoryMigration(w http.ResponseWriter, r *http.Request) {
	if !s.workAccess(w, r) {
		return
	}
	var b struct {
		Approve  bool  `json:"approve_default"`
		Expected int64 `json:"expected_revision"`
	}
	if !decode(w, r, &b) {
		return
	}
	p, err := s.Store.PersonalProfile(sessionOf(r).User.ID)
	if err != nil {
		storeError(w, err)
		return
	}
	if !b.Approve || p.Revision != b.Expected || p.PolicyOrigin == "user_choice" {
		memoryError(w, ErrConflict)
		return
	}
	if p.PolicyOrigin != "owner_approved_v2" {
		p.MemoryEnabled, p.AutoCaptureEnabled, p.ProactiveEnabled = true, true, true
		p.PolicyOrigin, p.PolicyVersion = "owner_approved_v2", 2
		p, err = s.Store.UpdatePersonalProfile(r.Context(), p, b.Expected)
	}
	if err != nil {
		memoryError(w, err)
		return
	}
	respond(w, 200, p)
}
