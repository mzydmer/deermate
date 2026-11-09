package controlplane

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"net/http"
	"strings"
	"time"
)

type memoryJob struct {
	memoryCapture
	ID, Status, Mode, Model, Provider, Result string
	Lease, Next                               int64
}

const memoryJobColumns = "id,owner,thread_id,run_id,message_id,message_hash,incarnation,policy_revision,deletion_revision,observed_at,status,mode,model,provider_state,result,lease_until,next_attempt"

func (s *Store) initializeMemoryExtraction() error {
	_, err := s.DB.Exec(`CREATE TABLE IF NOT EXISTS deermate_memory_jobs (
 id TEXT PRIMARY KEY,owner TEXT NOT NULL REFERENCES users(id),thread_id TEXT NOT NULL,run_id TEXT NOT NULL,
 message_id TEXT NOT NULL,message_hash TEXT NOT NULL,incarnation TEXT NOT NULL,
 policy_revision INTEGER NOT NULL,deletion_revision INTEGER NOT NULL,observed_at INTEGER NOT NULL,
 status TEXT NOT NULL,mode TEXT NOT NULL,model TEXT NOT NULL DEFAULT '',provider_state TEXT NOT NULL DEFAULT 'reserved',
 result TEXT NOT NULL DEFAULT '',failure_code TEXT NOT NULL DEFAULT '',receipts TEXT NOT NULL DEFAULT '[]',lease_until INTEGER NOT NULL DEFAULT 0,next_attempt INTEGER NOT NULL DEFAULT 0,
 created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS deermate_memory_jobs_queue ON deermate_memory_jobs(status,next_attempt,created_at);
CREATE TABLE IF NOT EXISTS deermate_memory_model_budget (
 owner TEXT NOT NULL REFERENCES users(id),day TEXT NOT NULL,used INTEGER NOT NULL,
 PRIMARY KEY(owner,day));`)
	if err != nil {
		return err
	}
	var failureColumn int
	if err = s.DB.QueryRow("SELECT count(*) FROM pragma_table_info('deermate_memory_jobs') WHERE name='failure_code'").Scan(&failureColumn); err != nil {
		return err
	}
	if failureColumn == 0 {
		if _, err = s.DB.Exec("ALTER TABLE deermate_memory_jobs ADD COLUMN failure_code TEXT NOT NULL DEFAULT ''"); err != nil {
			return err
		}
	}
	return s.initializeMemoryHistory()
}

func scanMemoryJob(row scanner) (memoryJob, error) {
	var j memoryJob
	err := row.Scan(&j.ID, &j.Owner, &j.Thread, &j.Run, &j.Message, &j.Hash, &j.Incarnation, &j.Policy, &j.Deleted, &j.Observed, &j.Status, &j.Mode, &j.Model, &j.Provider, &j.Result, &j.Lease, &j.Next)
	if errors.Is(err, sql.ErrNoRows) {
		err = ErrNotFound
	}
	j.Job = j.ID
	return j, err
}

func canonicalMemoryInput(q memoryReader, source *memoryCapture) (string, bool) {
	if strings.HasPrefix(source.Run, "inbox:") {
		if source.Invalidated != 0 {
			return "", false
		}
		return inboxMemoryInput(q, source)
	}
	if !verifyCapture(q, source) {
		return "", false
	}
	var kwargs string
	if err := q.QueryRow("SELECT kwargs_json FROM runs WHERE run_id=? AND thread_id=? AND user_id=?", source.Run, source.Thread, source.Owner).Scan(&kwargs); err != nil {
		return "", false
	}
	var body struct {
		Input json.RawMessage `json:"input"`
	}
	if json.Unmarshal([]byte(kwargs), &body) != nil {
		return "", false
	}
	id, text, ok := captureText(body.Input)
	return text, ok && id == source.Message && digest(text) == source.Hash
}

