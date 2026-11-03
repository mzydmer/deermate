package controlplane

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func agentBody(t *testing.T, value any) string {
	t.Helper()
	raw, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	return string(raw)
}
func TestAgentAuthorizationConfirmationExpiryAndOwnership(t *testing.T) {
	store := testStore(t)
	owner := account(t, store, "agent-owner@example.com", "admin")
	other := account(t, store, "agent-other@example.com", "admin")
	b := session(t, store, owner)
	server := testServer(t, store, func(w http.ResponseWriter, r *http.Request) { w.Write([]byte(`{}`)) })
	pair := request(server, b, "POST", "/api/device-pairings", "{}", nil)
	requireStatus(t, pair, 201)
	var pairing map[string]any
	json.Unmarshal(pair.Body.Bytes(), &pairing)
	token := strings.Repeat("t", 43)
	device := agentDevice{ID: uuid(), Name: "Fixture Mac", Instance: strings.Repeat("a", 32), Projects: []string{"demo"}}
	claim := map[string]any{"pairing_id": pairing["pairing_id"], "code": pairing["code"], "device_token": token, "device": device}
	requireStatus(t, request(server, browser{}, "POST", "/api/agent-devices/pair", agentBody(t, claim), nil), 201)
	claim["device_token"] = strings.Repeat("z", 43)
	requireStatus(t, request(server, browser{}, "POST", "/api/agent-devices/pair", agentBody(t, claim), nil), 409)
	headers := map[string]string{"Authorization": "Bearer " + token}
	expires := time.Now().Add(time.Hour).Unix()
	policy := agentPolicy{Projects: []string{"demo"}, Operations: []string{"submit", "status", "continue", "cancel"}, Duration: "fixed", ExpiresAt: &expires, ExpiryPolicy: "finish"}
	create := request(server, b, "POST", "/api/agent-authorizations", agentBody(t, map[string]any{"device_id": device.ID, "name": "Codex", "policy": policy}), nil)
	requireStatus(t, create, 201)
	var g agentGrant
	json.Unmarshal(create.Body.Bytes(), &g)
	if g.Active != nil || g.Pending == nil || grantState(g, time.Now().Unix()) != "pending" {
		t.Fatal("request granted access before local confirmation")
	}
	requireStatus(t, request(server, session(t, store, other), "POST", "/api/agent-authorizations/"+g.ID+"/revocations", `{"expected_version":0}`, nil), 404)
	wrong := policy
	wrong.Projects = []string{"private"}
	requireStatus(t, request(server, browser{}, "POST", "/api/agent-devices/confirm", agentBody(t, map[string]any{"grant_id": g.ID, "version": 1, "policy": wrong}), headers), 409)
	requireStatus(t, request(server, browser{}, "POST", "/api/agent-devices/confirm", agentBody(t, map[string]any{"grant_id": g.ID, "version": 1, "policy": policy}), headers), 200)
	g, _ = server.agentGrant(g.ID, owner.ID)
	if grantState(g, time.Now().Unix()) != "expiring" || g.Version != 1 {
		t.Fatal("confirmed policy not activated")
	}
	later := expires + 86400
	renew := policy
	renew.ExpiresAt = &later
	requireStatus(t, request(server, b, "POST", "/api/agent-authorizations/"+g.ID+"/changes", agentBody(t, map[string]any{"expected_version": 1, "policy": renew}), nil), 202)
	g, _ = server.agentGrant(g.ID, owner.ID)
	if *g.Active.ExpiresAt != expires || g.Pending == nil {
		t.Fatal("pending renewal changed effective deadline")
	}
	requireStatus(t, request(server, b, "POST", "/api/agent-authorizations/"+g.ID+"/revocations", `{"expected_version":0}`, nil), 409)
	requireStatus(t, request(server, b, "POST", "/api/agent-authorizations/"+g.ID+"/revocations", `{"expected_version":1}`, nil), 202)
	requireStatus(t, request(server, browser{}, "POST", "/api/agent-devices/confirm", agentBody(t, map[string]any{"grant_id": g.ID, "version": 2, "policy": renew}), headers), 409)
	check := request(server, b, "POST", "/api/agent-authorizations/"+g.ID+"/checks", "{}", nil)
	requireStatus(t, check, 200)
	if !strings.Contains(check.Body.String(), "grant_revoked") {
		t.Fatal("revocation reason obscured")
	}
	requireStatus(t, request(server, browser{}, "POST", "/api/agent-devices/confirm", agentBody(t, map[string]any{"grant_id": g.ID, "version": 1, "revoked": true}), headers), 200)
	requireStatus(t, request(server, browser{}, "POST", "/api/agent-relay/"+g.ID+"/requests", `{"method":"POST","path":"/tasks"}`, map[string]string{"Authorization": "Bearer " + server.bridgeSecret(g.ID, 1)}), 403)
	if grantState(agentGrant{Active: &agentPolicy{ExpiresAt: &expires}}, expires) != "expired" {
		t.Fatal("expiry boundary")
	}
}
func TestAgentRelayScopeAndDeliveryOnce(t *testing.T) {
	store := testStore(t)
	owner := account(t, store, "relay-owner@example.com", "admin")
	server := testServer(t, store, func(w http.ResponseWriter, r *http.Request) {})
	d := agentDevice{ID: uuid(), Name: "fixture", Owner: owner.ID, Instance: strings.Repeat("a", 32), Projects: []string{"demo"}, LastSeen: time.Now().Unix(), Worker: "reachable"}
	raw, _ := json.Marshal(d)
	token := strings.Repeat("k", 43)
	store.DB.Exec("INSERT INTO deermate_agent_devices VALUES(?,?,?,?)", d.ID, owner.ID, digest(token), string(raw))
	g := agentGrant{ID: uuid(), Owner: owner.ID, Device: d.ID, Instance: d.Instance, Version: 1, Active: &agentPolicy{Projects: []string{"demo"}, Operations: []string{"status"}, Duration: "until_revoked", ExpiryPolicy: "stop"}}
	tx, _ := store.DB.Begin()
	if err := server.agentSave(tx, g, "fixture"); err != nil {
		t.Fatal(err)
	}
	tx.Commit()
	bridgeHeader := map[string]string{"Authorization": "Bearer " + server.bridgeSecret(g.ID, 1)}
	for _, body := range []string{`{"method":"POST","path":"/tasks","body":{"project_id":"demo"}}`, `{"method":"GET","path":"http://169.254.169.254/"}`, `{"method":"GET","path":"/tasks"}`} {
		requireStatus(t, request(server, browser{}, "POST", "/api/agent-relay/"+g.ID+"/requests", body, bridgeHeader), 403)
	}
	job := relayRequest{ID: uuid(), Grant: g.ID, Version: 1, Method: "GET", Path: "/capabilities", Deadline: time.Now().Add(time.Minute).Unix()}
	data, _ := json.Marshal(job)
	store.DB.Exec("INSERT INTO deermate_agent_requests VALUES(?,?,?,?,'queued',?,NULL,NULL)", job.ID, g.ID, d.ID, string(data), job.Deadline)
	dh := map[string]string{"Authorization": "Bearer " + token}
	first := request(server, browser{}, "POST", "/api/agent-devices/poll", `{"worker_status":"reachable"}`, dh)
	requireStatus(t, first, 200)
	if !strings.Contains(first.Body.String(), job.ID) {
		t.Fatal("job not delivered")
	}
	second := request(server, browser{}, "POST", "/api/agent-devices/poll", `{"worker_status":"reachable"}`, dh)
	requireStatus(t, second, 200)
	if strings.Contains(second.Body.String(), job.ID) {
		t.Fatal("sent job replayed")
	}
	result := agentBody(t, map[string]any{"request_id": job.ID, "status": 200, "body": map[string]bool{"ok": true}})
	requireStatus(t, request(server, browser{}, "POST", "/api/agent-devices/results", result, dh), 200)
	requireStatus(t, request(server, browser{}, "POST", "/api/agent-devices/results", result, dh), 409)
	inventory := request(server, session(t, store, owner), "GET", "/api/agent-authorizations", "", nil)
	requireStatus(t, inventory, 200)
	if strings.Contains(inventory.Body.String(), token) || strings.Contains(inventory.Body.String(), server.bridgeSecret(g.ID, 1)) {
		t.Fatal("credential in browser projection")
	}
	requireStatus(t, request(server, browser{}, "GET", "/admin/agents", "", nil), 401)
	member := account(t, store, "agent-member@example.com", "user")
	requireStatus(t, request(server, session(t, store, member), "GET", "/api/agent-authorizations", "", nil), 403)
	csrf := httptest.NewRequest("POST", "http://example.test/api/device-pairings", strings.NewReader("{}"))
	response := httptest.NewRecorder()
	server.ServeHTTP(response, csrf)
	requireStatus(t, response, 401)
}
