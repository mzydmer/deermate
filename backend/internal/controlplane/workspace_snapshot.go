package controlplane

import (
	"encoding/json"
	"net/http"
	"sort"
	"time"
)

type workspaceFocus struct {
	ID       string           `json:"id"`
	Kind     string           `json:"kind"`
	Title    string           `json:"title"`
	Thread   string           `json:"thread_id,omitempty"`
	Work     string           `json:"work_id,omitempty"`
	Reason   string           `json:"reason"`
	Evidence BriefingEvidence `json:"evidence"`
	Updated  int64            `json:"updated_at"`
	Seen     bool             `json:"seen"`
}

func (s *Store) initializeWorkspaceSnapshot() error {
	_, err := s.DB.Exec(`CREATE TABLE IF NOT EXISTS deermate_workspace_feedback (
 owner TEXT NOT NULL REFERENCES users(id),id TEXT NOT NULL,seen_version TEXT NOT NULL DEFAULT '',
 snoozed_until INTEGER NOT NULL DEFAULT 0,dismissed INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(owner,id));`)
	return err
}

func (s *Server) workspaceFocusItems(owner string, now time.Time) ([]workspaceFocus, error) {
	items := []workspaceFocus{}
	used := map[string]bool{}
	briefing, err := s.Store.Briefing(owner, now)
	if err != nil {
		return nil, err
	}
	for _, v := range briefing.Items {
		items = append(items, workspaceFocus{ID: v.Topic.ID, Kind: "topic", Title: v.Topic.Title, Thread: v.Topic.Thread, Reason: "followed", Evidence: v.Evidence})
		used[v.Topic.Thread] = true
	}
	// Recent conversations require no manually maintained follow list. Read-only
	// local evidence is enough; opening the home never asks an agent for a report.
	rows, err := s.Store.DB.Query(`SELECT t.thread_id FROM threads_meta t JOIN runs r ON r.thread_id=t.thread_id AND r.user_id=t.user_id
 WHERE t.user_id=? AND t.project_id IS NULL AND coalesce(t.incarnation,'')!=''
 AND coalesce(json_extract(t.metadata_json,'$.deerflow_archived'),0)=0
 AND r.evidence_origin='interactive' AND r.origin_kind IS NULL AND CAST(strftime('%s',r.updated_at) AS INTEGER)>=?
 GROUP BY t.thread_id ORDER BY max(r.updated_at) DESC,t.thread_id LIMIT 10`, owner, now.Add(-7*24*time.Hour).Unix())
	if err != nil {
		return nil, err
	}
	threads := []string{}
	for rows.Next() {
		var id string
		if rows.Scan(&id) == nil {
			threads = append(threads, id)
		}
	}
	err = rows.Err()
	rows.Close()
	if err != nil {
		return nil, err
	}
	for _, id := range threads {
		if !captureAllowed(s.Store.DB, owner, id) {
			continue
		}
		if used[id] {
			continue
		}
		source, e := ownedTopicSource(s.Store.DB, owner, id)
		if e != nil || source.Project != "" || source.Archived {
			continue
		}
		// A paused/completed/removed explicitly followed topic stays out of home.
		var suppressed int
		_ = s.Store.DB.QueryRow("SELECT count(*) FROM deermate_attention_topics WHERE owner=? AND thread_id=? AND (status!='active' OR snoozed_until>?)", owner, id, now.Unix()).Scan(&suppressed)
		if suppressed > 0 {
			continue
		}
		topic := AttentionTopic{Owner: owner, Thread: id, Incarnation: source.Incarnation}
		evidence, e := topicEvidence(s.Store.DB, topic, now)
		if e != nil {
			return nil, e
		}
		if !topicAvailable(s.Store.DB, topic) {
			continue
		}
		title := source.Title
		if title == "" {
			title = "未命名对话"
		}
		items = append(items, workspaceFocus{ID: "recent-" + digest(owner + "\x00" + id + "\x00" + source.Incarnation)[:32], Kind: "topic", Title: title, Thread: id, Reason: "recent_conversation", Evidence: evidence})
	}
	works, err := s.Store.workList(owner, "work", "", 0, 20)
	if err != nil {
		return nil, err
	}
	for _, raw := range works {
		v := s.workView(raw)
		if workString(v, "source_state") == "unavailable" || v.State == "closed" {
			continue
		}
		status := workString(v, "stage")
		if status == "" {
			status = v.State
		}
		evidence := BriefingEvidence{Kind: "work", Status: status, Verified: workBool(v, "verified"), CheckedAt: now.Unix(), OccurredAt: time.UnixMilli(v.Updated).UTC().Format(time.RFC3339), TrackingDegraded: workString(v, "execution_reason") != ""}
		fingerprint, _ := json.Marshal([]any{v.ID, v.Revision, v.State, status, evidence.Verified})
		evidence.Version = digest(string(fingerprint))
		items = append(items, workspaceFocus{ID: "work-" + v.ID, Kind: "work", Title: workString(v, "title"), Work: v.ID, Reason: "active_work", Evidence: evidence, Updated: v.Updated})
	}
	visible := []workspaceFocus{}
	for _, v := range items {
		var seen string
		var until int64
		var dismissed bool
		_ = s.Store.DB.QueryRow("SELECT seen_version,snoozed_until,dismissed FROM deermate_workspace_feedback WHERE owner=? AND id=?", owner, v.ID).Scan(&seen, &until, &dismissed)
		if dismissed || until > now.Unix() {
			continue
		}
		v.Seen = seen == v.Evidence.Version
		if v.Updated == 0 {
			for _, layout := range []string{time.RFC3339Nano, "2006-01-02 15:04:05.999999"} {
				if t, e := time.Parse(layout, v.Evidence.OccurredAt); e == nil {
					v.Updated = t.UnixMilli()
					break
				}
			}
		}
		visible = append(visible, v)
	}
	score := func(v workspaceFocus) int {
		if v.Evidence.Status == "input_required" || v.Evidence.Status == "failed" || v.Evidence.ValidationFailed {
			return 3
		}
		if !v.Seen && (v.Evidence.Verified || v.Evidence.Status == "completed" || v.Evidence.Status == "succeeded") {
			return 2
		}
		return 1
	}
	sort.SliceStable(visible, func(i, j int) bool {
		a, b := score(visible[i]), score(visible[j])
		if a != b {
			return a > b
		}
		return visible[i].Updated > visible[j].Updated
	})
	if len(visible) > 3 {
		visible = visible[:3]
	}
	return visible, nil
}

