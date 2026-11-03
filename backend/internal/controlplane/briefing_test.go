package controlplane

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"testing"
	"time"
)

func briefingFixture(t *testing.T, s *Store, u User, thread string) {
	t.Helper()
	_, err := s.DB.Exec(`CREATE TABLE IF NOT EXISTS threads_meta(thread_id TEXT PRIMARY KEY,user_id TEXT,incarnation TEXT,project_id TEXT,display_name TEXT,status TEXT,metadata_json TEXT);
CREATE TABLE IF NOT EXISTS runs(run_id TEXT PRIMARY KEY,thread_id TEXT,user_id TEXT,status TEXT,evidence_origin TEXT,origin_kind TEXT,created_at TEXT,updated_at TEXT);
CREATE TABLE IF NOT EXISTS mcp_tasks(id TEXT PRIMARY KEY,user_id TEXT,thread_id TEXT,thread_incarnation TEXT,status TEXT,result TEXT,last_polled_at TEXT,last_poll_error TEXT,cancel_requested_at TEXT,created_at TEXT,updated_at TEXT);`)
	if err != nil {
		t.Fatal(err)
	}
	_, err = s.DB.Exec(`INSERT INTO threads_meta VALUES(?,?,'generation',NULL,'私人助手','idle','{}')`, thread, u.ID)
	if err != nil {
		t.Fatal(err)
	}
}
func followTopic(t *testing.T, s *Store, u User, thread string) AttentionTopic {
	t.Helper()
	topic, err := s.createTopic(context.Background(), u.ID, "follow-"+thread, thread, "私人助手进度", "完成可用的秘书首页", 1)
	if err != nil {
		t.Fatal(err)
	}
	return topic
}
func TestAttentionOwnedIdempotentAndNotLimitedToRecentThreads(t *testing.T) {
	s := testStore(t)
	u := account(t, s, "owner@example.com", "user")
	other := account(t, s, "other@example.com", "user")
	briefingFixture(t, s, u, "old-thread")
	topic := followTopic(t, s, u, "old-thread")
	for i := 0; i < 25; i++ {
		briefingFixture(t, s, u, fmt.Sprintf("recent-%d", i))
	}
	if duplicate := followTopic(t, s, u, "old-thread"); duplicate.ID != topic.ID {
		t.Fatal("duplicate topic")
	}
	if _, err := s.createTopic(context.Background(), other.ID, "foreign", "old-thread", "foreign", "", 1); !errors.Is(err, ErrNotFound) {
		t.Fatal(err)
	}
	b, err := s.Briefing(u.ID, time.Now())
	if err != nil || len(b.Items) != 1 || b.Items[0].Topic.Thread != "old-thread" || b.Items[0].Changed {
		t.Fatal(b, err)
	}
	if b, err = s.Briefing(other.ID, time.Now()); err != nil || len(b.Items) != 0 {
		t.Fatal("cross-owner data", b, err)
	}
}
func TestBriefingUsesActualValidationAndSemanticSeenRevision(t *testing.T) {
	s := testStore(t)
	u := account(t, s, "owner@example.com", "user")
	briefingFixture(t, s, u, "thread")
	topic := followTopic(t, s, u, "thread")
	_, err := s.DB.Exec(`INSERT INTO mcp_tasks VALUES('task',?,?,'generation','completed',?,NULL,NULL,NULL,?,?)`, u.ID, "thread", `{"validation_status":"passed","validation":{"exit_code":1}}`, time.Now().Format(time.RFC3339), time.Now().Format(time.RFC3339))
	if err != nil {
		t.Fatal(err)
	}
	b, err := s.Briefing(u.ID, time.Now())
	if err != nil || b.Items[0].Evidence.Verified || !b.Items[0].Changed {
		t.Fatal(b, err)
	}
	if _, err = s.updateTopic(context.Background(), u.ID, topic.ID, "seen", "", "", 0, topic.Revision, "stale-version"); !errors.Is(err, ErrConflict) {
		t.Fatal("stale seen accepted", err)
	}
	topic, err = s.updateTopic(context.Background(), u.ID, topic.ID, "seen", "", "", 0, topic.Revision, b.Items[0].Evidence.Version)
	if err != nil {
		t.Fatal(err)
	}
	seen, _ := s.Briefing(u.ID, time.Now())
	if seen.Items[0].Changed {
		t.Fatal("read state ignored")
	}
	s.DB.Exec(`UPDATE mcp_tasks SET result='{"validation_status":"passed","validation":{"exit_code":0}}' WHERE id='task'`)
	passed, err := s.Briefing(u.ID, time.Now())
	if err != nil || !passed.Items[0].Evidence.Verified || !passed.Items[0].Changed {
		t.Fatal(passed, err)
	}
	stable, _ := s.Briefing(u.ID, time.Now().Add(time.Second))
	if stable.Version != passed.Version {
		t.Fatal("wall clock caused new content")
	}
}
func TestAttentionSourceArchiveAndReplacementMaskOldContent(t *testing.T) {
	for _, mutation := range []string{`DELETE FROM threads_meta`, `UPDATE threads_meta SET incarnation='another'`, `UPDATE threads_meta SET project_id='shared-project'`, `UPDATE threads_meta SET metadata_json='{"deerflow_archived":true}'`} {
		t.Run(mutation, func(t *testing.T) {
			s := testStore(t)
			u := account(t, s, "owner@example.com", "user")
			briefingFixture(t, s, u, "thread")
			topic := followTopic(t, s, u, "thread")
			s.DB.Exec(mutation)
			items, err := s.Topics(u.ID)
			if err != nil || items[0].SourceState != "unavailable" || items[0].Title != "" || items[0].Goal != "" || items[0].Thread != "" {
				t.Fatal(items, err)
			}
			b, err := s.Briefing(u.ID, time.Now())
			if err != nil || len(b.Items) != 0 || b.Unavailable != 1 {
				t.Fatal(b, err)
			}
			if _, err = s.updateTopic(context.Background(), u.ID, topic.ID, "remove", "", "", 0, topic.Revision, ""); err != nil {
				t.Fatal("unavailable topic could not be removed", err)
			}
		})
	}
}
func TestAttentionPauseCompleteAndTodaySnooze(t *testing.T) {
	s := testStore(t)
	u := account(t, s, "owner@example.com", "user")
	briefingFixture(t, s, u, "thread")
	topic := followTopic(t, s, u, "thread")
	p, _ := s.PersonalProfile(u.ID)
	p.Timezone = "America/Los_Angeles"
	s.UpdatePersonalProfile(context.Background(), p, p.Revision)
	var err error
	topic, err = s.updateTopic(context.Background(), u.ID, topic.ID, "snooze_today", "", "", 0, topic.Revision, "")
	if err != nil {
		t.Fatal(err)
	}
	zone, _ := time.LoadLocation("America/Los_Angeles")
	now := time.Now().In(zone)
	end := time.Date(now.Year(), now.Month(), now.Day()+1, 0, 0, 0, 0, zone)
	if topic.SnoozedUntil != end.Unix() {
		t.Fatal(topic.SnoozedUntil, end)
	}
	if b, err := s.Briefing(u.ID, time.Now()); err != nil || len(b.Items) != 0 {
		t.Fatal(b, err)
	}
	topic, err = s.updateTopic(context.Background(), u.ID, topic.ID, "unsnooze", "", "", 0, topic.Revision, "")
	if err != nil {
		t.Fatal(err)
	}
	topic, err = s.updateTopic(context.Background(), u.ID, topic.ID, "pause", "", "", 0, topic.Revision, "")
	if err != nil {
		t.Fatal(err)
	}
	if b, _ := s.Briefing(u.ID, time.Now()); len(b.Items) != 0 {
		t.Fatal(b)
	}
	topic, err = s.updateTopic(context.Background(), u.ID, topic.ID, "resume", "", "", 0, topic.Revision, "")
	if err != nil {
		t.Fatal(err)
	}
	_, err = s.updateTopic(context.Background(), u.ID, topic.ID, "complete", "", "", 0, topic.Revision, "")
	if err != nil {
		t.Fatal(err)
	}
}
func TestBriefingLocalDateAndOldPollIsNotFreshProgress(t *testing.T) {
	s := testStore(t)
	u := account(t, s, "owner@example.com", "user")
	briefingFixture(t, s, u, "thread")
	followTopic(t, s, u, "thread")
	p, _ := s.PersonalProfile(u.ID)
	p.Timezone = "Asia/Shanghai"
	s.UpdatePersonalProfile(context.Background(), p, p.Revision)
	s.DB.Exec(`INSERT INTO mcp_tasks VALUES('task',?,'thread','generation','working','{}','2020-01-01T00:00:00Z',NULL,NULL,'2020-01-01T00:00:00Z','2020-01-01T00:00:00Z')`, u.ID)
	b, err := s.Briefing(u.ID, time.Date(2026, 11, 2, 22, 0, 0, 0, time.UTC))
	if err != nil || b.LocalDate != "2026-11-03" || !b.Items[0].Evidence.Stale || !b.Items[0].Evidence.Busy {
		t.Fatal(b, err)
	}
	data, _ := json.Marshal(b)
	if len(data) > 8000 {
		t.Fatal("unbounded briefing")
	}
}
