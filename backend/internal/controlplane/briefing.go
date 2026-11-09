package controlplane

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"net/http"
	"sort"
	"strings"
	"time"
)

type AttentionTopic struct {
	ID           string `json:"id"`
	Thread       string `json:"thread_id"`
	Title        string `json:"title"`
	Goal         string `json:"goal"`
	Status       string `json:"status"`
	Priority     int    `json:"priority"`
	Revision     int64  `json:"revision"`
	SnoozedUntil int64  `json:"snoozed_until"`
	Seen         string `json:"seen_revision"`
	SourceState  string `json:"source_state"`
	Incarnation  string `json:"-"`
	Project      string `json:"-"`
	Owner        string `json:"-"`
}

type BriefingEvidence struct {
	Version          string `json:"version"`
	Kind             string `json:"kind"`
	Task             string `json:"task_id,omitempty"`
	Run              string `json:"run_id,omitempty"`
	Status           string `json:"status"`
	Verified         bool   `json:"verified"`
	ValidationFailed bool   `json:"validation_failed"`
	TrackingDegraded bool   `json:"tracking_degraded"`
	CancelRequested  bool   `json:"cancel_requested"`
	OccurredAt       string `json:"occurred_at"`
	PolledAt         string `json:"polled_at,omitempty"`
	CheckedAt        int64  `json:"checked_at"`
	Stale            bool   `json:"stale"`
	Busy             bool   `json:"busy"`
}
type BriefingItem struct {
	Topic            AttentionTopic   `json:"topic"`
	Evidence         BriefingEvidence `json:"evidence"`
	Changed          bool             `json:"has_changes"`
	Reason           string           `json:"reason"`
	FollowupQuestion string           `json:"followup_question"`
}
type PersonalBriefing struct {
	Version                string               `json:"version"`
	LocalDate              string               `json:"local_date"`
	Timezone               string               `json:"timezone"`
	CheckedAt              int64                `json:"checked_at"`
	Items                  []BriefingItem       `json:"items"`
	Total                  int                  `json:"total"`
	Unavailable            int                  `json:"unavailable"`
	Suggestions            []BriefingSuggestion `json:"suggestions"`
	SuggestionsUnavailable bool                 `json:"suggestions_unavailable"`
}

func (s *Store) initializeBriefing() error {
	_, err := s.DB.Exec(`CREATE TABLE IF NOT EXISTS deermate_attention_topics (
 id TEXT PRIMARY KEY,owner TEXT NOT NULL REFERENCES users(id),thread_id TEXT NOT NULL,incarnation TEXT NOT NULL,project_id TEXT NOT NULL DEFAULT '',
 title TEXT NOT NULL,goal TEXT NOT NULL DEFAULT '',status TEXT NOT NULL,priority INTEGER NOT NULL DEFAULT 1,revision INTEGER NOT NULL DEFAULT 1,
 snoozed_until INTEGER NOT NULL DEFAULT 0,seen_revision TEXT NOT NULL DEFAULT '',request_hash TEXT NOT NULL,created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS deermate_attention_owner ON deermate_attention_topics(owner,status,updated_at);
CREATE UNIQUE INDEX IF NOT EXISTS deermate_attention_thread ON deermate_attention_topics(owner,thread_id,incarnation) WHERE status!='removed';
CREATE TABLE IF NOT EXISTS deermate_briefing_snapshots (
 owner TEXT PRIMARY KEY REFERENCES users(id),version TEXT NOT NULL,local_date TEXT NOT NULL,payload TEXT NOT NULL,updated_at INTEGER NOT NULL);`)
	return err
}

const topicColumns = "id,owner,thread_id,incarnation,project_id,title,goal,status,priority,revision,snoozed_until,seen_revision"

