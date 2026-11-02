package controlplane

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"strings"
	"time"
	_ "time/tzdata" // The scratch control image has no system zoneinfo database.
	"unicode"
)

// Memory bodies live in DeerMem. An operation payload is a temporary delivery
// envelope, erased on completion/invalidation; references are not a second fact store.
type PersonalProfile struct {
	Owner              string `json:"owner"`
	DisplayName        string `json:"display_name"`
	Timezone           string `json:"timezone"`
	MemoryEnabled      bool   `json:"memory_enabled"`
	AutoCaptureEnabled bool   `json:"auto_capture_enabled"`
	ProactiveEnabled   bool   `json:"proactive_enabled"`
	Revision           int64  `json:"revision"`
	PolicyRevision     int64  `json:"policy_revision"`
	DeletionRevision   int64  `json:"deletion_revision"`
}

type MemoryReference struct {
	ID       string `json:"id"`
	Owner    string `json:"owner"`
	Category string `json:"category"`
	Scope    string `json:"scope"`
	Source   string `json:"source_id"`
	Status   string `json:"status"`
	Revision int64  `json:"revision"`
	Updated  int64  `json:"updated_at"`
}

type MemoryOperation struct {
	ID               string `json:"id"`
	Owner            string `json:"-"`
	FactID           string `json:"fact_id"`
	Kind             string `json:"kind"`
	Status           string `json:"status"`
	PolicyRevision   int64  `json:"-"`
	DeletionRevision int64  `json:"-"`
	Payload          string `json:"-"`
}

func (s *Store) initializeMemory() error {
	_, err := s.DB.Exec(`
CREATE TABLE IF NOT EXISTS deermate_personal_profiles (
 owner TEXT PRIMARY KEY REFERENCES users(id), display_name TEXT NOT NULL DEFAULT '', timezone TEXT NOT NULL DEFAULT 'UTC',
 memory_enabled INTEGER NOT NULL DEFAULT 0, auto_capture_enabled INTEGER NOT NULL DEFAULT 0, proactive_enabled INTEGER NOT NULL DEFAULT 0,
 revision INTEGER NOT NULL DEFAULT 0, policy_revision INTEGER NOT NULL DEFAULT 0, deletion_revision INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS deermate_memory_refs (
 id TEXT PRIMARY KEY, owner TEXT NOT NULL REFERENCES users(id), category TEXT NOT NULL, scope TEXT NOT NULL DEFAULT 'personal',
 source_id TEXT NOT NULL, status TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0,
 content_hash TEXT NOT NULL, updated_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS deermate_memory_owner ON deermate_memory_refs(owner,status,updated_at);
CREATE TABLE IF NOT EXISTS deermate_memory_operations (
 id TEXT PRIMARY KEY, owner TEXT NOT NULL REFERENCES users(id), fact_id TEXT NOT NULL REFERENCES deermate_memory_refs(id),
 kind TEXT NOT NULL, status TEXT NOT NULL, policy_revision INTEGER NOT NULL, deletion_revision INTEGER NOT NULL,
 request_hash TEXT NOT NULL, payload TEXT NOT NULL, created_at INTEGER NOT NULL, lease_until INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS deermate_memory_queue ON deermate_memory_operations(status,lease_until,created_at);
CREATE TABLE IF NOT EXISTS deermate_memory_barriers (
 owner TEXT NOT NULL REFERENCES users(id), fact_id TEXT NOT NULL, deletion_revision INTEGER NOT NULL,
 created_at INTEGER NOT NULL, PRIMARY KEY(owner,fact_id));
CREATE TABLE IF NOT EXISTS deermate_memory_sources (
 operation_id TEXT PRIMARY KEY REFERENCES deermate_memory_operations(id), owner TEXT NOT NULL REFERENCES users(id),
 thread_id TEXT NOT NULL, run_id TEXT NOT NULL, message_id TEXT NOT NULL, message_hash TEXT NOT NULL, incarnation TEXT NOT NULL,
 policy_revision INTEGER NOT NULL, deletion_revision INTEGER NOT NULL, observed_at INTEGER NOT NULL, admitted_at INTEGER NOT NULL, invalidated_at INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS deermate_memory_source_owner ON deermate_memory_sources(owner,observed_at);
CREATE INDEX IF NOT EXISTS deermate_memory_source_budget ON deermate_memory_sources(admitted_at,owner);`)
	if err != nil {
		return err
	}
	rows, err := s.DB.Query("PRAGMA table_info(deermate_personal_profiles)")
	if err != nil {
		return err
	}
	found := false
	for rows.Next() {
		var cid, notnull, pk int
		var name, kind string
		var defaultValue any
		if err = rows.Scan(&cid, &name, &kind, &notnull, &defaultValue, &pk); err != nil {
			rows.Close()
			return err
		}
		if name == "auto_capture_enabled" {
			found = true
		}
	}
	err = rows.Err()
	rows.Close()
	if err != nil {
		return err
	}
	if !found {
		_, err = s.DB.Exec("ALTER TABLE deermate_personal_profiles ADD COLUMN auto_capture_enabled INTEGER NOT NULL DEFAULT 0")
	}
	return err
}

