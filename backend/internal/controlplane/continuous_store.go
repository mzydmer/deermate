package controlplane

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"
)

const continuousVersion = 1

// workRecord is a versioned control-plane record. Native state remains owned by
// the existing task driver; private admission fields never leave public views.
type workRecord struct {
	ID       string         `json:"id"`
	Kind     string         `json:"kind"`
	Owner    string         `json:"-"`
	Parent   string         `json:"parent_id,omitempty"`
	State    string         `json:"state"`
	Revision int64          `json:"revision"`
	Created  int64          `json:"created_at"`
	Updated  int64          `json:"updated_at"`
	Data     map[string]any `json:"data"`
}

func (s *Store) initializeContinuous() error {
	_, err := s.DB.Exec(`CREATE TABLE IF NOT EXISTS deermate_work_records(
 id TEXT NOT NULL,kind TEXT NOT NULL,owner TEXT NOT NULL REFERENCES users(id),parent TEXT NOT NULL DEFAULT '',
 state TEXT NOT NULL,revision INTEGER NOT NULL,created INTEGER NOT NULL,updated INTEGER NOT NULL,data TEXT NOT NULL,
 PRIMARY KEY(owner,kind,id));
 CREATE INDEX IF NOT EXISTS deermate_work_active ON deermate_work_records(kind,state,updated,owner);
 CREATE INDEX IF NOT EXISTS deermate_work_owner ON deermate_work_records(owner,kind,updated,id);
 CREATE INDEX IF NOT EXISTS deermate_work_parent ON deermate_work_records(owner,parent,kind,state);
 CREATE TABLE IF NOT EXISTS deermate_work_keys(owner TEXT NOT NULL,kind TEXT NOT NULL,key TEXT NOT NULL,record TEXT NOT NULL,
 PRIMARY KEY(owner,kind,key));
 CREATE TABLE IF NOT EXISTS deermate_work_budget(owner TEXT NOT NULL,day TEXT NOT NULL,kind TEXT NOT NULL,used INTEGER NOT NULL,
 PRIMARY KEY(owner,day,kind));`)
	return err
}

const workColumns = "id,kind,owner,parent,state,revision,created,updated,data"

func scanWork(row scanner) (workRecord, error) {
	var v workRecord
	var data string
	err := row.Scan(&v.ID, &v.Kind, &v.Owner, &v.Parent, &v.State, &v.Revision, &v.Created, &v.Updated, &data)
	if errors.Is(err, sql.ErrNoRows) {
		return v, ErrNotFound
	}
	if err == nil {
		err = json.Unmarshal([]byte(data), &v.Data)
	}
	return v, err
}
func workGet(q memoryReader, owner, kind, id string) (workRecord, error) {
	return scanWork(q.QueryRow("SELECT "+workColumns+" FROM deermate_work_records WHERE owner=? AND kind=? AND id=?", owner, kind, id))
}
func workString(v workRecord, key string) string { s, _ := v.Data[key].(string); return s }
func workInt(v workRecord, key string) int64 {
	switch n := v.Data[key].(type) {
	case float64:
		return int64(n)
	case int:
		return int64(n)
	case int64:
		return n
	}
	return 0
}
func workBool(v workRecord, key string) bool { b, _ := v.Data[key].(bool); return b }
func newWork(owner, kind, state, parent string, data map[string]any) workRecord {
	return workRecord{ID: strings.ReplaceAll(uuid(), "-", ""), Owner: owner, Kind: kind, State: state, Parent: parent, Data: data}
}
func workHash(v any) string { b, _ := json.Marshal(v); return digest(string(b)) }

