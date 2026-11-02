package controlplane

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"testing"
	"time"
)

func captureTables(t *testing.T, s *Store) {
	t.Helper()
	_, err := s.DB.Exec(`CREATE TABLE IF NOT EXISTS threads_meta(thread_id TEXT PRIMARY KEY,user_id TEXT,incarnation TEXT,project_id TEXT);
CREATE TABLE IF NOT EXISTS runs(run_id TEXT PRIMARY KEY,thread_id TEXT,user_id TEXT,evidence_origin TEXT,origin_kind TEXT,operation_kind TEXT,kwargs_json TEXT,created_at TEXT,metadata_json TEXT DEFAULT '{}');`)
	if err != nil {
		t.Fatal(err)
	}
}

func captureFixture(t *testing.T, s *Store, u User, nonce, text string) memoryCapture {
	t.Helper()
	captureTables(t, s)
	p, err := s.PersonalProfile(u.ID)
	if err != nil {
		t.Fatal(err)
	}
	p.MemoryEnabled = true
	p.AutoCaptureEnabled = true
	p, err = s.UpdatePersonalProfile(context.Background(), p, p.Revision)
	if err != nil {
		t.Fatal(err)
	}
	c := memoryCapture{Owner: u.ID, Thread: "thread-" + nonce, Run: "run-" + nonce, Message: "message-" + nonce, Hash: digest(text), Policy: p.PolicyRevision, Deleted: p.DeletionRevision, Observed: time.Now().Unix()}
	c.Content, c.Category, _ = explicitMemory(text)
	input, _ := json.Marshal(map[string]any{"input": map[string]any{"messages": []any{map[string]any{"type": "human", "id": c.Message, "content": text}}}})
	if _, err = s.DB.Exec("INSERT INTO threads_meta(thread_id,user_id,incarnation) VALUES(?,?,'generation-one')", c.Thread, u.ID); err != nil {
		t.Fatal(err)
	}
	if _, err = s.DB.Exec("INSERT INTO runs(run_id,thread_id,user_id,evidence_origin,origin_kind,operation_kind,kwargs_json,created_at) VALUES(?,?,?,'interactive',NULL,'run',?,?)", c.Run, c.Thread, u.ID, string(input), time.Now().UTC().Format("2006-01-02 15:04:05.999999")); err != nil {
		t.Fatal(err)
	}
	return c
}

func admitCapture(t *testing.T, s *Store, c memoryCapture) MemoryOperation {
	t.Helper()
	op, err := s.admitMemory(context.Background(), c.Owner, "create", "", memoryMutation{OperationID: "fixture-" + c.Message, Content: c.Content, Category: c.Category}, &c)
	if err != nil {
		t.Fatal(err)
	}
	return op
}

func TestExplicitMemoryOnlyAdmitsDirectPersonalRequests(t *testing.T) {
	for _, text := range []string{"请记住：我偏好简洁的中文回答。", "记住：我的长期目标是学会日语。", "Remember: I prefer concise answers.", "Remember that I am learning Japanese."} {
		if _, _, ok := explicitMemory(text); !ok {
			t.Errorf("expected explicit personal request: %s", text)
		}
	}
	for _, text := range []string{"帮我查一下千问", "我喜欢简洁回答", "请记住：这个项目改成 Go。", "请记住：我喜欢的密码是 sk-fixture-secret", "请记住：我喜欢中文吗？", "请记住：我喜欢\n这段引用", "Remember: I prefer this repository.", "请记住：我的名字是小林。", "请记住：我喜欢中文，改为英文。"} {
		if _, _, ok := explicitMemory(text); ok {
			t.Errorf("unexpected capture: %s", text)
		}
	}
}

