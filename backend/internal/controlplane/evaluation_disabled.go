//go:build !deermate_evaluation || !linux

package controlplane

import (
	"database/sql"
	"net/http"
)

// Ordinary builds have no evaluation route, environment switch or clocks.
func evaluationDirectContext() bool                                                         { return true }
func (s *Server) evaluationFixtureRoutes()                                                  {}
func (s *Server) evaluationAdmitted(owner, inbox, text string)                              {}
func (s *Server) evaluationVisible(w http.ResponseWriter, owner string, items []workRecord) {}
func (s *Server) evaluationRoutedContext(tx *sql.Tx, op workRecord) error                   { return nil }
