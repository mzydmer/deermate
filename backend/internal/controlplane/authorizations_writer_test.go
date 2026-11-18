package controlplane

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestAuthorizationWritesWaitForSharedWriter(t *testing.T) {
	for _, phase := range []string{"create", "confirm", "change", "cancel", "revoke"} {
		t.Run(phase, func(t *testing.T) {
			store := testStore(t)
			owner := account(t, store, "grant-lock@example.com", "admin")
			server := testServer(t, store, func(http.ResponseWriter, *http.Request) {
				t.Error("database-only authorization called the runtime")
			})
			browser := session(t, store, owner)
			device := agentDevice{ID: uuid(), Owner: owner.ID, Name: "Synthetic", Instance: strings.Repeat("a", 32), Projects: []string{"demo"}}
			token := strings.Repeat("t", 43)
			encoded, _ := json.Marshal(device)
			if _, err := store.DB.Exec("INSERT INTO deermate_agent_devices VALUES(?,?,?,?)", device.ID, owner.ID, digest(token), string(encoded)); err != nil {
				t.Fatal(err)
			}
			expires := time.Now().Add(time.Hour).Unix()
			policy := agentPolicy{Projects: []string{"demo"}, Operations: []string{"status"}, Duration: "fixed", ExpiresAt: &expires, ExpiryPolicy: "stop"}
			grant := agentGrant{ID: uuid(), Owner: owner.ID, Device: device.ID, Instance: device.Instance, Name: "Synthetic", Active: &policy, Version: 1}
			path, status := "/api/agent-authorizations", 201
			body := map[string]any{"device_id": device.ID, "name": "Synthetic", "policy": policy}
			headers := map[string]string{}
			switch phase {
			case "confirm":
				grant.Active, grant.Version, grant.Pending, grant.PendingVersion = nil, 0, &policy, 1
				path, status = "/api/agent-devices/confirm", 200
				body = map[string]any{"grant_id": grant.ID, "version": 1, "policy": policy}
				headers["Authorization"] = "Bearer " + token
			case "change":
				path, status = path+"/"+grant.ID+"/changes", 202
				body = map[string]any{"expected_version": 1, "policy": policy}
			case "cancel":
				grant.Pending, grant.PendingVersion = &policy, 2
				path, status = path+"/"+grant.ID+"/changes/cancel", 200
				body = map[string]any{"pending_version": 2}
			case "revoke":
				path, status = path+"/"+grant.ID+"/revocations", 202
				body = map[string]any{"expected_version": 1}
			}
			if phase != "create" {
				encoded, _ := json.Marshal(grant)
				if _, err := store.DB.Exec("INSERT INTO deermate_agent_grants VALUES(?,?,?,?)", grant.ID, owner.ID, device.ID, string(encoded)); err != nil {
					t.Fatal(err)
				}
			}
			_, writer := competingWorkWriter(t, store)
			done := make(chan *httptest.ResponseRecorder, 1)
			requestBody := agentBody(t, body)
			go func() { done <- request(server, browser, "POST", path, requestBody, headers) }()
			select {
			case result := <-done:
				writer.Rollback()
				t.Fatalf("authorization returned before writer release: HTTP %d", result.Code)
			case <-time.After(100 * time.Millisecond):
			}
			if err := writer.Commit(); err != nil {
				t.Fatal(err)
			}
			select {
			case result := <-done:
				requireStatus(t, result, status)
			case <-time.After(6 * time.Second):
				t.Fatal("authorization exceeded the existing busy bound")
			}
			grants, err := server.agentGrants(owner.ID)
			if err != nil || len(grants) != 1 {
				t.Fatalf("authorization duplicated or disappeared: %d %v", len(grants), err)
			}
			if phase == "create" && (grants[0].Active != nil || grants[0].Pending == nil) {
				t.Fatal("creation bypassed local confirmation")
			}
			if phase == "revoke" && !grants[0].Revoked {
				t.Fatal("revocation did not take effect")
			}
		})
	}
}
