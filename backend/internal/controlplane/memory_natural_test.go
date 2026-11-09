package controlplane

import (
	"context"
	"encoding/json"
	"errors"
	"testing"
	"time"
)

func completeNatural(t *testing.T, s *Store, op MemoryOperation, revision int64) {
	t.Helper()
	claimed, err := s.claimMemory(context.Background(), op.Owner, op.ID)
	if err != nil {
		t.Fatal(err)
	}
	var body memoryMutation
	_ = json.Unmarshal([]byte(claimed.Payload), &body)
	if err = s.finishMemory(context.Background(), claimed, revision, body.Category, nil); err != nil {
		t.Fatal(err)
	}
}

func TestOrdinaryPreferenceAndStageKeepDifferentScopes(t *testing.T) {
	s := testStore(t)
	u := account(t, s, "natural@example.com", "admin")
	text := "以后给我的产品文档，先放样式图，再写规格细节。\n这次先出首页 PRD，不要开始写代码。"
	c := captureFixture(t, s, u, "plain-language", text)
	candidates := naturalMemories(text)
	if len(candidates) != 2 || candidates[0].Slot != "document_style" || candidates[1].Scope != "topic" {
		t.Fatal(candidates)
	}
	for i, candidate := range candidates {
		op, err := s.admitNaturalMemory(context.Background(), c, candidate, i)
		if err != nil {
			t.Fatal(err)
		}
		completeNatural(t, s, op, 1)
	}
	refs, err := s.MemoryReferences(u.ID)
	if err != nil || len(refs) != 2 {
		t.Fatal(refs, err)
	}
	for _, ref := range refs {
		if ref.Category == "preference" && (ref.Scope != "personal" || ref.Expires != 0) {
			t.Fatal("personal preference acquired a stage expiry", ref)
		}
		if ref.Category == "context" && (ref.Scope != "topic:"+c.Thread || ref.Expires < time.Now().Add(29*24*time.Hour).Unix()) {
			t.Fatal("stage became a permanent personal preference", ref)
		}
	}
}

func TestNaturalCorrectionReplacesOneSlotAndRetryKeepsIntent(t *testing.T) {
	s := testStore(t)
	u := account(t, s, "natural-correct@example.com", "admin")
	first := "以后回答先给结论，再补充证据"
	c := captureFixture(t, s, u, "first-natural", first)
	op, err := s.admitNaturalMemory(context.Background(), c, naturalMemories(first)[0], 0)
	if err != nil {
		t.Fatal(err)
	}
	completeNatural(t, s, op, 1)
	if retry, e := s.admitNaturalMemory(context.Background(), c, naturalMemories(first)[0], 0); e != nil || retry.ID != op.ID || retry.Kind != "create" {
		t.Fatal("a retry changed create into update", retry, e)
	}
	next := "以后回答改为先列事实，再给结论"
	c2 := captureFixture(t, s, u, "next-natural", next)
	correction, err := s.admitNaturalMemory(context.Background(), c2, naturalMemories(next)[0], 0)
	if err != nil || correction.Kind != "update" || correction.FactID != op.FactID {
		t.Fatal(correction, err)
	}
	completeNatural(t, s, correction, 2)
	ref, _ := scanMemoryRef(s.DB.QueryRow("SELECT "+memoryRefColumns+" FROM deermate_memory_refs WHERE id=?", op.FactID))
	if ref.Status != "active" || ref.Revision != 2 || ref.Source != correction.ID {
		t.Fatal("correction crossed its own deletion fence", ref)
	}
	if _, err = s.AdmitMemory(context.Background(), u.ID, "delete", ref.ID, memoryMutation{OperationID: "forget-natural", ExpectedRevision: ref.Revision}); err != nil {
		t.Fatal(err)
	}
	retry, err := s.admitNaturalMemory(context.Background(), c2, naturalMemories(next)[0], 0)
	if err != nil || retry.ID != correction.ID {
		t.Fatal(err, retry)
	}
	ref, _ = scanMemoryRef(s.DB.QueryRow("SELECT "+memoryRefColumns+" FROM deermate_memory_refs WHERE id=?", op.FactID))
	if ref.Status != "suppressed" {
		t.Fatal("old source revived forgotten content", ref)
	}
}

func TestNaturalCaptureRejectsQuestionsQuotesCredentialsAndSensitiveProfiles(t *testing.T) {
	for _, text := range []string{
		"帮我查一次跑鞋", "我喜欢哪个方案？", "他说：以后回答先给结论", "示例：我喜欢简短回复",
		"```以后回答先给结论```", "以后回答请带上 API Key: fixture_secret_value",
		"以后回复时使用验证码123456", "请记住：我喜欢 password is fake_password",
		"我的长期目标是治疗确诊病史", "我偏好保存同事的财务状况", "我习惯用身份证123456789012345678",
	} {
		if got := naturalMemories(text); len(got) != 0 {
			t.Errorf("unexpected personal profile from synthetic counterexample: %q", text)
		}
	}
}

func TestHabitsAndMultipleGoalsDoNotOverwriteAnswerPreference(t *testing.T) {
	for _, text := range []string{"我习惯早上看书", "我喜欢绿茶", "我的长期目标是学会日语", "I prefer tea."} {
		got := naturalMemories(text)
		if len(got) != 1 || got[0].Slot == "response_style" {
			t.Fatal(text, got)
		}
	}
}

