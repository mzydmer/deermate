package controlplane

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"database/sql"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net/mail"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"

	"golang.org/x/crypto/bcrypt"
	_ "modernc.org/sqlite"
)

var (
	ErrNotFound    = errors.New("not found")
	ErrConflict    = errors.New("account conflict")
	ErrLastAdmin   = errors.New("cannot remove the last active administrator")
	ErrCredentials = errors.New("invalid credentials")
	ErrDisabled    = errors.New("account disabled")
)

type User struct {
	ID          string   `json:"id"`
	Email       string   `json:"email"`
	Role        string   `json:"system_role"`
	Disabled    bool     `json:"disabled"`
	NeedsSetup  bool     `json:"needs_setup"`
	OAuth       *string  `json:"oauth_provider"`
	Permissions []string `json:"permissions"`
	Password    string   `json:"-"`
	Version     int      `json:"-"`
}

type Session struct {
	User                User
	TokenHash, CSRFHash string
	Expires             int64
}
type Store struct{ DB *sql.DB }
type Audit struct {
	ID     int64  `json:"id"`
	Actor  string `json:"actor_id"`
	Action string `json:"action"`
	Target string `json:"target_id"`
	At     int64  `json:"created_at"`
}

func OpenStore(filename string) (*Store, error) {
	if err := os.MkdirAll(filepath.Dir(filename), 0700); err != nil {
		return nil, err
	}
	// Set private permissions before SQLite creates its WAL/shared-memory files.
	f, err := os.OpenFile(filename, os.O_CREATE|os.O_RDWR, 0600)
	if err != nil {
		return nil, err
	}
	if err = f.Chmod(0600); err != nil {
		f.Close()
		return nil, err
	}
	if err = f.Close(); err != nil {
		return nil, err
	}
	u := url.URL{Scheme: "file", Path: filename}
	q := u.Query()
	q.Add("_pragma", "busy_timeout(5000)")
	q.Add("_pragma", "foreign_keys(1)")
	q.Add("_pragma", "journal_mode(WAL)")
	u.RawQuery = q.Encode()
	db, err := sql.Open("sqlite", u.String())
	if err != nil {
		return nil, err
	}
	db.SetMaxOpenConns(1)
	s := &Store{DB: db}
	if err = s.initialize(); err != nil {
		db.Close()
		return nil, err
	}
	if err = os.Chmod(filename, 0600); err != nil {
		db.Close()
		return nil, err
	}
	return s, nil
}

func (s *Store) initialize() error {
	_, err := s.DB.Exec(`CREATE TABLE IF NOT EXISTS users (
 id VARCHAR(36) PRIMARY KEY, email VARCHAR(320) NOT NULL, password_hash VARCHAR(128),
 system_role VARCHAR(16) NOT NULL DEFAULT 'user', created_at DATETIME NOT NULL,
 oauth_provider VARCHAR(32), oauth_id VARCHAR(128), needs_setup BOOLEAN NOT NULL DEFAULT 0,
 token_version INTEGER NOT NULL DEFAULT 0, disabled BOOLEAN NOT NULL DEFAULT 0)`)
	if err != nil {
		return err
	}
	rows, err := s.DB.Query("PRAGMA table_info(users)")
	if err != nil {
		return err
	}
	columns := map[string]bool{}
	for rows.Next() {
		var cid, notnull, pk int
		var name, typ string
		var def any
		if err = rows.Scan(&cid, &name, &typ, &notnull, &def, &pk); err != nil {
			rows.Close()
			return err
		}
		columns[name] = true
	}
	err = rows.Err()
	rows.Close()
	if err != nil {
		return err
	}
	for _, name := range []string{"id", "email", "password_hash", "system_role", "created_at", "oauth_provider", "needs_setup", "token_version", "disabled"} {
		if !columns[name] {
			return fmt.Errorf("unsupported pinned users schema: missing %s", name)
		}
	}
	_, err = s.DB.Exec(`CREATE UNIQUE INDEX IF NOT EXISTS deermate_users_email_fold ON users(lower(email));
 CREATE TABLE IF NOT EXISTS user_preferences (user_id VARCHAR(36) NOT NULL REFERENCES users(id), key VARCHAR(40) NOT NULL, value JSON, PRIMARY KEY(user_id,key));
 CREATE TABLE IF NOT EXISTS deermate_control_meta (key TEXT PRIMARY KEY,value TEXT NOT NULL);
 INSERT OR IGNORE INTO deermate_control_meta VALUES('accounts','locked');
 CREATE TABLE IF NOT EXISTS deermate_sessions (token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),csrf_hash TEXT NOT NULL,token_version INTEGER NOT NULL,expires_at INTEGER NOT NULL,created_at INTEGER NOT NULL);
 CREATE INDEX IF NOT EXISTS deermate_sessions_user ON deermate_sessions(user_id);
 CREATE TABLE IF NOT EXISTS deermate_audit (id INTEGER PRIMARY KEY AUTOINCREMENT,actor_id TEXT NOT NULL,action TEXT NOT NULL,target_id TEXT NOT NULL,created_at INTEGER NOT NULL);
 CREATE TABLE IF NOT EXISTS deermate_login_attempts (key TEXT PRIMARY KEY,failures INTEGER NOT NULL,window_start INTEGER NOT NULL);`)
	return err
}