func (s *Store) enqueueMemoryExtraction(ctx context.Context, source memoryCapture) (string, error) {
	tx, err := s.DB.BeginTx(ctx, nil)
	if err != nil {
		return "", err
	}
	defer tx.Rollback()
	p, err := readProfile(tx, source.Owner)
	if err != nil {
		return "", err
	}
	if source.Historical {
		var status string
		if tx.QueryRow("SELECT status FROM deermate_memory_history WHERE owner=?", source.Owner).Scan(&status) != nil || status != "processing" {
			return "", ErrConflict
		}
	}
	raw, valid := canonicalMemoryInput(tx, &source)
	if !valid || !automaticMemorySafe(raw) || !p.AutoCaptureEnabled || !captureAllowed(tx, source.Owner, source.Thread) || p.PolicyRevision != source.Policy || p.DeletionRevision != source.Deleted {
		return "", ErrConflict
	}
	mode := "model"
	if len(naturalMemories(raw)) > 0 || memoryControl(raw) {
		mode = "fast"
	} else if !memoryMayExtract(raw) {
		return "", ErrCredentials
	}
	id := "memory-" + digest(source.Owner + "\x00" + source.Thread + "\x00" + source.Message + "\x00" + source.Hash)[:48]
	var exists int
	if err = tx.QueryRow("SELECT count(*) FROM deermate_memory_jobs WHERE id=?", id).Scan(&exists); err != nil {
		return "", err
	}
	if exists != 0 {
		return id, nil
	}
	var ownerPending, totalPending int
	if err = tx.QueryRow("SELECT count(*),coalesce(sum(CASE WHEN owner=? THEN 1 ELSE 0 END),0) FROM deermate_memory_jobs WHERE status NOT IN ('completed','invalidated','failed')", source.Owner).Scan(&totalPending, &ownerPending); err != nil {
		return "", err
	}
	if ownerPending >= 50 || totalPending >= 200 {
		return "", ErrConflict
	}
	now := time.Now().Unix()
	_, err = tx.Exec(`INSERT INTO deermate_memory_jobs(id,owner,thread_id,run_id,message_id,message_hash,incarnation,policy_revision,deletion_revision,observed_at,status,mode,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,'pending',?,?,?)`, id, source.Owner, source.Thread, source.Run, source.Message, source.Hash, source.Incarnation, source.Policy, source.Deleted, source.Observed, mode, now, now)
	if err != nil {
		return "", err
	}
	if source.Historical {
		if _, err = tx.Exec("INSERT OR IGNORE INTO deermate_memory_history_items(owner,job_id) VALUES(?,?)", source.Owner, id); err != nil {
			return "", err
		}
	}
	return id, tx.Commit()
}

func (s *Store) memoryJobValid(j *memoryJob) bool {
	u, err := s.User(j.Owner)
	if err != nil || u.Disabled || u.NeedsSetup {
		return false
	}
	p, err := s.PersonalProfile(j.Owner)
	return err == nil && p.AutoCaptureEnabled && p.PolicyRevision == j.Policy && p.DeletionRevision == j.Deleted && captureAllowed(s.DB, j.Owner, j.Thread) && verifyCapture(s.DB, &j.memoryCapture)
}

// The budget is an admission ceiling, not a claim about actual billed tokens.
// UTC day prevents a timezone change from resetting a user's call allowance.
func (s *Store) claimMemoryModel(ctx context.Context, j memoryJob, model string) error {
	tx, err := s.DB.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	day := time.Now().UTC().Format("2006-01-02")
	var used, total int
	if err = tx.QueryRow("SELECT coalesce(sum(used),0),coalesce(sum(CASE WHEN owner=? THEN used ELSE 0 END),0) FROM deermate_memory_model_budget WHERE day=?", j.Owner, day).Scan(&total, &used); err != nil {
		return err
	}
	if used >= 4 || total >= 32 {
		return ErrConflict
	}
	result, err := tx.Exec(`UPDATE deermate_memory_jobs SET status='processing',model=?,lease_until=?,updated_at=? WHERE id=? AND owner=? AND status IN ('pending','waiting_model','budget_wait') AND provider_state='reserved'`, model, time.Now().Add(90*time.Second).Unix(), time.Now().Unix(), j.ID, j.Owner)
	if err != nil {
		return err
	}
	if n, _ := result.RowsAffected(); n != 1 {
		return ErrConflict
	}
	if _, err = tx.Exec(`INSERT INTO deermate_memory_model_budget(owner,day,used) VALUES(?,?,1) ON CONFLICT(owner,day) DO UPDATE SET used=used+1`, j.Owner, day); err != nil {
		return err
	}
	return tx.Commit()
}

