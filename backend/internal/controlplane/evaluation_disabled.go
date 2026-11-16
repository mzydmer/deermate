//go:build !deermate_evaluation || !linux

package controlplane

// Ordinary builds have no evaluation route, environment switch or clocks.
func evaluationDirectContext() bool                                  { return true }
func (s *Server) evaluationFixtureRoutes()                           {}
func (s *Server) evaluationAdmitted(owner, inbox string)             {}
func (s *Server) evaluationVisible(owner string, items []workRecord) {}
