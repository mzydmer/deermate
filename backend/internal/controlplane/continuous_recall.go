package controlplane

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"database/sql"
	"encoding/base64"
	"encoding/json"
	"errors"
	obs "github.com/mzydmer/deermate/backend/internal/observability"
	"net/http"
	"strconv"
	"strings"
)

func (s *Server) workSearch(w http.ResponseWriter, r *http.Request) {
	if !s.workAccess(w, r) {
		return
	}
	owner := sessionOf(r).User.ID
	q := strings.TrimSpace(r.URL.Query().Get("q"))
	if q == "" || len(q) > 256 {
		workError(w, ErrCredentials)
		return
	}
	table := "deermate_work_fts_" + digest(owner)[:24]
	var exists int
	if err := s.Store.DB.QueryRow("SELECT count(*) FROM sqlite_master WHERE type='table' AND name=?", table).Scan(&exists); err != nil {
		workError(w, err)
		return
	}
	items := []workRecord{}
	if exists == 0 {
		respond(w, 200, map[string]any{"items": items})
		return
	}
	// Trigram MATCH handles three or more characters. Short terms use a bounded
	// owner's latest 200 cards, never an unbounded scan of chat/native histories.
	// FTS5 can stop after the newest 20 indexed matches. Scoring every matching
	// historical event exceeded the small-host latency target for common terms.
	query := "SELECT id,kind FROM " + table + " WHERE " + table + " MATCH ? ORDER BY rowid DESC LIMIT 20"
	args := []any{"\"" + strings.ReplaceAll(q, "\"", "\"\"") + "\""}
	if len([]rune(q)) < 3 {
		query = "SELECT id,kind FROM (SELECT id,kind,data FROM deermate_work_records WHERE owner=? AND kind IN ('work','event') ORDER BY updated DESC LIMIT 200) WHERE instr(json_extract(data,'$.title'),?)>0 OR instr(coalesce(json_extract(data,'$.preview'),json_extract(data,'$.goal'),''),?)>0 LIMIT 20"
		args = []any{owner, q, q}
	}
	rows, err := s.Store.DB.Query(query, args...)
	if err != nil {
		workError(w, err)
		return
	}
	type ref struct{ id, kind string }
	refs := []ref{}
	for rows.Next() {
		var v ref
		if err = rows.Scan(&v.id, &v.kind); err != nil {
			break
		}
		refs = append(refs, v)
	}
	rows.Close()
	if err != nil {
		workError(w, err)
		return
	}
	for _, v := range refs {
		record, e := s.visibleWork(owner, v.kind, v.id)
		if e == nil {
			items = append(items, workPublic(record))
		}
	}
	respond(w, 200, map[string]any{"items": items, "short_query_bounded": len([]rune(q)) < 3})
}

func (s *Server) visibleWork(owner, kind, id string) (workRecord, error) {
	v, e := workGet(s.Store.DB, owner, kind, id)
	if e != nil {
		return v, e
	}
	if v.State == "removed" || v.State == "unavailable" || v.State == "superseded" {
		return v, ErrNotFound
	}
	if source := workString(v, "source_id"); source != "" {
		src, e := workGet(s.Store.DB, owner, "source", source)
		if e != nil || src.State != "enabled" || workString(src, "error") != "" || workInt(v, "source_generation") != workInt(src, "generation") {
			return v, ErrNotFound
		}
	}
	if kind == "decision" && workString(v, "rule_id") != "" {
		rule, err := workGet(s.Store.DB, owner, "rule", workString(v, "rule_id"))
		if err != nil || rule.State == "off" || rule.Revision != workInt(v, "rule_revision") {
			return v, ErrNotFound
		}
	}
	if kind == "event" && workString(v, "object_key") != "" {
		current, err := workExisting(s.Store.DB, owner, "github_object", workString(v, "object_key"))
		if err != nil || current != v.ID {
			return v, ErrNotFound
		}
	}
	return v, nil
}

