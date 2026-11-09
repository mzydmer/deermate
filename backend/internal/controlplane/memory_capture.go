package controlplane

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/json"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// Only an authenticated interactive submission can mint this context value.
// The runtime's durable owner/origin/message is verified again at admission.
type memoryCaptureKey struct{}
type memoryCapture struct {
	Owner, Thread, Run, Message, Hash, Incarnation string
	Content, Category                              string
	Policy, Deleted, Observed, Invalidated         int64
	Candidates                                     []memoryCandidate
	Job                                            string
	Historical                                     bool
}

type captureMessage struct {
	ID         string                     `json:"id"`
	Type       string                     `json:"type"`
	Role       string                     `json:"role"`
	Content    json.RawMessage            `json:"content"`
	Additional map[string]json.RawMessage `json:"additional_kwargs"`
}

func captureText(input json.RawMessage) (string, string, bool) {
	var body struct {
		Messages []captureMessage `json:"messages"`
	}
	if json.Unmarshal(input, &body) != nil || len(body.Messages) != 1 {
		return "", "", false
	}
	m := body.Messages[0]
	if !resourceID.MatchString(m.ID) || (m.Type != "human" && m.Role != "user") || (m.Type != "" && m.Type != "human") || (m.Role != "" && m.Role != "user") || len(m.Additional) != 0 {
		return "", "", false
	}
	var text string
	if json.Unmarshal(m.Content, &text) != nil {
		var blocks []struct {
			Type string `json:"type"`
			Text string `json:"text"`
		}
		if json.Unmarshal(m.Content, &blocks) != nil || len(blocks) != 1 || blocks[0].Type != "text" {
			return "", "", false
		}
		text = blocks[0].Text
	}
	return m.ID, text, len(text) <= 4000
}

func explicitMemory(text string) (string, string, bool) {
	text = strings.TrimSpace(text)
	if strings.ContainsAny(text, "\r\n`<>\"“”？?") {
		return "", "", false
	}
	lower := strings.ToLower(text)
	prefix := ""
	for _, p := range []string{"请记住：", "请记住:", "记住：", "记住:", "remember:", "remember that "} {
		if strings.HasPrefix(lower, p) {
			prefix = p
			break
		}
	}
	if prefix == "" {
		return "", "", false
	}
	body := strings.TrimSpace(text[len(prefix):])
	lower = strings.ToLower(body)
	if !validMemoryText(body) {
		return "", "", false
	}
	for _, blocked := range []string{"项目", "仓库", "改成", "改为", "不再", "忘记", "名字", "姓名", "时区", "project", "repository", "workspace", "instead", "forget", "my name", "timezone", "叫我", "称呼", "call me", "不要保存", "不要记", "别记", "do not save", "do not remember", "don't save"} {
		if strings.Contains(lower, blocked) {
			return "", "", false
		}
	}
	groups := []struct {
		category string
		prefixes []string
	}{
		{"preference", []string{"我偏好", "我喜欢", "我习惯", "我的回复偏好", "以后回答", "以后回复", "回答时", "回复时", "i prefer ", "i like ", "my preference is ", "please answer ", "always answer "}},
		{"goal", []string{"我的长期目标是", "my long-term goal is "}},
		{"context", []string{"我正在学习", "i am learning "}},
	}
	for _, g := range groups {
		for _, p := range g.prefixes {
			if strings.HasPrefix(lower, p) && len([]rune(body)) > len([]rune(p))+1 {
				return body, g.category, true
			}
		}
	}
	return "", "", false
}

type joinedBody struct {
	io.Reader
	io.Closer
}

func peekBody(body io.ReadCloser, maximum int64) ([]byte, io.ReadCloser, bool) {
	data, err := io.ReadAll(io.LimitReader(body, maximum+1))
	return data, joinedBody{io.MultiReader(bytes.NewReader(data), body), body}, err == nil && int64(len(data)) <= maximum
}

