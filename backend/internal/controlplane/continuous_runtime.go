package controlplane

import (
	"context"
	"crypto/subtle"
	"database/sql"
	"encoding/json"
	"net/http"
	"net/url"
	"strings"
	"time"
)

type workRuntimeResult struct {
	Accepted    bool   `json:"accepted"`
	Known       bool   `json:"known"`
	Run         string `json:"run_id"`
	Task        string `json:"tracking_id"`
	Thread      string `json:"thread_id"`
	Incarnation string `json:"incarnation"`
	Status      string `json:"status"`
	Native      string `json:"native_session"`
	Verified    bool   `json:"verified"`
	Preview     string `json:"preview"`
	Handoff     bool   `json:"handoff"`
}

func (s *Server) RunContinuousQueue(ctx context.Context) {
	ticker := time.NewTicker(3 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			for _, lane := range []string{"router", "assessor", "native", "source"} {
				go s.pumpContinuousLane(ctx, lane)
			}
		}
	}
}
func (s *Server) pumpContinuousLane(ctx context.Context, lane string) {
	select {
	case s.continuousLanes[lane] <- struct{}{}:
		defer func() { <-s.continuousLanes[lane] }()
	default:
		return
	}
	if lane == "router" && s.cfg.ContinuousEnabled {
		s.pumpRouter(ctx)
	}
	if lane == "native" && s.cfg.ContinuousEnabled {
		s.pumpAuto(ctx)
	}
	if lane != "source" {
		predicate := "json_extract(data,'$.kind')=?"
		if lane == "native" {
			predicate = "json_extract(data,'$.kind') NOT IN ('router','assessor') AND ?='native'"
		}
		rows, e := s.Store.DB.Query("SELECT "+workColumns+" FROM deermate_work_records WHERE kind='operation' AND state IN ('prepared','dispatching','acknowledged','uncertain') AND "+predicate+" ORDER BY CASE WHEN json_extract(data,'$.automatic')=1 THEN 1 ELSE 0 END,created,id LIMIT 10", lane)
		if e != nil {
			return
		}
		ops := []workRecord{}
		for rows.Next() {
			v, err := scanWork(rows)
			if err == nil {
				ops = append(ops, v)
			}
		}
		rows.Close()
		for _, op := range ops {
			if ctx.Err() != nil {
				return
			}
			s.deliverWork(ctx, op)
		}
		return
	}
	if !s.cfg.ContinuousEnabled {
		return
	}

	rows, e := s.Store.DB.Query("SELECT " + workColumns + " FROM deermate_work_records WHERE kind='source' AND state='enabled' ORDER BY updated LIMIT 1")
	if e != nil {
		return
	}
	var src workRecord
	if rows.Next() {
		src, e = scanWork(rows)
	}
	rows.Close()
	if e == nil && src.ID != "" && workEnabled(s.Store.DB, src.Owner) && time.Now().Unix()-workInt(src, "last_poll_at") >= 60 && time.Now().Unix() >= workInt(src, "retry_after") {
		pollctx, cancel := context.WithTimeout(ctx, 45*time.Second)
		err := s.pollGitHub(pollctx, src)
		cancel()
		if err != nil {
			_ = s.Store.workTransaction(ctx, func(tx *sql.Tx) error {
				v, e := workGet(tx, src.Owner, "source", src.ID)
				if e != nil || v.Revision != src.Revision {
					return ErrConflict
				}
				v.Data["error"] = safeWorkText(err.Error(), 100)
				v.Data["retry_after"] = time.Now().Add(5 * time.Minute).Unix()
				return workPut(tx, &v)
			})
		}
	}
}
func (s *Server) pumpRouter(ctx context.Context) {
	var inbox workRecord
	rows, e := s.Store.DB.Query("SELECT " + workColumns + " FROM deermate_work_records WHERE kind='inbox' AND state='pending' ORDER BY CASE WHEN json_extract(data,'$.origin')='user' THEN 0 ELSE 1 END,created,id LIMIT 1")
	if e != nil {
		return
	}
	if rows.Next() {
		inbox, e = scanWork(rows)
	}
	rows.Close()
	if e != nil || inbox.ID == "" {
		return
	}
	_ = s.Store.workTransaction(ctx, func(tx *sql.Tx) error {
		current, e := workGet(tx, inbox.Owner, "inbox", inbox.ID)
		if e != nil || current.State != "pending" {
			return ErrConflict
		}
		if !workEnabled(tx, inbox.Owner) {
			return ErrDisabled
		}
		var n int
		if e = tx.QueryRow("SELECT count(*) FROM deermate_work_records WHERE owner=? AND kind='operation' AND state IN ('prepared','dispatching','acknowledged','uncertain') AND json_extract(data,'$.kind')='router'", inbox.Owner).Scan(&n); e != nil || n > 0 {
			return ErrConflict
		}
		if workString(current, "origin") == "event" {
			event, rule, err := assessmentInputs(tx, inbox.Owner, workString(current, "event_id"), workString(current, "rule_id"))
			if err != nil || event.Revision != workInt(current, "event_revision") || rule.Revision != workInt(current, "rule_revision") {
				current.State = "stale"
				return workPut(tx, &current)
			}
		}
		router, e := workGet(tx, inbox.Owner, "router", "router")
		if e != nil {
			return e
		}
		op := newWork(inbox.Owner, "operation", "prepared", inbox.ID, map[string]any{"kind": "router", "thread_id": workString(router, "thread_id"), "message": workString(current, "text"), "inbox_id": current.ID, "origin": workString(current, "origin"), "work_id": workString(current, "work_id"), "event_id": workString(current, "event_id"), "event_revision": workInt(current, "event_revision"), "rule_id": workString(current, "rule_id"), "rule_revision": workInt(current, "rule_revision"), "_nonce": opaque(), "_user_version": workInt(current, "_user_version")})
		if e = workPut(tx, &op); e != nil {
			return e
		}
		current.State = "queued"
		current.Data["operation_id"] = op.ID
		return workPut(tx, &current)
	})
}
func (s *Server) deliverWork(ctx context.Context, snapshot workRecord) {
	u, e := s.Store.User(snapshot.Owner)
	if e != nil || u.Disabled || u.NeedsSetup || u.Role != "admin" || int64(u.Version) != workInt(snapshot, "_user_version") {
		return
	}
	op := snapshot
	perform := false
	if op.State == "prepared" {
		e = s.Store.workTransaction(ctx, func(tx *sql.Tx) error {
			var err error
			op, err = workGet(tx, u.ID, "operation", op.ID)
			if err != nil {
				return err
			}
			if op.State != "prepared" {
				return ErrConflict
			}
			if !s.cfg.ContinuousEnabled || !workEnabled(tx, u.ID) {
				return ErrDisabled
			}
			kind := workString(op, "kind")
			if kind == "router" || kind == "assessor" {
				if kind == "assessor" || workString(op, "origin") == "event" {
					event, rule, err := assessmentInputs(tx, u.ID, workString(op, "event_id"), workString(op, "rule_id"))
					if err != nil || event.Revision != workInt(op, "event_revision") || rule.Revision != workInt(op, "rule_revision") {
						op.State = "settled"
						op.Data["status"] = "stale"
						return workPut(tx, &op)
					}
				}
				cfg, e := workGet(tx, u.ID, "settings", "settings")
				if e != nil || workString(cfg, "model") == "" {
					return ErrConflict
				}
				if e = workReserve(tx, u.ID, "model", 20, time.Now()); e != nil {
					return e
				}
				op.Data["model"] = workString(cfg, "model")
				op.Data["prompt_version"] = "continuous-v1"
			} else {
				v, e := workGet(tx, u.ID, "work", op.Parent)
				if e != nil {
					return e
				}
				if kind != "cancel" && v.State != "active" {
					return ErrConflict
				}
				g, e := s.workGrant(tx, u.ID, workString(op, "grant_id"), workString(op, "project"), kind)
				if e != nil || g.Version != int(workInt(op, "grant_version")) || g.Instance != workString(op, "instance_id") {
					return ErrConflict
				}
			}
			op.State = "dispatching"
			op.Data["sent_at"] = time.Now().Unix()
			return workPut(tx, &op)
		})
		if e != nil {
			return
		}
		if op.State != "dispatching" {
			return
		}
		perform = true
	}
	endpoint := "query"
	if perform {
		endpoint = "perform"
	}
	payload, _ := json.Marshal(map[string]any{"operation_id": op.ID, "nonce": workString(op, "_nonce")})
	req, _ := http.NewRequestWithContext(context.WithValue(ctx, sessionKey{}, Session{User: u}), "POST", s.cfg.Origin, nil)
	origin, _ := url.Parse(s.cfg.Origin)
	req.Host = origin.Host
	req.AddCookie(&http.Cookie{Name: "csrf_token", Value: opaque()})
	callctx, cancel := context.WithTimeout(ctx, 20*time.Second)
	raw, err := s.engine.query(callctx, req, "POST", "/api/plugins/deermate.continuous/actions/"+endpoint, payload)
	cancel()
	var result workRuntimeResult
	if err == nil {
		err = json.Unmarshal(raw, &result)
	}
	_ = s.Store.workTransaction(ctx, func(tx *sql.Tx) error {
		current, e := workGet(tx, u.ID, "operation", op.ID)
		if e != nil {
			return e
		}
		if current.State == "settled" {
			return nil
		}
		if err != nil || !result.Known {
			current.State = "uncertain"
			current.Data["reason"] = "receipt_unconfirmed"
			current.Data["next_action"] = "reconcile_original_operation"
			return workPut(tx, &current)
		}
		current.State = "acknowledged"
		current.Data["run_id"] = result.Run
		current.Data["tracking_id"] = result.Task
		current.Data["status"] = result.Status
		kind := workString(current, "kind")
		terminal := false
		switch result.Status {
		case "completed", "failed", "cancelled", "error", "interrupted", "rejected":
			terminal = true
		}
		if (kind == "router" || kind == "assessor") && result.Status == "input_required" {
			terminal = true
		}
		if terminal {
			current.State = "settled"
			current.Data["preview"] = safeWorkText(result.Preview, 2000)
			current.Data["verified"] = result.Verified
			current.Data["native_session"] = result.Native
		}
		if e = workPut(tx, &current); e != nil {
			return e
		}
		if kind == "router" {
			inbox, e := workGet(tx, u.ID, "inbox", current.Parent)
			if e != nil {
				return e
			}
			inbox.State = current.State
			if terminal {
				inbox.Data["reply"] = safeWorkText(result.Preview, 2000)
				if reply := workString(current, "reply"); reply != "" {
					inbox.Data["reply"] = reply
				}
			}
			return workPut(tx, &inbox)
		}
		if kind == "assessor" {
			if terminal {
				return s.settleAssessment(tx, u, current, result)
			}
			return nil
		}
		target, e := workGet(tx, u.ID, "work", current.Parent)
		if e != nil {
			return e
		}
		if result.Thread != "" && result.Thread != workString(target, "thread_id") {
			return ErrConflict
		}
		if result.Incarnation != "" {
			old := workString(target, "incarnation")
			if old != "" && old != result.Incarnation {
				return ErrConflict
			}
			target.Data["incarnation"] = result.Incarnation
		}
		if kind == "cancel" {
			if result.Status == "cancelled" {
				target.Data["stage"] = "cancelled"
			}
			if result.Accepted || result.Status == "cancel_requested" {
				target.Data["cancel_requested"] = true
			}
			return workPut(tx, &target)
		}
		target.Data["stage"] = result.Status
		target.Data["head"] = result.Task
		if !terminal && result.Status == "input_required" && workString(current, "attention_notified") != "input_required" {
			current.Data["attention_notified"] = "input_required"
			if e = workPut(tx, &current); e != nil {
				return e
			}
			if _, e = enqueueRouter(tx, u, "attention-"+current.ID, "Work "+target.ID+" requires owner input. Inspect the original task; do not start a replacement.", "receipt", target.ID); e != nil {
				return e
			}
		}
		if !terminal && time.Now().Unix()-workInt(current, "sent_at") > 1800 {
			target.Data["attention"] = "deadline_observation_required"
		}
		if terminal {
			if workString(target, "active_operation") == current.ID {
				delete(target.Data, "active_operation")
			}
			target.Data["verified"] = result.Verified
			target.Data["outcome"] = result.Status
			target.Data["preview"] = safeWorkText(result.Preview, 2000)
			if result.Status == "completed" && !result.Verified {
				target.Data["stage"] = "verification_required"
			}
			if result.Handoff {
				target.Data["stage"] = "handoff"
			}
			refs, _ := target.Data["refs"].([]any)
			refs = append(refs, map[string]any{"kind": "operation", "id": current.ID})
			if len(refs) > 15 {
				refs = refs[len(refs)-15:]
			}
			target.Data["refs"] = refs
			if _, e = enqueueRouter(tx, u, "receipt-"+current.ID, "Work "+target.ID+" has a new authoritative receipt: "+result.Status+". Verified: "+boolText(result.Verified)+". Read its references if needed.", "receipt", target.ID); e != nil {
				return e
			}
		}
		return workPut(tx, &target)
	})
}
func boolText(b bool) string {
	if b {
		return "true"
	}
	return "false"
}