func TestCapturedMemoryHasAtomicSourceAndIdempotentOriginalIntent(t *testing.T) {
	s := testStore(t)
	u := account(t, s, "capture@example.com", "admin")
	c := captureFixture(t, s, u, "one", "请记住：我偏好简洁的中文回答。")
	op := admitCapture(t, s, c)
	if duplicate := admitCapture(t, s, c); duplicate.ID != op.ID {
		t.Fatal("same message created another operation")
	}
	source, err := captureSource(s.DB, op.ID)
	if err != nil || source.Incarnation != "generation-one" || !verifyCapture(s.DB, source) {
		t.Fatal(source, err)
	}
	if _, err = s.AdmitMemory(context.Background(), u.ID, "delete", op.FactID, memoryMutation{OperationID: "forget-capture"}); err != nil {
		t.Fatal(err)
	}
	if duplicate := admitCapture(t, s, c); duplicate.Status != "invalidated" {
		t.Fatal("forgotten old message revived", duplicate)
	}
	var n int
	s.DB.QueryRow("SELECT count(*) FROM deermate_memory_sources").Scan(&n)
	if n != 1 {
		t.Fatal(n)
	}
}

func TestCaptureRefusesUntrustedOriginOwnershipProjectAndHistoricalReplay(t *testing.T) {
	for _, variant := range []string{"owner", "origin", "project", "message", "incarnation", "old-run", "no-consent"} {
		t.Run(variant, func(t *testing.T) {
			s := testStore(t)
			u := account(t, s, "capture@example.com", "admin")
			c := captureFixture(t, s, u, "one", "请记住：我偏好简洁的中文回答。")
			switch variant {
			case "owner":
				s.DB.Exec("UPDATE runs SET user_id='other'")
			case "origin":
				s.DB.Exec("UPDATE runs SET origin_kind='mcp_notification'")
			case "project":
				s.DB.Exec("UPDATE threads_meta SET project_id='project-one'")
			case "message":
				c.Hash = digest("another body")
			case "incarnation":
				s.DB.Exec("UPDATE threads_meta SET incarnation=NULL")
			case "old-run":
				s.DB.Exec("UPDATE runs SET created_at='2020-01-01 00:00:00'")
			case "no-consent":
				s.DB.Exec("UPDATE deermate_personal_profiles SET auto_capture_enabled=0")
			}
			_, err := s.admitMemory(context.Background(), u.ID, "create", "", memoryMutation{OperationID: "refused", Content: c.Content, Category: c.Category}, &c)
			if err == nil {
				t.Fatal("unqualified source admitted")
			}
			var count int
			s.DB.QueryRow("SELECT count(*) FROM deermate_memory_operations").Scan(&count)
			if count != 0 {
				t.Fatal("partial admission", count)
			}
		})
	}
}

func TestCaptureCorrectionAndSourceDeletionFenceLateWrites(t *testing.T) {
	s := testStore(t)
	u := account(t, s, "capture@example.com", "admin")
	c := captureFixture(t, s, u, "one", "请记住：我偏好简洁的中文回答。")
	op := admitCapture(t, s, c)
	claimed, err := s.claimMemory(context.Background(), u.ID, op.ID)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = s.DB.Exec("DELETE FROM runs WHERE run_id=?", c.Run); err != nil {
		t.Fatal(err)
	}
	if err = s.finishMemory(context.Background(), claimed, 1, "preference", nil); err != nil {
		t.Fatal(err)
	}
	op, _ = s.MemoryOperation(u.ID, op.ID)
	if op.Status != "invalidated" || op.Payload != "" {
		t.Fatal("late source commit survived", op)
	}
	c = captureFixture(t, s, u, "two", "请记住：我偏好中文短句回答。")
	late := admitCapture(t, s, c)
	manual, err := s.AdmitMemory(context.Background(), u.ID, "create", "", memoryMutation{OperationID: "manual", Content: "我偏好详细回答", Category: "preference"})
	if err != nil {
		t.Fatal(err)
	}
	manual, err = s.claimMemory(context.Background(), u.ID, manual.ID)
	if err != nil {
		t.Fatal(err)
	}
	if err = s.finishMemory(context.Background(), manual, 1, "preference", nil); err != nil {
		t.Fatal(err)
	}
	if _, err = s.AdmitMemory(context.Background(), u.ID, "update", manual.FactID, memoryMutation{OperationID: "correct-manual", Content: "我偏好简短回答", Category: "preference", ExpectedRevision: 1}); err != nil {
		t.Fatal(err)
	}
	late, _ = s.MemoryOperation(u.ID, late.ID)
	if late.Status != "invalidated" || late.Payload != "" {
		t.Fatal("correction did not stop late capture", late)
	}
}

