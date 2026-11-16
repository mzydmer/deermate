//go:build !deermate_evaluation || !linux

package controlplane

import (
	"net/http"
	"strings"
	"testing"
)

func TestOrdinaryBinaryHasNoEvaluationRoutesOrModeSwitch(t *testing.T) {
	t.Setenv("DEERMATE_EVALUATION_MODE", "B")
	t.Setenv("DEERMATE_EVALUATION_KEY", strings.Repeat("x", 40))
	db := testStore(t)
	u := account(t, db, "evaluation-boundary@example.com", "admin")
	s := testServer(t, db, func(w http.ResponseWriter, r *http.Request) {
		t.Error("Evaluation route must not reach the runtime")
	})
	b := session(t, db, u)
	w := request(s, b, "GET", "/__deermate_evaluation/evidence", "", nil)
	requireStatus(t, w, 404)
	if !evaluationDirectContext() {
		t.Fatal("A test environment variable changed ordinary subscription routing")
	}
	var tables int
	if err := db.DB.QueryRow("SELECT count(*) FROM sqlite_master WHERE name='deermate_evaluation_timings'").Scan(&tables); err != nil || tables != 0 {
		t.Fatal("Ordinary binary created test timing state", tables, err)
	}
}
