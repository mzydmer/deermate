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

const followupQuestion = "根据已有任务和验证记录，整理这个会话的进展、尚未完成的事项，以及下一步建议。只做分析，不执行新任务。"

type BriefingIntent struct {
	ID            string `json:"id"`
	Kind          string `json:"kind"`
	Question      string `json:"question"`
	Status        string `json:"status"`
	Thread        string `json:"thread_id"`
	Run           string `json:"run_id,omitempty"`
	Task          string `json:"task_id,omitempty"`
	Project       string `json:"project,omitempty"`
	Executor      string `json:"executor,omitempty"`
	Expires       int64  `json:"expires_at"`
	Owner         string `json:"-"`
	Topic         string `json:"-"`
	TopicRevision int64  `json:"-"`
	SourceVersion string `json:"-"`
	Fact          string `json:"-"`
	FactRevision  int64  `json:"-"`
	UserVersion   int    `json:"-"`
	Token         string `json:"-"`
	Context       string `json:"-"`
	Continuation  string `json:"-"`
}

const intentColumns = "id,owner,kind,question,status,thread_id,run_id,task_id,project,executor,expires_at,topic_id,topic_revision,source_version,fact_id,fact_revision,user_version,admission_token,context_json,continuation_json"

func scanIntent(row scanner) (BriefingIntent, error) {
	var i BriefingIntent
	err := row.Scan(&i.ID, &i.Owner, &i.Kind, &i.Question, &i.Status, &i.Thread, &i.Run, &i.Task, &i.Project, &i.Executor, &i.Expires, &i.Topic, &i.TopicRevision, &i.SourceVersion, &i.Fact, &i.FactRevision, &i.UserVersion, &i.Token, &i.Context, &i.Continuation)
	if errors.Is(err, sql.ErrNoRows) {
		err = ErrNotFound
	}
	return i, err
}
func (s *Store) initializeBriefingActions() error {
	_, err := s.DB.Exec(`CREATE TABLE IF NOT EXISTS deermate_briefing_intents (
 id TEXT PRIMARY KEY,owner TEXT NOT NULL REFERENCES users(id),kind TEXT NOT NULL,question TEXT NOT NULL,status TEXT NOT NULL,
 thread_id TEXT NOT NULL,run_id TEXT NOT NULL DEFAULT '',task_id TEXT NOT NULL DEFAULT '',project TEXT NOT NULL DEFAULT '',executor TEXT NOT NULL DEFAULT '',
 expires_at INTEGER NOT NULL,topic_id TEXT NOT NULL DEFAULT '',topic_revision INTEGER NOT NULL DEFAULT 0,source_version TEXT NOT NULL,
 fact_id TEXT NOT NULL DEFAULT '',fact_revision INTEGER NOT NULL DEFAULT 0,user_version INTEGER NOT NULL,admission_token TEXT NOT NULL,
 context_json TEXT NOT NULL,continuation_json TEXT NOT NULL DEFAULT '{}',request_hash TEXT NOT NULL,created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS deermate_briefing_intent_owner ON deermate_briefing_intents(owner,created_at);
CREATE UNIQUE INDEX IF NOT EXISTS deermate_briefing_intent_request ON deermate_briefing_intents(owner,request_hash);`)
	return err
}

func (s *Store) intent(owner, id string) (BriefingIntent, error) {
	return scanIntent(s.DB.QueryRow("SELECT "+intentColumns+" FROM deermate_briefing_intents WHERE owner=? AND id=?", owner, id))
}

func validIntentSource(q memoryReader, i BriefingIntent) bool {
	var role string
	var disabled, setup bool
	var version int
	if q.QueryRow("SELECT system_role,disabled,needs_setup,token_version FROM users WHERE id=?", i.Owner).Scan(&role, &disabled, &setup, &version) != nil || role != "admin" || disabled || setup || version != i.UserVersion {
		return false
	}
	if i.Topic != "" {
		t, err := scanTopic(q.QueryRow("SELECT "+topicColumns+" FROM deermate_attention_topics WHERE owner=? AND id=?", i.Owner, i.Topic))
		if err != nil || t.Status != "active" || t.Revision != i.TopicRevision || t.SnoozedUntil > time.Now().Unix() || !topicAvailable(q, t) {
			return false
		}
		e, err := topicEvidence(q, t, time.Now())
		return err == nil && e.Version == i.SourceVersion && !e.Stale
	}
	if i.Kind == "new_topic" && i.Fact != "" {
		p, err := readProfile(q, i.Owner)
		if err != nil || !p.MemoryEnabled || !p.ProactiveEnabled {
			return false
		}
		var frame struct {
			Policy int64 `json:"policy_revision"`
		}
		if json.Unmarshal([]byte(i.Context), &frame) != nil || frame.Policy != p.PolicyRevision {
			return false
		}
		var revision int64
		var status, scope string
		if q.QueryRow("SELECT revision,status,scope FROM deermate_memory_refs WHERE owner=? AND id=?", i.Owner, i.Fact).Scan(&revision, &status, &scope) != nil || revision != i.FactRevision || status != "active" || scope != "personal" {
			return false
		}
		var op string
		if q.QueryRow("SELECT source_id FROM deermate_memory_refs WHERE id=?", i.Fact).Scan(&op) != nil {
			return false
		}
		source, err := captureSource(q, op)
		return errors.Is(err, sql.ErrNoRows) || (err == nil && verifyCapture(q, source))
	}
	return false
}