type memoryReader interface{ QueryRow(string, ...any) *sql.Row }

func readProfile(q memoryReader, owner string) (PersonalProfile, error) {
	p := PersonalProfile{Owner: owner, Timezone: "UTC"}
	err := q.QueryRow(`SELECT display_name,timezone,memory_enabled,auto_capture_enabled,proactive_enabled,revision,policy_revision,deletion_revision
FROM deermate_personal_profiles WHERE owner=?`, owner).Scan(&p.DisplayName, &p.Timezone, &p.MemoryEnabled, &p.AutoCaptureEnabled, &p.ProactiveEnabled, &p.Revision, &p.PolicyRevision, &p.DeletionRevision)
	if errors.Is(err, sql.ErrNoRows) {
		err = nil
	}
	return p, err
}

func (s *Store) PersonalProfile(owner string) (PersonalProfile, error) {
	return readProfile(s.DB, owner)
}

func validMemoryText(text string) bool {
	if len(strings.TrimSpace(text)) == 0 || len(text) > 4000 {
		return false
	}
	for _, r := range text {
		if unicode.IsControl(r) && r != '\n' && r != '\t' {
			return false
		}
	}
	lower := strings.ToLower(text)
	for _, marker := range []string{"sk-", "-----begin ", "api_key=", "api key:", "authorization:", "password=", "密码：", "验证码："} {
		if strings.Contains(lower, marker) {
			return false
		}
	}
	return true
}

func (s *Store) UpdatePersonalProfile(ctx context.Context, p PersonalProfile, expected int64) (PersonalProfile, error) {
	if len([]rune(p.DisplayName)) > 80 || strings.IndexFunc(p.DisplayName, unicode.IsControl) >= 0 || p.Timezone == "Local" || len(p.Timezone) > 80 {
		return p, ErrCredentials
	}
	if _, err := time.LoadLocation(p.Timezone); err != nil {
		return p, ErrCredentials
	}
	tx, err := s.DB.BeginTx(ctx, nil)
	if err != nil {
		return p, err
	}
	defer tx.Rollback()
	if _, err = tx.Exec("INSERT OR IGNORE INTO deermate_personal_profiles(owner) VALUES(?)", p.Owner); err != nil {
		return p, err
	}
	current, err := readProfile(tx, p.Owner)
	if err != nil {
		return p, err
	}
	if current.Revision != expected {
		return p, ErrConflict
	}
	p.Revision = current.Revision + 1
	p.DeletionRevision = current.DeletionRevision
	p.PolicyRevision = current.PolicyRevision
	policyChanged := current.MemoryEnabled != p.MemoryEnabled || current.AutoCaptureEnabled != p.AutoCaptureEnabled || current.ProactiveEnabled != p.ProactiveEnabled
	if policyChanged {
		p.PolicyRevision++
	}
	_, err = tx.Exec(`UPDATE deermate_personal_profiles SET display_name=?,timezone=?,memory_enabled=?,auto_capture_enabled=?,proactive_enabled=?,revision=?,policy_revision=? WHERE owner=?`, strings.TrimSpace(p.DisplayName), p.Timezone, p.MemoryEnabled, p.AutoCaptureEnabled, p.ProactiveEnabled, p.Revision, p.PolicyRevision, p.Owner)
	if err != nil {
		return p, err
	}
	// Policy changes invalidate delayed candidates and erase their plaintext envelopes.
	if policyChanged {
		_, err = tx.Exec(`UPDATE deermate_memory_refs SET status='interrupted' WHERE owner=? AND status IN ('pending','updating')`, p.Owner)
		if err == nil {
			_, err = tx.Exec(`UPDATE deermate_memory_operations SET status='invalidated',payload='' WHERE owner=? AND kind!='delete' AND status IN ('pending','processing','uncertain')`, p.Owner)
		}
		if err != nil {
			return p, err
		}
	}
	return p, tx.Commit()
}