func (s *Server) workContext(w http.ResponseWriter, r *http.Request) {
	if !s.workAccess(w, r) {
		return
	}
	owner := sessionOf(r).User.ID
	v, e := s.visibleWork(owner, "work", r.PathValue("id"))
	if e != nil {
		workError(w, e)
		return
	}
	pageSize := 10
	if raw := r.URL.Query().Get("limit"); raw != "" {
		n, err := strconv.Atoi(raw)
		if err != nil || n < 1 || n > 20 {
			workError(w, ErrCredentials)
			return
		}
		pageSize = n
	}
	offset := 0
	if token := r.URL.Query().Get("cursor"); token != "" {
		var err error
		offset, err = s.readWorkCursor(token, owner, v.ID, v.Revision)
		if err != nil {
			workError(w, err)
			return
		}
	}
	items := []any{contextWork(v)}
	used, _ := json.Marshal(items)
	seen := map[string]bool{"work:" + v.ID: true}
	truncated := false
	frontier := []workRecord{v}
	for depth := 0; depth < 3 && len(frontier) > 0; depth++ {
		next := []workRecord{}
		for _, node := range frontier {
			refs, _ := node.Data["refs"].([]any)
			for _, raw := range refs {
				ref, ok := raw.(map[string]any)
				if !ok {
					continue
				}
				kind, _ := ref["kind"].(string)
				id, _ := ref["id"].(string)
				if !slicesWorkState(kind, "work", "event", "decision", "rule", "operation") {
					continue
				}
				key := kind + ":" + id
				if seen[key] {
					continue
				}
				seen[key] = true
				if len(items) >= 20 {
					truncated = true
					break
				}
				linked, err := s.visibleWork(owner, kind, id)
				if revision, ok := ref["revision"].(float64); ok && revision > 0 && linked.Revision != int64(revision) {
					err = ErrConflict
				}
				var item any
				if err != nil {
					item = map[string]any{"id": id, "kind": kind, "state": "unavailable"}
				} else {
					item = contextWork(linked)
				}
				encoded, _ := json.Marshal(item)
				if len(used)+len(encoded)+1 > 30720 {
					truncated = true
					break
				}
				used = append(used, encoded...)
				items = append(items, item)
				if err == nil {
					next = append(next, linked)
				}
			}
		}
		frontier = next
	}
	if offset > len(items) {
		workError(w, ErrConflict)
		return
	}
	end := min(len(items), offset+pageSize)
	nextCursor := ""
	if end < len(items) {
		nextCursor = s.workCursor(owner, v.ID, v.Revision, end)
	}
	respond(w, 200, map[string]any{"items": items[offset:end], "next_cursor": nextCursor, "truncated": truncated, "limits": map[string]int{"hops": 3, "objects": 20, "bytes": 32768}, "execution_thread_id": workString(v, "thread_id")})
}

func (s *Server) routerView(w http.ResponseWriter, r *http.Request) {
	if !s.workAccess(w, r) {
		return
	}
	owner := sessionOf(r).User.ID
	router, e := workGet(s.Store.DB, owner, "router", "router")
	if e != nil && !errors.Is(e, ErrNotFound) {
		workError(w, e)
		return
	}
	items, e := s.Store.workList(owner, "inbox", "router", 0, 20)
	if e != nil {
		workError(w, e)
		return
	}
	respond(w, 200, map[string]any{"session": workPublic(router), "items": items})
}
func (s *Server) routerMessage(w http.ResponseWriter, r *http.Request) {
	if !s.workAccess(w, r) {
		return
	}
	var b workBody
	if !decode(w, r, &b) {
		return
	}
	if !workOperationID.MatchString(b.Operation) || strings.TrimSpace(b.Text) == "" || len(b.Text) > 8000 {
		workError(w, ErrCredentials)
		return
	}
	owner := sessionOf(r).User.ID
	var out workRecord
	e := s.Store.workTransaction(r.Context(), func(tx *sql.Tx) error {
		if !s.cfg.ContinuousEnabled {
			return ErrDisabled
		}
		if e := claimWorkOwner(tx, owner); e != nil {
			return e
		}
		var e error
		out, e = enqueueRouter(tx, sessionOf(r).User, b.Operation, b.Text, "user", b.Work, r.Context())
		return e
	})
	if e != nil {
		workError(w, e)
		return
	}
	s.captureRouterMemory(r.Context(), owner, out)
	respond(w, 200, workPublic(out))
}
func enqueueRouter(tx *sql.Tx, u User, key, text, origin, work string, traceContexts ...context.Context) (workRecord, error) {
	if id, e := workExisting(tx, u.ID, "inbox", key); e == nil {
		v, e := workGet(tx, u.ID, "inbox", id)
		if e == nil && workString(v, "_request_hash") != workHash([]any{text, origin, work}) {
			return v, ErrConflict
		}
		return v, e
	}
	router, e := workGet(tx, u.ID, "router", "router")
	if errors.Is(e, ErrNotFound) {
		router = workRecord{ID: "router", Kind: "router", Owner: u.ID, State: "active", Data: map[string]any{"thread_id": "router-" + strings.ReplaceAll(uuid(), "-", "")}}
		e = workPut(tx, &router)
	}
	if e != nil {
		return workRecord{}, e
	}
	var count int
	if e = tx.QueryRow("SELECT count(*) FROM deermate_work_records WHERE owner=? AND kind='inbox' AND state IN ('pending','dispatching','acknowledged','uncertain')", u.ID).Scan(&count); e != nil {
		return workRecord{}, e
	}
	if count >= 100 {
		return workRecord{}, ErrConflict
	}
	v := newWork(u.ID, "inbox", "pending", "router", map[string]any{"text": safeWorkText(text, 4000), "origin": origin, "work_id": work, "_user_version": u.Version, "_request_hash": workHash([]any{text, origin, work})})
	if origin == "user" && len(text) <= 4000 && text == workString(v, "text") && automaticMemorySafe(text) {
		if p, err := readProfile(tx, u.ID); err == nil && p.AutoCaptureEnabled {
			v.Data["_memory_eligible"] = true
			v.Data["_memory_thread"] = workString(router, "thread_id")
			v.Data["_memory_policy"] = p.PolicyRevision
			v.Data["_memory_deleted"] = p.DeletionRevision
		}
	}
	if e = workPut(tx, &v); e != nil {
		return v, e
	}
	if len(traceContexts) > 0 {
		bindTrace(tx, u.ID, v.ID, obs.WithRefs(traceContexts[0], map[string]string{"conversation_id": workString(router, "thread_id"), "work_id": work}))
	}
	return v, workUnique(tx, u.ID, "inbox", key, v.ID)
}

