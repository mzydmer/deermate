package controlplane

import (
	"context"
	"database/sql"
	"encoding/json"
	"net/http"
	"strings"
	"time"
)

// Interactive work is part of the desk. The legacy enabled bit controls
// background observation only, so an old pause cannot silently resume it.
func claimWorkOwner(tx *sql.Tx, owner string) error {
	if _, err := tx.Exec("INSERT OR IGNORE INTO deermate_control_meta VALUES('agent-owner',?)", owner); err != nil {
		return err
	}
	var registered string
	if err := tx.QueryRow("SELECT value FROM deermate_control_meta WHERE key='agent-owner'").Scan(&registered); err != nil {
		return err
	}
	if registered != owner {
		return ErrConflict
	}
	return nil
}

func (s *Server) defaultWorkModel(r *http.Request) (string, error) {
	preferences, err := s.Store.Preferences(sessionOf(r).User.ID)
	if err != nil {
		return "", err
	}
	selected, _ := preferences["model_name"].(string)
	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
	defer cancel()
	raw, err := s.engine.query(ctx, r, "GET", "/api/models", nil)
	if err != nil {
		return "", err
	}
	var catalog struct {
		Models []struct {
			Name string `json:"name"`
		} `json:"models"`
	}
	if err = json.Unmarshal(raw, &catalog); err != nil {
		return "", err
	}
	if len(catalog.Models) == 0 {
		return "", ErrCredentials
	}
	model := catalog.Models[0].Name
	for _, candidate := range catalog.Models {
		if candidate.Name == selected {
			model = selected
			break
		}
	}
	if strings.TrimSpace(model) == "" || !s.boundedWorkModel(r, model) {
		return "", ErrCredentials
	}
	return model, nil
}

func backgroundWorkOperation(op workRecord) bool {
	return workBool(op, "automatic") || workString(op, "kind") == "assessor" || (workString(op, "origin") == "event" || workString(op, "origin") == "assessment")
}
