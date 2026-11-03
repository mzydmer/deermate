"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { fetch as authFetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";
import type { AgentThread } from "@/core/threads/types";
import { titleOfThread } from "@/core/threads/utils";

type Topic = {
  id: string;
  thread_id: string;
  title: string;
  goal: string;
  status: string;
  priority: number;
  revision: number;
  source_state: string;
  snoozed_until: number;
};
type Evidence = {
  version: string;
  kind: string;
  task_id?: string;
  status: string;
  verified: boolean;
  validation_failed: boolean;
  tracking_degraded: boolean;
  cancel_requested: boolean;
  occurred_at: string;
  polled_at?: string;
  checked_at: number;
  stale: boolean;
  busy: boolean;
};
type Item = {
  topic: Topic;
  evidence: Evidence;
  has_changes: boolean;
  followup_question: string;
};
type Suggestion = {
  fact_id: string;
  fact_revision: number;
  question: string;
  reason: string;
};
type Briefing = {
  version: string;
  local_date: string;
  timezone: string;
  checked_at: number;
  items: Item[];
  total: number;
  unavailable: number;
  suggestions: Suggestion[];
  suggestions_unavailable: boolean;
};
type Intent = {
  id: string;
  kind: string;
  question: string;
  status: string;
  thread_id: string;
  run_id?: string;
  task_id?: string;
  project?: string;
  executor?: string;
};
type Continuation = { project: string; executor: string; fingerprint: string };