const userColumns = "id,email,coalesce(password_hash,''),system_role,disabled,needs_setup,token_version,oauth_provider"

type scanner interface{ Scan(...any) error }

func scanUser(row scanner) (User, error) {
	var u User
	err := row.Scan(&u.ID, &u.Email, &u.Password, &u.Role, &u.Disabled, &u.NeedsSetup, &u.Version, &u.OAuth)
	if errors.Is(err, sql.ErrNoRows) {
		return u, ErrNotFound
	}
	u.Permissions = []string{"threads:read"}
	if u.Role == "admin" {
		u.Permissions = []string{"threads:read", "threads:create", "threads:delete", "runs:create", "runs:cancel"}
	}
	return u, err
}
func (s *Store) User(id string) (User, error) {
	return scanUser(s.DB.QueryRow("SELECT "+userColumns+" FROM users WHERE id=?", id))
}
func (s *Store) UserByEmail(email string) (User, error) {
	return scanUser(s.DB.QueryRow("SELECT "+userColumns+" FROM users WHERE lower(email)=?", strings.ToLower(strings.TrimSpace(email))))
}
func (s *Store) Users() ([]User, error) {
	rows, err := s.DB.Query("SELECT " + userColumns + " FROM users ORDER BY created_at,id LIMIT 1000")
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []User{}
	for rows.Next() {
		u, e := scanUser(rows)
		if e != nil {
			return nil, e
		}
		out = append(out, u)
	}
	return out, rows.Err()
}
func (s *Store) Initialized() (bool, error) {
	var count int
	err := s.DB.QueryRow("SELECT count(*) FROM users WHERE system_role='admin'").Scan(&count)
	return count > 0, err
}