func TestCaptureProxyPreservesSubmissionAndDoesNotCaptureQuotedOrOversizedRuns(t *testing.T) {
	s := testStore(t)
	u := account(t, s, "capture@example.com", "admin")
	c := captureFixture(t, s, u, "one", "请记住：我偏好简洁的中文回答。")
	var submitted string
	server := testServer(t, s, func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		submitted = string(body)
		w.Header().Set("Content-Location", "/api/threads/"+c.Thread+"/runs/"+c.Run)
		w.Header().Set("Content-Type", "text/event-stream")
		fmt.Fprint(w, "event: end\ndata: {}\n\n")
	})
	b := session(t, s, u)
	body := fmt.Sprintf(`{"input":{"messages":[{"type":"human","id":%q,"content":%q}]}}`, c.Message, "请记住：我偏好简洁的中文回答。")
	w := request(server, b, "POST", "/api/threads/"+c.Thread+"/runs/stream", body, nil)
	requireStatus(t, w, 200)
	if submitted != body || w.Header().Get("X-Deermate-Memory-Status") != "queued" || !strings.Contains(w.Body.String(), "event: end") {
		t.Fatal("proxy changed chat or did not admit capture", w.Header())
	}
	quoted := strings.Replace(body, `"content":`, `"additional_kwargs":{"quote":"outside text"},"content":`, 1)
	w = request(server, b, "POST", "/api/threads/"+c.Thread+"/runs/stream", quoted, nil)
	requireStatus(t, w, 200)
	if submitted != quoted || w.Header().Get("X-Deermate-Memory-Status") != "" {
		t.Fatal("quoted source captured")
	}
	large := `{"input":` + strings.Repeat(" ", 70<<10) + `{}}`
	w = request(server, b, "POST", "/api/threads/"+c.Thread+"/runs/stream", large, nil)
	requireStatus(t, w, 200)
	if submitted != large {
		t.Fatal("bounded inspection truncated the forwarded body")
	}
}

func TestMemoryCaptureMigrationPreservesExistingPersonalData(t *testing.T) {
	s := testStore(t)
	u := account(t, s, "migration-memory@example.com", "user")
	before := enableMemory(t, s, u)
	op, err := s.AdmitMemory(context.Background(), u.ID, "create", "", memoryMutation{OperationID: "before-upgrade", Content: "已有个人背景", Category: "context"})
	if err != nil {
		t.Fatal(err)
	}
	if _, err = s.DB.Exec("ALTER TABLE deermate_personal_profiles DROP COLUMN auto_capture_enabled"); err != nil {
		t.Fatal(err)
	}
	if err = s.initializeMemory(); err != nil {
		t.Fatal(err)
	}
	after, err := s.PersonalProfile(u.ID)
	if err != nil || after.AutoCaptureEnabled || !after.MemoryEnabled || after.DisplayName != before.DisplayName || after.Revision != before.Revision {
		t.Fatal("migration changed existing profile", after, err)
	}
	if old, err := s.MemoryOperation(u.ID, op.ID); err != nil || old.ID != op.ID || old.Status != "pending" {
		t.Fatal("migration lost an existing fact", old, err)
	}
}