func scanTopic(row scanner) (AttentionTopic, error) {
	var t AttentionTopic
	err := row.Scan(&t.ID, &t.Owner, &t.Thread, &t.Incarnation, &t.Project, &t.Title, &t.Goal, &t.Status, &t.Priority, &t.Revision, &t.SnoozedUntil, &t.Seen)
	if errors.Is(err, sql.ErrNoRows) {
		err = ErrNotFound
	}
	return t, err
}

type topicSource struct {
	Incarnation, Project, Title, Status string
	Archived                            bool
}

func ownedTopicSource(q memoryReader, owner, thread string) (topicSource, error) {
	var t topicSource
	var metadata string
	err := q.QueryRow(`SELECT coalesce(incarnation,''),coalesce(project_id,''),coalesce(display_name,''),coalesce(status,''),coalesce(metadata_json,'{}') FROM threads_meta WHERE thread_id=? AND user_id=?`, thread, owner).Scan(&t.Incarnation, &t.Project, &t.Title, &t.Status, &metadata)
	if errors.Is(err, sql.ErrNoRows) {
		return t, ErrNotFound
	}
	if err != nil {
		return t, err
	}
	var m map[string]any
	if json.Unmarshal([]byte(metadata), &m) != nil {
		return t, ErrConflict
	}
	if title, ok := m["title"].(string); ok && title != "" {
		t.Title = title
	}
	t.Archived, _ = m["deerflow_archived"].(bool)
	if t.Incarnation == "" {
		return t, ErrConflict
	}
	return t, nil
}
func maskTopic(q memoryReader, t AttentionTopic) AttentionTopic {
	t.SourceState = "available"
	if !topicAvailable(q, t) {
		t.SourceState = "unavailable"
		t.Thread = ""
		t.Title = ""
		t.Goal = ""
	}
	return t
}

func topicAvailable(q memoryReader, t AttentionTopic) bool {
	source, err := ownedTopicSource(q, t.Owner, t.Thread)
	return err == nil && source.Project == "" && !source.Archived && source.Incarnation == t.Incarnation && source.Project == t.Project
}

func (s *Store) Topics(owner string) ([]AttentionTopic, error) {
	rows, err := s.DB.Query("SELECT "+topicColumns+" FROM deermate_attention_topics WHERE owner=? AND status!='removed' ORDER BY priority DESC,updated_at DESC,id LIMIT 50", owner)
	if err != nil {
		return nil, err
	}
	out := []AttentionTopic{}
	for rows.Next() {
		t, e := scanTopic(rows)
		if e != nil {
			rows.Close()
			return nil, e
		}
		out = append(out, t)
	}
	err = rows.Err()
	rows.Close()
	if err != nil {
		return nil, err
	}
	for i := range out {
		out[i].SourceState = "available"
		if !topicAvailable(s.DB, out[i]) {
			out[i].SourceState = "unavailable"
			out[i].Title = ""
			out[i].Goal = ""
			out[i].Thread = ""
		}
	}
	return out, nil
}

