package controlplane

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"regexp"
	"strings"
)

type memoryCandidate struct {
	Content  string `json:"content"`
	Category string `json:"category"`
	Scope    string `json:"scope,omitempty"`
	Project  string `json:"project,omitempty"`
	Slot     string `json:"slot,omitempty"`
	Evidence string `json:"evidence,omitempty"`
}

var naturalProject = regexp.MustCompile(`^([\pL][\pL0-9_-]{1,39}?)\s*(?:项目)?(?:的)?(?:主后端|控制端|后端|前端|[Ww]orker)`)
var memorySentences = regexp.MustCompile(`[\r\n。；;]+`)
var memorySecretPattern = regexp.MustCompile(`(?i)(?:密码|验证码|短信码|动态码|私钥|密钥|api[_ -]?key|password|passcode|otp|access[_ -]?token|client[_ -]?secret)[：:=\s]*(?:是|为|is)?[：:=\s]*[a-z0-9_./+\-]{3,}|\b[0-9]{12,19}[x]?\b`)

func automaticMemorySafe(text string) bool {
	if !validMemoryText(text) || strings.ContainsAny(text, "`<>\"“”") {
		return false
	}
	lower := strings.ToLower(text)
	for _, term := range []string{"引用", "他说", "她说", "别人说", "网页写", "原文", "测试样本", "验收样本", "示例：", "示例:", "do not remember", "don't remember", "不要记", "别记", "不要保存", "病史", "确诊", "诊断", "身份证", "银行卡", "信用卡", "年薪", "财务状况", "同事的", "朋友的", "diagnosis", "medical history", "my salary"} {
		if strings.Contains(lower, term) {
			return false
		}
	}
	return true
}

func memoryMayExtract(text string) bool {
	if memoryControl(text) {
		return true
	}
	if strings.ContainsAny(text, "?？") || containsMemoryTerm(text, "按已保存", "你保存的", "我之前说的", "偏好是什么", "偏好有哪些") {
		return false
	}
	strong := containsMemoryTerm(strings.ToLower(text), "偏好", "更喜欢", "喜欢用", "习惯", "以后", "这次", "本次", "长期目标", "我正在", "我在学", "我的目标", "i prefer", "i like", "my goal")
	project := strings.Contains(text, "项目") && containsMemoryTerm(text, "采用", "使用", "保持", "改为", "必须", "统一用")
	return automaticMemorySafe(text) && !containsMemoryTerm(text, "哪个", "哪种", "喜欢什么", "是否喜欢") && (strong || project)
}

func memoryControl(text string) bool {
	switch strings.Trim(strings.TrimSpace(text), "。.!！") {
	case "刚才那条已经过时", "刚才那条记忆已经过时", "忘记刚才那条记忆", "不要再记住刚才那条", "forget that last memory":
		return true
	}
	return false
}

// A bounded fast path for explicit everyday statements. General language goes
// through the separately admitted extraction queue, never a greedy full-chat regex.
func naturalMemories(text string) []memoryCandidate {
	if !automaticMemorySafe(text) {
		return nil
	}
	if content, category, ok := explicitMemory(text); ok {
		return []memoryCandidate{{Content: content, Category: category}}
	}
	var out []memoryCandidate
	for _, sentence := range memorySentences.Split(strings.TrimSpace(text), -1) {
		part := strings.TrimSpace(sentence)
		lower := strings.ToLower(part)
		if len([]rune(part)) < 5 || strings.ContainsAny(part, "？?") {
			continue
		}
		c := memoryCandidate{Content: part, Category: "preference"}
		switch {
		case strings.HasPrefix(part, "开始开发"), strings.HasPrefix(part, "开始实现"), strings.HasPrefix(part, "现在开始开发"), strings.HasPrefix(part, "下面开始开发"), strings.HasPrefix(part, "下面开始实现"), strings.HasPrefix(part, "接下来开始写代码"):
			c.Scope, c.Category, c.Slot = "topic", "context", "current_phase"
		case strings.HasPrefix(part, "这次"), strings.HasPrefix(part, "本次"), strings.HasPrefix(lower, "this time "):
			c.Scope, c.Category, c.Slot = "topic", "context", "current_phase"
		case naturalProject.MatchString(part):
			label := naturalProject.FindStringSubmatch(part)[1]
			if label == "这个" || label == "当前" || label == "我的" || label == "本次" {
				c.Scope, c.Category, c.Slot = "topic", "context", "project_requirement"
			} else {
				c.Scope, c.Category, c.Project = "project", "context", label
				c.Slot = ""
			}
		case strings.HasPrefix(part, "以后") && containsMemoryTerm(part, "回答", "回复", "答复", "结论", "文档", "说明", "写作"):
			c.Slot = "response_style"
			if containsMemoryTerm(part, "文档", "说明") {
				c.Slot = "document_style"
			}
		case strings.HasPrefix(part, "回答时"), strings.HasPrefix(part, "回复时"), strings.HasPrefix(part, "我偏好"), strings.HasPrefix(part, "我习惯"), strings.HasPrefix(part, "我喜欢"), strings.HasPrefix(lower, "i prefer "), strings.HasPrefix(lower, "i like "):
			if containsMemoryTerm(lower, "项目", "仓库", "project", "repository") {
				c.Scope, c.Category = "topic", "context"
			} else if containsMemoryTerm(lower, "回答", "回复", "答复", "结论", "answer", "response") {
				c.Slot = "response_style"
			}
		case strings.HasPrefix(part, "我的长期目标是"), strings.HasPrefix(lower, "my long-term goal is "):
			c.Category = "goal"
		default:
			continue
		}
		out = append(out, c)
		if len(out) == 3 {
			break
		}
	}
	return out
}