func TestMemoryCaptureDailyBudgetsAreAtomicAndGlobal(t *testing.T) {
	s := testStore(t)
	u := account(t, s, "budget-memory@example.com", "user")
	c := captureFixture(t, s, u, "first", "请记住：我偏好简洁的中文回答。")
	original := admitCapture(t, s, c)
	seed := func(count int, owner string) {
		tx, err := s.DB.Begin()
		if err != nil {
			t.Fatal(err)
		}
		defer tx.Rollback()
		for i := 0; i < count; i++ {
			id := fmt.Sprintf("budget-%s-%d", owner, i)
			if _, err = tx.Exec(`INSERT INTO deermate_memory_operations(id,owner,fact_id,kind,status,policy_revision,deletion_revision,request_hash,payload,created_at)
VALUES(?,?,?,'create','completed',1,0,'fixture','',?)`, id, owner, original.FactID, time.Now().Unix()); err != nil {
				t.Fatal(err)
			}
			if _, err = tx.Exec(`INSERT INTO deermate_memory_sources VALUES(?,?,? ,? ,? ,? ,'generation-one',1,0,?,?,0)`, id, owner, c.Thread, c.Run, c.Message, c.Hash, time.Now().Unix(), time.Now().Unix()); err != nil {
				t.Fatal(err)
			}
		}
		if err = tx.Commit(); err != nil {
			t.Fatal(err)
		}
	}
	seed(49, u.ID)
	second := captureFixture(t, s, u, "over-owner", "请记住：我喜欢中文短句回答。")
	if _, err := s.admitMemory(context.Background(), u.ID, "create", "", memoryMutation{OperationID: "over-owner", Content: second.Content, Category: second.Category}, &second); err == nil {
		t.Fatal("owner quota bypassed")
	}
	other := account(t, s, "other-budget@example.com", "user")
	seed(450, other.ID)
	third := account(t, s, "third-budget@example.com", "user")
	thirdSource := captureFixture(t, s, third, "over-instance", "请记住：我喜欢英文短句回答。")
	if _, err := s.admitMemory(context.Background(), third.ID, "create", "", memoryMutation{OperationID: "over-instance", Content: thirdSource.Content, Category: thirdSource.Category}, &thirdSource); err == nil {
		t.Fatal("instance quota bypassed")
	}
	var count int
	s.DB.QueryRow("SELECT count(*) FROM deermate_memory_sources").Scan(&count)
	if count != 500 {
		t.Fatal("quota failure partially inserted", count)
	}
}

func TestEditedSourceStaysRevokedAfterEditRecordIsRemoved(t *testing.T) {
	s := testStore(t)
	u := account(t, s, "edited-source@example.com", "user")
	c := captureFixture(t, s, u, "source", "请记住：我偏好简洁的中文回答。")
	op := admitCapture(t, s, c)
	claimed, err := s.claimMemory(context.Background(), u.ID, op.ID)
	if err != nil {
		t.Fatal(err)
	}
	if err = s.finishMemory(context.Background(), claimed, 1, "preference", nil); err != nil {
		t.Fatal(err)
	}
	metadata, _ := json.Marshal(map[string]any{"replay_kind": "edit", "regenerate_from_run_id": c.Run})
	if _, err = s.DB.Exec(`INSERT INTO runs(run_id,thread_id,user_id,kwargs_json,metadata_json) VALUES('edit-run',?,?,'{}',?)`, c.Thread, u.ID, string(metadata)); err != nil {
		t.Fatal(err)
	}
	refs, err := s.MemoryReferences(u.ID)
	if err != nil || len(refs) != 1 || refs[0].Status != "source_unavailable" {
		t.Fatal(refs, err)
	}
	if _, err = s.DB.Exec("DELETE FROM runs WHERE run_id='edit-run'"); err != nil {
		t.Fatal(err)
	}
	refs, err = s.MemoryReferences(u.ID)
	if err != nil || refs[0].Status != "source_unavailable" {
		t.Fatal("old source revived after edit cleanup", refs, err)
	}
	source, err := captureSource(s.DB, op.ID)
	if err != nil || source.Invalidated == 0 {
		t.Fatal(source, err)
	}
}