func (s *Store) saveIntent(ctx context.Context, u User, i BriefingIntent, fingerprint string) (BriefingIntent, error) {
	var empty BriefingIntent
	tx, err := s.DB.BeginTx(ctx, nil)
	if err != nil {
		return empty, err
	}
	defer tx.Rollback()
	old, err := scanIntent(tx.QueryRow("SELECT "+intentColumns+" FROM deermate_briefing_intents WHERE owner=? AND request_hash=?", u.ID, fingerprint))
	if err == nil {
		// A prepared intent has never crossed the submission fence. An explicit
		// new click may renew its preview after rechecking the same authority.
		// Submitted/uncertain intents always reconcile the original operation.
		if old.Status == "prepared" && old.Expires <= time.Now().Unix() {
			if !validIntentSource(tx, old) {
				return empty, ErrConflict
			}
			old.Expires = time.Now().Add(15 * time.Minute).Unix()
			if _, err = tx.Exec("UPDATE deermate_briefing_intents SET expires_at=?,updated_at=? WHERE id=? AND status='prepared'", old.Expires, time.Now().Unix(), old.ID); err != nil {
				return empty, err
			}
			return old, tx.Commit()
		}
		return old, nil
	}
	if !errors.Is(err, ErrNotFound) {
		return empty, err
	}
	i.ID = "intent_" + uuid()
	i.Owner = u.ID
	i.UserVersion = u.Version
	i.Status = "prepared"
	i.Token = opaque()
	i.Expires = time.Now().Add(15 * time.Minute).Unix()
	if i.Kind == "new_topic" {
		i.Thread = "briefing-" + uuid()
	}
	if !validIntentSource(tx, i) {
		return empty, ErrConflict
	}
	_, err = tx.Exec(`INSERT INTO deermate_briefing_intents(id,owner,kind,question,status,thread_id,expires_at,topic_id,topic_revision,source_version,fact_id,fact_revision,user_version,admission_token,context_json,continuation_json,project,executor,request_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`, i.ID, u.ID, i.Kind, i.Question, i.Status, i.Thread, i.Expires, i.Topic, i.TopicRevision, i.SourceVersion, i.Fact, i.FactRevision, u.Version, i.Token, i.Context, i.Continuation, i.Project, i.Executor, fingerprint, time.Now().Unix(), time.Now().Unix())
	if err != nil {
		return empty, err
	}
	return i, tx.Commit()
}

func (s *Store) claimIntent(ctx context.Context, u User, id string) (BriefingIntent, bool, error) {
	var empty BriefingIntent
	tx, err := s.DB.BeginTx(ctx, nil)
	if err != nil {
		return empty, false, err
	}
	defer tx.Rollback()
	i, err := scanIntent(tx.QueryRow("SELECT "+intentColumns+" FROM deermate_briefing_intents WHERE owner=? AND id=?", u.ID, id))
	if err != nil {
		return empty, false, err
	}
	if i.Status != "prepared" {
		return i, false, nil
	}
	if !validIntentSource(tx, i) {
		return empty, false, ErrConflict
	}
	if i.Expires < time.Now().Unix() {
		return empty, false, ErrConflict
	}
	_, err = tx.Exec("UPDATE deermate_briefing_intents SET status='submitting',updated_at=? WHERE id=?", time.Now().Unix(), id)
	if err != nil {
		return empty, false, err
	}
	i.Status = "submitting"
	return i, true, tx.Commit()
}

