package controlplane

import (
	"bytes"
	_ "embed"
	"net/http"
)

//go:embed admin.html
var adminHTML []byte

//go:embed design-tokens.css
var designTokens []byte

func (s *Server) adminPage(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.Header().Set("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
	_, _ = w.Write(bytes.Replace(adminHTML, []byte("/* DEERMATE_DESIGN_TOKENS */"), designTokens, 1))
}
