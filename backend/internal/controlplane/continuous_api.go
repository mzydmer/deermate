package controlplane

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"time"
)

var workOperationID = regexp.MustCompile(`^[a-zA-Z0-9_-]{1,128}$`)
var workRepository = regexp.MustCompile(`^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$`)

type workBody struct {
	Operation    string   `json:"operation_id"`
	Expected     int64    `json:"expected_revision"`
	Action       string   `json:"action"`
	Title        string   `json:"title"`
	Goal         string   `json:"goal"`
	Text         string   `json:"text"`
	Project      string   `json:"project"`
	Grant        string   `json:"grant_id"`
	Thread       string   `json:"thread_id"`
	Work         string   `json:"work_id"`
	Mode         string   `json:"mode"`
	Enabled      *bool    `json:"enabled"`
	Source       string   `json:"source_id"`
	Instruction  string   `json:"instruction"`
	EventKinds   []string `json:"event_kinds"`
	NativeBudget int      `json:"native_budget"`
	Model        string   `json:"model"`
}

func (s *Server) continuousRoutes() {
	for _, p := range []struct {
		method, path string
		h            http.HandlerFunc
	}{
		{"GET", "/api/me/continuous-config", s.continuousConfig}, {"PATCH", "/api/me/continuous-config", s.continuousConfig},
		{"GET", "/api/me/work-orders", s.workOrders}, {"POST", "/api/me/work-orders", s.workOrders},
		{"GET", "/api/me/work-orders/search", s.workSearch}, {"GET", "/api/me/work-orders/{id}", s.workOrder}, {"PATCH", "/api/me/work-orders/{id}", s.workOrder},
		{"POST", "/api/me/work-orders/{id}/actions", s.workAction}, {"GET", "/api/me/work-orders/{id}/timeline", s.workTimeline}, {"GET", "/api/me/work-orders/{id}/context", s.workContext},
		{"GET", "/api/me/router", s.routerView}, {"POST", "/api/me/router/messages", s.routerMessage},
		{"GET", "/api/me/event-sources", s.workSources}, {"GET", "/api/me/event-sources/{id}", s.workSources}, {"PATCH", "/api/me/event-sources/{id}", s.workSources},
		{"GET", "/api/me/automation-rules", s.workRules}, {"POST", "/api/me/automation-rules", s.workRules}, {"PATCH", "/api/me/automation-rules/{id}", s.workRules},
		{"GET", "/api/me/agent-decisions", s.workDecisions}, {"POST", "/api/me/agent-decisions/{id}/actions", s.workDecisionAction},
	} {
		s.mux.HandleFunc(p.method+" "+p.path, s.protected(true, p.h))
	}
	s.mux.HandleFunc("POST /internal/deermate/continuous/{id}", s.workInternal)
}
func (s *Server) workAccess(w http.ResponseWriter, r *http.Request) bool {
	if !personalAccess(w, r) {
		return false
	}
	var owner string
	err := s.Store.DB.QueryRow("SELECT value FROM deermate_control_meta WHERE key='agent-owner'").Scan(&owner)
	if err != nil && !errors.Is(err, sql.ErrNoRows) {
		storeError(w, err)
		return false
	}
	if owner != "" && owner != sessionOf(r).User.ID {
		fail(w, 403, "single_owner_required", "This device installation belongs to another owner")
		return false
	}
	return true
}
func workError(w http.ResponseWriter, err error) {
	if errors.Is(err, ErrCredentials) {
		fail(w, 422, "invalid_work_input", "Check the goal, operation, model and registered scope")
		return
	}
	if errors.Is(err, ErrConflict) {
		fail(w, 409, "work_conflict", "Work changed, is busy, or lacks current authorization/budget; reconcile the original operation")
		return
	}
	if errors.Is(err, ErrDisabled) {
		fail(w, 409, "continuous_disabled", "Enable the continuous secretary before starting work")
		return
	}
	storeError(w, err)
}
func workPage(r *http.Request) (int, int, error) {
	o := 0
	l := 20
	var e error
	if v := r.URL.Query().Get("offset"); v != "" {
		o, e = strconv.Atoi(v)
		if e != nil {
			return 0, 0, ErrCredentials
		}
	}
	if v := r.URL.Query().Get("limit"); v != "" {
		l, e = strconv.Atoi(v)
		if e != nil {
			return 0, 0, ErrCredentials
		}
	}
	if o < 0 || o > 10000 || l < 1 || l > 50 {
		return 0, 0, ErrCredentials
	}
	return o, l, nil
}
func (s *Server) continuousConfig(w http.ResponseWriter, r *http.Request) {
	if !s.workAccess(w, r) {
		return
	}
	owner := sessionOf(r).User.ID
	v, err := workGet(s.Store.DB, owner, "settings", "settings")
	if errors.Is(err, ErrNotFound) {
		v = workRecord{ID: "settings", Owner: owner, Kind: "settings", State: "disabled", Data: map[string]any{"enabled": false, "model": "", "native_budget": 0}}
		err = nil
	}
	if err != nil {
		workError(w, err)
		return
	}
	if r.Method == "PATCH" {
		var b workBody
		if !decode(w, r, &b) {
			return
		}
		if !s.cfg.ContinuousEnabled {
			fail(w, 409, "module_disabled", "The installation has not enabled the continuous module")
			return
		}
		if b.Enabled == nil || len(b.Model) > 150 || b.NativeBudget < 0 || b.NativeBudget > 2 {
			workError(w, ErrCredentials)
			return
		}
		if *b.Enabled && !s.boundedWorkModel(r, b.Model) {
			fail(w, 422, "bounded_model_required", "Select a configured model with verified output and retry limits")
			return
		}
		err = s.Store.workTransaction(r.Context(), func(tx *sql.Tx) error {
			current, e := workGet(tx, owner, "settings", "settings")
			if e == nil {
				v = current
			} else if !errors.Is(e, ErrNotFound) {
				return e
			}
			if v.Revision != b.Expected {
				return ErrConflict
			}
			if _, e = tx.Exec("INSERT OR IGNORE INTO deermate_control_meta VALUES('agent-owner',?)", owner); e != nil {
				return e
			}
			var registered string
			if e = tx.QueryRow("SELECT value FROM deermate_control_meta WHERE key='agent-owner'").Scan(&registered); e != nil {
				return e
			}
			if registered != owner {
				return ErrConflict
			}
			v.Data["enabled"] = *b.Enabled
			v.Data["model"] = b.Model
			v.Data["native_budget"] = b.NativeBudget
			v.State = "disabled"
			if *b.Enabled {
				v.State = "enabled"
			}
			return workPut(tx, &v)
		})
		if err != nil {
			workError(w, err)
			return
		}
	}
	reserved := map[string]int{"model": 0, "native": 0}
	day := time.Now().UTC().Format("2006-01-02")
	rows, err := s.Store.DB.Query("SELECT kind,used FROM deermate_work_budget WHERE owner=? AND day=? AND kind IN ('model','native')", owner, day)
	if err != nil {
		workError(w, err)
		return
	}
	for rows.Next() {
		var kind string
		var used int
		if err = rows.Scan(&kind, &used); err != nil {
			rows.Close()
			workError(w, err)
			return
		}
		reserved[kind] = used
	}
	rows.Close()
	respond(w, 200, map[string]any{"config": workPublic(v), "module_available": s.cfg.ContinuousEnabled, "contract_version": continuousVersion, "github_configured": (workRepository.MatchString(s.cfg.GitHubRepository) && s.cfg.GitHubSecretHome != ""), "reserved": reserved, "budget_day": day})
}
func (s *Server) workOrders(w http.ResponseWriter, r *http.Request) {
	if !s.workAccess(w, r) {
		return
	}
	owner := sessionOf(r).User.ID
	if r.Method == "GET" {
		o, l, e := workPage(r)
		if e != nil {
			workError(w, e)
			return
		}
		items, e := s.Store.workList(owner, "work", "", o, l)
		if e != nil {
			workError(w, e)
			return
		}
		respond(w, 200, map[string]any{"items": s.workViews(items), "next_offset": o + len(items)})
		return
	}
	var b workBody
	if !decode(w, r, &b) {
		return
	}
	v, e := s.createWork(r.Context(), sessionOf(r).User, b, "interactive")
	if e != nil {
		workError(w, e)
		return
	}
	respond(w, 200, s.workView(v))
}
func (s *Server) createWork(ctx context.Context, u User, b workBody, origin string) (out workRecord, err error) {
	if !workOperationID.MatchString(b.Operation) || strings.TrimSpace(b.Goal) == "" || len(b.Goal) > 8000 || len(b.Title) > 200 || len(b.Project) > 100 {
		return out, ErrCredentials
	}
	if b.Title == "" {
		b.Title = string([]rune(strings.TrimSpace(b.Goal))[:min(40, len([]rune(strings.TrimSpace(b.Goal))))])
	}
	err = s.Store.workTransaction(ctx, func(tx *sql.Tx) error {
		if !s.cfg.ContinuousEnabled || !workEnabled(tx, u.ID) {
			return ErrDisabled
		}
		fingerprint := workHash([]any{b.Goal, b.Title, b.Project, b.Grant, b.Thread, origin})
		if id, e := workExisting(tx, u.ID, "create", b.Operation); e == nil {
			out, e = workGet(tx, u.ID, "work", id)
			if e == nil && workString(out, "_request_hash") != fingerprint {
				return ErrConflict
			}
			return e
		} else if !errors.Is(e, ErrNotFound) {
			return e
		}
		var count int
		if e := tx.QueryRow("SELECT count(*) FROM deermate_work_records WHERE owner=? AND kind='work' AND state!='closed' AND state!='removed'", u.ID).Scan(&count); e != nil {
			return e
		}
		if count >= 20 {
			return ErrConflict
		}
		thread := strings.ReplaceAll(uuid(), "-", "")
		incarnation := ""
		if b.Thread != "" {
			source, e := ownedTopicSource(tx, u.ID, b.Thread)
			if e != nil || source.Archived {
				return ErrConflict
			}
			thread = b.Thread
			incarnation = source.Incarnation
		}
		out = newWork(u.ID, "work", "active", "", map[string]any{"title": b.Title, "goal": b.Goal, "project": b.Project, "grant_id": b.Grant, "executor": "codex", "server": "deermate", "thread_id": thread, "incarnation": incarnation, "stage": "ready", "origin": origin, "_request_hash": fingerprint, "_user_version": u.Version})
		if b.Thread != "" {
			var head string
			err := tx.QueryRow("SELECT id FROM mcp_tasks WHERE user_id=? AND thread_id=? AND coalesce(thread_incarnation,'')=? ORDER BY created_at DESC,id DESC LIMIT 1", u.ID, thread, incarnation).Scan(&head)
			if err != nil {
				return ErrConflict
			}
			out.Data["head"] = head
		}
		if e := workUnique(tx, u.ID, "execution_thread", thread, out.ID); e != nil {
			return e
		}
		if e := workPut(tx, &out); e != nil {
			return e
		}
		return workUnique(tx, u.ID, "create", b.Operation, out.ID)
	})
	return
}
func (s *Server) workOrder(w http.ResponseWriter, r *http.Request) {
	if !s.workAccess(w, r) {
		return
	}
	owner := sessionOf(r).User.ID
	v, e := workGet(s.Store.DB, owner, "work", r.PathValue("id"))
	if e != nil {
		workError(w, e)
		return
	}
	if r.Method == "PATCH" {
		var b workBody
		if !decode(w, r, &b) {
			return
		}
		if strings.TrimSpace(b.Title) == "" || len(b.Title) > 200 {
			workError(w, ErrCredentials)
			return
		}
		e = s.Store.workTransaction(r.Context(), func(tx *sql.Tx) error {
			var e error
			v, e = workGet(tx, owner, "work", v.ID)
			if e != nil {
				return e
			}
			if b.Expected != v.Revision {
				return ErrConflict
			}
			v.Data["title"] = b.Title
			return workPut(tx, &v)
		})
		if e != nil {
			workError(w, e)
			return
		}
	}
	respond(w, 200, s.workView(v))
}
func (s *Server) workAction(w http.ResponseWriter, r *http.Request) {
	if !s.workAccess(w, r) {
		return
	}
	var b workBody
	if !decode(w, r, &b) {
		return
	}
	owner := sessionOf(r).User.ID
	if !workOperationID.MatchString(b.Operation) {
		workError(w, ErrCredentials)
		return
	}
	var out workRecord
	err := s.Store.workTransaction(r.Context(), func(tx *sql.Tx) error {
		v, e := workGet(tx, owner, "work", r.PathValue("id"))
		if e != nil {
			return e
		}
		if b.Action == "execute" && b.Text == "" {
			b.Text = workString(v, "goal")
		}
		if id, e := workExisting(tx, owner, "action", b.Operation); e == nil {
			out, e = workGet(tx, owner, "operation", id)
			if e == nil && workString(out, "_request_hash") != workHash([]any{v.ID, b.Action, b.Text}) {
				return ErrConflict
			}
			return e
		}
		if v.Revision != b.Expected {
			return ErrConflict
		}
		if v.State == "closed" && b.Action != "reconcile" {
			return ErrConflict
		}
		if b.Action == "cancel" && workString(v, "active_operation") != "" {
			pending, err := workGet(tx, owner, "operation", workString(v, "active_operation"))
			if err != nil {
				return err
			}
			if pending.State == "prepared" {
				pending.State = "settled"
				pending.Data["status"] = "cancelled_before_dispatch"
				if err = workPut(tx, &pending); err != nil {
					return err
				}
				delete(v.Data, "active_operation")
				v.Data["stage"] = "cancelled"
				if err = workPut(tx, &v); err != nil {
					return err
				}
				out = newWork(owner, "operation", "settled", v.ID, map[string]any{"kind": "cancel", "status": "cancelled_before_dispatch", "_request_hash": workHash([]any{v.ID, b.Action, b.Text})})
				if err = workPut(tx, &out); err != nil {
					return err
				}
				return workUnique(tx, owner, "action", b.Operation, out.ID)
			}
		}
		if b.Action == "execute" || b.Action == "followup" || b.Action == "cancel" {
			message := b.Text
			if b.Action == "execute" && message == "" {
				message = workString(v, "goal")
			}
			out, e = s.prepareWorkOperation(tx, sessionOf(r).User, v, b.Action, message, b.Operation, false)
			return e
		}
		if b.Action == "reconcile" {
			out = v
			return nil
		}
		switch b.Action {
		case "pause":
			v.State = "paused"
		case "resume":
			if v.State != "paused" {
				return ErrConflict
			}
			v.State = "active"
		case "close":
			if workString(v, "active_operation") != "" {
				return ErrConflict
			}
			v.State = "closed"
			v.Data["outcome"] = "not_needed"
			_, _ = tx.Exec("DELETE FROM deermate_work_keys WHERE owner=? AND kind='subscription' AND record=?", owner, v.ID)
		default:
			return ErrCredentials
		}
		if e = workPut(tx, &v); e != nil {
			return e
		}
		out = newWork(owner, "operation", "settled", v.ID, map[string]any{"kind": b.Action, "_request_hash": workHash([]any{v.ID, b.Action, b.Text})})
		if e = workPut(tx, &out); e != nil {
			return e
		}
		return workUnique(tx, owner, "action", b.Operation, out.ID)
	})
	if err != nil {
		workError(w, err)
		return
	}
	respond(w, 200, workPublic(out))
}
func (s *Server) workTimeline(w http.ResponseWriter, r *http.Request) {
	if !s.workAccess(w, r) {
		return
	}
	owner := sessionOf(r).User.ID
	id := r.PathValue("id")
	if _, e := workGet(s.Store.DB, owner, "work", id); e != nil {
		workError(w, e)
		return
	}
	o, l, e := workPage(r)
	if e != nil {
		workError(w, e)
		return
	}
	rows, e := s.Store.DB.Query("SELECT "+workColumns+" FROM deermate_work_records WHERE owner=? AND parent=? ORDER BY created DESC,id DESC LIMIT ? OFFSET ?", owner, id, l, o)
	if e != nil {
		workError(w, e)
		return
	}
	defer rows.Close()
	items := []workRecord{}
	for rows.Next() {
		v, e := scanWork(rows)
		if e != nil {
			workError(w, e)
			return
		}
		items = append(items, workPublic(v))
	}
	rows.Close()
	respond(w, 200, map[string]any{"items": s.workViews(items), "next_offset": o + len(items)})
}
func (s *Server) workDecisions(w http.ResponseWriter, r *http.Request) {
	if !s.workAccess(w, r) {
		return
	}
	o, l, e := workPage(r)
	if e != nil {
		workError(w, e)
		return
	}
	items, e := s.Store.workList(sessionOf(r).User.ID, "decision", "", o, l)
	if e != nil {
		workError(w, e)
		return
	}
	respond(w, 200, map[string]any{"items": s.workViews(items), "next_offset": o + len(items)})
}