func (s *Store) inspectIntent(owner, id string) (BriefingIntent, error) {
	i, err := s.intent(owner, id)
	if err != nil {
		return i, err
	}
	// Completed requests remain inspectable after their task advances. Ownership
	// and the topic incarnation are still required; never return revoked bodies.
	var current User
	current, err = s.User(owner)
	if err != nil || current.Role != "admin" || current.Disabled || current.Version != i.UserVersion {
		return BriefingIntent{}, ErrNotFound
	}
	if i.Topic != "" {
		t, e := scanTopic(s.DB.QueryRow("SELECT "+topicColumns+" FROM deermate_attention_topics WHERE owner=? AND id=?", owner, i.Topic))
		if e != nil || t.Status == "removed" || !topicAvailable(s.DB, t) {
			i.Status = "blocked"
			i.Question = ""
			i.Thread = ""
			i.Task = ""
			i.Run = ""
			return i, nil
		}
	}
	if i.Kind == "new_topic" && !validIntentSource(s.DB, i) {
		i.Status = "blocked"
		i.Question = ""
		i.Thread = ""
		i.Run = ""
		return i, nil
	}
	if i.Status == "prepared" {
		return i, nil
	}
	if i.Kind != "continue" {
		key := "http-run:" + digest(owner+"\x00"+i.Thread+"\x00extension:deermate.briefing:"+i.ID)
		var status string
		err = s.DB.QueryRow("SELECT run_id,status FROM runs WHERE user_id=? AND thread_id=? AND idempotency_key=?", owner, i.Thread, key).Scan(&i.Run, &status)
		if err == nil {
			switch status {
			case "success":
				i.Status = "completed"
			case "pending", "running":
				i.Status = "running"
			default:
				i.Status = "failed"
			}
		}
	} else {
		var status string
		err = s.DB.QueryRow("SELECT id,status FROM mcp_tasks WHERE user_id=? AND thread_id=? AND tool_call_id=? AND run_id=? ORDER BY created_at LIMIT 1", owner, i.Thread, i.ID, "briefing:"+i.ID).Scan(&i.Task, &status)
		if err == nil {
			switch status {
			case "completed":
				i.Status = "completed"
			case "failed", "cancelled":
				i.Status = "failed"
			default:
				i.Status = "running"
			}
		}
	}
	if err != nil && !errors.Is(err, sql.ErrNoRows) {
		return i, err
	}
	if errors.Is(err, sql.ErrNoRows) {
		i.Status = "uncertain"
	}
	_, err = s.DB.Exec("UPDATE deermate_briefing_intents SET status=?,run_id=?,task_id=?,updated_at=? WHERE owner=? AND id=?", i.Status, i.Run, i.Task, time.Now().Unix(), owner, id)
	return i, err
}

func (s *Server) prepareBriefingIntent(w http.ResponseWriter, r *http.Request) {
	if !personalAccess(w, r) {
		return
	}
	u := sessionOf(r).User
	if u.Role != "admin" {
		fail(w, 403, "permission_denied", "This account cannot start Agent runs")
		return
	}
	var body struct {
		Kind         string `json:"kind"`
		Topic        string `json:"topic_id"`
		Evidence     string `json:"evidence_revision"`
		Fact         string `json:"fact_id"`
		FactRevision int64  `json:"fact_revision"`
		Message      string `json:"message"`
		Fingerprint  string `json:"continuation_fingerprint"`
	}
	if !decode(w, r, &body) {
		return
	}
	i := BriefingIntent{Owner: u.ID, Kind: body.Kind, Topic: body.Topic, Fact: body.Fact, FactRevision: body.FactRevision, Continuation: "{}"}
	if body.Kind == "followup" || body.Kind == "continue" {
		t, err := scanTopic(s.Store.DB.QueryRow("SELECT "+topicColumns+" FROM deermate_attention_topics WHERE owner=? AND id=?", u.ID, body.Topic))
		if err != nil {
			storeError(w, err)
			return
		}
		if !topicAvailable(s.Store.DB, t) || t.Status != "active" {
			memoryError(w, ErrConflict)
			return
		}
		e, err := topicEvidence(s.Store.DB, t, time.Now())
		if err != nil || e.Version != body.Evidence || e.Busy || e.Stale {
			memoryError(w, ErrConflict)
			return
		}
		i.Thread = t.Thread
		i.TopicRevision = t.Revision
		i.SourceVersion = e.Version
		frame, _ := json.Marshal(map[string]any{"topic": t.Title, "goal": t.Goal, "evidence": e, "checked_at": time.Now().Unix()})
		i.Context = string(frame)
		i.Question = followupQuestion
		if body.Kind == "continue" {
			if !validMemoryText(body.Message) || len([]rune(body.Message)) > 1000 {
				memoryError(w, ErrCredentials)
				return
			}
			payload, _ := json.Marshal(map[string]any{"topic_id": t.ID, "source_version": e.Version})
			ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
			defer cancel()
			description, err := s.engine.query(ctx, r, "POST", "/api/plugins/deermate.briefing/actions/describe", payload)
			if err != nil {
				fail(w, 409, "continuation_unavailable", "The existing coding session cannot continue now")
				return
			}
			var info struct {
				Project     string `json:"project"`
				Executor    string `json:"executor"`
				Head        string `json:"head"`
				Fingerprint string `json:"fingerprint"`
			}
			if json.Unmarshal(description, &info) != nil || info.Head != e.Task || info.Executor != "codex" || info.Project == "" || info.Fingerprint != body.Fingerprint {
				memoryError(w, ErrConflict)
				return
			}
			i.Question = strings.TrimSpace(body.Message)
			i.Continuation = string(description)
			i.Project = info.Project
			i.Executor = info.Executor
		}
	} else if body.Kind == "new_topic" {
		fact, err := s.suggestionFact(r, u.ID, body.Fact, body.FactRevision)
		if err != nil {
			memoryError(w, ErrConflict)
			return
		}
		i.SourceVersion = digest(string(fact))
		i.Context = string(fact)
		i.Question = suggestedQuestion(fact)
	} else {
		memoryError(w, ErrCredentials)
		return
	}
	if i.Kind != "continue" {
		ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
		defer cancel()
		raw, e := s.engine.query(ctx, r, "GET", "/api/models", nil)
		var listing struct {
			Models []json.RawMessage `json:"models"`
		}
		if e != nil || json.Unmarshal(raw, &listing) != nil || len(listing.Models) == 0 {
			fail(w, 409, "model_unavailable", "Configure an available chat model before starting a follow-up")
			return
		}
	}
	frame, _ := json.Marshal([]any{i.Kind, i.Topic, i.TopicRevision, i.SourceVersion, i.Fact, i.FactRevision, i.Question, i.Continuation, u.Version})
	result, err := s.Store.saveIntent(r.Context(), u, i, digest(string(frame)))
	if err != nil {
		memoryError(w, err)
		return
	}
	respond(w, 200, result)
}