func opaque() string {
	var data [32]byte
	if _, err := rand.Read(data[:]); err != nil {
		panic(err)
	}
	return base64.RawURLEncoding.EncodeToString(data[:])
}
func digest(text string) string { v := sha256.Sum256([]byte(text)); return hex.EncodeToString(v[:]) }
func uuid() string {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		panic(err)
	}
	b[6] = (b[6] & 15) | 64
	b[8] = (b[8] & 63) | 128
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}
func prehash(password string) []byte {
	sum := sha256.Sum256([]byte(password))
	return []byte(base64.StdEncoding.EncodeToString(sum[:]))
}
func hashPassword(password string, cost int) (string, error) {
	b, err := bcrypt.GenerateFromPassword(prehash(password), cost)
	return "$dfv2$" + string(b), err
}
func verifyPassword(password, encoded string) bool {
	var input []byte
	if strings.HasPrefix(encoded, "$dfv2$") {
		input = prehash(password)
		encoded = strings.TrimPrefix(encoded, "$dfv2$")
	} else {
		input = []byte(password)
		encoded = strings.TrimPrefix(encoded, "$dfv1$")
	}
	return bcrypt.CompareHashAndPassword([]byte(encoded), input) == nil
}
func validPassword(password string) bool {
	return len(password) >= 12 && len(password) <= 1024 && !map[string]bool{"password1234": true, "123456789012": true, "abcdefghijkl": true}[strings.ToLower(password)]
}
func validEmail(email string) bool {
	address, err := mail.ParseAddress(email)
	if err != nil || address.Address != email || len(email) > 254 {
		return false
	}
	local, domain, ok := strings.Cut(email, "@")
	if !ok || len(local) == 0 || len(local) > 64 || strings.HasPrefix(local, ".") || strings.HasSuffix(local, ".") || strings.Contains(local, "..") {
		return false
	}
	for _, c := range local {
		if c > 127 || c <= 32 || strings.ContainsRune("<>()[\\],;:\"", c) {
			return false
		}
	}
	labels := strings.Split(domain, ".")
	if len(labels) < 2 {
		return false
	}
	tld := labels[len(labels)-1]
	if len(tld) < 2 || map[string]bool{"arpa": true, "invalid": true, "local": true, "localhost": true, "onion": true, "test": true}[tld] {
		return false
	}
	for _, label := range labels {
		if len(label) == 0 || len(label) > 63 || label[0] == '-' || label[len(label)-1] == '-' {
			return false
		}
		for _, c := range label {
			if !(c >= 'a' && c <= 'z' || c >= '0' && c <= '9' || c == '-') {
				return false
			}
		}
	}
	for _, c := range tld {
		if c < 'a' || c > 'z' {
			return false
		}
	}
	return true
}

// The first write serializes account decisions across SQLite connections,
// before any count/read. It protects bootstrap and combined role/disable edits.
func (s *Store) accountTx(ctx context.Context) (*sql.Tx, error) {
	tx, err := s.DB.BeginTx(ctx, nil)
	if err != nil {
		return nil, err
	}
	if _, err = tx.ExecContext(ctx, "UPDATE deermate_control_meta SET value=value WHERE key='accounts'"); err != nil {
		tx.Rollback()
		return nil, err
	}
	return tx, nil
}
func auditTx(tx *sql.Tx, actor, action, target string) error {
	_, err := tx.Exec("INSERT INTO deermate_audit(actor_id,action,target_id,created_at) VALUES(?,?,?,?)", actor, action, target, time.Now().Unix())
	return err
}

func (s *Store) CreateUser(ctx context.Context, email, password, role, actor string, bootstrap bool, cost int) (User, error) {
	var zero User
	email = strings.ToLower(strings.TrimSpace(email))
	if !validEmail(email) || !validPassword(password) || (role != "admin" && role != "user") {
		return zero, ErrCredentials
	}
	hash, err := hashPassword(password, cost)
	if err != nil {
		return zero, err
	}
	tx, err := s.accountTx(ctx)
	if err != nil {
		return zero, err
	}
	defer tx.Rollback()
	if bootstrap {
		var count int
		if err = tx.QueryRow("SELECT count(*) FROM users WHERE system_role='admin'").Scan(&count); err != nil {
			return zero, err
		}
		if count > 0 {
			return zero, ErrConflict
		}
		role = "admin"
	}
	var count int
	if err = tx.QueryRow("SELECT count(*) FROM users WHERE lower(email)=?", email).Scan(&count); err != nil {
		return zero, err
	}
	if count > 0 {
		return zero, ErrConflict
	}
	id := uuid()
	_, err = tx.Exec("INSERT INTO users(id,email,password_hash,system_role,created_at,needs_setup,token_version,disabled) VALUES(?,?,?,?,?,0,0,0)", id, email, hash, role, time.Now().UTC().Format("2006-01-02 15:04:05.000000"))
	if err != nil {
		return zero, err
	}
	if err = auditTx(tx, actor, "user.create", id); err != nil {
		return zero, err
	}
	if err = tx.Commit(); err != nil {
		return zero, err
	}
	return s.User(id)
}