type routerCommand struct {
	Action   string `json:"action"`
	Text     string `json:"text"`
	Goal     string `json:"goal"`
	Title    string `json:"title"`
	Work     string `json:"work_id"`
	Project  string `json:"project"`
	Grant    string `json:"grant_id"`
	Decision string `json:"decision_id"`
	Event    string `json:"event_id"`
	Rule     string `json:"rule_id"`
}

func (s *Server) workInternal(w http.ResponseWriter, r *http.Request) {
	var b routerCommand
	if !decode(w, r, &b) {
		return
	}
	var owner string
	if s.Store.DB.QueryRow("SELECT owner FROM deermate_work_records WHERE kind='operation' AND id=?", r.PathValue("id")).Scan(&owner) != nil {
		workError(w, ErrNotFound)
		return
	}
	op, e := workGet(s.Store.DB, owner, "operation", r.PathValue("id"))
	if e != nil {
		workError(w, e)
		return
	}
	token := strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")
	if token == "" || subtle.ConstantTimeCompare([]byte(token), []byte(workString(op, "_nonce"))) != 1 {
		fail(w, 403, "operation_required", "Canonical operation capability required")
		return
	}
	u, e := s.Store.User(owner)
	if e != nil || u.Disabled || u.NeedsSetup || u.Role != "admin" || int64(u.Version) != workInt(op, "_user_version") || !s.cfg.ContinuousEnabled || !workEnabled(s.Store.DB, owner) || workString(op, "kind") != "router" || !slicesWorkState(op.State, "dispatching", "acknowledged", "uncertain") {
		fail(w, 403, "operation_expired", "Router admission is no longer current")
		return
	}
	if workBool(op, "_tool_done") {
		respond(w, 200, op.Data["_tool_result"])
		return
	}
	e = s.Store.workTransaction(r.Context(), func(tx *sql.Tx) error {
		v, err := workGet(tx, owner, "operation", op.ID)
		if err != nil {
			return err
		}
		if workBool(v, "_tool_claimed") {
			return ErrConflict
		}
		v.Data["_tool_claimed"] = true
		return workPut(tx, &v)
	})
	if e != nil {
		workError(w, e)
		return
	}
	var result any
	switch b.Action {
	case "read":
		if b.Work != "" {
			v, err := s.visibleWork(owner, "work", b.Work)
			if err != nil {
				workError(w, err)
				return
			}
			result = s.workView(v)
		} else {
			items, err := s.Store.workList(owner, "work", "", 0, 10)
			if err != nil {
				workError(w, err)
				return
			}
			result = map[string]any{"items": s.workViews(items)}
		}
	case "respond":
		result = map[string]any{"message": safeWorkText(b.Text, 2000)}
	case "propose", "execute", "followup":
		// External content may propose or request assessment, never promote itself
		// into a user's explicit task execution instruction.
		if b.Action != "propose" && workString(op, "origin") != "user" {
			workError(w, ErrConflict)
			return
		}
		if b.Action == "propose" {
			e = s.Store.workTransaction(r.Context(), func(tx *sql.Tx) error {
				v := newWork(owner, "decision", "suggested", "", map[string]any{"title": safeWorkText(b.Title, 200), "goal": safeWorkText(b.Goal, 4000), "project": b.Project, "grant_id": b.Grant, "operation_id": op.ID, "basis": "router_proposal"})
				result = workPublic(v)
				return workPut(tx, &v)
			})
		} else {
			var v workRecord
			if b.Work != "" {
				v, e = s.visibleWork(owner, "work", b.Work)
			} else {
				v, e = s.createWork(r.Context(), u, workBody{Operation: "router-" + op.ID, Goal: b.Goal, Title: b.Title, Project: b.Project, Grant: b.Grant}, "router_user")
			}
			if e == nil {
				e = s.Store.workTransaction(r.Context(), func(tx *sql.Tx) error {
					current, err := workGet(tx, owner, "work", v.ID)
					if err != nil {
						return err
					}
					message := b.Text
					if message == "" {
						message = workString(current, "goal")
					}
					kind := "execute"
					if workString(current, "head") != "" {
						kind = "followup"
					}
					out, err := s.prepareWorkOperation(tx, u, current, kind, message, "router-action-"+op.ID, false)
					result = workPublic(out)
					return err
				})
			}
		}
	case "accept":
		if workString(op, "origin") != "user" {
			workError(w, ErrConflict)
			return
		}
		e = s.Store.workTransaction(r.Context(), func(tx *sql.Tx) error {
			decision, err := workGet(tx, owner, "decision", b.Decision)
			if err != nil {
				return err
			}
			out, err := s.acceptWorkDecision(tx, u, decision, b.Project, b.Grant, false)
			result = workPublic(out)
			return err
		})
	case "assess":
		e = s.Store.workTransaction(r.Context(), func(tx *sql.Tx) error {
			event, rule, err := assessmentInputs(tx, owner, b.Event, b.Rule)
			if err != nil {
				return err
			}
			if existing, err := workExisting(tx, owner, "assessment", event.ID+":"+rule.ID+":"+strconvWork(rule.Revision)); err == nil {
				v, err := workGet(tx, owner, "operation", existing)
				result = workPublic(v)
				return err
			}
			v := newWork(owner, "operation", "prepared", event.ID, map[string]any{"kind": "assessor", "thread_id": "assessor-" + strings.ReplaceAll(uuid(), "-", ""), "event_id": event.ID, "event_revision": event.Revision, "rule_id": rule.ID, "rule_revision": rule.Revision, "source_generation": workInt(event, "source_generation"), "message": assessmentPrompt(event, rule), "_nonce": opaque(), "_user_version": u.Version})
			if err = workPut(tx, &v); err != nil {
				return err
			}
			result = workPublic(v)
			return workUnique(tx, owner, "assessment", event.ID+":"+rule.ID+":"+strconvWork(rule.Revision), v.ID)
		})
	default:
		workError(w, ErrCredentials)
		return
	}
	if e != nil {
		workError(w, e)
		return
	}
	e = s.Store.workTransaction(r.Context(), func(tx *sql.Tx) error {
		v, err := workGet(tx, owner, "operation", op.ID)
		if err != nil {
			return err
		}
		if workBool(v, "_tool_done") {
			return nil
		}
		v.Data["_tool_done"] = true
		v.Data["_tool_result"] = result
		if b.Action == "respond" {
			v.Data["reply"] = safeWorkText(b.Text, 2000)
		}
		return workPut(tx, &v)
	})
	if e != nil {
		workError(w, e)
		return
	}
	respond(w, 200, result)
}
func slicesWorkState(s string, states ...string) bool {
	for _, v := range states {
		if s == v {
			return true
		}
	}
	return false
}