func (s *Store) createTopic(ctx context.Context, owner, nonce, thread, title, goal string, priority int) (AttentionTopic, error) {
	var empty AttentionTopic
	if !resourceID.MatchString(nonce) || !resourceID.MatchString(thread) || len([]rune(title)) > 120 || len([]rune(goal)) > 500 || priority < 0 || priority > 2 {
		return empty, ErrCredentials
	}
	if (title != "" && !validMemoryText(title)) || (goal != "" && !validMemoryText(goal)) {
		return empty, ErrCredentials
	}
	id := "topic_" + digest(owner + "\x00" + nonce)[:32]
	fingerprint := digest(thread + "\x00" + title + "\x00" + goal + "\x00" + string(rune(priority+'0')))
	tx, err := s.DB.BeginTx(ctx, nil)
	if err != nil {
		return empty, err
	}
	defer tx.Rollback()
	var hash string
	err = tx.QueryRow("SELECT request_hash FROM deermate_attention_topics WHERE id=? AND owner=?", id, owner).Scan(&hash)
	if err == nil {
		if hash != fingerprint {
			return empty, ErrConflict
		}
		old, e := scanTopic(tx.QueryRow("SELECT "+topicColumns+" FROM deermate_attention_topics WHERE id=? AND owner=?", id, owner))
		return maskTopic(tx, old), e
	}
	if !errors.Is(err, sql.ErrNoRows) {
		return empty, err
	}
	source, err := ownedTopicSource(tx, owner, thread)
	if err != nil {
		return empty, err
	}
	if source.Archived || source.Project != "" {
		return empty, ErrConflict
	}
	previous, err := scanTopic(tx.QueryRow("SELECT "+topicColumns+" FROM deermate_attention_topics WHERE owner=? AND thread_id=? AND incarnation=? AND status!='removed'", owner, thread, source.Incarnation))
	if err == nil {
		return maskTopic(tx, previous), nil
	}
	if !errors.Is(err, ErrNotFound) {
		return empty, err
	}
	var total, active int
	if err = tx.QueryRow("SELECT count(*),coalesce(sum(CASE WHEN status='active' THEN 1 ELSE 0 END),0) FROM deermate_attention_topics WHERE owner=? AND status!='removed'", owner).Scan(&total, &active); err != nil {
		return empty, err
	}
	if total >= 50 || active >= 20 {
		return empty, ErrConflict
	}
	if title == "" {
		title = source.Title
	}
	if title == "" {
		title = "Untitled conversation"
	}
	t := AttentionTopic{ID: id, Owner: owner, Thread: thread, Incarnation: source.Incarnation, Project: source.Project, Title: title, Goal: goal, Status: "active", Priority: priority, Revision: 1, SourceState: "available"}
	evidence, err := topicEvidence(tx, t, time.Now())
	if err != nil {
		return empty, err
	}
	t.Seen = evidence.Version
	_, err = tx.Exec(`INSERT INTO deermate_attention_topics(id,owner,thread_id,incarnation,project_id,title,goal,status,priority,seen_revision,request_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)`, id, owner, thread, source.Incarnation, source.Project, title, goal, t.Status, priority, t.Seen, fingerprint, time.Now().Unix(), time.Now().Unix())
	if err != nil {
		return empty, err
	}
	t = maskTopic(tx, t)
	return t, tx.Commit()
}

