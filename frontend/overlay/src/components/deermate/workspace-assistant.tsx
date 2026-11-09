"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Clock3, MessageSquarePlus, Shield } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { WorkspaceSidebarTrigger } from "@/components/workspace/workspace-sidebar-trigger";
import { useAuth } from "@/core/auth/AuthProvider";
import { useI18n } from "@/core/i18n/hooks";

import { GoalSuggestions } from "./goal-suggestions";
import { PersonalGreeting, PersonalMemoryPanel } from "./personal-memory";
import { SecretaryConversation } from "./secretary-conversation";
import { workspaceAPI } from "./workspace-api";
import { HistoryProgress } from "./workspace-memory";

type Focus = {
  id: string;
  kind: string;
  title: string;
  thread_id?: string;
  work_id?: string;
  seen: boolean;
  reason: string;
  evidence: {
    version: string;
    status: string;
    verified: boolean;
    validation_failed: boolean;
    stale: boolean;
    tracking_degraded: boolean;
    occurred_at: string;
    checked_at: number;
  };
};
type Snapshot = {
  checked_at: number;
  profile: {
    memory_enabled: boolean;
    auto_capture_enabled: boolean;
    timezone: string;
  };
  items: Focus[];
};
type MemorySummary = {
  items: { id: string; content: string; scope: string; expires_at?: number }[];
};

export function WorkspaceHeader({ title, zh }: { title: string; zh: boolean }) {
  return (
    <header className="dm-topbar">
      <div>
        <WorkspaceSidebarTrigger />
        <span>{title}</span>
      </div>
      <div className="dm-topbar-right">
        <Link href="/docs">{zh ? "使用说明" : "Help"}</Link>
      </div>
    </header>
  );
}