func (s *Server) workspaceSnapshot(w http.ResponseWriter, r *http.Request) {
	if !personalAccess(w, r) {
		return
	}
	owner := sessionOf(r).User.ID
	now := time.Now()
	profile, err := s.Store.PersonalProfile(owner)
	if err != nil {
		storeError(w, err)
		return
	}
	items, err := s.workspaceFocusItems(owner, now)
	if err != nil {
		fail(w, 503, "workspace_unavailable", "Workspace evidence is temporarily unavailable")
		return
	}
	respond(w, 200, map[string]any{"profile": profile, "items": items, "checked_at": now.Unix(), "timezone": profile.Timezone})
}

func (s *Server) workspaceFeedback(w http.ResponseWriter, r *http.Request) {
	if !personalAccess(w, r) {
		return
	}
	var b struct {
		ID      string `json:"id"`
		Version string `json:"version"`
		Action  string `json:"action"`
	}
	if !decode(w, r, &b) {
		return
	}
	if !resourceID.MatchString(b.ID) || !resourceID.MatchString(b.Version) {
		memoryError(w, ErrCredentials)
		return
	}
	owner := sessionOf(r).User.ID
	now := time.Now()
	var query string
	var args []any
	switch b.Action {
	case "seen":
		query = "INSERT INTO deermate_workspace_feedback(owner,id,seen_version) VALUES(?,?,?) ON CONFLICT(owner,id) DO UPDATE SET seen_version=excluded.seen_version"
		args = []any{owner, b.ID, b.Version}
	case "snooze_today":
		p, err := s.Store.PersonalProfile(owner)
		if err != nil {
			storeError(w, err)
			return
		}
		zone, err := time.LoadLocation(p.Timezone)
		if err != nil {
			memoryError(w, err)
			return
		}
		local := now.In(zone)
		until := time.Date(local.Year(), local.Month(), local.Day()+1, 0, 0, 0, 0, zone).Unix()
		query = "INSERT INTO deermate_workspace_feedback(owner,id,snoozed_until) VALUES(?,?,?) ON CONFLICT(owner,id) DO UPDATE SET snoozed_until=excluded.snoozed_until"
		args = []any{owner, b.ID, until}
	case "dismiss":
		query = "INSERT INTO deermate_workspace_feedback(owner,id,dismissed) VALUES(?,?,1) ON CONFLICT(owner,id) DO UPDATE SET dismissed=1"
		args = []any{owner, b.ID}
	default:
		memoryError(w, ErrCredentials)
		return
	}
	if _, err := s.Store.DB.ExecContext(r.Context(), query, args...); err != nil {
		storeError(w, err)
		return
	}
	respond(w, 200, map[string]bool{"saved": true})
}