func (s *Store) updateTopic(ctx context.Context, owner, id, action, title, goal string, priority int, expected int64, seen string) (AttentionTopic, error) {
	var empty AttentionTopic
	tx, err := s.DB.BeginTx(ctx, nil)
	if err != nil {
		return empty, err
	}
	defer tx.Rollback()
	t, err := scanTopic(tx.QueryRow("SELECT "+topicColumns+" FROM deermate_attention_topics WHERE owner=? AND id=?", owner, id))
	if err != nil {
		return empty, err
	}
	if t.Revision != expected || t.Status == "removed" {
		return empty, ErrConflict
	}
	switch action {
	case "pause":
		t.Status = "paused"
	case "complete":
		t.Status = "completed"
		if _, err = tx.Exec("INSERT INTO deermate_memory_stage_ends(owner,thread_id,observed_at) VALUES(?,?,?) ON CONFLICT(owner,thread_id) DO UPDATE SET observed_at=excluded.observed_at", owner, t.Thread, time.Now().Unix()); err != nil {
			return empty, err
		}
		if _, err = tx.Exec("UPDATE deermate_memory_operations SET status='invalidated',payload='' WHERE owner=? AND kind!='delete' AND status IN('pending','processing','uncertain') AND fact_id IN(SELECT id FROM deermate_memory_refs WHERE owner=? AND scope=?)", owner, owner, "topic:"+t.Thread); err != nil {
			return empty, err
		}
		if _, err = tx.Exec("UPDATE deermate_memory_refs SET status='interrupted' WHERE owner=? AND scope=? AND status IN('pending','updating')", owner, "topic:"+t.Thread); err != nil {
			return empty, err
		}
		if _, err = tx.Exec("UPDATE deermate_memory_jobs SET status='invalidated',result='' WHERE owner=? AND thread_id=? AND status NOT IN('completed','invalidated','failed')", owner, t.Thread); err != nil {
			return empty, err
		}
		if _, err = tx.Exec("UPDATE deermate_memory_refs SET expires_at=? WHERE owner=? AND scope=?", time.Now().Unix(), owner, "topic:"+t.Thread); err != nil {
			return empty, err
		}
	case "remove":
		t.Status = "removed"
		t.Title = ""
		t.Goal = ""
	case "resume":
		if !topicAvailable(tx, t) {
			return empty, ErrConflict
		}
		var count int
		if err = tx.QueryRow("SELECT count(*) FROM deermate_attention_topics WHERE owner=? AND status='active' AND id!=?", owner, id).Scan(&count); err != nil {
			return empty, err
		}
		if count >= 20 {
			return empty, ErrConflict
		}
		t.Status = "active"
		t.SnoozedUntil = 0
	case "snooze_today":
		p, e := readProfile(tx, owner)
		if e != nil {
			return empty, e
		}
		zone, e := time.LoadLocation(p.Timezone)
		if e != nil {
			return empty, e
		}
		now := time.Now().In(zone)
		t.SnoozedUntil = time.Date(now.Year(), now.Month(), now.Day()+1, 0, 0, 0, 0, zone).Unix()
	case "unsnooze":
		t.SnoozedUntil = 0
	case "seen":
		if !topicAvailable(tx, t) {
			return empty, ErrConflict
		}
		e, eErr := topicEvidence(tx, t, time.Now())
		if eErr != nil {
			return empty, eErr
		}
		if seen != e.Version {
			return empty, ErrConflict
		}
		t.Seen = e.Version
	case "edit":
		if !validMemoryText(title) || len([]rune(title)) > 120 || len([]rune(goal)) > 500 || priority < 0 || priority > 2 || (goal != "" && !validMemoryText(goal)) {
			return empty, ErrCredentials
		}
		t.Title = title
		t.Goal = goal
		t.Priority = priority
	default:
		return empty, ErrCredentials
	}
	t.Revision++
	_, err = tx.Exec(`UPDATE deermate_attention_topics SET title=?,goal=?,status=?,priority=?,revision=?,snoozed_until=?,seen_revision=?,updated_at=? WHERE owner=? AND id=?`, t.Title, t.Goal, t.Status, t.Priority, t.Revision, t.SnoozedUntil, t.Seen, time.Now().Unix(), owner, id)
	if err != nil {
		return empty, err
	}
	_, err = tx.Exec("DELETE FROM deermate_briefing_snapshots WHERE owner=?", owner)
	if err != nil {
		return empty, err
	}
	t = maskTopic(tx, t)
	return t, tx.Commit()
}