func containsMemoryTerm(value string, terms ...string) bool {
	for _, term := range terms {
		if strings.Contains(value, term) {
			return true
		}
	}
	return false
}

func candidateScope(c memoryCandidate, source memoryCapture) string {
	switch c.Scope {
	case "project":
		return "project:" + projectMemoryKey(c.Project)
	case "topic":
		return "topic:" + source.Thread
	default:
		return "personal"
	}
}

func (s *Store) admitNaturalMemory(ctx context.Context, source memoryCapture, c memoryCandidate, index int) (MemoryOperation, error) {
	nonce := "chat-" + digest(source.Owner + "\x00" + source.Thread + "\x00" + source.Message + "\x00" + source.Hash)[:58]
	if index > 0 {
		nonce = nonce[:60] + fmt.Sprintf("-%d", index)
	}
	key := digest(source.Owner + "\x00memory\x00" + nonce)
	// Resolve a retry before looking for a correction target: the first attempt
	// may already have created the slot. A retry must not turn create into update.
	if prior, err := s.MemoryOperation(source.Owner, key); err == nil {
		return prior, nil
	} else if !errors.Is(err, ErrNotFound) {
		return MemoryOperation{}, err
	}
	b := memoryMutation{OperationID: nonce, Content: c.Content, Category: c.Category, Scope: c.Scope, Project: c.Project, Slot: c.Slot}
	kind, target := "create", ""
	if c.Slot != "" {
		ref, err := scanMemoryRef(s.DB.QueryRow("SELECT "+memoryRefColumns+" FROM deermate_memory_refs WHERE owner=? AND scope=? AND slot=? AND status='active' ORDER BY updated_at DESC,id LIMIT 1", source.Owner, candidateScope(c, source), c.Slot))
		if err == nil {
			if source.Job != "" {
				var historical int
				_ = s.DB.QueryRow("SELECT count(*) FROM deermate_memory_history_items WHERE owner=? AND job_id=?", source.Owner, source.Job).Scan(&historical)
				if historical > 0 {
					return s.MemoryOperation(source.Owner, ref.Source)
				}
			}
			kind, target, b.ExpectedRevision = "update", ref.ID, ref.Revision
		} else if !errors.Is(err, ErrNotFound) {
			return MemoryOperation{}, err
		}
	} else {
		// Repeating an identical fact is a known no-op, not a storage conflict
		// that keeps the durable extraction queue retrying forever.
		ref, err := scanMemoryRef(s.DB.QueryRow("SELECT "+memoryRefColumns+" FROM deermate_memory_refs WHERE owner=? AND scope=? AND category=? AND content_hash=? AND status='active' LIMIT 1", source.Owner, candidateScope(c, source), c.Category, digest(strings.TrimSpace(c.Content))))
		if err == nil && verifyCapture(s.DB, &source) && captureAllowed(s.DB, source.Owner, source.Thread) {
			prior, priorErr := captureSource(s.DB, ref.Source)
			if priorErr != nil && !errors.Is(priorErr, sql.ErrNoRows) {
				return MemoryOperation{}, priorErr
			}
			if priorErr == nil && !verifyCapture(s.DB, prior) {
				// A newly stated fact may replace a revoked source. The old
				// operation itself remains invalid and is never replayed.
				kind, target, b.ExpectedRevision = "update", ref.ID, ref.Revision
			} else {
				return s.MemoryOperation(source.Owner, ref.Source)
			}
		} else if err != nil && !errors.Is(err, ErrNotFound) {
			return MemoryOperation{}, err
		}
	}
	return s.admitMemory(ctx, source.Owner, kind, target, b, &source)
}
