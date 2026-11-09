package controlplane

import (
	"encoding/json"
	"net/http"
	"testing"
	"time"
)

func TestWorkspaceSnapshotUsesOwnedEvidenceWithoutRuntimeCalls(t *testing.T) {
	s := testStore(t)
	u := account(t, s, "snapshot@example.com", "admin")
	other := account(t, s, "snapshot-other@example.com", "admin")
	for _, id := range []string{"needs-reply", "recent-result", "temporary-private"} {
		briefingFixture(t, s, u, id)
	}
	now := time.Now().UTC().Format(time.RFC3339)
	for _, input := range []struct{ id, status string }{{"needs-reply", "input_required"}, {"recent-result", "completed"}, {"temporary-private", "completed"}} {
		_, err := s.DB.Exec("INSERT INTO runs(run_id,thread_id,user_id,status,evidence_origin,created_at,updated_at) VALUES(?,?,?,?,'interactive',?,?)", "run-"+input.id, input.id, u.ID, input.status, now, now)
		if err != nil {
			t.Fatal(err)
		}
	}
	_, _ = s.DB.Exec("INSERT INTO deermate_topic_memory(owner,thread_id,mode) VALUES(?,'temporary-private','temporary')", u.ID)
	server := testServer(t, s, func(http.ResponseWriter, *http.Request) { t.Error("home read invoked runtime/provider") })
	browser := session(t, s, u)
	header := map[string]string{"X-Expected-User-Id": u.ID}
	read := func() []workspaceFocus {
		t.Helper()
		response := request(server, browser, "GET", "/api/me/workspace-snapshot", "", header)
		requireStatus(t, response, 200)
		var out struct {
			Items []workspaceFocus `json:"items"`
		}
		if json.Unmarshal(response.Body.Bytes(), &out) != nil {
			t.Fatal("invalid snapshot")
		}
		return out.Items
	}
	items := read()
	if len(items) != 2 || items[0].Thread != "needs-reply" {
		t.Fatal(items)
	}
	for range 3 {
		if again := read(); len(again) != 2 {
			t.Fatal(again)
		}
	}
	payload, _ := json.Marshal(map[string]string{"id": items[0].ID, "version": items[0].Evidence.Version, "action": "snooze_today"})
	requireStatus(t, request(server, browser, "POST", "/api/me/workspace-feedback", string(payload), header), 200)
	if items = read(); len(items) != 1 || items[0].Thread != "recent-result" {
		t.Fatal("feedback not persistent", items)
	}
	rows, err := server.workspaceFocusItems(other.ID, time.Now())
	if err != nil || len(rows) != 0 {
		t.Fatal("cross owner snapshot", rows, err)
	}
	var models, jobs int
	_ = s.DB.QueryRow("SELECT count(*) FROM deermate_memory_jobs").Scan(&jobs)
	_ = s.DB.QueryRow("SELECT coalesce(sum(used),0) FROM deermate_memory_model_budget").Scan(&models)
	if models != 0 || jobs != 0 {
		t.Fatal("refresh scheduled extraction", models, jobs)
	}
	_, _ = s.DB.Exec("UPDATE threads_meta SET project_id='foreign' WHERE thread_id='recent-result'")
	if items = read(); len(items) != 0 {
		t.Fatal("revoked source visible", items)
	}
}
