package controlplane

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"net/http"
	"reflect"
	"sync/atomic"
	"testing"
	"time"

	"modernc.org/sqlite"
)

// Separate connections model the real Go/Gateway shared WAL database. The
// writer is held by a channel/transaction, never by a timing assumption about
// the production model or Native process.
func competingWorkWriter(t *testing.T, store *Store) (*sql.DB, *sql.Tx) {
	t.Helper()
	var sequence int
	var name, filename string
	if err := store.DB.QueryRow("PRAGMA database_list").Scan(&sequence, &name, &filename); err != nil {
		t.Fatal(err)
	}
	db, err := sql.Open("sqlite", "file:"+filename+"?_pragma=busy_timeout(1000)")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { db.Close() })
	tx, err := db.Begin()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { tx.Rollback() })
	if _, err = tx.Exec("INSERT INTO deermate_control_meta(key,value) VALUES('fixture-gateway-writer','held')"); err != nil {
		t.Fatal(err)
	}
	return db, tx
}

func workClaimFixture(t *testing.T) (*Store, User, workRecord) {
	t.Helper()
	store := testStore(t)
	user := account(t, store, "lock-fixture@example.com", "admin")
	op := newWork(user.ID, "operation", "acknowledged", "original-inbox", map[string]any{
		"kind": "router", "thread_id": "original-thread", "_nonce": "fixture-only",
		"_user_version": user.Version,
	})
	if err := store.workTransaction(context.Background(), func(tx *sql.Tx) error {
		if err := workPut(tx, &op); err != nil {
			return err
		}
		return workUnique(tx, user.ID, "input", "original-stable-input", op.ID)
	}); err != nil {
		t.Fatal(err)
	}
	op, err := workGet(store.DB, user.ID, "operation", op.ID)
	if err != nil {
		t.Fatal(err)
	}
	return store, user, op
}

func claimOriginalWork(tx *sql.Tx, op workRecord) error {
	current, err := workGet(tx, op.Owner, "operation", op.ID)
	if err != nil {
		return err
	}
	if workBool(current, "_tool_claimed") {
		return ErrConflict
	}
	current.Data["_tool_claimed"] = true
	return workPut(tx, &current)
}

func assertOriginalWork(t *testing.T, store *Store, original workRecord, claimed bool) {
	t.Helper()
	current, err := workGet(store.DB, original.Owner, "operation", original.ID)
	if err != nil {
		t.Fatal(err)
	}
	if current.ID != original.ID || current.Parent != original.Parent || workString(current, "thread_id") != workString(original, "thread_id") || workBool(current, "_tool_claimed") != claimed {
		t.Fatalf("original operation identity/claim changed: %+v", current)
	}
	if id, err := workExisting(store.DB, original.Owner, "input", "original-stable-input"); err != nil || id != original.ID {
		t.Fatalf("stable input key changed: %s %v", id, err)
	}
	var native int
	if err := store.DB.QueryRow("SELECT count(*) FROM deermate_work_records WHERE kind='operation' AND json_extract(data,'$.kind') IN ('execute','followup')").Scan(&native); err != nil || native != 0 {
		t.Fatalf("database-only claim created Native work: %d %v", native, err)
	}
}

func TestDeferredWorkClaimReproducesSharedWriterBusyAndRollsBack(t *testing.T) {
	store, _, original := workClaimFixture(t)
	_, writer := competingWorkWriter(t, store)
	tx, err := store.DB.BeginTx(context.Background(), nil)
	if err != nil {
		t.Fatal(err)
	}
	// Exact production claim sequence: SELECT canonical operation, then UPDATE.
	err = claimOriginalWork(tx, original)
	var sqliteError *sqlite.Error
	if !errors.As(err, &sqliteError) || sqliteError.Code() != 5 {
		t.Fatalf("expected the real shared-writer SQLITE_BUSY(5), got %v", err)
	}
	t.Log("observed SQLITE_BUSY on deferred read-to-write upgrade")
	if err := tx.Rollback(); err != nil {
		t.Fatal(err)
	}
	if err := writer.Rollback(); err != nil {
		t.Fatal(err)
	}
	current, err := workGet(store.DB, original.Owner, "operation", original.ID)
	if err != nil || !reflect.DeepEqual(current, original) {
		t.Fatalf("failed claim did not roll back: %+v %v", current, err)
	}
	assertOriginalWork(t, store, original, false)
}

func TestWorkTransactionAcquiresWriterBeforeCallbackWithoutReplay(t *testing.T) {
	store, _, original := workClaimFixture(t)
	_, writer := competingWorkWriter(t, store)
	entered := make(chan struct{})
	done := make(chan error, 1)
	var calls atomic.Int32
	go func() {
		done <- store.workTransaction(context.Background(), func(tx *sql.Tx) error {
			calls.Add(1)
			close(entered)
			return claimOriginalWork(tx, original)
		})
	}()
	select {
	case <-entered:
		writer.Rollback()
		<-done
		t.Fatal("callback entered before the competing writer released; deferred upgrade remains")
	case <-time.After(100 * time.Millisecond):
	}
	if err := writer.Commit(); err != nil {
		t.Fatal(err)
	}
	select {
	case err := <-done:
		if err != nil || calls.Load() != 1 {
			t.Fatalf("claim failed or callback replayed: calls=%d err=%v", calls.Load(), err)
		}
	case <-time.After(6 * time.Second):
		t.Fatal("writer acquisition did not finish within the existing SQLite busy bound")
	}
	assertOriginalWork(t, store, original, true)
	if err := store.workTransaction(context.Background(), func(tx *sql.Tx) error { return claimOriginalWork(tx, original) }); !errors.Is(err, ErrConflict) {
		t.Fatalf("duplicate original claim was not fenced: %v", err)
	}
}