async function homeAPI<T>(
  user: string,
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await authFetch(`${getBackendBaseURL()}/api/me/${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", "X-Expected-User-Id": user },
  });
  if (!response.ok)
    throw new Error(
      response.status >= 400 && response.status < 500
        ? "changed"
        : "unavailable",
    );
  return (await response.json()) as T;
}

export function PersonalHome({
  userId,
  zh,
  canRun,
  threads,
  onTask,
}: {
  userId: string;
  zh: boolean;
  canRun: boolean;
  threads: AgentThread[];
  onTask: (thread: string, id: string, status: string) => void;
}) {
  const t = (cn: string, en: string) => (zh ? cn : en);
  const cache = useQueryClient();
  const briefing = useQuery({
    queryKey: ["deermate", "briefing", userId],
    queryFn: ({ signal }) => homeAPI<Briefing>(userId, "briefing", { signal }),
    retry: 1,
    gcTime: 0,
    refetchInterval: 30000,
    refetchIntervalInBackground: false,
  });
  const topics = useQuery({
    queryKey: ["deermate", "attention", userId],
    queryFn: ({ signal }) =>
      homeAPI<{ items: Topic[] }>(userId, "attention-topics", { signal }),
    retry: 1,
    gcTime: 0,
  });
  const [thread, setThread] = useState("");
  const [oldLink, setOldLink] = useState("");
  const [goal, setGoal] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [intent, setIntent] = useState<Intent | null>(null);
  const createNonce = useRef<string | null>(null);
  const pendingAction = useRef<Intent | null>(null);
  const pollUntil = useRef(0);
  const operation = useQuery({
    queryKey: ["deermate", "briefing-action", userId, intent?.id],
    queryFn: ({ signal }) =>
      homeAPI<Intent>(userId, `briefing/actions/${intent!.id}`, { signal }),
    enabled:
      !!intent &&
      !["completed", "failed", "blocked", "prepared"].includes(intent.status),
    refetchInterval: (q) =>
      Date.now() >= pollUntil.current ||
      ["completed", "failed", "blocked"].includes(q.state.data?.status ?? "")
        ? false
        : 3000,
    retry: 1,
    gcTime: 0,
  });
  useEffect(() => {
    if (operation.data) {
      setIntent(operation.data);
      if (["completed", "failed", "blocked"].includes(operation.data.status)) {
        void cache.invalidateQueries({
          queryKey: ["deermate", "briefing", userId],
        });
      }
    }
  }, [cache, operation.data, userId]);
  const refresh = async () => {
    await Promise.all([
      cache.invalidateQueries({ queryKey: ["deermate", "briefing", userId] }),
      cache.invalidateQueries({ queryKey: ["deermate", "attention", userId] }),
    ]);
  };
  const message = (reason: unknown) =>
    reason instanceof Error && reason.message === "changed"
      ? t(
          "来源或状态已变化，请刷新后核对。",
          "The source or state changed. Refresh to reconcile.",
        )
      : t(
          "暂时无法完成。已接纳的操作只会核对原结果，不会自动重发。",
          "Unavailable. Admitted actions are reconciled, never automatically replayed.",
        );
  async function addTopic() {
    setBusy(true);
    setError("");
    try {
      let selected = oldLink.trim() || thread;
      if (selected.includes("/")) {
        const link = new URL(selected, window.location.origin);
        if (
          link.origin !== window.location.origin ||
          !/^\/workspace\/chats\/[A-Za-z0-9_-]+$/.test(link.pathname)
        )
          throw new Error("changed");
        selected = link.pathname.split("/").pop()!;
      }
      createNonce.current ??= crypto.randomUUID();
      await homeAPI(userId, "attention-topics", {
        method: "POST",
        body: JSON.stringify({
          operation_id: createNonce.current,
          thread_id: selected,
          goal: goal.trim(),
          priority: 1,
        }),
      });
      createNonce.current = null;
      setGoal("");
      setOldLink("");
      await refresh();
    } catch (e) {
      if (e instanceof Error && e.message === "changed")
        createNonce.current = null;
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  async function editTopic(topic: Topic, action: string, evidence?: string) {
    setBusy(true);
    setError("");
    try {
      await homeAPI(userId, `attention-topics/${topic.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          action,
          expected_revision: topic.revision,
          evidence_revision: evidence ?? "",
        }),
      });
      await refresh();
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  async function runAction(
    body: Record<string, unknown>,
    expected: string,
    scope?: Continuation,
  ) {
    setBusy(true);
    setError("");
    try {
      const prepared =
        pendingAction.current ??
        (await homeAPI<Intent>(userId, "briefing/actions", {
          method: "POST",
          body: JSON.stringify(body),
        }));
      if (
        prepared.question !== expected ||
        (scope &&
          (prepared.project !== scope.project ||
            prepared.executor !== scope.executor))
      )
        throw new Error("changed");
      pendingAction.current = prepared;
      const admitted = await homeAPI<Intent>(
        userId,
        `briefing/actions/${prepared.id}`,
        { method: "POST", body: "{}" },
      );
      pendingAction.current = null;
      pollUntil.current = Date.now() + 120000;
      setIntent(admitted);
      await refresh();
    } catch (e) {
      if (pendingAction.current) {
        pollUntil.current = Date.now() + 120000;
        setIntent({ ...pendingAction.current, status: "uncertain" });
        pendingAction.current = null;
      }
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  function time(value: string | number) {
    const date =
      typeof value === "number"
        ? new Date(value * 1000)
        : new Date(
            /[zZ]$|[+-]\d\d:\d\d$/.test(value)
              ? value
              : value.replace(" ", "T") + "Z",
          );
    if (Number.isNaN(date.getTime())) return t("时间未知", "Time unknown");
    return new Intl.DateTimeFormat(zh ? "zh-CN" : "en-US", {
      timeZone: briefing.data?.timezone ?? "UTC",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  }
  function status(e: Evidence) {
    if (e.stale || e.tracking_degraded)
      return t(
        "更新尚未核对，以下为最后已知状态",
        "Update unverified; showing the last known state",
      );
    if (e.kind === "conversation")
      return t(
        "已有对话记录，尚无执行任务结果",
        "Conversation recorded; no execution result yet",
      );
    if (e.validation_failed)
      return t(
        "执行已结束，独立验证未通过",
        "Execution ended; independent validation did not pass",
      );
    if (e.verified)
      return t(
        "任务已完成，独立验证通过",
        "Task complete; independent validation passed",
      );
    return (
      (
        {
          completed: t(
            "执行已结束，结果尚待验证",
            "Execution ended; result not independently verified",
          ),
          failed: t("任务执行失败", "Task failed"),
          input_required: t("需要你答复", "Your response is needed"),
          working: t("任务正在执行", "Task in progress"),
          submitted: t("任务已排队", "Task queued"),
          cancelled: t("任务已取消", "Task cancelled"),
        } as Record<string, string>
      )[e.status] ?? t("状态待核对", "State unverified")
    );
  }
  const data = briefing.isError ? undefined : briefing.data;
  return (
    <section
      className="dm-personal-home"
      aria-label={t("今日关注", "Today's focus")}
    >
      <div className="dm-section-heading">
        <h2>{t("今日关注", "Today's focus")}</h2>
        <button
          className="dm-text-button"
          disabled={busy}
          onClick={() => void refresh()}
        >
          {t("刷新关注", "Refresh focus")}
        </button>
      </div>
      {briefing.isLoading && (
        <p role="status">{t("正在核对你的关注…", "Checking your focus…")}</p>
      )}
      {briefing.isError && (
        <p role="alert">
          {t(
            "关注暂不可用，已有对话和任务仍可打开。",
            "Focus unavailable. Your existing chats and tasks remain accessible.",
          )}
        </p>
      )}
      {data && (
        <>
          <p className="dm-small dm-muted">
            {data.local_date} · {data.timezone} ·{" "}
            {t("记录核对于", "Records checked at")} {time(data.checked_at)}
          </p>
          {data.items.length === 0 && (
            <p className="dm-muted">
              {t(
                "今天还没有需要展示的关注。你可以选择一个历史对话，之后从这里跟进。",
                "No focus items to show today. Follow an existing chat to pick up here later.",
              )}
            </p>
          )}
          <ul className="dm-focus-list">
            {data.items.map((item) => (
              <li key={item.topic.id}>
                <div className="dm-section-heading">
                  <h3>
                    <Link href={`/workspace/chats/${item.topic.thread_id}`}>
                      {item.topic.title}
                    </Link>
                  </h3>
                  {item.has_changes && (
                    <span className="dm-small">
                      {t("记录有变化", "Record changed")}
                    </span>
                  )}
                </div>
                {item.topic.goal && <p>{item.topic.goal}</p>}
                <p>{status(item.evidence)}</p>
                <p className="dm-small dm-muted">
                  {item.evidence.occurred_at && (
                    <>
                      {t("来源发生于", "Source event")}{" "}
                      {time(item.evidence.occurred_at)} ·{" "}
                    </>
                  )}
                  {item.evidence.polled_at && (
                    <>
                      {t("执行端同步于", "Executor synced")}{" "}
                      {time(item.evidence.polled_at)} ·{" "}
                    </>
                  )}
                  {t("你主动关注的对话", "A conversation you chose to follow")}
                </p>
                {item.evidence.cancel_requested && (
                  <p className="dm-small">
                    {t(
                      "已有取消请求，不代表执行已经停止。",
                      "Cancellation was requested; this does not confirm execution stopped.",
                    )}
                  </p>
                )}
                <div className="dm-focus-actions">
                  <Link href={`/workspace/chats/${item.topic.thread_id}`}>
                    {item.evidence.busy
                      ? t("查看进行中任务", "View ongoing work")
                      : t("打开原对话", "Open conversation")}
                  </Link>
                  {item.evidence.task_id && (
                    <button
                      className="dm-text-button"
                      onClick={() =>
                        onTask(
                          item.topic.thread_id,
                          item.evidence.task_id!,
                          item.evidence.status,
                        )
                      }
                    >
                      {t("查看结果", "View result")}
                    </button>
                  )}
                  <button
                    className="dm-text-button"
                    disabled={busy}
                    onClick={() =>
                      void editTopic(item.topic, "seen", item.evidence.version)
                    }
                  >
                    {t("标记已读", "Mark read")}
                  </button>
                  <button
                    className="dm-text-button"
                    disabled={busy}
                    onClick={() => void editTopic(item.topic, "snooze_today")}
                  >
                    {t("今天先不看", "Hide for today")}
                  </button>
                </div>
                {!item.evidence.busy && !item.evidence.stale && (
                  <details className="dm-focus-followup">
                    <summary>{t("跟进这个话题", "Follow up")}</summary>
                    <p>{item.followup_question}</p>
                    <button
                      className="dm-button"
                      disabled={busy || !canRun}
                      onClick={() =>
                        void runAction(
                          {
                            kind: "followup",
                            topic_id: item.topic.id,
                            evidence_revision: item.evidence.version,
                          },
                          item.followup_question,
                        )
                      }
                    >
                      {t("一键只读跟进", "Ask a read-only follow-up")}
                    </button>
                    {item.evidence.task_id && (
                      <NativeContinuation
                        user={userId}
                        item={item}
                        zh={zh}
                        disabled={busy || !canRun}
                        onRun={runAction}
                      />
                    )}
                  </details>
                )}
              </li>
            ))}
          </ul>
          {data.unavailable > 0 && (
            <p className="dm-muted">
              {t(
                "部分关注的来源已不可用或已归档，旧内容已隐藏。",
                "Some sources are unavailable or archived; their old contents are hidden.",
              )}
            </p>
          )}
          {data.total > 3 && (
            <p className="dm-small">
              {t(
                `还有 ${data.total - 3} 项关注，可在下方管理。`,
                `${data.total - 3} more followed items are available below.`,
              )}
            </p>
          )}
          {data.suggestions.length > 0 && (
            <div className="dm-suggestions">
              <h3>{t("你可能想接着研究", "You might explore next")}</h3>
              {data.suggestions.map((suggestion) => (
                <div key={suggestion.fact_id}>
                  <p>{suggestion.question}</p>
                  <p className="dm-small dm-muted">
                    {t(
                      "因为你明确保存了这个长期目标。",
                      "Because you explicitly saved this long-term goal.",
                    )}
                  </p>
                  <button
                    className="dm-text-button"
                    disabled={busy || !canRun}
                    onClick={() =>
                      void runAction(
                        {
                          kind: "new_topic",
                          fact_id: suggestion.fact_id,
                          fact_revision: suggestion.fact_revision,
                        },
                        suggestion.question,
                      )
                    }
                  >
                    {t("开始这个话题", "Start this topic")}
                  </button>
                </div>
              ))}
            </div>
          )}
          {data.suggestions_unavailable && (
            <p className="dm-muted">
              {t(
                "新话题建议暂不可用，原有关注仍保留。",
                "Suggestions unavailable; your followed topics remain.",
              )}
            </p>
          )}
        </>
      )}
      {intent && (
        <div role="status" className="dm-home-action">
          <p>
            {intent.status === "completed"
              ? t("跟进已完成。", "Follow-up complete.")
              : intent.status === "failed"
                ? t(
                    "跟进未能完成，可打开记录检查。",
                    "Follow-up failed. Open its record to inspect.",
                  )
                : intent.status === "blocked"
                  ? t(
                      "来源或权限已变化，旧动作已停止使用。",
                      "Source or permission changed; the old action is blocked.",
                    )
                  : intent.status === "uncertain"
                    ? t(
                        "结果待确认，只核对同一次操作。",
                        "Outcome uncertain; only the original operation is reconciled.",
                      )
                    : intent.status === "prepared"
                      ? t(
                          "请求尚未接纳，可以重试同一次操作。",
                          "Not admitted yet. You can retry the same request.",
                        )
                      : t("已接纳，正在处理。", "Admitted and in progress.")}
          </p>
          {intent.status === "prepared" && (
            <button
              className="dm-text-button"
              disabled={busy}
              onClick={() => {
                pendingAction.current = intent;
                void runAction({}, intent.question);
              }}
            >
              {t("重试这次请求", "Retry this request")}
            </button>
          )}
          {["uncertain", "running", "submitting"].includes(intent.status) && (
            <button
              className="dm-text-button"
              disabled={busy || operation.isFetching}
              onClick={() => {
                pollUntil.current = Date.now() + 120000;
                void operation.refetch();
              }}
            >
              {t("核对原结果", "Reconcile original result")}
            </button>
          )}
          {intent.thread_id && (
            <Link href={`/workspace/chats/${intent.thread_id}`}>
              {t("查看跟进结果", "Open follow-up result")}
            </Link>
          )}
        </div>
      )}
      <details className="dm-attention-management">
        <summary>{t("管理关注", "Manage focus")}</summary>
        {topics.isError && (
          <p role="alert">
            {t("暂时无法读取关注。", "Could not load followed topics.")}
          </p>
        )}
        <ul className="dm-focus-list">
          {!topics.isError &&
            topics.data?.items.map((topic) => (
              <li key={topic.id}>
                <p>
                  {topic.source_state === "available"
                    ? topic.title
                    : t(
                        "来源已不可用或已归档",
                        "Source unavailable or archived",
                      )}
                </p>
                <span className="dm-small dm-muted">
                  {topic.status === "paused"
                    ? t("已暂停", "Paused")
                    : topic.status === "completed"
                      ? t("已完成关注", "Finished")
                      : topic.snoozed_until > Date.now() / 1000
                        ? t("今天已隐藏", "Hidden for today")
                        : t("正在关注", "Following")}
                </span>
                <div className="dm-focus-actions">
                  {topic.status === "active" && (
                    <button
                      className="dm-text-button"
                      disabled={busy}
                      onClick={() => void editTopic(topic, "pause")}
                    >
                      {t("暂停关注", "Pause")}
                    </button>
                  )}
                  {(topic.status !== "active" ||
                    topic.snoozed_until > Date.now() / 1000) &&
                    topic.source_state === "available" && (
                      <button
                        className="dm-text-button"
                        disabled={busy}
                        onClick={() => void editTopic(topic, "resume")}
                      >
                        {t("恢复关注", "Resume")}
                      </button>
                    )}
                  {topic.status === "active" && (
                    <button
                      className="dm-text-button"
                      disabled={busy}
                      onClick={() => void editTopic(topic, "complete")}
                    >
                      {t("完成关注", "Finish")}
                    </button>
                  )}
                  <button
                    className="dm-text-button"
                    disabled={busy}
                    onClick={() => void editTopic(topic, "remove")}
                  >
                    {t("不再关注", "Unfollow")}
                  </button>
                </div>
              </li>
            ))}
        </ul>
        <form
          className="dm-memory-form"
          onSubmit={(event) => {
            event.preventDefault();
            void addTopic();
          }}
        >
          <label>
            {t("选择一个已有对话", "Choose an existing conversation")}
            <select
              value={thread}
              disabled={busy || !!createNonce.current}
              onChange={(event) => setThread(event.target.value)}
            >
              <option value="">
                {t("选择对话…", "Choose a conversation…")}
              </option>
              {threads.map((entry) => (
                <option key={entry.thread_id} value={entry.thread_id}>
                  {titleOfThread(entry, t("未命名对话", "Untitled conversation"))}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t("或粘贴历史对话链接", "Or paste an older conversation link")}
            <input
              value={oldLink}
              disabled={busy || !!createNonce.current}
              maxLength={1000}
              onChange={(event) => setOldLink(event.target.value)}
              placeholder="/workspace/chats/…"
            />
          </label>
          <label>
            {t("你想跟进什么", "What would you like to follow?")}
            <input
              value={goal}
              disabled={busy || !!createNonce.current}
              maxLength={500}
              onChange={(event) => setGoal(event.target.value)}
            />
          </label>
          <button
            className="dm-button"
            disabled={busy || (!thread && !oldLink)}
          >
            {createNonce.current
              ? t("核对同一次关注", "Reconcile follow")
              : t("关注这个对话", "Follow this conversation")}
          </button>
        </form>
      </details>
      {error && <p role="alert">{error}</p>}
    </section>
  );
}

function NativeContinuation({
  user,
  item,
  zh,
  disabled,
  onRun,
}: {
  user: string;
  item: Item;
  zh: boolean;
  disabled: boolean;
  onRun: (
    body: Record<string, unknown>,
    question: string,
    scope: Continuation,
  ) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");
  const info = useQuery({
    queryKey: [
      "deermate",
      "home-continuation",
      user,
      item.topic.id,
      item.evidence.version,
    ],
    queryFn: ({ signal }) =>
      homeAPI<Continuation>(
        user,
        `attention-topics/${item.topic.id}/continuation`,
        { signal },
      ),
    enabled: open && !disabled,
    retry: false,
    gcTime: 0,
  });
  return (
    <details onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>
        {zh ? "继续执行具体下一步" : "Execute a specific next step"}
      </summary>
      {info.isLoading && (
        <p role="status">
          {zh ? "正在核对原会话…" : "Checking the existing session…"}
        </p>
      )}
      {info.isError && (
        <p>
          {zh
            ? "当前无法续接，请打开原会话检查连接、输入或恢复状态。"
            : "Continuation unavailable. Inspect the original chat and connection."}
        </p>
      )}
      {info.data && (
        <form
          className="dm-memory-form"
          onSubmit={(event) => {
            event.preventDefault();
            void onRun(
              {
                kind: "continue",
                topic_id: item.topic.id,
                evidence_revision: item.evidence.version,
                message: message.trim(),
                continuation_fingerprint: info.data.fingerprint,
              },
              message.trim(),
              info.data,
            );
          }}
        >
          <p>
            {zh
              ? "沿用原项目与执行器"
              : "Uses the existing project and executor"}
            ：{info.data.project} · {info.data.executor}
          </p>
          <label>
            {zh ? "这一次具体做什么" : "What should this step do?"}
            <textarea
              value={message}
              maxLength={1000}
              onChange={(event) => setMessage(event.target.value)}
              required
            />
          </label>
          <p className="dm-small dm-muted">
            {zh
              ? "只提交一轮原会话任务，不更换项目或新增执行权限。"
              : "One continuation in the existing session, without changing project or permissions."}
          </p>
          <button className="dm-button" disabled={disabled || !message.trim()}>
            {zh ? "继续执行这一项" : "Execute this step"}
          </button>
        </form>
      )}
    </details>
  );
}