export function WorkspaceAssistant() {
  const { user } = useAuth();
  const { locale } = useI18n();
  const zh = locale === "zh-CN";
  const t = (cn: string, en: string) => (zh ? cn : en);
  const router = useRouter();
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [focusOpen, setFocusOpen] = useState(true);
  useEffect(() => {
    if (window.matchMedia("(width < 600px)").matches) setFocusOpen(false);
  }, []);
  const temporaryIntent = useRef<string | null>(null);
  const owner = user?.id ?? "";
  const snapshot = useQuery({
    queryKey: ["workspace-snapshot", owner],
    queryFn: () => workspaceAPI<Snapshot>(owner, "workspace-snapshot"),
    enabled: !!owner,
    refetchInterval: 30000,
    retry: 1,
  });
  const memory = useQuery({
    queryKey: ["workspace-memory-summary", owner],
    queryFn: () => workspaceAPI<MemorySummary>(owner, "memories"),
    enabled: !!owner,
    refetchInterval: 10000,
    retry: 1,
    gcTime: 0,
  });
  async function feedback(item: Focus, action: string) {
    try {
      await workspaceAPI(owner, "workspace-feedback", {
        method: "POST",
        body: JSON.stringify({
          id: item.id,
          version: item.evidence.version,
          action,
        }),
      });
      await snapshot.refetch();
    } catch {
      setError(
        t(
          "这次操作没保存，请稍后再试。",
          "This change was not saved. Try again.",
        ),
      );
    }
  }
  async function temporary() {
    if (creating) return;
    setCreating(true);
    setError("");
    try {
      const key = `deermate:temporary-pending:${owner}`;
      if (!temporaryIntent.current) {
        const prior = sessionStorage.getItem(key);
        temporaryIntent.current =
          prior && /^[a-f0-9-]{36}$/.test(prior) ? prior : crypto.randomUUID();
      }
      sessionStorage.setItem(key, temporaryIntent.current);
      if (sessionStorage.getItem(key) !== temporaryIntent.current)
        throw new Error("journal");
      const v = await workspaceAPI<{ thread_id: string }>(
        owner,
        "temporary-topics",
        {
          method: "POST",
          body: JSON.stringify({ operation_id: temporaryIntent.current }),
        },
      );
      try {
        sessionStorage.removeItem(key);
      } catch {
        /* Creation was acknowledged. */
      }
      router.push(`/workspace/chats/${v.thread_id}`);
    } catch {
      setError(
        t(
          "临时对话还没创建成功。再点一次会核对同一个对话。",
          "Creation is unconfirmed. Retry to reconcile the same conversation.",
        ),
      );
    } finally {
      setCreating(false);
    }
  }
  if (!user) return null;
  const memories = memory.isError
    ? []
    : (memory.data?.items
        .filter((v) => !v.expires_at || v.expires_at > Date.now() / 1000)
        .slice(0, 3) ?? []);
  return (
    <div className="dm-desk dm-assistant">
      <WorkspaceHeader title={t("助手", "Assistant")} zh={zh} />
      <main className="dm-assistant-grid">
        <div className="dm-assistant-main">
          <section className="dm-assistant-greeting">
            <PersonalGreeting userId={owner} zh={zh} />
            <p>
              {snapshot.data?.items.length
                ? t(
                    "上次的事，可以从这里接着来。",
                    "Here is where we left off.",
                  )
                : t("有什么事，直接和我说。", "Tell me what is on your mind.")}
            </p>
          </section>
          {snapshot.isLoading && (
            <p role="status" className="dm-muted">
              {t("在看最近的事…", "Checking recent work…")}
            </p>
          )}
          {snapshot.isError && (
            <p role="alert">
              {t(
                "最近的进展暂时没读到，仍然可以和我聊天。",
                "Recent updates are unavailable. You can still chat.",
              )}{" "}
              <button
                className="dm-text-button"
                onClick={() => void snapshot.refetch()}
              >
                {t("再试一次", "Retry")}
              </button>
            </p>
          )}
          {!!snapshot.data?.items.length && (
            <section
              className="dm-assistant-focus"
              aria-labelledby="dm-focus-title"
            >
              <div className="dm-section-heading">
                <h2 id="dm-focus-title">
                  <button
                    className="dm-text-button dm-focus-toggle"
                    aria-expanded={focusOpen}
                    aria-controls="dm-focus-items"
                    onClick={() => setFocusOpen(!focusOpen)}
                  >
                    {t("先看看这几件事", "A few things to pick up")} ·{" "}
                    {snapshot.data.items.length}{" "}
                    {focusOpen ? t("收起", "Hide") : t("展开", "Show")}
                  </button>
                </h2>
                <Link href="/workspace/work">
                  {t("全部工作", "All work")} <ArrowRight size={14} />
                </Link>
              </div>
              {focusOpen && (
                <ul id="dm-focus-items">
                  {snapshot.data.items.map((item) => (
                    <li
                      key={item.id}
                      className="ds-app-card dm-focus-card"
                      data-design-variant="compact"
                    >
                      <div className="dm-section-heading">
                        <span className="dm-small dm-muted">
                          {item.evidence.status === "input_required"
                            ? t("等你答复", "Needs your reply")
                            : item.evidence.verified
                              ? t("验证有结果了", "Validation is available")
                              : item.seen
                                ? t("你之前看过", "Previously viewed")
                                : t("最近的事", "Recent work")}
                        </span>
                        <span className="dm-small dm-muted dm-focus-time">
                          <Clock3 size={13} />
                          {focusTime(
                            item.evidence.occurred_at,
                            snapshot.data?.profile.timezone ?? "UTC",
                            zh,
                          )}
                        </span>
                        {item.evidence.stale && (
                          <span className="dm-small">
                            {t("待重新核对", "Needs a fresh check")}
                          </span>
                        )}
                      </div>
                      <h3>{item.title || t("未命名工作", "Untitled work")}</h3>
                      <p>{focusDescription(item, zh)}</p>
                      <div className="dm-assistant-actions">
                        <Link
                          className="ds-app-button-secondary"
                          href={
                            item.kind === "work"
                              ? `/workspace/work#${item.work_id}`
                              : `/workspace/chats/${item.thread_id}`
                          }
                          onClick={() => void feedback(item, "seen")}
                        >
                          {item.kind === "work"
                            ? t("看看结果", "View work")
                            : t("接着聊", "Continue chat")}
                          <ArrowRight size={14} />
                        </Link>
                        <button
                          className="dm-text-button"
                          onClick={() => void feedback(item, "snooze_today")}
                        >
                          {t("今天先不看", "Later today")}
                        </button>
                        <button
                          className="dm-text-button"
                          onClick={() => void feedback(item, "dismiss")}
                        >
                          {t("不用再提醒", "Stop reminding me")}
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}
          {user.system_role === "admin" ? (
            <SecretaryConversation userId={owner} zh={zh} />
          ) : (
            <p>
              {t(
                "你可以打开自己的对话。执行工作需要管理员授权。",
                "Open your own chats. Execution requires administrator permission.",
              )}
            </p>
          )}
          <div className="dm-assistant-actions dm-assistant-new">
            <Link href="/workspace/chats/new">
              <MessageSquarePlus size={16} />
              {t("开始新话题", "Start a new topic")}
            </Link>
            <button
              className="dm-text-button"
              onClick={() => void temporary()}
              disabled={creating}
            >
              <Shield size={16} />
              {creating
                ? t("创建中…", "Creating…")
                : t("临时对话", "Temporary chat")}
            </button>
          </div>
          {error && <p role="alert">{error}</p>}
        </div>
        <aside className="dm-assistant-aside">
          <section className="ds-app-card">
            <div className="dm-section-heading">
              <h2>{t("关于你", "About you")}</h2>
              <Link href="/workspace/memory">{t("查看全部", "View all")}</Link>
            </div>
            <p className="dm-muted">
              {t(
                "聊天中提到的习惯和要求，我会慢慢记下来。",
                "I keep track of preferences and requirements you share.",
              )}
            </p>
            {snapshot.data && !snapshot.data.profile.auto_capture_enabled && (
              <p role="status">
                {t(
                  "自动整理已暂停，已有内容仍可查看和修改。",
                  "Automatic capture is paused. Saved facts remain manageable.",
                )}
              </p>
            )}
            {snapshot.data && !snapshot.data.profile.memory_enabled && (
              <p role="status">
                {t(
                  "回答中暂不使用已有记忆。",
                  "Saved memory is currently excluded from answers.",
                )}
              </p>
            )}
            {memory.isLoading && (
              <p role="status" className="dm-muted">
                {t("正在读取记忆…", "Loading memory…")}
              </p>
            )}
            {memory.isError ? (
              <p>
                {t("记忆暂时没读到。", "Memory is temporarily unavailable.")}
              </p>
            ) : (
              <ul className="dm-assistant-memory-summary">
                {memories.map((v) => (
                  <li key={v.id}>{v.content}</li>
                ))}
              </ul>
            )}
            {!memory.isLoading && !memory.isError && !memories.length && (
              <p className="dm-muted">
                {t(
                  "还没有记下什么。正常聊天就好，不用先填资料。",
                  "Nothing saved yet. Just start talking; there is no profile to fill in.",
                )}
              </p>
            )}
            <Link href="/workspace/memory">
              {t("记错了，随时改", "Correct anything I get wrong")}
              <ArrowRight size={14} />
            </Link>
          </section>
          {user.system_role === "admin" && (
            <GoalSuggestions userId={owner} zh={zh} />
          )}
          <HistoryProgress userId={owner} zh={zh} compact />
        </aside>
      </main>
    </div>
  );
}

function focusTime(value: string, timezone: string, zh: boolean) {
  const iso = value.replace(" ", "T");
  const normalized = /[zZ]$|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + "Z";
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime()))
    return zh ? "时间待核对" : "Time unavailable";
  return new Intl.DateTimeFormat(zh ? "zh-CN" : "en-US", {
    timeZone: timezone,
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(date);
}

function focusDescription(v: Focus, zh: boolean) {
  const t = (a: string, b: string) => (zh ? a : b);
  if (v.evidence.stale || v.evidence.tracking_degraded)
    return t(
      "这是上次核对到的状态，连接恢复后再确认进展。",
      "This is the last known state. Reconcile the original work when the connection is available.",
    );
  if (v.evidence.validation_failed)
    return t(
      "验证还没通过，可以回去看看卡在哪里。",
      "Validation failed. Open the work to inspect the result.",
    );
  if (v.evidence.verified)
    return t(
      "已有验证通过的记录。发布情况请看工作详情。",
      "Validation passed. Check the details for deployment evidence.",
    );
  const labels: Record<string, [string, string]> = {
    input_required: [
      "有个问题需要你答复，回到原话题就能继续。",
      "A question needs your reply. Continue in the original chat.",
    ],
    failed: [
      "这次没做完，可以先看看报错。",
      "This attempt failed. Check its error before continuing.",
    ],
    working: [
      "上次核对时还在处理。",
      "It was still running at the last check.",
    ],
    running: [
      "上次核对时还在处理。",
      "It was still running at the last check.",
    ],
    completed: [
      "这一步已经结束，验证和发布情况分开查看。",
      "This step ended. Validation and deployment have separate evidence.",
    ],
    cancelled: [
      "已停止，之前的记录还在。",
      "Stopped. Earlier records are still available.",
    ],
  };
  return labels[v.evidence.status]
    ? t(...labels[v.evidence.status]!)
    : t(
        "上次聊到这里，可以沿着原话题继续。",
        "Pick up in the original conversation.",
      );
}

export function WorkspaceMemory() {
  const { user } = useAuth();
  const { locale } = useI18n();
  const zh = locale === "zh-CN";
  return user ? (
    <div className="dm-desk dm-assistant">
      <WorkspaceHeader title={zh ? "关于你" : "About you"} zh={zh} />
      <main className="dm-assistant-memory-page">
        <h1>{zh ? "关于你" : "About you"}</h1>
        <p className="dm-muted">
          {zh
            ? "这些是你聊过的习惯、目标和要求。看看有没有记错。"
            : "Preferences, goals and requirements you shared. Correct anything that is wrong."}
        </p>
        <HistoryProgress userId={user.id} zh={zh} />
        <PersonalMemoryPanel userId={user.id} zh={zh} embedded />
      </main>
    </div>
  ) : null;
}