func scanMemoryRef(row scanner) (MemoryReference, error) {
	var m MemoryReference
	err := row.Scan(&m.ID, &m.Owner, &m.Category, &m.Scope, &m.Source, &m.Status, &m.Revision, &m.Updated)
	if errors.Is(err, sql.ErrNoRows) {
		err = ErrNotFound
	}
	return m, err
}

const memoryRefColumns = "id,owner,category,scope,source_id,status,revision,updated_at"

func (s *Store) MemoryReferences(owner string) ([]MemoryReference, error) {
	rows, err := s.DB.Query("SELECT "+memoryRefColumns+" FROM deermate_memory_refs WHERE owner=? AND status!='deleted' ORDER BY updated_at DESC,id LIMIT 2000", owner)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []MemoryReference{}
	for rows.Next() {
		m, err := scanMemoryRef(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, m)
	}
	if err = rows.Err(); err != nil {
		return nil, err
	}
	rows.Close()
	// Derive source-unavailable presentation without exposing its old body.
	for i := range out {
		if out[i].Status != "active" {
			continue
		}
		source, e := captureSource(s.DB, out[i].Source)
		if e == nil && (source.Owner != owner || !verifyCapture(s.DB, source)) {
			if _, err = s.DB.Exec("UPDATE deermate_memory_sources SET invalidated_at=max(invalidated_at,?) WHERE operation_id=? AND owner=?", time.Now().Unix(), out[i].Source, owner); err != nil {
				return nil, err
			}
			out[i].Status = "source_unavailable"
		} else if e != nil && !errors.Is(e, sql.ErrNoRows) {
			return nil, e
		}
	}
	return out, nil
}

type memoryMutation struct {
	OperationID      string `json:"operation_id"`
	Content          string `json:"content"`
	Category         string `json:"category"`
	ExpectedRevision int64  `json:"expected_revision"`
}

const memoryOperationColumns = "id,owner,fact_id,kind,status,policy_revision,deletion_revision,payload"

func scanMemoryOperation(row scanner) (MemoryOperation, error) {
	var op MemoryOperation
	err := row.Scan(&op.ID, &op.Owner, &op.FactID, &op.Kind, &op.Status, &op.PolicyRevision, &op.DeletionRevision, &op.Payload)
	if errors.Is(err, sql.ErrNoRows) {
		err = ErrNotFound
	}
	return op, err
}
func (s *Store) MemoryOperation(owner, id string) (MemoryOperation, error) {
	return scanMemoryOperation(s.DB.QueryRow("SELECT "+memoryOperationColumns+" FROM deermate_memory_operations WHERE owner=? AND id=?", owner, id))
}

