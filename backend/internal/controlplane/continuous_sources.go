package controlplane

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"slices"
	"strconv"
	"strings"
	"time"
)

func (s *Server) workSources(w http.ResponseWriter, r *http.Request) {
	if !s.workAccess(w, r) {
		return
	}
	owner := sessionOf(r).User.ID
	src, e := workGet(s.Store.DB, owner, "source", "github")
	if errors.Is(e, ErrNotFound) {
		src = workRecord{ID: "github", Kind: "source", Owner: owner, State: "disabled", Data: map[string]any{"repository": s.cfg.GitHubRepository, "generation": 1, "baseline": false}}
		e = nil
	}
	if e != nil {
		workError(w, e)
		return
	}
	if id := r.PathValue("id"); id != "" && id != "github" {
		workError(w, ErrNotFound)
		return
	}
	if r.Method == "PATCH" {
		var b workBody
		if !decode(w, r, &b) {
			return
		}
		if b.Enabled == nil || !workRepository.MatchString(s.cfg.GitHubRepository) {
			workError(w, ErrCredentials)
			return
		}
		if *b.Enabled {
			if _, err := s.githubToken(); err != nil {
				fail(w, 422, "github_secret_required", "Configure the deployment's read-only GitHub secret reference before enabling this source")
				return
			}
		}
		e = s.Store.workTransaction(r.Context(), func(tx *sql.Tx) error {
			if !s.cfg.ContinuousEnabled || !workEnabled(tx, owner) {
				return ErrDisabled
			}
			current, err := workGet(tx, owner, "source", "github")
			if err == nil {
				src = current
			} else if !errors.Is(err, ErrNotFound) {
				return err
			}
			if src.Revision != b.Expected {
				return ErrConflict
			}
			enabled := src.State == "enabled"
			src.State = "disabled"
			if *b.Enabled {
				src.State = "enabled"
			}
			if enabled != *b.Enabled {
				src.Data["generation"] = workInt(src, "generation") + 1
				src.Data["baseline"] = false
				delete(src.Data, "etag")
				delete(src.Data, "cursor")
			}
			src.Data["repository"] = s.cfg.GitHubRepository
			return workPut(tx, &src)
		})
		if e != nil {
			workError(w, e)
			return
		}
	}
	view := workPublic(src)
	view.Data["configured_repository"] = s.cfg.GitHubRepository
	if r.PathValue("id") == "" {
		respond(w, 200, map[string]any{"items": []workRecord{view}})
	} else {
		respond(w, 200, view)
	}
}
func (s *Server) workRules(w http.ResponseWriter, r *http.Request) {
	if !s.workAccess(w, r) {
		return
	}
	owner := sessionOf(r).User.ID
	if r.Method == "GET" {
		items, e := s.Store.workList(owner, "rule", "", 0, 50)
		if e != nil {
			workError(w, e)
			return
		}
		respond(w, 200, map[string]any{"items": items})
		return
	}
	var b workBody
	if !decode(w, r, &b) {
		return
	}
	if b.Mode == "" {
		b.Mode = "observe"
	}
	if !slices.Contains([]string{"off", "observe", "auto"}, b.Mode) || b.Source != "github" || strings.TrimSpace(b.Instruction) == "" || len(b.Instruction) > 4000 || b.NativeBudget < 0 || b.NativeBudget > 2 || len(b.EventKinds) > 3 {
		workError(w, ErrCredentials)
		return
	}
	for _, k := range b.EventKinds {
		if !slices.Contains([]string{"issue", "comment", "ci"}, k) {
			workError(w, ErrCredentials)
			return
		}
	}
	if b.Mode == "auto" && (b.NativeBudget == 0 || b.Project == "" || b.Grant == "") {
		workError(w, ErrCredentials)
		return
	}
	if b.Mode == "auto" {
		settings, err := workGet(s.Store.DB, owner, "settings", "settings")
		if err != nil || workInt(settings, "native_budget") == 0 || !s.boundedWorkModel(r, workString(settings, "model")) {
			fail(w, 422, "bounded_model_required", "Automatic mode requires a currently supported bounded model")
			return
		}
	}
	var out workRecord
	e := s.Store.workTransaction(r.Context(), func(tx *sql.Tx) error {
		if !s.cfg.ContinuousEnabled || !workEnabled(tx, owner) {
			return ErrDisabled
		}
		if r.Method == "POST" {
			if !workOperationID.MatchString(b.Operation) {
				return ErrCredentials
			}
			if id, e := workExisting(tx, owner, "rule", b.Operation); e == nil {
				var err error
				out, err = workGet(tx, owner, "rule", id)
				if err == nil && workString(out, "_request_hash") != workHash(b) {
					return ErrConflict
				}
				return err
			}
			var n int
			if tx.QueryRow("SELECT count(*) FROM deermate_work_records WHERE owner=? AND kind='rule'", owner).Scan(&n) != nil || n >= 20 {
				return ErrConflict
			}
			out = newWork(owner, "rule", b.Mode, "", map[string]any{})
		} else {
			var err error
			out, err = workGet(tx, owner, "rule", r.PathValue("id"))
			if err != nil {
				return err
			}
			if out.Revision != b.Expected {
				return ErrConflict
			}
		}
		out.State = b.Mode
		out.Data = map[string]any{"source_id": b.Source, "instruction": b.Instruction, "event_kinds": b.EventKinds, "project": b.Project, "grant_id": b.Grant, "native_budget": b.NativeBudget, "_request_hash": workHash(b)}
		if err := workPut(tx, &out); err != nil {
			return err
		}
		if r.Method == "POST" {
			return workUnique(tx, owner, "rule", b.Operation, out.ID)
		}
		return nil
	})
	if e != nil {
		workError(w, e)
		return
	}
	respond(w, 200, workPublic(out))
}