func (s *Store) UpdateUser(ctx context.Context, id string, role *string, disabled *bool, actor string) (User, error) {
	var zero User
	if role == nil && disabled == nil {
		return zero, ErrCredentials
	}
	if role != nil && *role != "admin" && *role != "user" {
		return zero, ErrCredentials
	}
	tx, err := s.accountTx(ctx)
	if err != nil {
		return zero, err
	}
	defer tx.Rollback()
	u, err := scanUser(tx.QueryRow("SELECT "+userColumns+" FROM users WHERE id=?", id))
	if err != nil {
		return zero, err
	}
	newRole, newDisabled := u.Role, u.Disabled
	if role != nil {
		newRole = *role
	}
	if disabled != nil {
		newDisabled = *disabled
	}
	if u.Role == "admin" && !u.Disabled && (newRole != "admin" || newDisabled) {
		var count int
		err = tx.QueryRow("SELECT count(*) FROM users WHERE system_role='admin' AND disabled=0").Scan(&count)
		if err != nil {
			return zero, err
		}
		if count <= 1 {
			return zero, ErrLastAdmin
		}
	}
	_, err = tx.Exec("UPDATE users SET system_role=?,disabled=?,token_version=token_version+1 WHERE id=?", newRole, newDisabled, id)
	if err != nil {
		return zero, err
	}
	if _, err = tx.Exec("DELETE FROM deermate_sessions WHERE user_id=?", id); err != nil {
		return zero, err
	}
	if err = auditTx(tx, actor, "user.update", id); err != nil {
		return zero, err
	}
	if err = tx.Commit(); err != nil {
		return zero, err
	}
	return s.User(id)
}

