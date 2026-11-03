package controlplane

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"crypto/subtle"
	"database/sql"
	_ "embed"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"slices"
	"strings"
	"time"
)

//go:embed authorizations.html
var authorizationsHTML []byte

var agentName = regexp.MustCompile(`^[a-zA-Z0-9_-]{1,80}$`)
var nativeTaskPath = regexp.MustCompile(`^/tasks/[0-9a-f]{32}(/(cancel|continue))?$`)

type agentPolicy struct {
	Projects     []string `json:"projects"`
	Operations   []string `json:"operations"`
	Duration     string   `json:"duration"`
	ExpiresAt    *int64   `json:"expires_at"`
	ExpiryPolicy string   `json:"expiry_policy"`
}
type agentGrant struct {
	ID             string       `json:"id"`
	Owner          string       `json:"owner_id"`
	Device         string       `json:"device_id"`
	Name           string       `json:"name"`
	Instance       string       `json:"instance_id"`
	Version        int          `json:"version"`
	Active         *agentPolicy `json:"active"`
	Pending        *agentPolicy `json:"pending"`
	PendingVersion int          `json:"pending_version"`
	Revoked        bool         `json:"revoked"`
	Cleanup        bool         `json:"device_confirmed"`
	Updated        int64        `json:"updated_at"`
}
type agentDevice struct {
	ID       string   `json:"id"`
	Name     string   `json:"name"`
	Owner    string   `json:"owner_id"`
	Instance string   `json:"instance_id"`
	Projects []string `json:"projects"`
	LastSeen int64    `json:"last_seen_at"`
	Worker   string   `json:"worker_status"`
}
type relayRequest struct {
	ID       string          `json:"id"`
	Grant    string          `json:"grant_id"`
	Version  int             `json:"version"`
	Method   string          `json:"method"`
	Path     string          `json:"path"`
	Body     json.RawMessage `json:"body"`
	Deadline int64           `json:"deadline"`
}