func semanticMemoryCandidate(raw string, c memoryCandidate) (memoryCandidate, bool) {
	if len(c.Evidence) < 6 || !strings.Contains(raw, c.Evidence) || !automaticMemorySafe(c.Content) || len(c.Content) > 2000 {
		return c, false
	}
	if c.Category != "preference" && c.Category != "goal" && c.Category != "context" {
		return c, false
	}
	if c.Scope == "" {
		c.Scope = "personal"
	}
	if c.Scope == "project" {
		if !memoryProjectLabel.MatchString(c.Project) || !strings.Contains(raw, c.Project) || containsMemoryTerm(c.Project, "这个", "当前", "本次") {
			return c, false
		}
		c.Slot = ""
	} else if c.Scope == "topic" {
		if containsMemoryTerm(c.Evidence, "这次", "本次", "this time") {
			c.Slot = "current_phase"
		} else {
			c.Slot = ""
		}
	} else if c.Scope == "personal" {
		if containsMemoryTerm(strings.ToLower(c.Evidence), "项目", "仓库", "project", "repository") {
			c.Scope, c.Category, c.Slot = "topic", "context", ""
		} else if c.Category == "preference" {
			if containsMemoryTerm(strings.ToLower(c.Evidence), "文档", "说明", "document") {
				c.Slot = "document_style"
			} else if containsMemoryTerm(strings.ToLower(c.Evidence), "回答", "回复", "答复", "结论", "结果", "answer", "response", "conclusion") {
				c.Slot = "response_style"
			} else {
				c.Slot = ""
			}
		} else {
			c.Slot = ""
		}
	} else {
		return c, false
	}
	return c, true
}

func (s *Server) settleMemoryJob(ctx context.Context, j memoryJob) {
	if !s.Store.memoryJobValid(&j) {
		_, _ = s.Store.DB.ExecContext(ctx, "UPDATE deermate_memory_jobs SET status='invalidated',result='',updated_at=? WHERE id=?", time.Now().Unix(), j.ID)
		return
	}
	raw, ok := canonicalMemoryInput(s.Store.DB, &j.memoryCapture)
	if !ok {
		return
	}
	if memoryControl(raw) {
		s.settleMemoryControl(ctx, j)
		return
	}
	candidates := naturalMemories(raw)
	if j.Mode == "model" {
		var result struct {
			Candidates []memoryCandidate `json:"candidates"`
		}
		if len(j.Result) > 16000 || json.Unmarshal([]byte(j.Result), &result) != nil || len(result.Candidates) > 3 {
			_, _ = s.Store.DB.ExecContext(ctx, "UPDATE deermate_memory_jobs SET status='failed',result='' WHERE id=?", j.ID)
			return
		}
		candidates = nil
		for _, c := range result.Candidates {
			if candidate, valid := semanticMemoryCandidate(raw, c); valid {
				candidates = append(candidates, candidate)
			}
		}
	}
	ids := []string{}
	for i, c := range candidates {
		if c.Scope == "topic" && memoryStageEnded(s.Store.DB, j.Owner, j.Thread, j.Observed) {
			continue
		}
		// The persistent global Router is not a project/stage conversation.
		if strings.HasPrefix(j.Run, "inbox:") && c.Scope == "topic" {
			continue
		}
		op, err := s.Store.admitNaturalMemory(ctx, j.memoryCapture, c, i)
		if err != nil {
			// A prior preference value may still be in canonical delivery. Retry
			// deterministic admission only, never the extraction model.
			_, _ = s.Store.DB.ExecContext(ctx, "UPDATE deermate_memory_jobs SET next_attempt=?,updated_at=? WHERE id=?", time.Now().Add(3*time.Second).Unix(), time.Now().Unix(), j.ID)
			return
		}
		j.Deleted = max(j.Deleted, op.DeletionRevision)
		ids = append(ids, op.ID)
	}
	// No raw input or candidate body remains after admission. Individual fact
	// operation receipts, not this job state, confirm actual canonical writes.
	receipts, _ := json.Marshal(ids)
	_, _ = s.Store.DB.ExecContext(ctx, "UPDATE deermate_memory_jobs SET status='completed',result='',receipts=?,updated_at=? WHERE id=? AND status NOT IN ('invalidated','failed')", string(receipts), time.Now().Unix(), j.ID)
}