var githubSHA = regexp.MustCompile(`^[a-fA-F0-9]{40,64}$`)

type githubObject struct {
	State   string          `json:"state"`
	Labels  json.RawMessage `json:"labels"`
	SHA     string          `json:"head_sha"`
	ID      int64           `json:"id"`
	Number  int             `json:"number"`
	Title   string          `json:"title"`
	Body    string          `json:"body"`
	Updated string          `json:"updated_at"`
	URL     string          `json:"issue_url"`
	Pull    json.RawMessage `json:"pull_request"`
}
type githubPoll struct {
	objects     []githubObject
	etag        string
	notModified bool
}

func (s *Server) githubRead(ctx context.Context, path, etag string) ([]byte, string, int, error) {
	if !workRepository.MatchString(s.cfg.GitHubRepository) {
		return nil, "", 0, ErrCredentials
	}
	// Paths are constructed exclusively below; no browser/model-supplied URL.
	req, e := http.NewRequestWithContext(ctx, "GET", "https://api.github.com/repos/"+s.cfg.GitHubRepository+path, nil)
	if e != nil {
		return nil, "", 0, e
	}
	req.Header.Set("Accept", "application/vnd.github+json")
	req.Header.Set("X-GitHub-Api-Version", "2022-11-28")
	req.Header.Set("User-Agent", "DeerMate/continuous-v1")
	if etag != "" {
		req.Header.Set("If-None-Match", etag)
	}
	token, err := s.githubToken()
	if err != nil {
		return nil, "", 0, err
	}
	req.Header.Set("Authorization", "Bearer "+token)
	transport := s.githubTransport
	if transport == nil {
		transport = &http.Transport{Proxy: nil, DisableKeepAlives: true}
	}
	client := &http.Client{Timeout: 15 * time.Second, Transport: transport, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
	resp, e := client.Do(req)
	if e != nil {
		return nil, "", 0, fmt.Errorf("github_unavailable")
	}
	defer resp.Body.Close()
	if resp.StatusCode == 304 {
		return nil, etag, 304, nil
	}
	if resp.StatusCode != 200 {
		return nil, "", resp.StatusCode, fmt.Errorf("github_status_%d", resp.StatusCode)
	}
	raw, e := io.ReadAll(io.LimitReader(resp.Body, (1<<20)+1))
	if e != nil || len(raw) > 1<<20 {
		return nil, "", 0, fmt.Errorf("github_response_limit")
	}
	return raw, resp.Header.Get("ETag"), 200, nil
}
func (s *Server) pollGitHub(ctx context.Context, src workRecord) error {
	if workString(src, "repository") != s.cfg.GitHubRepository {
		return fmt.Errorf("repository_configuration_changed")
	}
	cursor := workString(src, "cursor")
	if cursor == "" {
		cursor = time.Now().UTC().Add(-time.Minute).Format(time.RFC3339)
	}
	since := ""
	if cursor != "" {
		t, e := time.Parse(time.RFC3339, cursor)
		if e != nil {
			return e
		}
		since = "&since=" + url.QueryEscape(t.Add(-time.Minute).Format(time.RFC3339))
	}
	objects := []struct {
		obj  githubObject
		kind string
	}{}
	etag := ""
	now := time.Now().UTC().Format(time.RFC3339)
	for _, kind := range []string{"issue", "comment"} {
		endpoint := "/issues?state=all&sort=updated&direction=asc&per_page=50"
		if kind == "comment" {
			endpoint = "/issues/comments?sort=updated&direction=asc&per_page=50"
		}
		for page := 1; page <= 5; page++ {
			conditional := ""
			if kind == "issue" && page == 1 {
				conditional = workString(src, "etag")
			}
			raw, tag, status, e := s.githubRead(ctx, endpoint+since+"&page="+strconv.Itoa(page), conditional)
			if e != nil {
				return e
			}
			if status == 304 {
				break
			}
			if kind == "issue" && page == 1 {
				etag = tag
			}
			var batch []githubObject
			if json.Unmarshal(raw, &batch) != nil {
				return fmt.Errorf("github_contract")
			}
			for _, obj := range batch {
				objects = append(objects, struct {
					obj  githubObject
					kind string
				}{obj, kind})
			}
			if len(batch) < 50 {
				break
			}
			if page == 5 {
				return fmt.Errorf("github_page_backpressure")
			}
		}
	}
	ci, checked, err := s.githubBoundCI(ctx, src)
	if err != nil {
		return err
	}
	objects = append(objects, ci...)
	if err = s.ingestGitHub(ctx, src, objects, etag, now); err != nil {
		return err
	}
	for _, work := range checked {
		_ = s.Store.workTransaction(ctx, func(tx *sql.Tx) error {
			current, e := workGet(tx, src.Owner, "work", work.ID)
			if e != nil {
				return e
			}
			current.Data["ci_checked_at"] = time.Now().Unix()
			return workPut(tx, &current)
		})
	}
	return nil
}
func (s *Server) ingestGitHub(ctx context.Context, snapshot workRecord, objects []struct {
	obj  githubObject
	kind string
}, etag, cursor string) error {
	return s.Store.workTransaction(ctx, func(tx *sql.Tx) error {
		src, e := workGet(tx, snapshot.Owner, "source", snapshot.ID)
		if e != nil {
			return e
		}
		if src.Revision != snapshot.Revision || src.State != "enabled" || !workEnabled(tx, src.Owner) {
			return ErrConflict
		}
		u, e := scanUser(tx.QueryRow("SELECT "+userColumns+" FROM users WHERE id=?", src.Owner))
		if e != nil || u.Disabled || u.Role != "admin" || u.NeedsSetup {
			return ErrConflict
		}
		var count int
		if e = tx.QueryRow("SELECT count(*) FROM deermate_work_records WHERE owner=? AND kind='event'", src.Owner).Scan(&count); e != nil {
			return e
		}
		if count+len(objects) > 10000 {
			return fmt.Errorf("event_storage_backpressure")
		}
		var candidates int
		if e = tx.QueryRow("SELECT count(*) FROM deermate_work_records e WHERE e.owner=? AND e.kind='event' AND e.state='candidate' AND json_extract(e.data,'$.source_generation')=? AND NOT EXISTS (SELECT 1 FROM deermate_work_records d WHERE d.owner=e.owner AND d.kind='decision' AND json_extract(d.data,'$.event_id')=e.id)", src.Owner, workInt(src, "generation")).Scan(&candidates); e != nil {
			return e
		}
		if candidates+len(objects) > 1000 {
			return fmt.Errorf("candidate_storage_backpressure")
		}
		baseline := workBool(src, "baseline")
		for _, entry := range objects {
			obj := entry.obj
			number := obj.Number
			if entry.kind == "comment" {
				if !strings.HasPrefix(obj.URL, "https://api.github.com/repos/"+s.cfg.GitHubRepository+"/issues/") {
					return ErrCredentials
				}
				n, _ := strconv.Atoi(obj.URL[strings.LastIndex(obj.URL, "/")+1:])
				number = n
			}
			if obj.ID <= 0 || number <= 0 {
				return ErrCredentials
			}
			objectKey := fmt.Sprintf("%s:%d:%d", entry.kind, obj.ID, workInt(src, "generation"))
			revision := workHash([]any{obj.Updated, obj.Title, obj.Body, obj.Pull, obj.State, obj.Labels, obj.SHA})
			key := objectKey + ":" + revision
			if _, err := workExisting(tx, src.Owner, "github_event", key); err == nil {
				continue
			}
			if old, e := workExisting(tx, src.Owner, "github_object", objectKey); e == nil {
				previous, err := workGet(tx, src.Owner, "event", old)
				if err == nil {
					previous.State = "superseded"
					if err = workPut(tx, &previous); err != nil {
						return err
					}
				}
			}
			// Initial baseline is durable but cannot become retroactive automation input.
			event := newWork(src.Owner, "event", "baseline", "", map[string]any{"object_key": objectKey, "source_id": src.ID, "source_generation": workInt(src, "generation"), "source_revision": src.Revision, "remote_id": obj.ID, "remote_revision": revision, "event_kind": entry.kind, "title": safeWorkText(obj.Title, 200), "preview": safeWorkText(obj.Body, 2000), "thread_key": fmt.Sprintf("github:%s:%d", s.cfg.GitHubRepository, number), "is_pr": len(obj.Pull) > 0 && string(obj.Pull) != "null", "head_sha": obj.SHA, "number": number, "updated_at": obj.Updated})
			if baseline {
				event.State = "candidate"
			}
			if e = workPut(tx, &event); e != nil {
				return e
			}
			if e = workUnique(tx, src.Owner, "github_event", key, event.ID); e != nil {
				return e
			}
			if _, e = tx.Exec("INSERT INTO deermate_work_keys(owner,kind,key,record) VALUES(?,?,?,?) ON CONFLICT(owner,kind,key) DO UPDATE SET record=excluded.record", src.Owner, "github_object", objectKey, event.ID); e != nil {
				return e
			}
			if !baseline {
				continue
			}
			// Known subscriptions receive bounded context directly. No Router/model call.
			if workID, err := workExisting(tx, src.Owner, "subscription", workString(event, "thread_key")); err == nil {
				target, err := workGet(tx, src.Owner, "work", workID)
				if err == nil && target.State != "closed" && workInt(target, "source_generation") == workInt(src, "generation") {
					event.Parent = target.ID
					event.State = "context"
					if e = workPut(tx, &event); e != nil {
						return e
					}
					target.Data["has_update"] = true
					if e = workPut(tx, &target); e != nil {
						return e
					}
					continue
				}
			}
			rules, err := tx.Query("SELECT "+workColumns+" FROM deermate_work_records WHERE owner=? AND kind='rule' AND state IN ('observe','auto') ORDER BY id LIMIT 20", src.Owner)
			if err != nil {
				return err
			}
			selected := []workRecord{}
			for rules.Next() {
				v, err := scanWork(rules)
				if err != nil {
					rules.Close()
					return err
				}
				selected = append(selected, v)
			}
			rules.Close()
			for _, rule := range selected {
				kinds, _ := rule.Data["event_kinds"].([]any)
				allowed := len(kinds) == 0
				for _, k := range kinds {
					if k == entry.kind {
						allowed = true
					}
				}
				if !allowed {
					continue
				}
				// Immutable references are resolved again before assessment/admission.
				if err = enqueueExternal(tx, u, event, rule); err != nil {
					return err
				}
			}
		}
		src.Data["baseline"] = true
		src.Data["cursor"] = cursor
		src.Data["etag"] = etag
		src.Data["last_poll_at"] = time.Now().Unix()
		delete(src.Data, "error")
		return workPut(tx, &src)
	})
}

// Only PRs already subscribed to a current work item are eligible for CI reads.
func (s *Server) githubBoundCI(ctx context.Context, src workRecord) ([]struct {
	obj  githubObject
	kind string
}, []workRecord, error) {
	rows, e := s.Store.DB.Query("SELECT "+workColumns+" FROM deermate_work_records WHERE owner=? AND kind='work' AND state IN ('active','paused') AND json_extract(data,'$.source_id')=? AND json_extract(data,'$.source_generation')=? AND json_extract(data,'$.is_pr')=1 ORDER BY coalesce(json_extract(data,'$.ci_checked_at'),0),id LIMIT 2", src.Owner, src.ID, workInt(src, "generation"))
	if e != nil {
		return nil, nil, e
	}
	works := []workRecord{}
	for rows.Next() {
		v, err := scanWork(rows)
		if err != nil {
			rows.Close()
			return nil, nil, err
		}
		works = append(works, v)
	}
	rows.Close()
	events := []struct {
		obj  githubObject
		kind string
	}{}
	for _, work := range works {
		number := workInt(work, "number")
		if number <= 0 {
			return nil, nil, ErrCredentials
		}
		raw, _, _, err := s.githubRead(ctx, "/pulls/"+strconvWork(number), "")
		if err != nil {
			return nil, nil, err
		}
		var pr struct {
			Head struct {
				SHA string `json:"sha"`
			} `json:"head"`
		}
		if json.Unmarshal(raw, &pr) != nil || !githubSHA.MatchString(pr.Head.SHA) {
			return nil, nil, fmt.Errorf("github_pr_contract")
		}
		for page := 1; page <= 2; page++ {
			raw, _, _, err = s.githubRead(ctx, "/commits/"+pr.Head.SHA+"/check-runs?per_page=50&page="+strconv.Itoa(page), "")
			if err != nil {
				return nil, nil, err
			}
			var batch struct {
				Runs []struct {
					ID         int64  `json:"id"`
					Name       string `json:"name"`
					Status     string `json:"status"`
					Conclusion string `json:"conclusion"`
					Started    string `json:"started_at"`
					Completed  string `json:"completed_at"`
					SHA        string `json:"head_sha"`
				} `json:"check_runs"`
			}
			if json.Unmarshal(raw, &batch) != nil {
				return nil, nil, fmt.Errorf("github_checks_contract")
			}
			for _, run := range batch.Runs {
				if run.SHA != pr.Head.SHA {
					return nil, nil, ErrConflict
				}
				events = append(events, struct {
					obj  githubObject
					kind string
				}{githubObject{ID: run.ID, Number: int(number), Title: "CI: " + run.Name, Body: run.Status + " / " + run.Conclusion, Updated: run.Started + "/" + run.Completed, SHA: run.SHA, State: run.Status + ":" + run.Conclusion}, "ci"})
			}
			if len(batch.Runs) < 50 {
				break
			}
			if page == 2 {
				return nil, nil, fmt.Errorf("github_ci_backpressure")
			}
		}
	}
	return events, works, nil
}

func enqueueExternal(tx *sql.Tx, u User, event, rule workRecord) error {
	rows, e := tx.Query("SELECT "+workColumns+" FROM deermate_work_records WHERE owner=? AND kind='inbox' AND state='pending' AND json_extract(data,'$.event_thread')=? AND json_extract(data,'$.rule_id')=? AND json_extract(data,'$.rule_revision')=? ORDER BY updated DESC LIMIT 5", u.ID, workString(event, "thread_key"), rule.ID, rule.Revision)
	if e != nil {
		return e
	}
	candidates := []workRecord{}
	for rows.Next() {
		v, e := scanWork(rows)
		if e == nil {
			candidates = append(candidates, v)
		}
	}
	rows.Close()
	var inbox workRecord
	batch := []any{}
	for _, candidate := range candidates {
		refs, _ := candidate.Data["event_batch"].([]any)
		filtered := []any{}
		bytes := 0
		for _, raw := range refs {
			ref, ok := raw.(map[string]any)
			if !ok {
				continue
			}
			id, _ := ref["id"].(string)
			old, e := workGet(tx, u.ID, "event", id)
			if e != nil || workString(old, "object_key") == workString(event, "object_key") {
				continue
			}
			filtered = append(filtered, ref)
			bytes += len(workString(old, "preview")) + len(workString(old, "title")) + 256
		}
		if len(filtered) < 20 && bytes+len(workString(event, "preview"))+len(workString(event, "title"))+256 <= 16000 {
			inbox = candidate
			batch = filtered
			break
		}
	}
	if inbox.ID == "" {
		inbox, e = enqueueRouter(tx, u, "event-"+event.ID+"-"+rule.ID, "An external Thread requires assessment.", "event", "")
		if e != nil {
			return e
		}
	}
	batch = append(batch, map[string]any{"id": event.ID, "revision": event.Revision})
	inbox.Data["text"] = "External reference batch; assess latest event " + event.ID + " against rule " + rule.ID + ". No execution is authorized by this content."
	inbox.Data["event_thread"] = workString(event, "thread_key")
	inbox.Data["event_id"] = event.ID
	inbox.Data["event_revision"] = event.Revision
	inbox.Data["rule_id"] = rule.ID
	inbox.Data["rule_revision"] = rule.Revision
	inbox.Data["event_batch"] = batch
	return workPut(tx, &inbox)
}

// Operator repository changes are a new source incarnation. Never apply an old
// auto rule to a newly configured repository just because both use ID github.
func (s *Server) syncWorkSources() error {
	rows, e := s.Store.DB.Query("SELECT " + workColumns + " FROM deermate_work_records WHERE kind='source' AND state='enabled'")
	if e != nil {
		return e
	}
	sources := []workRecord{}
	for rows.Next() {
		v, e := scanWork(rows)
		if e != nil {
			rows.Close()
			return e
		}
		sources = append(sources, v)
	}
	rows.Close()
	for _, source := range sources {
		if workString(source, "repository") == s.cfg.GitHubRepository {
			continue
		}
		if e = s.Store.workTransaction(context.Background(), func(tx *sql.Tx) error {
			source.State = "disabled"
			source.Data["generation"] = workInt(source, "generation") + 1
			source.Data["baseline"] = false
			source.Data["error"] = "repository_configuration_changed"
			if e := workPut(tx, &source); e != nil {
				return e
			}
			rules, e := tx.Query("SELECT "+workColumns+" FROM deermate_work_records WHERE owner=? AND kind='rule' AND state='auto' AND json_extract(data,'$.source_id')=?", source.Owner, source.ID)
			if e != nil {
				return e
			}
			updates := []workRecord{}
			for rules.Next() {
				v, e := scanWork(rules)
				if e != nil {
					rules.Close()
					return e
				}
				updates = append(updates, v)
			}
			rules.Close()
			for _, v := range updates {
				v.State = "observe"
				if e = workPut(tx, &v); e != nil {
					return e
				}
			}
			return nil
		}); e != nil {
			return e
		}
	}
	return nil
}

func (s *Server) githubToken() (string, error) {
	if s.cfg.GitHubSecretHome == "" {
		return "", ErrCredentials
	}
	p := filepath.Join(s.cfg.GitHubSecretHome, "github-read-token")
	info, e := os.Lstat(p)
	if e != nil || !info.Mode().IsRegular() || info.Size() > 4096 || info.Mode().Perm()&0077 != 0 {
		return "", ErrCredentials
	}
	raw, e := os.ReadFile(p)
	if e != nil {
		return "", ErrCredentials
	}
	token := strings.TrimSpace(string(raw))
	if token == "" || strings.ContainsAny(token, "\r\n") {
		return "", ErrCredentials
	}
	return token, nil
}