func (s *Server) initAuthorizations() error {
	_, err := s.Store.DB.Exec(`CREATE TABLE IF NOT EXISTS deermate_agent_devices(id TEXT PRIMARY KEY,owner TEXT NOT NULL,token_hash TEXT NOT NULL UNIQUE,data TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS deermate_agent_pairs(id TEXT PRIMARY KEY,owner TEXT NOT NULL,secret_hash TEXT NOT NULL,expires INTEGER NOT NULL,device TEXT);
 CREATE TABLE IF NOT EXISTS deermate_agent_grants(id TEXT PRIMARY KEY,owner TEXT NOT NULL,device TEXT NOT NULL,data TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS deermate_agent_events(id INTEGER PRIMARY KEY AUTOINCREMENT,owner TEXT NOT NULL,grant_id TEXT NOT NULL,action TEXT NOT NULL,created INTEGER NOT NULL);
 CREATE TABLE IF NOT EXISTS deermate_agent_requests(id TEXT PRIMARY KEY,grant_id TEXT NOT NULL,device TEXT NOT NULL,data TEXT NOT NULL,state TEXT NOT NULL,deadline INTEGER NOT NULL,response TEXT,status INTEGER);
 CREATE INDEX IF NOT EXISTS deermate_agent_pending ON deermate_agent_requests(device,state,deadline);`)
	return err
}
func (s *Server) authorizationRoutes() {
	s.mux.HandleFunc("GET /admin/agents", s.protected(true, func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		w.Header().Set("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
		_, _ = w.Write(bytes.Replace(authorizationsHTML, []byte("/* DEERMATE_DESIGN_TOKENS */"), designTokens, 1))
	}))
	s.mux.HandleFunc("GET /api/agent-authorizations", s.protected(true, s.agentInventory))
	s.mux.HandleFunc("POST /api/device-pairings", s.protected(true, s.agentPairStart))
	s.mux.HandleFunc("POST /api/agent-authorizations", s.protected(true, s.agentCreate))
	s.mux.HandleFunc("POST /api/agent-authorizations/{id}/changes", s.protected(true, s.agentChange))
	s.mux.HandleFunc("POST /api/agent-authorizations/{id}/revocations", s.protected(true, s.agentRevoke))
	s.mux.HandleFunc("POST /api/agent-authorizations/{id}/checks", s.protected(true, s.agentCheck))
	s.mux.HandleFunc("POST /api/agent-devices/pair", s.agentPairClaim)
	s.mux.HandleFunc("POST /api/agent-devices/poll", s.agentPoll)
	s.mux.HandleFunc("POST /api/agent-devices/confirm", s.agentConfirm)
	s.mux.HandleFunc("POST /api/agent-devices/results", s.agentResult)
	s.mux.HandleFunc("POST /api/agent-relay/{id}/requests", s.agentRelay)
}
func grantState(g agentGrant, now int64) string {
	if g.Revoked {
		return "revoked"
	}
	if g.Active == nil {
		return "pending"
	}
	if g.Active.ExpiresAt != nil {
		if *g.Active.ExpiresAt <= now {
			return "expired"
		}
		if *g.Active.ExpiresAt-now <= 86400 {
			return "expiring"
		}
	}
	return "active"
}
func (s *Server) agentGrants(owner string) ([]agentGrant, error) {
	rows, err := s.Store.DB.Query("SELECT data FROM deermate_agent_grants WHERE owner=? ORDER BY rowid DESC LIMIT 128", owner)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []agentGrant{}
	for rows.Next() {
		var data string
		var g agentGrant
		if err = rows.Scan(&data); err != nil {
			return nil, err
		}
		if err = json.Unmarshal([]byte(data), &g); err != nil {
			return nil, err
		}
		out = append(out, g)
	}
	return out, rows.Err()
}
func (s *Server) agentGrant(id, owner string) (agentGrant, error) {
	var data string
	var g agentGrant
	err := s.Store.DB.QueryRow("SELECT data FROM deermate_agent_grants WHERE id=? AND owner=?", id, owner).Scan(&data)
	if errors.Is(err, sql.ErrNoRows) {
		return g, ErrNotFound
	}
	if err != nil {
		return g, err
	}
	err = json.Unmarshal([]byte(data), &g)
	return g, err
}
func (s *Server) agentSave(tx *sql.Tx, g agentGrant, event string) error {
	data, err := json.Marshal(g)
	if err != nil {
		return err
	}
	_, err = tx.Exec("INSERT INTO deermate_agent_grants VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data", g.ID, g.Owner, g.Device, string(data))
	if err != nil {
		return err
	}
	_, err = tx.Exec("INSERT INTO deermate_agent_events(owner,grant_id,action,created) VALUES(?,?,?,?)", g.Owner, g.ID, event, time.Now().Unix())
	return err
}
func (s *Server) agentInventory(w http.ResponseWriter, r *http.Request) {
	owner := sessionOf(r).User.ID
	grants, err := s.agentGrants(owner)
	if err != nil {
		storeError(w, err)
		return
	}
	rows, err := s.Store.DB.Query("SELECT data FROM deermate_agent_devices WHERE owner=? ORDER BY rowid LIMIT 128", owner)
	if err != nil {
		storeError(w, err)
		return
	}
	devices := []agentDevice{}
	for rows.Next() {
		var data string
		var d agentDevice
		if rows.Scan(&data) == nil && json.Unmarshal([]byte(data), &d) == nil {
			devices = append(devices, d)
		}
	}
	err = rows.Err()
	rows.Close()
	if err != nil {
		storeError(w, err)
		return
	}
	events := []map[string]any{}
	rows, err = s.Store.DB.Query("SELECT grant_id,action,created FROM deermate_agent_events WHERE owner=? ORDER BY id DESC LIMIT 50", owner)
	if err != nil {
		storeError(w, err)
		return
	}
	for rows.Next() {
		var id, action string
		var at int64
		if rows.Scan(&id, &action, &at) == nil {
			events = append(events, map[string]any{"grant_id": id, "action": action, "at": at})
		}
	}
	rows.Close()
	views := []map[string]any{}
	for _, g := range grants {
		views = append(views, map[string]any{"grant": g, "status": grantState(g, time.Now().Unix()), "execution_readiness": "not_checked"})
	}
	respond(w, 200, map[string]any{"grants": views, "devices": devices, "events": events, "server_time": time.Now().Unix()})
}
func (s *Server) agentPairStart(w http.ResponseWriter, r *http.Request) {
	// The installed MCP runtime is single-owner; do not share it across admins.
	owner := sessionOf(r).User.ID
	tx, err := s.Store.DB.Begin()
	if err != nil { storeError(w, err); return }
	defer tx.Rollback()
	_, err = tx.Exec("INSERT OR IGNORE INTO deermate_control_meta(key,value) VALUES('agent-owner',?)", owner)
	var enrolledOwner string
	if err == nil { err = tx.QueryRow("SELECT value FROM deermate_control_meta WHERE key='agent-owner'").Scan(&enrolledOwner) }
	if err != nil { storeError(w, err); return }
	if enrolledOwner != owner { fail(w,403,"single_owner_required","This installation's device connector belongs to another owner"); return }
	if err = tx.Commit(); err != nil { storeError(w,err); return }
	id, secret := uuid(), opaque()
	expiry := time.Now().Add(10 * time.Minute).Unix()
	var count int
	s.Store.DB.QueryRow("SELECT count(*) FROM deermate_agent_pairs WHERE owner=? AND expires>?", owner, time.Now().Unix()).Scan(&count)
	if count >= 8 {
		fail(w, 429, "pairing_limit", "Wait for an existing pairing request to expire")
		return
	}
	_, err = s.Store.DB.Exec("INSERT INTO deermate_agent_pairs VALUES(?,?,?,?,NULL)", id, owner, digest(secret), expiry)
	if err != nil {
		storeError(w, err)
		return
	}
	respond(w, 201, map[string]any{"pairing_id": id, "code": secret, "expires_at": expiry, "server": s.cfg.Origin})
}
func (s *Server) agentPairClaim(w http.ResponseWriter, r *http.Request) {
	var b struct {
		Pairing string      `json:"pairing_id"`
		Code    string      `json:"code"`
		Token   string      `json:"device_token"`
		Device  agentDevice `json:"device"`
	}
	if !decode(w, r, &b) {
		return
	}
	d := b.Device
	if len(b.Token) != 43 || len(b.Code) != 43 || len(d.Name) == 0 || len(d.Name) > 80 || len(d.Projects) == 0 || len(d.Projects) > 32 || len(d.Instance) != 32 || len(d.ID) != 36 {
		fail(w, 422, "invalid_device", "Invalid registered device")
		return
	}
	for _, p := range d.Projects {
		if !agentName.MatchString(p) {
			fail(w, 422, "invalid_project", "Invalid project identifier")
			return
		}
	}
	tx, err := s.Store.DB.Begin()
	if err != nil {
		storeError(w, err)
		return
	}
	defer tx.Rollback()
	var owner, hash string
	var expires int64
	var used sql.NullString
	err = tx.QueryRow("SELECT owner,secret_hash,expires,device FROM deermate_agent_pairs WHERE id=?", b.Pairing).Scan(&owner, &hash, &expires, &used)
	if err != nil || subtle.ConstantTimeCompare([]byte(hash), []byte(digest(b.Code))) != 1 || expires <= time.Now().Unix() {
		fail(w, 403, "pairing_expired", "Pairing is invalid or expired")
		return
	}
	if used.Valid {
		var existing string
		err = tx.QueryRow("SELECT token_hash FROM deermate_agent_devices WHERE id=? AND owner=?", d.ID, owner).Scan(&existing)
		if used.String != d.ID || err != nil || existing != digest(b.Token) {
			fail(w, 409, "pairing_consumed", "Pairing was already consumed")
			return
		}
		respond(w, 200, map[string]string{"device_id": d.ID})
		return
	}
	var role string
	var disabled bool
	if tx.QueryRow("SELECT system_role,disabled FROM users WHERE id=?", owner).Scan(&role, &disabled) != nil || role != "admin" || disabled {
		fail(w, 403, "owner_disabled", "Owner is unavailable")
		return
	}
	d.Owner = owner
	d.LastSeen = 0
	d.Worker = "unknown"
	data, _ := json.Marshal(d)
	_, err = tx.Exec("INSERT INTO deermate_agent_devices VALUES(?,?,?,?)", d.ID, owner, digest(b.Token), string(data))
	if err == nil {
		_, err = tx.Exec("UPDATE deermate_agent_pairs SET device=? WHERE id=?", d.ID, b.Pairing)
	}
	if err == nil {
		err = tx.Commit()
	}
	if err != nil {
		storeError(w, err)
		return
	}
	respond(w, 201, map[string]string{"device_id": d.ID})
}
func (s *Server) agentDeviceAuth(w http.ResponseWriter, r *http.Request) (agentDevice, bool) {
	var d agentDevice
	token := strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")
	if len(token) != 43 {
		fail(w, 401, "device_auth", "Device credential required")
		return d, false
	}
	var data string
	err := s.Store.DB.QueryRow("SELECT d.data FROM deermate_agent_devices d JOIN users u ON u.id=d.owner WHERE d.token_hash=? AND u.disabled=0 AND u.system_role='admin'", digest(token)).Scan(&data)
	if err != nil || json.Unmarshal([]byte(data), &d) != nil {
		fail(w, 401, "device_auth", "Device credential rejected")
		return d, false
	}
	return d, true
}
func validateAgentPolicy(p agentPolicy, d agentDevice) bool {
	if len(p.Projects) == 0 || len(p.Projects) > 32 || len(p.Operations) == 0 || len(p.Operations) > 4 || (p.ExpiryPolicy != "finish" && p.ExpiryPolicy != "stop") {
		return false
	}
	for _, v := range p.Projects {
		if !slices.Contains(d.Projects, v) {
			return false
		}
	}
	for _, v := range p.Operations {
		if !slices.Contains([]string{"submit", "status", "continue", "cancel"}, v) {
			return false
		}
	}
	switch p.Duration {
	case "until_revoked":
		return p.ExpiresAt == nil
	case "fixed":
		return p.ExpiresAt != nil && *p.ExpiresAt > time.Now().Unix() && *p.ExpiresAt <= 253402300799
	default:
		return false
	}
}
func (s *Server) agentCreate(w http.ResponseWriter, r *http.Request) {
	var b struct {
		Device string      `json:"device_id"`
		Name   string      `json:"name"`
		Policy agentPolicy `json:"policy"`
	}
	if !decode(w, r, &b) {
		return
	}
	owner := sessionOf(r).User.ID
	var data string
	var d agentDevice
	err := s.Store.DB.QueryRow("SELECT data FROM deermate_agent_devices WHERE id=? AND owner=?", b.Device, owner).Scan(&data)
	if err != nil || json.Unmarshal([]byte(data), &d) != nil {
		storeError(w, ErrNotFound)
		return
	}
	if len(b.Name) == 0 || len(b.Name) > 80 || !validateAgentPolicy(b.Policy, d) {
		fail(w, 422, "invalid_policy", "Choose registered projects, operations, expiry and task policy")
		return
	}
	tx, err := s.Store.DB.Begin()
	if err != nil {
		storeError(w, err)
		return
	}
	defer tx.Rollback()
	var n int
	tx.QueryRow("SELECT count(*) FROM deermate_agent_grants WHERE device=? AND json_extract(data,'$.revoked')=0", b.Device).Scan(&n)
	if n > 0 {
		fail(w, 409, "existing_grant", "Modify or revoke the existing authorization for this device")
		return
	}
	g := agentGrant{ID: uuid(), Owner: owner, Device: d.ID, Name: b.Name, Instance: d.Instance, Pending: &b.Policy, PendingVersion: 1, Updated: time.Now().Unix()}
	err = s.agentSave(tx, g, "authorization.requested")
	if err == nil {
		err = tx.Commit()
	}
	if err != nil {
		storeError(w, err)
		return
	}
	respond(w, 201, g)
}
func (s *Server) agentChange(w http.ResponseWriter, r *http.Request) {
	var b struct {
		Version int         `json:"expected_version"`
		Policy  agentPolicy `json:"policy"`
	}
	if !decode(w, r, &b) {
		return
	}
	owner := sessionOf(r).User.ID
	tx, err := s.Store.DB.Begin()
	if err != nil {
		storeError(w, err)
		return
	}
	defer tx.Rollback()
	var data, deviceData string
	var g agentGrant
	var d agentDevice
	err = tx.QueryRow("SELECT data FROM deermate_agent_grants WHERE id=? AND owner=?", r.PathValue("id"), owner).Scan(&data)
	if err != nil {
		storeError(w, ErrNotFound)
		return
	}
	json.Unmarshal([]byte(data), &g)
	if g.Revoked || g.Version != b.Version || g.Pending != nil {
		fail(w, 409, "version_conflict", "Authorization changed or already has a pending request")
		return
	}
	tx.QueryRow("SELECT data FROM deermate_agent_devices WHERE id=?", g.Device).Scan(&deviceData)
	json.Unmarshal([]byte(deviceData), &d)
	if !validateAgentPolicy(b.Policy, d) {
		fail(w, 422, "invalid_policy", "Check the selected authorization policy")
		return
	}
	g.Pending = &b.Policy
	g.PendingVersion = g.Version + 1
	g.Updated = time.Now().Unix()
	err = s.agentSave(tx, g, "authorization.change_requested")
	if err == nil {
		err = tx.Commit()
	}
	if err != nil {
		storeError(w, err)
		return
	}
	respond(w, 202, g)
}
func (s *Server) agentRevoke(w http.ResponseWriter, r *http.Request) {
	var b struct {
		Version int `json:"expected_version"`
	}
	if !decode(w, r, &b) {
		return
	}
	tx, err := s.Store.DB.Begin()
	if err != nil {
		storeError(w, err)
		return
	}
	defer tx.Rollback()
	var data string
	var g agentGrant
	err = tx.QueryRow("SELECT data FROM deermate_agent_grants WHERE id=? AND owner=?", r.PathValue("id"), sessionOf(r).User.ID).Scan(&data)
	if err != nil {
		storeError(w, ErrNotFound)
		return
	}
	json.Unmarshal([]byte(data), &g)
	if b.Version != g.Version {
		fail(w, 409, "version_conflict", "Reload this authorization")
		return
	}
	g.Revoked = true
	g.Pending = nil
	g.Cleanup = false
	g.Updated = time.Now().Unix()
	err = s.agentSave(tx, g, "authorization.revoked_stop_requested")
	if err == nil {
		err = tx.Commit()
	}
	if err != nil {
		storeError(w, err)
		return
	}
	respond(w, 202, g)
}
func (s *Server) agentPoll(w http.ResponseWriter, r *http.Request) {
	d, ok := s.agentDeviceAuth(w, r)
	if !ok {
		return
	}
	var b struct {
		Worker string `json:"worker_status"`
	}
	if !decode(w, r, &b) {
		return
	}
	if b.Worker != "reachable" && b.Worker != "unavailable" {
		fail(w, 422, "invalid_status", "Unknown worker observation")
		return
	}
	d.LastSeen = time.Now().Unix()
	d.Worker = b.Worker
	data, _ := json.Marshal(d)
	if _, err := s.Store.DB.Exec("UPDATE deermate_agent_devices SET data=? WHERE id=?", string(data), d.ID); err != nil {
		storeError(w, err)
		return
	}
	grants, err := s.agentGrants(d.Owner)
	if err != nil {
		storeError(w, err)
		return
	}
	own := []agentGrant{}
	for _, g := range grants {
		if g.Device == d.ID {
			own = append(own, g)
		}
	}
	// Deliver once. A lost reply leaves outcome unknown; never requeue a mutation.
	tx, err := s.Store.DB.Begin()
	if err != nil {
		storeError(w, err)
		return
	}
	defer tx.Rollback()
	var requestData string
	var job *relayRequest
	err = tx.QueryRow("SELECT data FROM deermate_agent_requests WHERE device=? AND state='queued' AND deadline>? ORDER BY rowid LIMIT 1", d.ID, time.Now().Unix()).Scan(&requestData)
	if err == nil {
		var j relayRequest
		if json.Unmarshal([]byte(requestData), &j) == nil {
			for _, g := range own {
				if g.ID == j.Grant && g.Version == j.Version && (grantState(g, time.Now().Unix()) == "active" || grantState(g, time.Now().Unix()) == "expiring") {
					job = &j
				}
			}
			_, err = tx.Exec("UPDATE deermate_agent_requests SET state='sent' WHERE id=? AND state='queued'", j.ID)
		}
	}
	if err != nil && !errors.Is(err, sql.ErrNoRows) {
		storeError(w, err)
		return
	}
	if err = tx.Commit(); err != nil {
		storeError(w, err)
		return
	}
	_, _ = s.Store.DB.Exec("DELETE FROM deermate_agent_requests WHERE deadline<?", time.Now().Add(-10*time.Minute).Unix())
	respond(w, 200, map[string]any{"grants": own, "request": job, "server_time": time.Now().Unix(), "lease_until": time.Now().Add(90 * time.Second).Unix()})
}
func (s *Server) agentConfirm(w http.ResponseWriter, r *http.Request) {
	d, ok := s.agentDeviceAuth(w, r)
	if !ok {
		return
	}
	var b struct {
		ID      string       `json:"grant_id"`
		Version int          `json:"version"`
		Policy  *agentPolicy `json:"policy"`
		Revoked bool         `json:"revoked"`
	}
	if !decode(w, r, &b) {
		return
	}
	tx, err := s.Store.DB.Begin()
	if err != nil {
		storeError(w, err)
		return
	}
	defer tx.Rollback()
	var data string
	var g agentGrant
	err = tx.QueryRow("SELECT data FROM deermate_agent_grants WHERE id=? AND device=?", b.ID, d.ID).Scan(&data)
	if err != nil {
		storeError(w, ErrNotFound)
		return
	}
	json.Unmarshal([]byte(data), &g)
	event := "authorization.device_confirmed"
	if g.Revoked {
		if !b.Revoked {
			fail(w, 409, "revoked", "Cannot reactivate a revoked authorization")
			return
		}
		g.Cleanup = true
		event = "authorization.device_cleanup_confirmed"
	} else {
		expected, _ := json.Marshal(g.Pending)
		actual, _ := json.Marshal(b.Policy)
		if g.Pending == nil || b.Version != g.PendingVersion || !bytes.Equal(expected, actual) || !validateAgentPolicy(*g.Pending, d) {
			fail(w, 409, "version_conflict", "Local confirmation does not match the current request")
			return
		}
		g.Active = g.Pending
		g.Version = g.PendingVersion
		g.Pending = nil
		g.PendingVersion = 0
		g.Cleanup = true
	}
	g.Updated = time.Now().Unix()
	err = s.agentSave(tx, g, event)
	if err == nil {
		err = tx.Commit()
	}
	if err != nil {
		storeError(w, err)
		return
	}
	if err = s.writeAgentBridge(d.Owner); err != nil {
		fail(w, 503, "configuration_pending", "Authorization saved; runtime configuration could not be written")
		return
	}
	respond(w, 200, g)
}
func (s *Server) bridgeSecret(id string, version int) string {
	m := hmac.New(sha256.New, []byte(s.cfg.JWTSecret))
	fmt.Fprintf(m, "deermate-agent-bridge:%s:%d", id, version)
	return base64.RawURLEncoding.EncodeToString(m.Sum(nil))
}
func (s *Server) writeAgentBridge(owner string) error {
	if s.cfg.AuthorizationHome == "" {
		return nil
	}
	grants, err := s.agentGrants(owner)
	if err != nil {
		return err
	}
	entries := []map[string]any{}
	for _, g := range grants {
		if g.Active != nil && !g.Revoked {
			entries = append(entries, map[string]any{"id": g.ID, "instance_id": g.Instance, "version": g.Version, "projects": g.Active.Projects, "expires_at": g.Active.ExpiresAt, "token": s.bridgeSecret(g.ID, g.Version)})
		}
	}
	if err = os.MkdirAll(s.cfg.AuthorizationHome, 0700); err != nil {
		return err
	}
	info, err := os.Lstat(s.cfg.AuthorizationHome)
	if err != nil || !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
		return fmt.Errorf("unsafe authorization directory")
	}
	data, _ := json.Marshal(map[string]any{"grants": entries, "owner_id": owner})
	f, err := os.CreateTemp(s.cfg.AuthorizationHome, "bridge-*")
	if err != nil {
		return err
	}
	defer os.Remove(f.Name())
	if err = f.Chmod(0600); err == nil {
		_, err = f.Write(data)
	}
	closeErr := f.Close()
	if err == nil {
		err = closeErr
	}
	if err == nil {
		err = os.Rename(f.Name(), filepath.Join(s.cfg.AuthorizationHome, "bridge.json"))
	}
	return err
}
func (s *Server) agentRelay(w http.ResponseWriter, r *http.Request) {
	var data string
	var g agentGrant
	err := s.Store.DB.QueryRow("SELECT g.data FROM deermate_agent_grants g JOIN users u ON u.id=g.owner WHERE g.id=? AND u.disabled=0 AND u.system_role='admin'", r.PathValue("id")).Scan(&data)
	if err != nil || json.Unmarshal([]byte(data), &g) != nil {
		fail(w, 401, "authorization_invalid", "Authorization unavailable")
		return
	}
	token := strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")
	if subtle.ConstantTimeCompare([]byte(token), []byte(s.bridgeSecret(g.ID, g.Version))) != 1 {
		fail(w, 401, "credential_invalid", "Scoped bridge credential rejected")
		return
	}
	state := grantState(g, time.Now().Unix())
	if state != "active" && state != "expiring" {
		fail(w, 403, "grant_"+state, "Authorization is not active")
		return
	}
	var b struct {
		Method string          `json:"method"`
		Path   string          `json:"path"`
		Body   json.RawMessage `json:"body"`
	}
	if !decode(w, r, &b) {
		return
	}
	op := ""
	switch {
	case b.Method == "GET" && b.Path == "/capabilities":
		op = "check"
	case b.Method == "POST" && b.Path == "/tasks":
		op = "submit"
	case nativeTaskPath.MatchString(b.Path) && b.Method == "GET" && !strings.Contains(b.Path[7:], "/"):
		op = "status"
	case nativeTaskPath.MatchString(b.Path) && b.Method == "POST" && strings.HasSuffix(b.Path, "/cancel"):
		op = "cancel"
	case nativeTaskPath.MatchString(b.Path) && b.Method == "POST" && strings.HasSuffix(b.Path, "/continue"):
		op = "continue"
	}
	if op == "" || (op != "check" && !slices.Contains(g.Active.Operations, op)) {
		fail(w, 403, "operation_denied", "Operation is outside this authorization")
		return
	}
	if op == "submit" {
		var body struct {
			Project string `json:"project_id"`
		}
		if json.Unmarshal(b.Body, &body) != nil || !slices.Contains(g.Active.Projects, body.Project) {
			fail(w, 403, "project_denied", "Project is outside this authorization")
			return
		}
	}
	var dd string
	var d agentDevice
	s.Store.DB.QueryRow("SELECT data FROM deermate_agent_devices WHERE id=?", g.Device).Scan(&dd)
	json.Unmarshal([]byte(dd), &d)
	if time.Now().Unix()-d.LastSeen > 90 {
		fail(w, 503, "device_offline", "Device is offline; task outcome is not established")
		return
	}
	var outstanding int
	s.Store.DB.QueryRow("SELECT count(*) FROM deermate_agent_requests WHERE device=? AND state IN ('queued','sent') AND deadline>?", d.ID, time.Now().Unix()).Scan(&outstanding)
	if outstanding >= 8 {
		fail(w, 429, "device_busy", "Too many pending device operations")
		return
	}
	job := relayRequest{ID: uuid(), Grant: g.ID, Version: g.Version, Method: b.Method, Path: b.Path, Body: b.Body, Deadline: time.Now().Add(15 * time.Second).Unix()}
	raw, _ := json.Marshal(job)
	_, err = s.Store.DB.Exec("INSERT INTO deermate_agent_requests VALUES(?,?,?,?,'queued',?,NULL,NULL)", job.ID, g.ID, d.ID, string(raw), job.Deadline)
	if err != nil {
		storeError(w, err)
		return
	}
	ticker := time.NewTicker(100 * time.Millisecond)
	defer ticker.Stop()
	ctx, cancel := context.WithTimeout(r.Context(), 16*time.Second)
	defer cancel()
	for {
		var response sql.NullString
		var status sql.NullInt64
		var current string
		err = s.Store.DB.QueryRow("SELECT state,response,status FROM deermate_agent_requests WHERE id=?", job.ID).Scan(&current, &response, &status)
		if err != nil {
			storeError(w, err)
			return
		}
		if current == "done" {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(int(status.Int64))
			_, _ = w.Write([]byte(response.String))
			_, _ = s.Store.DB.Exec("DELETE FROM deermate_agent_requests WHERE id=?", job.ID)
			return
		}
		select {
		case <-ctx.Done():
			fail(w, 504, "outcome_unknown", "Device operation timed out. Inspect the original task/key; no operation was replayed.")
			return
		case <-ticker.C:
		}
	}
}
func (s *Server) agentResult(w http.ResponseWriter, r *http.Request) {
	d, ok := s.agentDeviceAuth(w, r)
	if !ok {
		return
	}
	var b struct {
		ID     string          `json:"request_id"`
		Status int             `json:"status"`
		Body   json.RawMessage `json:"body"`
	}
	r.Body = http.MaxBytesReader(w, r.Body, 2_100_000)
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	if decoder.Decode(&b) != nil || !json.Valid(b.Body) || len(b.Body) > 2_000_000 || b.Status < 200 || b.Status > 599 {
		fail(w, 422, "invalid_result", "Invalid bounded device result")
		return
	}
	result, err := s.Store.DB.Exec("UPDATE deermate_agent_requests SET state='done',response=?,status=? WHERE id=? AND device=? AND state='sent'", string(b.Body), b.Status, b.ID, d.ID)
	if err != nil {
		storeError(w, err)
		return
	}
	n, _ := result.RowsAffected()
	if n != 1 {
		fail(w, 409, "request_state", "Result is already recorded or request is unavailable")
		return
	}
	respond(w, 200, map[string]bool{"saved": true})
}
func (s *Server) agentCheck(w http.ResponseWriter, r *http.Request) {
	g, err := s.agentGrant(r.PathValue("id"), sessionOf(r).User.ID)
	if err != nil {
		storeError(w, err)
		return
	}
	state := grantState(g, time.Now().Unix())
	var data string
	var d agentDevice
	s.Store.DB.QueryRow("SELECT data FROM deermate_agent_devices WHERE id=?", g.Device).Scan(&data)
	json.Unmarshal([]byte(data), &d)
	reason := "not_checked"
	if state != "active" && state != "expiring" {
		reason = "grant_" + state
	} else if time.Now().Unix()-d.LastSeen > 90 {
		reason = "device_offline"
	} else if d.Worker == "unavailable" {
		reason = "worker_unavailable"
	}
	respond(w, 200, map[string]any{"authorization": state, "connection": reason, "last_seen_at": d.LastSeen, "worker_observation": d.Worker, "execution_readiness": "not_checked", "task_outcome": "not_checked", "checked_at": time.Now().Unix()})
}