func (s *Server) runMemoryJob(ctx context.Context, j memoryJob) {
	if j.Status == "completed" || j.Status == "invalidated" || j.Status == "failed" {
		return
	}
	if !s.Store.memoryJobValid(&j) {
		_, _ = s.Store.DB.ExecContext(ctx, "UPDATE deermate_memory_jobs SET status='invalidated',result='' WHERE id=?", j.ID)
		return
	}
	if j.Mode == "fast" || j.Provider == "completed" {
		s.settleMemoryJob(ctx, j)
		return
	}
	if j.Status == "processing" || j.Status == "uncertain" {
		// A crashed caller may have lost a provider acknowledgement. Only a
		// durable result can settle it; a missing receipt never re-invokes LLM.
		if j.Lease < time.Now().Unix() {
			_, _ = s.Store.DB.ExecContext(ctx, "UPDATE deermate_memory_jobs SET status='uncertain',next_attempt=? WHERE id=?", time.Now().Add(10*time.Second).Unix(), j.ID)
		} else {
			_, _ = s.Store.DB.ExecContext(ctx, "UPDATE deermate_memory_jobs SET next_attempt=? WHERE id=?", time.Now().Add(3*time.Second).Unix(), j.ID)
		}
		return
	}
	u, err := s.Store.User(j.Owner)
	if err != nil || u.Disabled || u.NeedsSetup {
		return
	}
	r, _ := http.NewRequestWithContext(context.WithValue(ctx, sessionKey{}, Session{User: u}), "POST", s.cfg.Origin+"/api/me/memory-extraction", nil)
	csrf := opaque()
	r.AddCookie(&http.Cookie{Name: "csrf_token", Value: csrf})
	r.Header.Set("X-CSRF-Token", csrf)
	model, err := s.defaultWorkModel(r)
	if err != nil {
		_, _ = s.Store.DB.ExecContext(ctx, "UPDATE deermate_memory_jobs SET status='waiting_model',next_attempt=? WHERE id=?", time.Now().Add(30*time.Second).Unix(), j.ID)
		return
	}
	if err = s.Store.claimMemoryModel(ctx, j, model); err != nil {
		_, _ = s.Store.DB.ExecContext(ctx, "UPDATE deermate_memory_jobs SET status='budget_wait',next_attempt=? WHERE id=? AND status IN ('pending','waiting_model','budget_wait')", time.Now().Add(time.Hour).Unix(), j.ID)
		return
	}
	callCtx, cancel := context.WithTimeout(ctx, 45*time.Second)
	defer cancel()
	r = r.WithContext(context.WithValue(callCtx, sessionKey{}, Session{User: u}))
	body, _ := json.Marshal(map[string]string{"job_id": j.ID})
	acknowledgement, callErr := s.engine.query(callCtx, r, "POST", "/api/plugins/deermate.memory/actions/extract", body)
	var acknowledgementState struct {
		State string `json:"state"`
	}
	_ = json.Unmarshal(acknowledgement, &acknowledgementState)
	current, err := scanMemoryJob(s.Store.DB.QueryRow("SELECT "+memoryJobColumns+" FROM deermate_memory_jobs WHERE id=?", j.ID))
	if err != nil {
		return
	}
	if current.Provider == "completed" {
		s.settleMemoryJob(ctx, current)
	} else if callErr != nil || (acknowledgementState.State != "scheduled" && acknowledgementState.State != "calling") {
		_, _ = s.Store.DB.ExecContext(ctx, "UPDATE deermate_memory_jobs SET status='uncertain',next_attempt=? WHERE id=? AND status='processing'", time.Now().Add(10*time.Second).Unix(), j.ID)
	}
}

func (s *Server) RunMemoryExtractionQueue(ctx context.Context) {
	go s.runMemoryExtractionMode(ctx, "model")
	s.runMemoryExtractionMode(ctx, "fast")
}

func (s *Server) runMemoryExtractionMode(ctx context.Context, mode string) {
	ticker := time.NewTicker(time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
		j, err := scanMemoryJob(s.Store.DB.QueryRow("SELECT "+memoryJobColumns+" FROM deermate_memory_jobs WHERE mode=? AND status IN ('pending','waiting_model','budget_wait','processing','uncertain') AND next_attempt<=? ORDER BY created_at,id LIMIT 1", mode, time.Now().Unix()))
		if err == nil {
			s.runMemoryJob(ctx, j)
		}
	}
}