func TestWorkTransactionBusyBeforeCallbackLeavesOriginalUntouched(t *testing.T) {
	store, _, original := workClaimFixture(t)
	_, writer := competingWorkWriter(t, store)
	if _, err := store.DB.Exec("PRAGMA busy_timeout=25"); err != nil {
		t.Fatal(err)
	}
	var calls int
	err := store.workTransaction(context.Background(), func(tx *sql.Tx) error {
		calls++
		return claimOriginalWork(tx, original)
	})
	if err == nil || calls != 0 {
		t.Fatalf("busy admission ran/replayed callback: calls=%d err=%v", calls, err)
	}
	if err := writer.Rollback(); err != nil {
		t.Fatal(err)
	}
	assertOriginalWork(t, store, original, false)
}

func TestRouterClaimContentionPreservesOriginalActionAndDoesNotDispatch(t *testing.T) {
	var runtimeCalls atomic.Int32
	server, user, _ := continuousFixture(t, func(w http.ResponseWriter, r *http.Request) {
		runtimeCalls.Add(1)
		t.Error("Router command sent an external runtime action")
	})
	work := fixtureWork(t, server, user, "stable-lock-work")
	op := newWork(user.ID, "operation", "acknowledged", "original-inbox", map[string]any{
		"kind": "router", "thread_id": "original-thread", "origin": "user",
		"_nonce": opaque(), "_user_version": user.Version,
	})
	if err := server.Store.workTransaction(context.Background(), func(tx *sql.Tx) error { return workPut(tx, &op) }); err != nil {
		t.Fatal(err)
	}
	original, err := workGet(server.Store.DB, user.ID, "operation", op.ID)
	if err != nil {
		t.Fatal(err)
	}
	_, writer := competingWorkWriter(t, server.Store)
	if _, err := server.Store.DB.Exec("PRAGMA busy_timeout=25"); err != nil {
		t.Fatal(err)
	}
	body, _ := json.Marshal(map[string]string{"action": "execute", "work_id": work.ID, "text": "Explicit fixture owner work"})
	path := "/internal/deermate/continuous/" + op.ID
	headers := map[string]string{"Authorization": "Bearer " + workString(op, "_nonce")}
	response := request(server, browser{}, "POST", path, string(body), headers)
	requireStatus(t, response, 503)
	if err := writer.Rollback(); err != nil {
		t.Fatal(err)
	}
	current, err := workGet(server.Store.DB, user.ID, "operation", op.ID)
	if err != nil || !reflect.DeepEqual(current, original) || runtimeCalls.Load() != 0 {
		t.Fatalf("busy claim changed original or dispatched: %+v %v calls=%d", current, err, runtimeCalls.Load())
	}
	var native int
	if err := server.Store.DB.QueryRow("SELECT count(*) FROM deermate_work_records WHERE kind='operation' AND json_extract(data,'$.kind')='execute'").Scan(&native); err != nil || native != 0 {
		t.Fatalf("busy claim admitted native work: %d %v", native, err)
	}
	// These are explicit test requests after confirmed rollback, not automatic
	// retries by workTransaction. Both use the original Router operation token.
	first := request(server, browser{}, "POST", path, string(body), headers)
	requireStatus(t, first, 200)
	again := request(server, browser{}, "POST", path, string(body), headers)
	requireStatus(t, again, 200)
	var action, repeated workRecord
	if err := json.Unmarshal(first.Body.Bytes(), &action); err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(again.Body.Bytes(), &repeated); err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(action, repeated) {
		t.Fatal("same original action did not return the same operation receipt")
	}
	key, err := workExisting(server.Store.DB, user.ID, "action", "router-action-"+op.ID)
	if err != nil || key != action.ID || runtimeCalls.Load() != 0 {
		t.Fatalf("original stable action key changed or dispatched: %s %v calls=%d", key, err, runtimeCalls.Load())
	}
	if err := server.Store.DB.QueryRow("SELECT count(*) FROM deermate_work_records WHERE kind='operation' AND json_extract(data,'$.kind')='execute'").Scan(&native); err != nil || native != 1 {
		t.Fatalf("original action was admitted more than once: %d %v", native, err)
	}
}

func TestWorkTransactionCanceledBeforeCallbackDoesNotClaim(t *testing.T) {
	store, _, original := workClaimFixture(t)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	var calls int
	err := store.workTransaction(ctx, func(tx *sql.Tx) error {
		calls++
		return claimOriginalWork(tx, original)
	})
	if !errors.Is(err, context.Canceled) || calls != 0 {
		t.Fatalf("cancelled admission invoked callback: calls=%d err=%v", calls, err)
	}
	assertOriginalWork(t, store, original, false)
}
