package controlplane

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"sync"
	"testing"
	"time"
)

func preparedHome(t *testing.T) (*Store, User, BriefingIntent) {
	t.Helper()
	s := testStore(t)
	u := account(t, s, "home@example.com", "admin")
	briefingFixture(t, s, u, "thread")
	if _, err := s.DB.Exec(`ALTER TABLE runs ADD COLUMN idempotency_key TEXT; ALTER TABLE mcp_tasks ADD COLUMN tool_call_id TEXT; ALTER TABLE mcp_tasks ADD COLUMN run_id TEXT;`); err != nil {
		t.Fatal(err)
	}
	topic := followTopic(t, s, u, "thread")
	evidence, err := topicEvidence(s.DB, topic, time.Now())
	if err != nil {
		t.Fatal(err)
	}
	i, err := s.saveIntent(context.Background(), u, BriefingIntent{Kind: "followup", Thread: topic.Thread, Topic: topic.ID, TopicRevision: topic.Revision, SourceVersion: evidence.Version, Question: followupQuestion, Context: "{}", Continuation: "{}"}, "same-request")
	if err != nil {
		t.Fatal(err)
	}
	return s, u, i
}

func TestHomeClaimIsOnceAndUnknownOnlyReconciles(t *testing.T) {
	s, u, i := preparedHome(t)
	var wg sync.WaitGroup
	var mu sync.Mutex
	admissions := 0
	for n := 0; n < 12; n++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			_, fresh, err := s.claimIntent(context.Background(), u, i.ID)
			if err != nil {
				t.Error(err)
			}
			if fresh {
				mu.Lock()
				admissions++
				mu.Unlock()
			}
		}()
	}
	wg.Wait()
	if admissions != 1 {
		t.Fatalf("%d admissions", admissions)
	}
	unknown, err := s.inspectIntent(u.ID, i.ID)
	if err != nil || unknown.Status != "uncertain" {
		t.Fatal(unknown, err)
	}
	_, fresh, err := s.claimIntent(context.Background(), u, i.ID)
	if err != nil || fresh {
		t.Fatal("uncertain action replayed", fresh, err)
	}
	key := "http-run:" + digest(u.ID+"\x00thread\x00extension:deermate.briefing:"+i.ID)
	if _, err = s.DB.Exec(`INSERT INTO runs(run_id,thread_id,user_id,status,evidence_origin,origin_kind,idempotency_key) VALUES('late-run','thread',?,'success','interactive','extension',?)`, u.ID, key); err != nil {
		t.Fatal(err)
	}
	result, err := s.inspectIntent(u.ID, i.ID)
	if err != nil || result.Status != "completed" || result.Run != "late-run" {
		t.Fatal(result, err)
	}
	_, fresh, err = s.claimIntent(context.Background(), u, i.ID)
	if err != nil || fresh {
		t.Fatal("completed action replayed", fresh, err)
	}
}

func TestHomePreviewExpiryCanRenewWithoutReplacingOperation(t *testing.T) {
	s, u, i := preparedHome(t)
	s.DB.Exec("UPDATE deermate_briefing_intents SET expires_at=1")
	if _, _, err := s.claimIntent(context.Background(), u, i.ID); !errors.Is(err, ErrConflict) {
		t.Fatal(err)
	}
	renewed, err := s.saveIntent(context.Background(), u, i, "same-request")
	if err != nil || renewed.ID != i.ID || renewed.Token != i.Token || renewed.Expires <= time.Now().Unix() {
		t.Fatal(renewed, err)
	}
	if _, fresh, err := s.claimIntent(context.Background(), u, i.ID); err != nil || !fresh {
		t.Fatal(fresh, err)
	}
	s.DB.Exec("UPDATE deermate_briefing_intents SET expires_at=1,status='uncertain'")
	old, err := s.saveIntent(context.Background(), u, i, "same-request")
	if err != nil || old.Status != "uncertain" || old.Expires != 1 {
		t.Fatal("unknown operation renewed", old, err)
	}
}

func TestHomePreviewRechecksAuthorityAndCanonicalSource(t *testing.T) {
	for _, mutation := range []string{
		`UPDATE users SET token_version=token_version+1`,
		`UPDATE users SET system_role='user'`,
		`UPDATE users SET disabled=1`,
		`UPDATE deermate_attention_topics SET revision=revision+1`,
		`UPDATE deermate_attention_topics SET status='paused'`,
		`UPDATE threads_meta SET incarnation='replacement'`,
		`UPDATE threads_meta SET metadata_json='{"deerflow_archived":true}'`,
	} {
		t.Run(mutation, func(t *testing.T) {
			s, u, i := preparedHome(t)
			if _, err := s.DB.Exec(mutation); err != nil {
				t.Fatal(err)
			}
			if _, _, err := s.claimIntent(context.Background(), u, i.ID); !errors.Is(err, ErrConflict) {
				t.Fatal("revoked preview admitted", err)
			}
		})
	}
}

func TestHomeIntentIsPrivateAndDeletedSourceMasksQuestion(t *testing.T) {
	s, u, i := preparedHome(t)
	other := account(t, s, "other@example.com", "admin")
	if _, err := s.inspectIntent(other.ID, i.ID); !errors.Is(err, ErrNotFound) {
		t.Fatal(err)
	}
	if _, _, err := s.claimIntent(context.Background(), other, i.ID); !errors.Is(err, ErrNotFound) {
		t.Fatal(err)
	}
	s.DB.Exec("DELETE FROM threads_meta")
	result, err := s.inspectIntent(u.ID, i.ID)
	if err != nil || result.Status != "blocked" || result.Question != "" || result.Thread != "" || result.Run != "" || result.Task != "" {
		t.Fatal(result, err)
	}
}

func TestHomePublicAdmissionCannotBypassOwnerCSRFOrRuntimeNamespace(t *testing.T) {
	s, u, i := preparedHome(t)
	ordinary := account(t, s, "reader@example.com", "user")
	server := testServer(t, s, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/models" {
			t.Errorf("unexpected runtime call: %s", r.URL.Path)
		}
		respond(w, 200, map[string]any{"models": []any{}})
	})
	b := session(t, s, u)
	path := "/api/me/briefing/actions/" + i.ID
	requireStatus(t, request(server, browser{}, "POST", path, "{}", nil), 401)
	requireStatus(t, request(server, session(t, s, ordinary), "POST", path, "{}", map[string]string{"X-Expected-User-Id": ordinary.ID}), 403)
	requireStatus(t, request(server, b, "POST", path, "{}", map[string]string{"X-Expected-User-Id": "wrong"}), 409)
	requireStatus(t, request(server, b, "POST", path, "{}", map[string]string{"X-CSRF-Token": ""}), 403)
	requireStatus(t, request(server, b, "POST", "/api/plugins/deermate.briefing/actions/perform", "{}", nil), 403)
	requireStatus(t, request(server, b, "POST", "/api/threads/thread/runs", "{}", map[string]string{"Idempotency-Key": "  extension:deermate.briefing:forged"}), 403)
	body, _ := json.Marshal(map[string]any{"kind": "followup", "topic_id": i.Topic, "evidence_revision": i.SourceVersion})
	requireStatus(t, request(server, b, "POST", "/api/me/briefing/actions", string(body), map[string]string{"X-Expected-User-Id": u.ID}), 409)
	var count int
	s.DB.QueryRow("SELECT count(*) FROM deermate_briefing_intents").Scan(&count)
	if count != 1 {
		t.Fatal("unconfigured model left an intent", count)
	}
}