func (s *Store) AdmitMemory(ctx context.Context, owner, kind, id string, body memoryMutation) (MemoryOperation, error) {
	return s.admitMemory(ctx, owner, kind, id, body, nil)
}

func (s *Store) admitMemory(ctx context.Context, owner, kind, id string, body memoryMutation, source *memoryCapture) (MemoryOperation, error) {
	var empty MemoryOperation
	if !resourceID.MatchString(body.OperationID) {
		return empty, ErrCredentials
	}
	validCategory := body.Category == "preference" || body.Category == "goal" || body.Category == "context"
	if kind != "delete" && (!validMemoryText(body.Content) || !validCategory) {
		return empty, ErrCredentials
	}
	key := digest(owner + "\x00memory\x00" + body.OperationID)
	encoded, _ := json.Marshal(body)
	hash := digest(kind + "\x00" + id + "\x00" + string(encoded))
	tx, err := s.DB.BeginTx(ctx, nil)
	if err != nil {
		return empty, err
	}
	defer tx.Rollback()
	if _, err = tx.Exec("INSERT OR IGNORE INTO deermate_personal_profiles(owner) VALUES(?)", owner); err != nil {
		return empty, err
	}
	var previousHash string
	err = tx.QueryRow("SELECT request_hash FROM deermate_memory_operations WHERE id=? AND owner=?", key, owner).Scan(&previousHash)
	if err == nil {
		if previousHash != hash {
			return empty, ErrConflict
		}
		return scanMemoryOperation(tx.QueryRow("SELECT "+memoryOperationColumns+" FROM deermate_memory_operations WHERE id=?", key))
	}
	if !errors.Is(err, sql.ErrNoRows) {
		return empty, err
	}
	p, err := readProfile(tx, owner)
	if err != nil {
		return empty, err
	}
	if source != nil {
		if !p.MemoryEnabled || !p.AutoCaptureEnabled || p.PolicyRevision != source.Policy || p.DeletionRevision != source.Deleted || !verifyCapture(tx, source) {
			return empty, ErrConflict
		}
		var daily, instance int
		midnight := time.Now().UTC().Truncate(24 * time.Hour).Unix()
		if err = tx.QueryRow("SELECT count(*),coalesce(sum(CASE WHEN owner=? THEN 1 ELSE 0 END),0) FROM deermate_memory_sources WHERE admitted_at>=?", owner, midnight).Scan(&instance, &daily); err != nil {
			return empty, err
		}
		if daily >= 50 || instance >= 500 {
			return empty, ErrConflict
		}
	}
	if kind == "create" {
		if !p.MemoryEnabled {
			return empty, ErrDisabled
		}
		var count int
		err = tx.QueryRow("SELECT count(*) FROM deermate_memory_refs WHERE owner=? AND status!='deleted'", owner).Scan(&count)
		if err != nil {
			return empty, err
		}
		if count >= 2000 {
			return empty, ErrConflict
		}
		var duplicate int
		err = tx.QueryRow("SELECT count(*) FROM deermate_memory_refs WHERE owner=? AND scope='personal' AND category=? AND content_hash=? AND status IN ('pending','active','updating')", owner, body.Category, digest(strings.TrimSpace(body.Content))).Scan(&duplicate)
		if err != nil {
			return empty, err
		}
		if duplicate > 0 {
			return empty, ErrConflict
		}
		id = "mem_" + key[:32]
		_, err = tx.Exec(`INSERT INTO deermate_memory_refs(id,owner,category,source_id,status,content_hash,updated_at) VALUES(?,?,?,?,?,?,?)`, id, owner, body.Category, key, "pending", digest(strings.TrimSpace(body.Content)), time.Now().Unix())
	} else {
		ref, e := scanMemoryRef(tx.QueryRow("SELECT "+memoryRefColumns+" FROM deermate_memory_refs WHERE id=? AND owner=?", id, owner))
		if e != nil {
			return empty, e
		}
		if ref.Revision != body.ExpectedRevision || (kind == "update" && ref.Status != "active") {
			return empty, ErrConflict
		}
		var busy int
		e = tx.QueryRow("SELECT count(*) FROM deermate_memory_operations WHERE fact_id=? AND status IN ('pending','processing','uncertain')", id).Scan(&busy)
		if e != nil {
			return empty, e
		}
		if kind == "update" && busy > 0 {
			return empty, ErrConflict
		}
		if kind == "delete" {
			p.DeletionRevision++
			_, err = tx.Exec("UPDATE deermate_personal_profiles SET deletion_revision=? WHERE owner=?", p.DeletionRevision, owner)
			if err == nil {
				_, err = tx.Exec("INSERT OR REPLACE INTO deermate_memory_barriers VALUES(?,?,?,?)", owner, id, p.DeletionRevision, time.Now().Unix())
			}
			if err == nil {
				_, err = tx.Exec("UPDATE deermate_memory_refs SET status='suppressed',updated_at=? WHERE id=?", time.Now().Unix(), id)
			}
			if err == nil {
				_, err = tx.Exec("UPDATE deermate_memory_operations SET status='invalidated',payload='' WHERE owner=? AND fact_id=? AND status IN ('pending','processing','uncertain')", owner, id)
			}
		} else {
			p.DeletionRevision++
			if _, err = tx.Exec("UPDATE deermate_personal_profiles SET deletion_revision=? WHERE owner=?", p.DeletionRevision, owner); err != nil {
				return empty, err
			}
			// Stop using an old fact immediately while its correction is delivered.
			_, err = tx.Exec("UPDATE deermate_memory_refs SET status='updating',updated_at=? WHERE id=?", time.Now().Unix(), id)
		}
	}
	if err != nil {
		return empty, err
	}
	op := MemoryOperation{ID: key, Owner: owner, FactID: id, Kind: kind, Status: "pending", PolicyRevision: p.PolicyRevision, DeletionRevision: p.DeletionRevision, Payload: string(encoded)}
	_, err = tx.Exec(`INSERT INTO deermate_memory_operations(id,owner,fact_id,kind,status,policy_revision,deletion_revision,request_hash,payload,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)`, op.ID, owner, id, kind, op.Status, p.PolicyRevision, p.DeletionRevision, hash, op.Payload, time.Now().Unix())
	if err != nil {
		return empty, err
	}
	if source != nil {
		_, err = tx.Exec(`INSERT INTO deermate_memory_sources(operation_id,owner,thread_id,run_id,message_id,message_hash,incarnation,policy_revision,deletion_revision,observed_at,admitted_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)`, op.ID, owner, source.Thread, source.Run, source.Message, source.Hash, source.Incarnation, source.Policy, source.Deleted, source.Observed, time.Now().Unix())
		if err != nil {
			return empty, err
		}
	}
	if kind == "update" || kind == "delete" {
		if err = invalidateCaptured(tx, owner, p.DeletionRevision); err != nil {
			return empty, err
		}
	}
	return op, tx.Commit()
}

