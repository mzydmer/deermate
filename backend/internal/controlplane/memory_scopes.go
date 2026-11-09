package controlplane

import (
	"database/sql"
	"regexp"
	"strings"
)

var memoryProjectLabel = regexp.MustCompile(`^[\pL0-9][\pL0-9 ._-]{1,79}$`)

func (s *Store) initializeMemoryScopes() error {
	rows, err := s.DB.Query("PRAGMA table_info(deermate_memory_refs)")
	if err != nil {
		return err
	}
	found := map[string]bool{}
	for rows.Next() {
		var cid, notnull, pk int
		var name, kind string
		var def any
		if err = rows.Scan(&cid, &name, &kind, &notnull, &def, &pk); err != nil {
			rows.Close()
			return err
		}
		found[name] = true
	}
	err = rows.Err()
	rows.Close()
	if err != nil {
		return err
	}
	for _, col := range []struct{ name, definition string }{
		{"slot", "TEXT NOT NULL DEFAULT ''"}, {"expires_at", "INTEGER NOT NULL DEFAULT 0"},
	} {
		if !found[col.name] {
			if _, err = s.DB.Exec("ALTER TABLE deermate_memory_refs ADD COLUMN " + col.name + " " + col.definition); err != nil {
				return err
			}
		}
	}
	_, err = s.DB.Exec(`CREATE TABLE IF NOT EXISTS deermate_memory_projects (
 owner TEXT NOT NULL REFERENCES users(id),id TEXT NOT NULL,label TEXT NOT NULL,
 PRIMARY KEY(owner,id));
CREATE TABLE IF NOT EXISTS deermate_memory_project_topics (
 owner TEXT NOT NULL REFERENCES users(id),thread_id TEXT NOT NULL,project_id TEXT NOT NULL,
 PRIMARY KEY(owner,thread_id));
CREATE TABLE IF NOT EXISTS deermate_memory_usage (
 owner TEXT NOT NULL REFERENCES users(id),fact_id TEXT NOT NULL,thread_id TEXT NOT NULL,last_used INTEGER NOT NULL,
 PRIMARY KEY(owner,fact_id,thread_id));
CREATE TABLE IF NOT EXISTS deermate_memory_stage_ends (
 owner TEXT NOT NULL REFERENCES users(id),thread_id TEXT NOT NULL,observed_at INTEGER NOT NULL,
 PRIMARY KEY(owner,thread_id));
CREATE UNIQUE INDEX IF NOT EXISTS deermate_memory_slot ON deermate_memory_refs(owner,scope,slot)
WHERE slot!='' AND status IN ('pending','active','updating');`)
	if err != nil {
		return err
	}
	return s.initializeMemoryExtraction()
}

func projectMemoryKey(label string) string {
	return "project-" + digest(strings.ToLower(strings.TrimSpace(label)))[:24]
}

func memoryStageEnded(q memoryReader, owner, thread string, observed int64) bool {
	var ended int64
	_ = q.QueryRow("SELECT observed_at FROM deermate_memory_stage_ends WHERE owner=? AND thread_id=?", owner, thread).Scan(&ended)
	return ended > 0 && observed <= ended
}

// These are private, owner-local organization labels, not shared-project ACLs
// or Worker grants. Naming a project never grants a tool or data permission.
func resolveMemoryScope(tx *sql.Tx, owner string, b memoryMutation, source *memoryCapture) (string, error) {
	switch b.Scope {
	case "", "personal":
		return "personal", nil
	case "topic":
		thread := b.Thread
		if source != nil {
			thread = source.Thread
		}
		if !resourceID.MatchString(thread) {
			return "", ErrCredentials
		}
		if !captureAllowed(tx, owner, thread) {
			return "", ErrConflict
		}
		if source == nil {
			if _, err := ownedTopicSource(tx, owner, thread); err != nil {
				return "", err
			}
		}
		return "topic:" + thread, nil
	case "project":
		label := strings.TrimSpace(b.Project)
		if !memoryProjectLabel.MatchString(label) || !validMemoryText(label) {
			return "", ErrCredentials
		}
		key := projectMemoryKey(label)
		if _, err := tx.Exec("INSERT OR IGNORE INTO deermate_memory_projects(owner,id,label) VALUES(?,?,?)", owner, key, label); err != nil {
			return "", err
		}
		if source != nil {
			if _, err := tx.Exec(`INSERT INTO deermate_memory_project_topics(owner,thread_id,project_id) VALUES(?,?,?) ON CONFLICT(owner,thread_id) DO UPDATE SET project_id=excluded.project_id`, owner, source.Thread, key); err != nil {
				return "", err
			}
		}
		return "project:" + key, nil
	default:
		return "", ErrCredentials
	}
}
