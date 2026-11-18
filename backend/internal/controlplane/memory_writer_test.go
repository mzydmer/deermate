package controlplane

import (
	"context"
	"reflect"
	"testing"
	"time"
)

// Use a second real SQLite connection, as the Gateway does, to hold a writer
// while Go claims or seals a delivery. No runtime request is replayed here.
func TestMemoryDeliveryWaitsForSharedWriter(t *testing.T) {
	for _, phase := range []string{"claim", "finish"} {
		t.Run(phase, func(t *testing.T) {
			store := testStore(t)
			user := account(t, store, "memory-lock@example.com", "admin")
			enableMemory(t, store, user)
			ctx, cancel := context.WithTimeout(context.Background(), 6*time.Second)
			defer cancel()
			op, err := store.AdmitMemory(ctx, user.ID, "create", "", memoryMutation{
				OperationID: "original-memory", Content: "偏好青竹色", Category: "preference",
			})
			if err != nil {
				t.Fatal(err)
			}
			if phase == "finish" {
				op, err = store.claimMemory(ctx, user.ID, op.ID)
				if err != nil {
					t.Fatal(err)
				}
			}
			_, writer := competingWorkWriter(t, store)
			done := make(chan error, 1)
			go func() {
				if phase == "claim" {
					_, e := store.claimMemory(ctx, user.ID, op.ID)
					done <- e
				} else {
					done <- store.finishMemory(ctx, op, 1, "preference", nil)
				}
			}()
			select {
			case err := <-done:
				writer.Rollback()
				t.Fatalf("delivery returned before shared writer released: %v", err)
			case <-time.After(100 * time.Millisecond):
			}
			if err := writer.Commit(); err != nil {
				t.Fatal(err)
			}
			select {
			case err := <-done:
				if err != nil {
					t.Fatal(err)
				}
			case <-ctx.Done():
				t.Fatal("delivery did not finish within the existing busy/context bound")
			}
			got, err := store.MemoryOperation(user.ID, op.ID)
			want := "processing"
			if phase == "finish" {
				want = "completed"
			}
			if err != nil || got.ID != op.ID || got.FactID != op.FactID || got.Status != want {
				t.Fatalf("original delivery identity/status changed: %+v %v", got, err)
			}
			var count int
			if err := store.DB.QueryRow("SELECT count(*) FROM deermate_memory_operations").Scan(&count); err != nil || count != 1 {
				t.Fatalf("delivery was duplicated: %d %v", count, err)
			}
		})
	}
}

func TestMemoryDeliveryBusyLeavesOriginalReceiptUntouched(t *testing.T) {
	for _, phase := range []string{"claim", "finish"} {
		t.Run(phase, func(t *testing.T) {
			store := testStore(t)
			user := account(t, store, "memory-busy@example.com", "admin")
			enableMemory(t, store, user)
			ctx := context.Background()
			op, err := store.AdmitMemory(ctx, user.ID, "create", "", memoryMutation{
				OperationID: "original-busy", Content: "偏好青竹色", Category: "preference",
			})
			if err != nil {
				t.Fatal(err)
			}
			if phase == "finish" {
				if _, err = store.claimMemory(ctx, user.ID, op.ID); err != nil {
					t.Fatal(err)
				}
			}
			before, err := store.MemoryOperation(user.ID, op.ID)
			if err != nil {
				t.Fatal(err)
			}
			_, writer := competingWorkWriter(t, store)
			if _, err := store.DB.Exec("PRAGMA busy_timeout=25"); err != nil {
				t.Fatal(err)
			}
			if phase == "claim" {
				_, err = store.claimMemory(ctx, user.ID, op.ID)
			} else {
				err = store.finishMemory(ctx, before, 1, "preference", nil)
			}
			if err == nil {
				t.Fatal("delivery ignored the bounded competing write lock")
			}
			if err := writer.Rollback(); err != nil {
				t.Fatal(err)
			}
			after, err := store.MemoryOperation(user.ID, op.ID)
			if err != nil || !reflect.DeepEqual(before, after) {
				t.Fatalf("failed transaction changed the original receipt: %+v %v", after, err)
			}
		})
	}
}