func (s *Store) claimMemory(ctx context.Context, owner, id string) (MemoryOperation, error) {
	tx, err := s.DB.BeginTx(ctx, nil)
	if err != nil {
		return MemoryOperation{}, err
	}
	defer tx.Rollback()
	op, err := scanMemoryOperation(tx.QueryRow("SELECT "+memoryOperationColumns+" FROM deermate_memory_operations WHERE owner=? AND id=?", owner, id))
	if err != nil {
		return op, err
	}
	result, err := tx.Exec(`UPDATE deermate_memory_operations SET status='processing',lease_until=? WHERE id=? AND (status='pending' OR (status IN ('processing','uncertain') AND lease_until<?))`, time.Now().Add(90*time.Second).Unix(), id, time.Now().Unix())
	if err != nil {
		return op, err
	}
	n, _ := result.RowsAffected()
	if n != 1 {
		return op, ErrConflict
	}
	op.Status = "processing"
	return op, tx.Commit()
}

func (s *Store) finishMemory(ctx context.Context, op MemoryOperation, revision int64, category string, callErr error) error {
	tx, err := s.DB.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	var status string
	if err = tx.QueryRow("SELECT status FROM deermate_memory_operations WHERE id=?", op.ID).Scan(&status); err != nil {
		return err
	}
	if status != "processing" {
		return nil
	}
	stale := false
	source, sourceErr := captureSource(tx, op.ID)
	if sourceErr == nil {
		profile, e := readProfile(tx, op.Owner)
		if e != nil {
			return e
		}
		stale = profile.PolicyRevision != source.Policy || profile.DeletionRevision != source.Deleted || !verifyCapture(tx, source)
	} else if !errors.Is(sourceErr, sql.ErrNoRows) {
		return sourceErr
	}
	if stale {
		if _, err = tx.Exec("UPDATE deermate_memory_sources SET invalidated_at=max(invalidated_at,?) WHERE operation_id=?", time.Now().Unix(), op.ID); err != nil {
			return err
		}
		_, err = tx.Exec("UPDATE deermate_memory_operations SET status='invalidated',payload='' WHERE id=?", op.ID)
		if err == nil {
			_, err = tx.Exec("UPDATE deermate_memory_refs SET status='interrupted' WHERE id=? AND status IN ('pending','updating')", op.FactID)
		}
	} else if callErr != nil {
		_, err = tx.Exec("UPDATE deermate_memory_operations SET status='uncertain',lease_until=? WHERE id=?", time.Now().Add(time.Minute).Unix(), op.ID)
	} else {
		p, e := readProfile(tx, op.Owner)
		if e != nil {
			return e
		}
		var forgotten int
		if err = tx.QueryRow("SELECT count(*) FROM deermate_memory_barriers WHERE owner=? AND fact_id=?", op.Owner, op.FactID).Scan(&forgotten); err != nil {
			return err
		}
		// Explicit deliveries address one fixed fact. An unrelated deletion may
		// invalidate cached contexts, but cannot cancel this fact's valid intent.
		if op.Kind != "delete" && (p.PolicyRevision != op.PolicyRevision || forgotten > 0) {
			_, err = tx.Exec("UPDATE deermate_memory_operations SET status='invalidated',payload='' WHERE id=?", op.ID)
		} else {
			state := "active"
			if op.Kind == "delete" {
				state = "deleted"
			}
			var payload memoryMutation
			_ = json.Unmarshal([]byte(op.Payload), &payload)
			_, err = tx.Exec("UPDATE deermate_memory_refs SET status=?,revision=?,category=?,source_id=?,content_hash=?,updated_at=? WHERE owner=? AND id=?", state, revision, category, op.ID, digest(strings.TrimSpace(payload.Content)), time.Now().Unix(), op.Owner, op.FactID)
			if err == nil {
				_, err = tx.Exec("UPDATE deermate_memory_operations SET status='completed',payload='' WHERE id=?", op.ID)
			}
		}
	}
	if err != nil {
		return err
	}
	return tx.Commit()
}

func invalidateCaptured(tx *sql.Tx, owner string, deleted int64) error {
	_, err := tx.Exec(`UPDATE deermate_memory_refs SET status='interrupted' WHERE id IN
 (SELECT o.fact_id FROM deermate_memory_operations o JOIN deermate_memory_sources s ON s.operation_id=o.id
 WHERE s.owner=? AND s.deletion_revision!=? AND o.status IN ('pending','processing','uncertain'))`, owner, deleted)
	if err != nil {
		return err
	}
	_, err = tx.Exec(`UPDATE deermate_memory_operations SET status='invalidated',payload='' WHERE id IN
 (SELECT operation_id FROM deermate_memory_sources WHERE owner=? AND deletion_revision!=?)
 AND status IN ('pending','processing','uncertain')`, owner, deleted)
	return err
}