func topicEvidence(q memoryReader, t AttentionTopic, now time.Time) (BriefingEvidence, error) {
	e := BriefingEvidence{Kind: "conversation", Status: "no_tasks", CheckedAt: now.Unix()}
	var active int
	if err := q.QueryRow("SELECT count(*) FROM runs WHERE thread_id=? AND user_id=? AND status IN ('pending','running')", t.Thread, t.Owner).Scan(&active); err != nil {
		return e, err
	}
	e.Busy = active > 0
	var polled, pollError, cancel sql.NullString
	var verified, failed bool
	err := q.QueryRow(`SELECT id,status,updated_at,last_polled_at,last_poll_error,cancel_requested_at,
coalesce(json_extract(result,'$.validation_status')='passed' AND json_type(result,'$.validation.exit_code')='integer' AND json_extract(result,'$.validation.exit_code')=0,0),
coalesce(json_type(result,'$.validation.exit_code')='integer' AND json_extract(result,'$.validation.exit_code')!=0,0)
FROM mcp_tasks WHERE thread_id=? AND user_id=? AND coalesce(thread_incarnation,'')=? ORDER BY created_at DESC,id DESC LIMIT 1`, t.Thread, t.Owner, t.Incarnation).Scan(&e.Task, &e.Status, &e.OccurredAt, &polled, &pollError, &cancel, &verified, &failed)
	if err == nil {
		e.Kind = "task"
		e.Verified = verified && e.Status == "completed"
		e.ValidationFailed = failed
		e.PolledAt = polled.String
		e.TrackingDegraded = pollError.Valid && pollError.String != ""
		e.CancelRequested = cancel.Valid
		if e.Status == "working" || e.Status == "submitted" || e.Status == "input_required" {
			e.Busy = true
			e.Stale = e.TrackingDegraded || !polled.Valid || oldEvidenceTime(polled.String, now)
		}
	} else if errors.Is(err, sql.ErrNoRows) {
		err = q.QueryRow(`SELECT run_id,status,updated_at FROM runs WHERE thread_id=? AND user_id=? AND evidence_origin='interactive' AND origin_kind IS NULL ORDER BY created_at DESC,run_id DESC LIMIT 1`, t.Thread, t.Owner).Scan(&e.Run, &e.Status, &e.OccurredAt)
		if errors.Is(err, sql.ErrNoRows) {
			err = nil
			e.Status = "no_tasks"
		}
	}
	if err != nil {
		return e, err
	}
	data, _ := json.Marshal([]any{e.Kind, e.Task, e.Run, e.Status, e.Verified, e.TrackingDegraded, e.CancelRequested, e.Stale, e.ValidationFailed})
	e.Version = digest(string(data))
	return e, nil
}
func oldEvidenceTime(value string, now time.Time) bool {
	for _, layout := range []string{time.RFC3339Nano, "2006-01-02 15:04:05.999999999-07:00", "2006-01-02 15:04:05.999999999"} {
		if t, e := time.Parse(layout, value); e == nil {
			return now.Sub(t) > 5*time.Minute
		}
	}
	return true
}

func (s *Store) Briefing(owner string, now time.Time) (PersonalBriefing, error) {
	b := PersonalBriefing{CheckedAt: now.Unix(), Items: []BriefingItem{}}
	p, err := s.PersonalProfile(owner)
	if err != nil {
		return b, err
	}
	b.Timezone = p.Timezone
	zone, err := time.LoadLocation(p.Timezone)
	if err != nil {
		return b, err
	}
	b.LocalDate = now.In(zone).Format("2006-01-02")
	topics, err := s.Topics(owner)
	if err != nil {
		return b, err
	}
	eligible := []BriefingItem{}
	for _, t := range topics {
		if t.Status != "active" || t.SnoozedUntil > now.Unix() {
			continue
		}
		if t.SourceState != "available" {
			b.Unavailable++
			continue
		}
		e, err := topicEvidence(s.DB, t, now)
		if err != nil {
			return b, err
		}
		if !topicAvailable(s.DB, t) {
			b.Unavailable++
			continue
		}
		i := BriefingItem{Topic: t, Evidence: e, Changed: t.Seen != "" && t.Seen != e.Version, Reason: "explicit_follow", FollowupQuestion: followupQuestion}
		eligible = append(eligible, i)
	}
	sort.SliceStable(eligible, func(i, j int) bool {
		score := func(v BriefingItem) int {
			n := v.Topic.Priority
			if v.Evidence.Status == "failed" || v.Evidence.Status == "input_required" || v.Evidence.ValidationFailed {
				n += 20
			}
			if v.Changed {
				n += 10
			}
			return n
		}
		return score(eligible[i]) > score(eligible[j])
	})
	b.Total = len(eligible)
	if len(eligible) > 3 {
		eligible = eligible[:3]
	}
	b.Items = eligible
	fingerprint := []any{b.LocalDate, b.Timezone, p.PolicyRevision, p.DeletionRevision, b.Unavailable, b.Total}
	for _, i := range eligible {
		fingerprint = append(fingerprint, []any{i.Topic.ID, i.Topic.Revision, i.Evidence.Version, i.Changed, i.Evidence.Busy})
	}
	data, _ := json.Marshal(fingerprint)
	b.Version = digest(string(data))
	return b, nil
}

