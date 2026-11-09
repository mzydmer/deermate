package controlplane

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"net/http"
	"time"
)

func (s *Server) settleMemoryControl(ctx context.Context, j memoryJob) {
	// A deictic command may refer only to the uniquely latest capture in this
	// same canonical conversation. Never guess across projects or conversations.
	rows, err := s.Store.DB.Query(`SELECT r.id,r.revision,z.message_id,z.observed_at FROM deermate_memory_refs r
  JOIN deermate_memory_sources z ON z.operation_id=r.source_id
  WHERE r.owner=? AND z.thread_id=? AND z.invalidated_at=0 AND r.status='active' AND z.observed_at>=?
  ORDER BY z.observed_at DESC,z.admitted_at DESC,z.operation_id DESC LIMIT 4`, j.Owner, j.Thread, time.Now().Add(-30*time.Minute).Unix())
	if err != nil {
		return
	}
	type target struct {
		id, message  string
		revision, at int64
	}
	targets := []target{}
	for rows.Next() {
		var v target
		if rows.Scan(&v.id, &v.revision, &v.message, &v.at) == nil {
			targets = append(targets, v)
		}
	}
	rows.Close()
	if len(targets) == 0 || (len(targets) > 1 && (targets[1].message == targets[0].message || targets[1].at == targets[0].at)) {
		_, _ = s.Store.DB.ExecContext(ctx, "UPDATE deermate_memory_jobs SET status='clarification',result='' WHERE id=?", j.ID)
		return
	}
	v := targets[0]
	op, err := s.Store.AdmitMemory(ctx, j.Owner, "delete", v.id, memoryMutation{OperationID: "control-" + j.ID[:48], ExpectedRevision: v.revision})
	if err != nil {
		return
	}
	receipts, _ := json.Marshal([]string{op.ID})
	_, _ = s.Store.DB.ExecContext(ctx, "UPDATE deermate_memory_jobs SET status='completed',result='',receipts=? WHERE id=?", string(receipts), j.ID)
}

func (s *Server) memoryActivity(w http.ResponseWriter, r *http.Request) {
	if !personalAccess(w, r) {
		return
	}
	owner, thread := sessionOf(r).User.ID, r.URL.Query().Get("thread_id")
	if thread == "" {
		memoryError(w, ErrCredentials)
		return
	}
	// Reading activity never calls the Gateway, a provider, or a native agent.
	rows, err := s.Store.DB.Query("SELECT id,status,receipts,updated_at FROM deermate_memory_jobs WHERE owner=? AND thread_id=? ORDER BY created_at DESC,id DESC LIMIT 10", owner, thread)
	if err != nil {
		storeError(w, err)
		return
	}
	type activity struct {
		ID         string            `json:"id"`
		Status     string            `json:"status"`
		Operations []MemoryOperation `json:"operations"`
		Updated    int64             `json:"updated_at"`
		ids        []string
	}
	items := []activity{}
	for rows.Next() {
		var v activity
		var receipts string
		if rows.Scan(&v.ID, &v.Status, &receipts, &v.Updated) == nil {
			_ = json.Unmarshal([]byte(receipts), &v.ids)
			v.Operations = []MemoryOperation{}
			items = append(items, v)
		}
	}
	rows.Close()
	for i := range items {
		for _, id := range items[i].ids {
			if op, e := s.Store.MemoryOperation(owner, id); e == nil {
				if op.Kind != "delete" && op.Status == "completed" {
					var current int
					_ = s.Store.DB.QueryRow("SELECT count(*) FROM deermate_memory_refs WHERE owner=? AND id=? AND source_id=? AND status='active' AND (expires_at=0 OR expires_at>?)", owner, op.FactID, op.ID, time.Now().Unix()).Scan(&current)
					if current == 0 {
						continue
					}
					if source, e := captureSource(s.Store.DB, op.ID); (e == nil && !verifyCapture(s.Store.DB, source)) || (e != nil && !errors.Is(e, sql.ErrNoRows)) {
						continue
					}
				}
				items[i].Operations = append(items[i].Operations, op)
			}
		}
	}
	respond(w, 200, map[string]any{"items": items})
}