func workPut(tx *sql.Tx, v *workRecord) error {
	b, err := json.Marshal(v.Data)
	if err != nil {
		return err
	}
	if len(b) > 65536 {
		return ErrCredentials
	}
	now := time.Now().UnixMilli()
	old := v.Revision
	if old == 0 {
		v.Created = now
		v.Updated = now
		v.Revision = 1
		_, err = tx.Exec("INSERT INTO deermate_work_records VALUES(?,?,?,?,?,?,?,?,?)", v.ID, v.Kind, v.Owner, v.Parent, v.State, v.Revision, v.Created, v.Updated, string(b))
	} else {
		v.Revision++
		v.Updated = now
		var result sql.Result
		result, err = tx.Exec("UPDATE deermate_work_records SET parent=?,state=?,revision=?,updated=?,data=? WHERE owner=? AND kind=? AND id=? AND revision=?", v.Parent, v.State, v.Revision, v.Updated, string(b), v.Owner, v.Kind, v.ID, old)
		if err == nil {
			n, _ := result.RowsAffected()
			if n != 1 {
				return ErrConflict
			}
		}
	}
	if err != nil {
		if strings.Contains(strings.ToLower(err.Error()), "constraint") {
			return ErrConflict
		}
		return err
	}
	if v.Kind == "work" || v.Kind == "event" {
		table := "deermate_work_fts_" + digest(v.Owner)[:24]
		// One physical FTS corpus per owner: foreign documents cannot affect ranking.
		if _, err = tx.Exec("CREATE VIRTUAL TABLE IF NOT EXISTS " + table + " USING fts5(id UNINDEXED,kind UNINDEXED,title,body,tokenize='trigram')"); err != nil {
			return err
		}
		if _, err = tx.Exec("DELETE FROM "+table+" WHERE id=? AND kind=?", v.ID, v.Kind); err != nil {
			return err
		}
		if v.State != "removed" && v.State != "unavailable" && v.State != "superseded" {
			_, err = tx.Exec("INSERT INTO "+table+"(id,kind,title,body) VALUES(?,?,?,?)", v.ID, v.Kind, workString(*v, "title"), workString(*v, "goal")+" "+workString(*v, "preview"))
		}
	}
	if v.Kind == "source" && (v.State != "enabled" || workString(*v, "error") != "") {
		table := "deermate_work_fts_" + digest(v.Owner)[:24]
		var exists int
		if e := tx.QueryRow("SELECT count(*) FROM sqlite_master WHERE type='table' AND name=?", table).Scan(&exists); e != nil {
			return e
		}
		if exists > 0 {
			_, err = tx.Exec("DELETE FROM "+table+" WHERE id IN (SELECT id FROM deermate_work_records WHERE owner=? AND json_extract(data,'$.source_id')=?)", v.Owner, v.ID)
		}
	}
	return err
}

func workPublic(v workRecord) workRecord {
	data := map[string]any{}
	for k, x := range v.Data {
		if !strings.HasPrefix(k, "_") {
			data[k] = x
		}
	}
	v.Data = data
	return v
}
func (s *Store) workList(owner, kind, parent string, offset, limit int) ([]workRecord, error) {
	if offset < 0 || offset > 10000 || limit < 1 || limit > 50 {
		return nil, ErrCredentials
	}
	rows, err := s.DB.Query("SELECT "+workColumns+" FROM deermate_work_records WHERE owner=? AND kind=? AND (?='' OR parent=?) ORDER BY updated DESC,id DESC LIMIT ? OFFSET ?", owner, kind, parent, parent, limit, offset)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []workRecord{}
	for rows.Next() {
		v, e := scanWork(rows)
		if e != nil {
			return nil, e
		}
		out = append(out, workPublic(v))
	}
	return out, rows.Err()
}
func workUnique(tx *sql.Tx, owner, kind, key, id string) error {
	_, err := tx.Exec("INSERT INTO deermate_work_keys VALUES(?,?,?,?)", owner, kind, key, id)
	if err != nil && strings.Contains(strings.ToLower(err.Error()), "constraint") {
		return ErrConflict
	}
	return err
}
func workExisting(q memoryReader, owner, kind, key string) (string, error) {
	var id string
	err := q.QueryRow("SELECT record FROM deermate_work_keys WHERE owner=? AND kind=? AND key=?", owner, kind, key).Scan(&id)
	if errors.Is(err, sql.ErrNoRows) {
		err = ErrNotFound
	}
	return id, err
}
func workReserve(tx *sql.Tx, owner, kind string, limit int, at time.Time) error {
	if limit < 1 {
		return fmt.Errorf("%w: budget_exhausted", ErrConflict)
	}
	day := at.UTC().Format("2006-01-02")
	_, err := tx.Exec("INSERT OR IGNORE INTO deermate_work_budget VALUES(?,?,?,0)", owner, day, kind)
	if err != nil {
		return err
	}
	r, err := tx.Exec("UPDATE deermate_work_budget SET used=used+1 WHERE owner=? AND day=? AND kind=? AND used<?", owner, day, kind, limit)
	if err == nil {
		n, _ := r.RowsAffected()
		if n != 1 {
			return fmt.Errorf("%w: budget_exhausted", ErrConflict)
		}
	}
	return err
}
func workEnabled(q memoryReader, owner string) bool {
	v, e := workGet(q, owner, "settings", "settings")
	return e == nil && workBool(v, "enabled")
}
func (s *Store) workTransaction(ctx context.Context, f func(*sql.Tx) error) error {
	tx, e := s.DB.BeginTx(ctx, nil)
	if e != nil {
		return e
	}
	defer tx.Rollback()
	if e = f(tx); e != nil {
		return e
	}
	return tx.Commit()
}