func (s *Server) performBriefingIntent(w http.ResponseWriter, r *http.Request) {
	if !personalAccess(w, r) {
		return
	}
	u := sessionOf(r).User
	if u.Role != "admin" {
		fail(w, 403, "permission_denied", "This account cannot start Agent runs")
		return
	}
	i, fresh, err := s.Store.claimIntent(r.Context(), u, r.PathValue("id"))
	if err != nil {
		memoryError(w, err)
		return
	}
	if fresh {
		body, _ := json.Marshal(map[string]string{"intent_id": i.ID})
		ctx, cancel := context.WithTimeout(r.Context(), 35*time.Second)
		defer cancel()
		_, callErr := s.engine.query(ctx, r, "POST", "/api/plugins/deermate.briefing/actions/perform", body)
		if callErr != nil {
			_, _ = s.Store.DB.Exec("UPDATE deermate_briefing_intents SET status='uncertain',updated_at=? WHERE id=? AND status='submitting'", time.Now().Unix(), i.ID)
		}
	}
	result, err := s.Store.inspectIntent(u.ID, i.ID)
	if err != nil {
		storeError(w, err)
		return
	}
	respond(w, 202, result)
}

func (s *Server) briefingActionRoutes() {
	s.mux.HandleFunc("GET /api/me/attention-topics/{id}/continuation", s.protected(false, func(w http.ResponseWriter, r *http.Request) {
		if !personalAccess(w, r) {
			return
		}
		u := sessionOf(r).User
		if u.Role != "admin" {
			fail(w, 403, "permission_denied", "Run permission is required")
			return
		}
		t, err := scanTopic(s.Store.DB.QueryRow("SELECT "+topicColumns+" FROM deermate_attention_topics WHERE owner=? AND id=?", u.ID, r.PathValue("id")))
		if err != nil {
			storeError(w, err)
			return
		}
		if !topicAvailable(s.Store.DB, t) {
			memoryError(w, ErrConflict)
			return
		}
		e, err := topicEvidence(s.Store.DB, t, time.Now())
		if err != nil || e.Task == "" || e.Busy || e.Stale {
			memoryError(w, ErrConflict)
			return
		}
		body, _ := json.Marshal(map[string]string{"topic_id": t.ID, "source_version": e.Version})
		ctx, cancel := context.WithTimeout(r.Context(), 12*time.Second)
		defer cancel()
		data, err := s.engine.query(ctx, r, "POST", "/api/plugins/deermate.briefing/actions/describe", body)
		if err != nil {
			fail(w, 409, "continuation_unavailable", "The existing coding session cannot continue now")
			return
		}
		respond(w, 200, data)
	}))
	s.mux.HandleFunc("POST /api/me/briefing/actions", s.protected(false, s.prepareBriefingIntent))
	s.mux.HandleFunc("POST /api/me/briefing/actions/{id}", s.protected(false, s.performBriefingIntent))
	s.mux.HandleFunc("GET /api/me/briefing/actions/{id}", s.protected(false, func(w http.ResponseWriter, r *http.Request) {
		if !personalAccess(w, r) {
			return
		}
		i, err := s.Store.inspectIntent(sessionOf(r).User.ID, r.PathValue("id"))
		if err != nil {
			storeError(w, err)
			return
		}
		respond(w, 200, i)
	}))
}