func (s *Server) prepareMemoryCapture(r *http.Request) *http.Request {
	if r.Method != "POST" || r.Body == nil {
		return r
	}
	parts := strings.Split(strings.Trim(r.URL.Path, "/"), "/")
	if (len(parts) != 4 && len(parts) != 5) || parts[0] != "api" || parts[1] != "threads" || parts[3] != "runs" || !resourceID.MatchString(parts[2]) || (len(parts) == 5 && parts[4] != "stream") {
		return r
	}
	p, err := s.Store.PersonalProfile(sessionOf(r).User.ID)
	if err != nil || !p.AutoCaptureEnabled || !captureAllowed(s.Store.DB, p.Owner, parts[2]) {
		return r
	}
	data, restored, ok := peekBody(r.Body, 64<<10)
	r.Body = restored
	if !ok {
		return r
	}
	var body struct {
		Input        json.RawMessage            `json:"input"`
		Command      json.RawMessage            `json:"command"`
		Metadata     map[string]json.RawMessage `json:"metadata"`
		Checkpoint   json.RawMessage            `json:"checkpoint"`
		CheckpointID json.RawMessage            `json:"checkpoint_id"`
		Config       map[string]json.RawMessage `json:"config"`
	}
	if json.Unmarshal(data, &body) != nil || (len(body.Command) > 0 && string(body.Command) != "null") || (len(body.Checkpoint) > 0 && string(body.Checkpoint) != "null") {
		return r
	}
	if len(body.CheckpointID) > 0 && string(body.CheckpointID) != "null" {
		return r
	}
	for key := range body.Config {
		if key != "recursion_limit" {
			return r
		}
	}
	// Replay/suggestion and non-interactive sources are never promoted by labels.
	if len(body.Metadata) != 0 {
		return r
	}
	id, text, ok := captureText(body.Input)
	if !ok {
		return r
	}
	candidates := naturalMemories(text)
	if len(candidates) == 0 && !memoryMayExtract(text) {
		return r
	}
	capture := memoryCapture{Owner: p.Owner, Thread: parts[2], Message: id, Hash: digest(text), Candidates: candidates, Policy: p.PolicyRevision, Deleted: p.DeletionRevision, Observed: time.Now().Unix()}
	if len(candidates) > 0 {
		capture.Content, capture.Category = candidates[0].Content, candidates[0].Category
	}
	return r.WithContext(context.WithValue(r.Context(), memoryCaptureKey{}, capture))
}

func (s *Server) captureMemoryResponse(response *http.Response) {
	capture, ok := response.Request.Context().Value(memoryCaptureKey{}).(memoryCapture)
	if !ok || response.StatusCode < 200 || response.StatusCode >= 300 {
		return
	}
	if location := response.Header.Get("Content-Location"); location != "" {
		u, err := url.Parse(location)
		if err != nil {
			return
		}
		parts := strings.Split(strings.Trim(u.Path, "/"), "/")
		if len(parts) != 5 || parts[0] != "api" || parts[1] != "threads" || parts[2] != capture.Thread || parts[3] != "runs" || !resourceID.MatchString(parts[4]) {
			return
		}
		capture.Run = parts[4]
	} else if strings.HasSuffix(response.Request.URL.Path, "/runs") {
		data, restored, valid := peekBody(response.Body, 32<<10)
		response.Body = restored
		if !valid {
			return
		}
		var record struct {
			Run    string `json:"run_id"`
			Thread string `json:"thread_id"`
		}
		if json.Unmarshal(data, &record) != nil || record.Thread != capture.Thread || !resourceID.MatchString(record.Run) {
			return
		}
		capture.Run = record.Run
	} else {
		return
	}
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	for i, candidate := range capture.Candidates {
		operation, err := s.Store.admitNaturalMemory(ctx, capture, candidate, i)
		if err != nil {
			continue
		}
		capture.Deleted = max(capture.Deleted, operation.DeletionRevision)
		state := "queued"
		if operation.Status == "completed" {
			state = "completed"
		} else if operation.Status == "invalidated" {
			state = "ignored"
		}
		response.Header.Set("X-Deermate-Memory-Status", state)
		response.Header.Set("X-Deermate-Memory-Operation", operation.ID)
	}
	if _, err := s.Store.enqueueMemoryExtraction(ctx, capture); err == nil {
		if response.Header.Get("X-Deermate-Memory-Status") == "" {
			response.Header.Set("X-Deermate-Memory-Status", "queued")
		}
	}
}