// safeWorkText is shared by all model-visible and persistent bounded previews.
func safeWorkText(s string, max int) string {
	s = strings.ReplaceAll(s, "\x00", "")
	r := []rune(s)
	if len(r) > max {
		return string(r[:max]) + "…"
	}
	return s
}

func (s *Server) prepareWorkOperation(tx *sql.Tx, u User, v workRecord, kind, message, key string, automatic bool) (workRecord, error) {
	if !s.cfg.ContinuousEnabled || !workEnabled(tx, u.ID) {
		return workRecord{}, ErrDisabled
	}
	if (v.State != "active" && kind != "cancel") || len(message) > 8000 || (kind != "cancel" && strings.TrimSpace(message) == "") {
		return workRecord{}, ErrConflict
	}
	if workString(v, "active_operation") != "" && kind != "cancel" {
		return workRecord{}, ErrConflict
	}
	grant, err := s.workGrant(tx, u.ID, workString(v, "grant_id"), workString(v, "project"), kind)
	if err != nil {
		return workRecord{}, err
	}
	if automatic {
		cfg, e := workGet(tx, u.ID, "settings", "settings")
		if e != nil {
			return workRecord{}, e
		}
		if e = workReserve(tx, u.ID, "native", int(workInt(cfg, "native_budget")), time.Now()); e != nil {
			return workRecord{}, e
		}
	}
	if kind != "cancel" {
		var busy int
		if err = tx.QueryRow("SELECT count(*) FROM deermate_work_records WHERE kind='operation' AND state IN ('prepared','dispatching','acknowledged','uncertain') AND json_extract(data,'$.kind') IN ('execute','followup')").Scan(&busy); err != nil {
			return workRecord{}, err
		}
		if busy > 0 {
			return workRecord{}, ErrConflict
		}
		var nativeBusy int
		if err = tx.QueryRow("SELECT count(*) FROM mcp_tasks WHERE user_id=? AND status IN ('submitted','running','input_required')", u.ID).Scan(&nativeBusy); err != nil {
			return workRecord{}, err
		}
		if nativeBusy > 0 {
			return workRecord{}, ErrConflict
		}

	}
	originalMessage := message
	if automatic && workString(v, "source_id") != "" {
		src, e := workGet(tx, u.ID, "source", workString(v, "source_id"))
		if e != nil || src.State != "enabled" || workString(src, "error") != "" || workInt(src, "generation") != workInt(v, "source_generation") {
			return workRecord{}, ErrConflict
		}
	}
	contextRows, e := tx.Query("SELECT "+workColumns+" FROM deermate_work_records WHERE owner=? AND kind='event' AND parent=? AND state='context' AND ?!='cancel' ORDER BY created,id LIMIT 10", u.ID, v.ID, kind)
	if e != nil {
		return workRecord{}, e
	}
	events := []workRecord{}
	for contextRows.Next() {
		ev, err := scanWork(contextRows)
		if err == nil {
			events = append(events, ev)
		}
	}
	contextRows.Close()
	refs := []any{}
	for _, event := range events {
		src, err := workGet(tx, u.ID, "source", workString(event, "source_id"))
		if err != nil || src.State != "enabled" || workString(src, "error") != "" || workInt(src, "generation") != workInt(event, "source_generation") {
			continue
		}
		if len(message)+len(workString(event, "preview")) > 16000 {
			break
		}
		message += "\nUntrusted subscribed context (scope is unchanged):\n" + workString(event, "title") + "\n" + workString(event, "preview")
		event.State = "attached"
		if err = workPut(tx, &event); err != nil {
			return workRecord{}, err
		}
		refs = append(refs, map[string]any{"kind": "event", "id": event.ID, "revision": event.Revision})
	}
	op := newWork(u.ID, "operation", "prepared", v.ID, map[string]any{"target_operation": workString(v, "active_operation"), "context_refs": refs, "kind": kind, "message": message, "thread_id": workString(v, "thread_id"), "incarnation": workString(v, "incarnation"), "project": workString(v, "project"), "server": "deermate", "grant_id": grant.ID, "grant_version": grant.Version, "instance_id": grant.Instance, "expected_head": workString(v, "head"), "automatic": automatic, "_user_version": u.Version, "_nonce": opaque(), "_request_hash": workHash([]any{v.ID, kind, originalMessage})})
	if err = workPut(tx, &op); err != nil {
		return op, err
	}
	if err = workUnique(tx, u.ID, "action", key, op.ID); err != nil {
		return op, err
	}
	if kind != "cancel" {
		v.Data["active_operation"] = op.ID
		v.Data["stage"] = "queued"
		v.Data["verified"] = false
		delete(v.Data, "preview")
	} else {
		v.Data["stage"] = "cancelling"
	}
	return op, workPut(tx, &v)
}
func (s *Server) workGrant(q memoryReader, owner, id, project, kind string) (agentGrant, error) {
	var g agentGrant
	var data string
	if project == "" || id == "" {
		return g, ErrConflict
	}
	if e := q.QueryRow("SELECT data FROM deermate_agent_grants WHERE id=? AND owner=?", id, owner).Scan(&data); e != nil {
		return g, ErrConflict
	}
	if json.Unmarshal([]byte(data), &g) != nil || !slicesWorkState(grantState(g, time.Now().Unix()), "active", "expiring") || g.Active == nil {
		return g, ErrConflict
	}
	allowed := func(items []string, x string) bool {
		for _, v := range items {
			if v == x {
				return true
			}
		}
		return false
	}
	op := "submit"
	if kind == "followup" {
		op = "continue"
	}
	if kind == "cancel" {
		op = "cancel"
	}
	if !allowed(g.Active.Projects, project) || !allowed(g.Active.Operations, op) {
		return g, ErrConflict
	}
	var d agentDevice
	if q.QueryRow("SELECT data FROM deermate_agent_devices WHERE id=? AND owner=?", g.Device, owner).Scan(&data) != nil || json.Unmarshal([]byte(data), &d) != nil || d.Instance != g.Instance || time.Now().Unix()-d.LastSeen > 90 || d.Worker != "reachable" || d.Continuous != "work-orders-v1" {
		return g, fmt.Errorf("%w: device_unavailable", ErrConflict)
	}
	return g, nil
}

func (s *Server) boundedWorkModel(r *http.Request, model string) bool {
	if strings.TrimSpace(model) == "" {
		return false
	}
	body, _ := json.Marshal(map[string]any{"model": model})
	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
	defer cancel()
	raw, e := s.engine.query(ctx, r, "POST", "/api/plugins/deermate.continuous/actions/capabilities", body)
	if e != nil {
		return false
	}
	var capability struct {
		Version int  `json:"contract_version"`
		Bounded bool `json:"bounded"`
	}
	return json.Unmarshal(raw, &capability) == nil && capability.Version == continuousVersion && capability.Bounded
}