func (s *Server) briefingRoutes() {
	s.mux.HandleFunc("GET /api/me/attention-topics", s.protected(false, func(w http.ResponseWriter, r *http.Request) {
		if !personalAccess(w, r) {
			return
		}
		topics, err := s.Store.Topics(sessionOf(r).User.ID)
		if err != nil {
			storeError(w, err)
			return
		}
		respond(w, 200, map[string]any{"items": topics})
	}))
	s.mux.HandleFunc("POST /api/me/attention-topics", s.protected(false, func(w http.ResponseWriter, r *http.Request) {
		if !personalAccess(w, r) {
			return
		}
		var body struct {
			Operation string `json:"operation_id"`
			Thread    string `json:"thread_id"`
			Title     string `json:"title"`
			Goal      string `json:"goal"`
			Priority  int    `json:"priority"`
		}
		if !decode(w, r, &body) {
			return
		}
		topic, err := s.Store.createTopic(r.Context(), sessionOf(r).User.ID, body.Operation, body.Thread, strings.TrimSpace(body.Title), strings.TrimSpace(body.Goal), body.Priority)
		if err != nil {
			memoryError(w, err)
			return
		}
		respond(w, 200, topic)
	}))
	s.mux.HandleFunc("PATCH /api/me/attention-topics/{id}", s.protected(false, func(w http.ResponseWriter, r *http.Request) {
		if !personalAccess(w, r) {
			return
		}
		var body struct {
			Action   string `json:"action"`
			Title    string `json:"title"`
			Goal     string `json:"goal"`
			Priority int    `json:"priority"`
			Expected int64  `json:"expected_revision"`
			Seen     string `json:"evidence_revision"`
		}
		if !decode(w, r, &body) {
			return
		}
		topic, err := s.Store.updateTopic(r.Context(), sessionOf(r).User.ID, r.PathValue("id"), body.Action, strings.TrimSpace(body.Title), strings.TrimSpace(body.Goal), body.Priority, body.Expected, body.Seen)
		if err != nil {
			memoryError(w, err)
			return
		}
		respond(w, 200, topic)
	}))
	get := s.protected(false, func(w http.ResponseWriter, r *http.Request) {
		if !personalAccess(w, r) {
			return
		}
		b, err := s.Store.Briefing(sessionOf(r).User.ID, time.Now())
		if err != nil {
			fail(w, 503, "briefing_unavailable", "Current evidence is unavailable; no task was started")
			return
		}
		b.Suggestions, b.SuggestionsUnavailable = s.briefingSuggestions(r)
		extra, _ := json.Marshal([]any{b.Version, b.Suggestions, b.SuggestionsUnavailable})
		b.Version = digest(string(extra))
		if r.Method == "POST" {
			payload, _ := json.Marshal(b)
			_, err = s.Store.DB.Exec(`INSERT INTO deermate_briefing_snapshots VALUES(?,?,?,?,?) ON CONFLICT(owner) DO UPDATE SET version=excluded.version,local_date=excluded.local_date,payload=excluded.payload,updated_at=excluded.updated_at WHERE version!=excluded.version`, sessionOf(r).User.ID, b.Version, b.LocalDate, string(payload), b.CheckedAt)
			if err != nil {
				storeError(w, err)
				return
			}
		}
		respond(w, 200, b)
	})
	s.mux.HandleFunc("GET /api/me/briefing", get)
	s.mux.HandleFunc("POST /api/me/briefing/refresh", get)
}