func (s *Store) SetPassword(ctx context.Context, id, password, actor string, expectedVersion int, cost int) error {
	if !validPassword(password) {
		return ErrCredentials
	}
	hash, err := hashPassword(password, cost)
	if err != nil {
		return err
	}
	tx, err := s.accountTx(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	u, err := scanUser(tx.QueryRow("SELECT "+userColumns+" FROM users WHERE id=?", id))
	if err != nil {
		return err
	}
	if expectedVersion >= 0 && u.Version != expectedVersion {
		return ErrConflict
	}
	if _, err = tx.Exec("UPDATE users SET password_hash=?,token_version=token_version+1,needs_setup=0 WHERE id=?", hash, id); err != nil {
		return err
	}
	if _, err = tx.Exec("DELETE FROM deermate_sessions WHERE user_id=?", id); err != nil {
		return err
	}
	if err = auditTx(tx, actor, "user.password_change", id); err != nil {
		return err
	}
	return tx.Commit()
}

func (s *Store) NewSession(ctx context.Context, u User, lifetime time.Duration) (string, string, error) {
	raw, csrf := opaque(), opaque()
	tx, err := s.accountTx(ctx)
	if err != nil {
		return "", "", err
	}
	defer tx.Rollback()
	current, err := scanUser(tx.QueryRow("SELECT "+userColumns+" FROM users WHERE id=?", u.ID))
	if err != nil {
		return "", "", err
	}
	if current.Disabled || current.Version != u.Version {
		return "", "", ErrCredentials
	}
	now := time.Now().Unix()
	if _, err = tx.Exec("DELETE FROM deermate_sessions WHERE expires_at<=?", now); err != nil {
		return "", "", err
	}
	_, err = tx.Exec("INSERT INTO deermate_sessions VALUES(?,?,?,?,?,?)", digest(raw), u.ID, digest(csrf), u.Version, time.Now().Add(lifetime).Unix(), now)
	if err != nil {
		return "", "", err
	}
	if err = auditTx(tx, u.ID, "session.create", u.ID); err != nil {
		return "", "", err
	}
	if err = tx.Commit(); err != nil {
		return "", "", err
	}
	return raw, csrf, nil
}
func (s *Store) Session(raw string) (Session, error) {
	var out Session
	if len(raw) != 43 {
		return out, ErrCredentials
	}
	var id string
	var version int
	err := s.DB.QueryRow("SELECT user_id,csrf_hash,token_version,expires_at FROM deermate_sessions WHERE token_hash=?", digest(raw)).Scan(&id, &out.CSRFHash, &version, &out.Expires)
	if errors.Is(err, sql.ErrNoRows) {
		return out, ErrCredentials
	}
	if err != nil {
		return out, err
	}
	u, err := s.User(id)
	if err != nil {
		return out, err
	}
	if u.Disabled {
		return out, ErrDisabled
	}
	if version != u.Version || out.Expires <= time.Now().Unix() {
		return out, ErrCredentials
	}
	out.User = u
	out.TokenHash = digest(raw)
	return out, nil
}
func (s *Store) Logout(ctx context.Context, session Session) error {
	tx, err := s.accountTx(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	if _, err = tx.Exec("DELETE FROM deermate_sessions WHERE token_hash=?", session.TokenHash); err != nil {
		return err
	}
	if err = auditTx(tx, session.User.ID, "session.logout", session.User.ID); err != nil {
		return err
	}
	return tx.Commit()
}
func (s *Store) SessionList(user string) ([]map[string]any, error) {
	rows, err := s.DB.Query("SELECT token_hash,created_at,expires_at FROM deermate_sessions WHERE user_id=? AND expires_at>? ORDER BY created_at DESC LIMIT 100", user, time.Now().Unix())
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []map[string]any{}
	for rows.Next() {
		var id string
		var at, expires int64
		if err = rows.Scan(&id, &at, &expires); err != nil {
			return nil, err
		}
		out = append(out, map[string]any{"id": id, "created_at": at, "expires_at": expires})
	}
	return out, rows.Err()
}
func (s *Store) RevokeSession(user, id string) error {
	r, err := s.DB.Exec("DELETE FROM deermate_sessions WHERE user_id=? AND token_hash=?", user, id)
	if err != nil {
		return err
	}
	n, _ := r.RowsAffected()
	if n == 0 {
		return ErrNotFound
	}
	return nil
}
func (s *Store) Audits() ([]Audit, error) {
	rows, err := s.DB.Query("SELECT id,actor_id,action,target_id,created_at FROM deermate_audit ORDER BY id DESC LIMIT 100")
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []Audit{}
	for rows.Next() {
		var a Audit
		if err = rows.Scan(&a.ID, &a.Actor, &a.Action, &a.Target, &a.At); err != nil {
			return nil, err
		}
		out = append(out, a)
	}
	return out, rows.Err()
}

func (s *Store) LoginAllowed(key string) (bool, error) {
	var count int
	var start int64
	err := s.DB.QueryRow("SELECT failures,window_start FROM deermate_login_attempts WHERE key=?", key).Scan(&count, &start)
	if errors.Is(err, sql.ErrNoRows) {
		return true, nil
	}
	return count < 7 || time.Now().Unix()-start >= 600, err
}
func (s *Store) LoginFailure(key string) error {
	now := time.Now().Unix()
	_, err := s.DB.Exec(`INSERT INTO deermate_login_attempts VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET failures=CASE WHEN ?-window_start>=600 THEN 1 ELSE failures+1 END,window_start=CASE WHEN ?-window_start>=600 THEN ? ELSE window_start END`, key, now, now, now, now)
	return err
}
func (s *Store) LoginSuccess(key string) error {
	_, err := s.DB.Exec("DELETE FROM deermate_login_attempts WHERE key=?", key)
	return err
}

func (s *Store) Preferences(id string) (map[string]any, error) {
	rows, err := s.DB.Query("SELECT key,value FROM user_preferences WHERE user_id=?", id)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := map[string]any{"notification_enabled": nil, "model_name": nil, "mode": nil, "reasoning_effort": nil, "locale": nil}
	for rows.Next() {
		var k string
		var b []byte
		if err = rows.Scan(&k, &b); err != nil {
			return nil, err
		}
		if _, ok := out[k]; ok {
			var v any
			if json.Unmarshal(b, &v) == nil {
				out[k] = v
			}
		}
	}
	return out, rows.Err()
}
func (s *Store) SetPreferences(ctx context.Context, id string, values map[string]any) error {
	tx, err := s.DB.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	for k, v := range values {
		if v == nil {
			_, err = tx.Exec("DELETE FROM user_preferences WHERE user_id=? AND key=?", id, k)
		} else {
			b, e := json.Marshal(v)
			if e != nil {
				return e
			}
			_, err = tx.Exec("INSERT INTO user_preferences(user_id,key,value) VALUES(?,?,?) ON CONFLICT(user_id,key) DO UPDATE SET value=excluded.value", id, k, string(b))
		}
		if err != nil {
			return err
		}
	}
	return tx.Commit()
}
