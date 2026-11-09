package controlplane

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"
	"time"
)

type BriefingSuggestion struct {
	Fact     string `json:"fact_id"`
	Revision int64  `json:"fact_revision"`
	Question string `json:"question"`
	Reason   string `json:"reason"`
}

func suggestedQuestion(fact json.RawMessage) string {
	var item struct {
		Content string `json:"content"`
	}
	_ = json.Unmarshal(fact, &item)
	text := []rune(strings.TrimSpace(item.Content))
	if len(text) > 160 {
		text = append(text[:160], []rune("…")...)
	}
	return "关于“" + string(text) + "”，下一步可以先做哪几件事？"
}

func (s *Server) suggestionFact(r *http.Request, owner, id string, revision int64) (json.RawMessage, error) {
	p, err := s.Store.PersonalProfile(owner)
	if err != nil || !p.MemoryEnabled || !p.ProactiveEnabled {
		return nil, ErrConflict
	}
	refs, err := s.Store.MemoryReferences(owner)
	if err != nil {
		return nil, err
	}
	found := false
	for _, ref := range refs {
		if ref.ID == id && ref.Revision == revision && ref.Status == "active" && ref.Scope == "personal" && ref.Category == "goal" {
			found = true
			break
		}
	}
	if !found {
		return nil, ErrNotFound
	}
	body, _ := json.Marshal(map[string]any{"ids": []string{id}, "query": ""})
	ctx, cancel := context.WithTimeout(r.Context(), 8*time.Second)
	defer cancel()
	data, err := s.engine.query(ctx, r, "POST", "/api/plugins/deermate.memory/actions/read", body)
	if err != nil {
		return nil, err
	}
	var response struct {
		Items []map[string]any `json:"items"`
	}
	if json.Unmarshal(data, &response) != nil || len(response.Items) != 1 {
		return nil, ErrNotFound
	}
	latest, err := s.Store.PersonalProfile(owner)
	if err != nil || !latest.MemoryEnabled || !latest.ProactiveEnabled || latest.PolicyRevision != p.PolicyRevision {
		return nil, ErrConflict
	}
	item := response.Items[0]
	item["policy_revision"] = p.PolicyRevision
	result, err := json.Marshal(item)
	return result, err
}

func (s *Server) briefingSuggestions(r *http.Request) ([]BriefingSuggestion, bool) {
	u := sessionOf(r).User
	p, err := s.Store.PersonalProfile(u.ID)
	out := []BriefingSuggestion{}
	if err != nil || !p.MemoryEnabled || !p.ProactiveEnabled {
		return out, false
	}
	refs, err := s.Store.MemoryReferences(u.ID)
	if err != nil {
		return out, true
	}
	for _, ref := range refs {
		if ref.Category != "goal" || ref.Status != "active" || ref.Scope != "personal" {
			continue
		}
		var dismissed bool
		_ = s.Store.DB.QueryRow("SELECT dismissed FROM deermate_workspace_feedback WHERE owner=? AND id=?", u.ID, "suggest-"+ref.ID).Scan(&dismissed)
		if dismissed {
			continue
		}
		fact, err := s.suggestionFact(r, u.ID, ref.ID, ref.Revision)
		if err != nil {
			return out, true
		}
		out = append(out, BriefingSuggestion{Fact: ref.ID, Revision: ref.Revision, Question: suggestedQuestion(fact), Reason: "explicit_saved_goal"})
		if len(out) == 2 {
			break
		}
	}
	return out, false
}