func TestProjectRequirementsAreOwnerLocalAndPendingSlotsCannotDuplicate(t *testing.T) {
	s := testStore(t)
	u := account(t, s, "project-natural@example.com", "admin")
	text := "DeerMate 控制端使用 Go"
	c := captureFixture(t, s, u, "named-project", text)
	got := naturalMemories(text)
	if len(got) != 1 || got[0].Scope != "project" || got[0].Project != "DeerMate" {
		t.Fatal(got)
	}
	op, err := s.admitNaturalMemory(context.Background(), c, got[0], 0)
	if err != nil {
		t.Fatal(err)
	}
	ref, _ := scanMemoryRef(s.DB.QueryRow("SELECT "+memoryRefColumns+" FROM deermate_memory_refs WHERE id=?", op.FactID))
	if ref.Scope != "project:"+projectMemoryKey("DeerMate") {
		t.Fatal(ref)
	}
	first := "以后回答先给结论"
	c2 := captureFixture(t, s, u, "pending-first", first)
	if _, err = s.admitNaturalMemory(context.Background(), c2, naturalMemories(first)[0], 0); err != nil {
		t.Fatal(err)
	}
	next := "以后回答先列事实，再给结论"
	c3 := captureFixture(t, s, u, "pending-next", next)
	if _, err = s.admitNaturalMemory(context.Background(), c3, naturalMemories(next)[0], 0); !errors.Is(err, ErrConflict) {
		t.Fatal("two unsettled values occupied one preference slot", err)
	}
}

func TestCompletedTopicFencesLateStageWrites(t *testing.T) {
	s := testStore(t)
	u := account(t, s, "stage-complete@example.com", "admin")
	text := "这次先出 PRD，不开始写代码"
	c := captureFixture(t, s, u, "stage-complete", text)
	_, err := s.DB.Exec(`ALTER TABLE threads_meta ADD COLUMN display_name TEXT DEFAULT '';
ALTER TABLE threads_meta ADD COLUMN status TEXT DEFAULT 'idle';
ALTER TABLE runs ADD COLUMN status TEXT DEFAULT 'success';
ALTER TABLE runs ADD COLUMN updated_at TEXT DEFAULT '';
CREATE TABLE mcp_tasks(id TEXT,user_id TEXT,thread_id TEXT,thread_incarnation TEXT,status TEXT,result TEXT,last_polled_at TEXT,last_poll_error TEXT,cancel_requested_at TEXT,created_at TEXT,updated_at TEXT);`)
	if err != nil {
		t.Fatal(err)
	}
	op, err := s.admitNaturalMemory(context.Background(), c, naturalMemories(text)[0], 0)
	if err != nil {
		t.Fatal(err)
	}
	job, err := s.enqueueMemoryExtraction(context.Background(), c)
	if err != nil {
		t.Fatal(err)
	}
	topic, err := s.createTopic(context.Background(), u.ID, "follow-stage", c.Thread, "阶段讨论", "先出 PRD", 1)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = s.updateTopic(context.Background(), u.ID, topic.ID, "complete", "", "", 0, topic.Revision, ""); err != nil {
		t.Fatal(err)
	}
	current, err := s.MemoryOperation(u.ID, op.ID)
	if err != nil || current.Status != "invalidated" {
		t.Fatal(current, err)
	}
	if _, err = s.admitNaturalMemory(context.Background(), c, naturalMemories(text)[0], 1); !errors.Is(err, ErrConflict) {
		t.Fatal("late phase resurrected after completion", err)
	}
	var status string
	_ = s.DB.QueryRow("SELECT status FROM deermate_memory_jobs WHERE id=?", job).Scan(&status)
	if status != "invalidated" {
		t.Fatal(status)
	}
	if err = s.finishMemory(context.Background(), op, 1, "context", nil); err != nil {
		t.Fatal(err)
	}
	ref, _ := scanMemoryRef(s.DB.QueryRow("SELECT "+memoryRefColumns+" FROM deermate_memory_refs WHERE id=?", op.FactID))
	if ref.Status == "active" {
		t.Fatal("late storage receipt restored completed stage")
	}
}

func TestFreshStatementReplacesRevokedDuplicateSourceWithoutReplayingIt(t *testing.T) {
	s := testStore(t)
	u := account(t, s, "restated-fact@example.com", "admin")
	text := "我喜欢绿茶"
	first := captureFixture(t, s, u, "old-habit", text)
	op, err := s.admitNaturalMemory(context.Background(), first, naturalMemories(text)[0], 0)
	if err != nil {
		t.Fatal(err)
	}
	completeNatural(t, s, op, 1)
	if _, err = s.DB.Exec("DELETE FROM runs WHERE run_id=?", first.Run); err != nil {
		t.Fatal(err)
	}
	refs, err := s.MemoryReferences(u.ID)
	if err != nil || refs[0].Status != "source_unavailable" {
		t.Fatal(refs, err)
	}
	fresh := captureFixture(t, s, u, "fresh-habit", text)
	replacement, err := s.admitNaturalMemory(context.Background(), fresh, naturalMemories(text)[0], 0)
	if err != nil || replacement.Kind != "update" || replacement.FactID != op.FactID {
		t.Fatal(replacement, err)
	}
	completeNatural(t, s, replacement, 2)
	refs, err = s.MemoryReferences(u.ID)
	if err != nil || refs[0].Status != "active" || refs[0].Source != replacement.ID {
		t.Fatal(refs, err)
	}
	old, err := s.admitNaturalMemory(context.Background(), first, naturalMemories(text)[0], 0)
	if err != nil || old.ID != op.ID {
		t.Fatal(old, err)
	}
	refs, _ = s.MemoryReferences(u.ID)
	if refs[0].Source != replacement.ID {
		t.Fatal("an old source replay replaced the fresh statement")
	}
}