// This is a pinned read-only contract over the same SQLite database. A missing
// or changed runtime schema fails closed and does not break the chat response.
func verifyCapture(q memoryReader, capture *memoryCapture) bool {
	if capture.Invalidated != 0 {
		return false
	}
	if strings.HasPrefix(capture.Run, "inbox:") {
		_, ok := inboxMemoryInput(q, capture)
		return ok
	}
	var kwargs string
	var incarnation sql.NullString
	err := q.QueryRow(`SELECT r.kwargs_json,t.incarnation FROM runs r JOIN threads_meta t ON t.thread_id=r.thread_id
WHERE r.run_id=? AND r.thread_id=? AND r.user_id=? AND t.user_id=?
AND CAST(strftime('%s',r.created_at) AS INTEGER)>=? AND r.evidence_origin='interactive' AND r.origin_kind IS NULL AND r.operation_kind='run' AND t.project_id IS NULL
AND coalesce(json_extract(t.metadata_json,'$.deerflow_archived'),0)=0
AND NOT EXISTS (SELECT 1 FROM runs e WHERE e.thread_id=r.thread_id AND e.user_id=r.user_id
AND json_extract(e.metadata_json,'$.replay_kind')='edit' AND json_extract(e.metadata_json,'$.regenerate_from_run_id')=r.run_id)`, capture.Run, capture.Thread, capture.Owner, capture.Owner, capture.Observed-1).Scan(&kwargs, &incarnation)
	if err != nil || !incarnation.Valid || incarnation.String == "" {
		return false
	}
	var body struct {
		Input json.RawMessage `json:"input"`
	}
	if json.Unmarshal([]byte(kwargs), &body) != nil {
		return false
	}
	id, text, ok := captureText(body.Input)
	if !ok || id != capture.Message || digest(text) != capture.Hash {
		return false
	}
	if capture.Incarnation != "" && capture.Incarnation != incarnation.String {
		return false
	}
	capture.Incarnation = incarnation.String
	return true
}

// Inbox sources are Go-owned user submissions, not Gateway runs or event text.
// The complete, untruncated input must have passed admission at submission time.
func inboxMemoryInput(q memoryReader, source *memoryCapture) (string, bool) {
	id := strings.TrimPrefix(source.Run, "inbox:")
	v, err := workGet(q, source.Owner, "inbox", id)
	if err != nil || !workBool(v, "_memory_eligible") || workString(v, "origin") != "user" || id != source.Message {
		return "", false
	}
	router, err := workGet(q, source.Owner, "router", "router")
	thread := workString(router, "thread_id")
	text := workString(v, "text")
	if err != nil || thread == "" || thread != source.Thread || workString(v, "_memory_thread") != thread || (source.Incarnation != "" && source.Incarnation != thread) || digest(text) != source.Hash || !automaticMemorySafe(text) || len(text) > 4000 {
		return "", false
	}
	source.Incarnation = thread
	return text, true
}

func (s *Server) captureRouterMemory(ctx context.Context, owner string, v workRecord) {
	if !workBool(v, "_memory_eligible") {
		return
	}
	c := memoryCapture{Owner: owner, Thread: workString(v, "_memory_thread"), Run: "inbox:" + v.ID, Message: v.ID, Hash: digest(workString(v, "text")), Incarnation: workString(v, "_memory_thread"), Policy: workInt(v, "_memory_policy"), Deleted: workInt(v, "_memory_deleted"), Observed: v.Created / 1000}
	_, _ = s.Store.enqueueMemoryExtraction(ctx, c)
}

func captureSource(q memoryReader, operation string) (*memoryCapture, error) {
	var c memoryCapture
	err := q.QueryRow(`SELECT owner,thread_id,run_id,message_id,message_hash,incarnation,policy_revision,deletion_revision,observed_at,invalidated_at
FROM deermate_memory_sources WHERE operation_id=?`, operation).Scan(&c.Owner, &c.Thread, &c.Run, &c.Message, &c.Hash, &c.Incarnation, &c.Policy, &c.Deleted, &c.Observed, &c.Invalidated)
	return &c, err
}