func (s *Server) workView(v workRecord) workRecord {
	v = workPublic(v)
	if v.Kind == "work" {
		kind := "execute"
		if workString(v, "head") != "" {
			kind = "followup"
		}
		_, err := s.workGrant(s.Store.DB, v.Owner, workString(v, "grant_id"), workString(v, "project"), kind)
		v.Data["can_execute"] = err == nil && s.cfg.ContinuousEnabled && v.State == "active" && workString(v, "active_operation") == ""
		_, cancelErr := s.workGrant(s.Store.DB, v.Owner, workString(v, "grant_id"), workString(v, "project"), "cancel")
		pendingID := workString(v, "active_operation")
		v.Data["can_cancel"] = cancelErr == nil && pendingID != ""
		if pendingID != "" {
			pending, e := workGet(s.Store.DB, v.Owner, "operation", pendingID)
			if e == nil && pending.State == "prepared" {
				v.Data["can_cancel"] = true
			}
		}
		if err != nil {
			v.Data["execution_reason"] = "current_worker_authorization_required"
		}
	}

	if refs, ok := v.Data["context_refs"].([]any); ok {
		for _, raw := range refs {
			ref, ok := raw.(map[string]any)
			if !ok {
				continue
			}
			id, _ := ref["id"].(string)
			if _, err := s.visibleWork(v.Owner, "event", id); err != nil {
				v.Data = map[string]any{"title": "Context source unavailable", "kind": workString(v, "kind"), "status": workString(v, "status"), "tracking_id": workString(v, "tracking_id")}
				return workPublic(v)
			}
		}
	}
	checked := v
	if v.Kind == "operation" && v.Parent != "" {
		if parent, e := workGet(s.Store.DB, v.Owner, "work", v.Parent); e == nil {
			checked = parent
		}
	}
	if workString(checked, "source_id") != "" {
		if _, e := s.visibleWork(checked.Owner, checked.Kind, checked.ID); e != nil {
			data := map[string]any{"title": "Source unavailable", "source_state": "unavailable", "source_id": workString(checked, "source_id"), "thread_id": workString(checked, "thread_id"), "project": workString(checked, "project"), "work_id": checked.ID}
			if v.Kind == "work" {
				data["stage"] = workString(v, "stage")
				data["can_cancel"] = v.Data["can_cancel"]
				data["can_execute"] = false
				data["active_operation"] = workString(v, "active_operation")
			} else {
				v.State = "source_unavailable"
			}
			v.Data = data
			return workPublic(v)
		}
	}
	return workPublic(v)
}
func (s *Server) workViews(items []workRecord) []workRecord {
	for i, v := range items {
		items[i] = s.workView(v)
	}
	return items
}

func contextWork(v workRecord) workRecord {
	v = workPublic(v)
	if v.Kind == "operation" {
		delete(v.Data, "message")
	}
	return v
}
func (s *Server) workCursor(owner, root string, revision int64, offset int) string {
	payload, _ := json.Marshal([]any{owner, root, revision, offset})
	mac := hmac.New(sha256.New, []byte(s.cfg.JWTSecret))
	mac.Write(payload)
	return base64.RawURLEncoding.EncodeToString(payload) + "." + base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
}
func (s *Server) readWorkCursor(token, owner, root string, revision int64) (int, error) {
	if len(token) > 512 {
		return 0, ErrCredentials
	}
	left, right, ok := strings.Cut(token, ".")
	if !ok {
		return 0, ErrCredentials
	}
	payload, e := base64.RawURLEncoding.DecodeString(left)
	if e != nil {
		return 0, ErrCredentials
	}
	signature, e := base64.RawURLEncoding.DecodeString(right)
	if e != nil {
		return 0, ErrCredentials
	}
	mac := hmac.New(sha256.New, []byte(s.cfg.JWTSecret))
	mac.Write(payload)
	if !hmac.Equal(mac.Sum(nil), signature) {
		return 0, ErrCredentials
	}
	var values []any
	if json.Unmarshal(payload, &values) != nil || len(values) != 4 {
		return 0, ErrCredentials
	}
	rev, ok := values[2].(float64)
	offset, good := values[3].(float64)
	if !ok || !good || values[0] != owner || values[1] != root || rev != float64(revision) || offset < 0 || offset > 20 || offset != float64(int(offset)) {
		return 0, ErrConflict
	}
	return int(offset), nil
}
