"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { fetch as authFetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

import { ContinuousIntents } from "./continuous-intents";

type RecordView = {
  id: string;
  kind: string;
  state: string;
  revision: number;
  updated_at: number;
  data: Record<string, unknown>;
};
type Page = { items: RecordView[] };
type Config = {
  config: RecordView;
  module_available: boolean;
  interactive_available?: boolean;
  github_configured: boolean;
  reserved?: { model: number; native: number };
  budget_day?: string;
};
type Router = { session: RecordView; items: RecordView[] };
const str = (v: RecordView, k: string) =>
  typeof v.data[k] === "string" ? v.data[k] : "";

export function ContinuousSecretary({
  userId,
  zh,
  canRun,
  workOnly = false,
}: {
  userId: string;
  zh: boolean;
  canRun: boolean;
  workOnly?: boolean;
}) {
  const text = (cn: string, en: string) => (zh ? cn : en);
  const cache = useQueryClient();
  const [message, setMessage] = useState("");
  const [goal, setGoal] = useState("");
  const [project, setProject] = useState("");
  const [grant, setGrant] = useState("");
  const [instruction, setInstruction] = useState("");
  const [selected, setSelected] = useState("");
  const [workFilter, setWorkFilter] = useState("all");
  useEffect(() => {
    if (workOnly) setSelected(window.location.hash.slice(1));
  }, [workOnly]);
  const [followups, setFollowups] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const intents = useRef(new ContinuousIntents());
  async function api<T>(
    path: string,
    method = "GET",
    body?: object,
  ): Promise<T> {
    const response = await authFetch(`${getBackendBaseURL()}/api/me/${path}`, {
      method,
      headers: {
        "Content-Type": "application/json",
        "X-Expected-User-Id": userId,
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    if (!response.ok) {
      const value = (await response.json().catch(() => null)) as {
        detail?: { message?: string };
      } | null;
      throw Object.assign(
        new Error(
          value?.detail?.message ??
            text(
              "暂时无法读取，请刷新后核对原操作。",
              "Unavailable. Refresh and inspect the original operation.",
            ),
        ),
        { status: response.status },
      );
    }
    return (await response.json()) as T;
  }
  const prefix = ["continuous", userId];
  const config = useQuery({
    queryKey: [...prefix, "config"],
    queryFn: () => api<Config>("continuous-config"),
    enabled: canRun,
    refetchInterval: canRun ? 10000 : false,
  });
  const enabled =
    config.data?.interactive_available ??
    config.data?.module_available ??
    false;
  const works = useQuery({
    queryKey: [...prefix, "works"],
    queryFn: () => api<Page>("work-orders"),
    enabled: canRun,
    refetchInterval: enabled ? 5000 : false,
  });
  const router = useQuery({
    queryKey: [...prefix, "router"],
    queryFn: () => api<Router>("router"),
    enabled: canRun && enabled,
    refetchInterval: enabled ? 5000 : false,
  });
  const sources = useQuery({
    queryKey: [...prefix, "sources"],
    queryFn: () => api<Page>("event-sources"),
    enabled: canRun && enabled,
  });
  const rules = useQuery({
    queryKey: [...prefix, "rules"],
    queryFn: () => api<Page>("automation-rules"),
    enabled: canRun && enabled,
  });
  const decisions = useQuery({
    queryKey: [...prefix, "decisions"],
    queryFn: () => api<Page>("agent-decisions"),
    enabled: canRun && enabled,
    refetchInterval: enabled ? 10000 : false,
  });
  const timeline = useQuery({
    queryKey: [...prefix, "timeline", selected],
    queryFn: () => api<Page>(`work-orders/${selected}/timeline`),
    enabled: !!selected,
    refetchInterval: 5000,
  });
  const current = works.data?.items.find((v) => v.id === selected);
  const readUnavailable = config.isError || works.isError;
  async function mutate(
    path: string,
    method: string,
    body: object,
    done?: () => void,
  ) {
    if (busy) return;
    setBusy(true);
    setError("");
    const intent = intents.current.begin(path, method, body);
    try {
      await api(path, method, intent.body);
      intents.current.confirmed(intent);
      done?.();
    } catch (e) {
      intents.current.rejected(
        intent,
        (e as { status?: number } | null)?.status,
      );
      setError(e instanceof Error ? e.message : "Unavailable");
    } finally {
      setBusy(false);
      await cache.invalidateQueries({ queryKey: prefix });
    }
  }
  const status = (v: RecordView) => {
    const raw =
      v.kind === "work" && ["paused", "closed"].includes(v.state)
        ? v.state
        : str(v, "stage") || v.state;
    const labels: Record<string, [string, string]> = {
      ready: ["待执行", "Ready"],
      waiting_budget: [
        "今日后台额度已用尽",
        "Daily background budget exhausted",
      ],
      waiting_model: ["等待模型配置", "Model configuration required"],
      waiting_assessor: ["研判排队中", "Assessment queued"],
      waiting_policy: [
        "当前规则已暂停派发",
        "Dispatch paused by current policy",
      ],
      waiting_authorization: [
        "等待设备连接或有效授权",
        "Device connection or current grant required",
      ],
      rejected: ["接纳前检查未通过", "Rejected before execution"],
      stale: ["依据已变化，未派发", "Source changed; not dispatched"],
      queued: ["等待接纳", "Queued"],
      pending: ["待处理", "Pending"],
      active: ["进行中", "Active"],
      running: ["执行中", "Running"],
      prepared: ["等待投递", "Prepared"],
      dispatching: ["正在核对接纳", "Confirming admission"],
      acknowledged: ["已接纳", "Acknowledged"],
      uncertain: [
        "回执未确认，核对原操作",
        "Receipt unknown; inspect original operation",
      ],
      settled: ["已收到回执", "Receipt received"],
      paused: ["已暂停派单", "Dispatch paused"],
      closed: ["已结束", "Closed"],
      completed: ["执行结束", "Execution finished"],
      verification_required: ["执行结束，尚需验证", "Verification required"],
      failed: ["执行失败", "Failed"],
      input_required: ["等待你的输入", "Input required"],
      cancel_requested: [
        "已请求停止，等待确认",
        "Stop requested; awaiting confirmation",
      ],
      cancelling: ["等待停止确认", "Awaiting stop confirmation"],
      cancelled: ["已确认停止", "Stopped"],
      handoff: ["范围有变化，待重新安排", "Scope changed; routing required"],
    };
    const label = labels[raw];
    return label ? text(...label) : raw;
  };
  if (!canRun) return null;
  return (
    <section
      className="dm-personal-home dm-continuous"
      aria-label={text("持续秘书", "Continuous secretary")}
    >
      <div className="dm-section-heading">
        <h2>{text("工作安排", "Work orders")}</h2>
        <Link href="/workspace/memory">
          {text("记忆管理", "Manage memory")}
        </Link>
        <button
          className="dm-text-button"
          disabled={busy}
          onClick={() => void cache.invalidateQueries({ queryKey: prefix })}
        >
          {text("刷新状态", "Refresh")}
        </button>
      </div>
      {config.isPending && (
        <p role="status" className="dm-muted">
          {text("正在读取设置…", "Loading settings…")}
        </p>
      )}
      {works.isPending && (
        <p role="status" className="dm-muted">
          {text("正在读取工作…", "Loading work…")}
        </p>
      )}
      {(config.isError || works.isError || router.isError) && (
        <p role="alert">
          {text(
            "暂时无法刷新，已显示的状态可能过时。",
            "Refresh failed. Displayed state may be stale.",
          )}
        </p>
      )}
      {error && (
        <p role="alert" className="dm-continuous-error">
          {error}
        </p>
      )}
      {config.data && !enabled && (
        <p role="status" className="dm-muted">
          {text(
            "秘书服务暂不可用，请稍后重试。",
            "The secretary is temporarily unavailable. Try again later.",
          )}
        </p>
      )}
      {enabled && !workOnly && (
        <>
          <form
            className="dm-continuous-form"
            onSubmit={(e) => {
              e.preventDefault();
              void mutate("router/messages", "POST", { text: message }, () =>
                setMessage(""),
              );
            }}
          >
            <label>
              {text("交代给秘书", "Ask your secretary")}
              <textarea
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                maxLength={8000}
                placeholder={text(
                  "告诉我你想跟进哪项工作，或交代一个新目标。",
                  "Follow up on work, or describe a new goal.",
                )}
                required
              />
            </label>
            <button
              className="dm-button"
              disabled={
                busy || readUnavailable || router.isError || !message.trim()
              }
            >
              {text("发送", "Send")}
            </button>
          </form>
          {router.isPending && (
            <p role="status" className="dm-muted">
              {text("正在读取秘书回执…", "Loading secretary receipts…")}
            </p>
          )}
          <ul className="dm-focus-list dm-router-messages" aria-live="polite">
            {router.data?.items
              .slice(0, 6)
              .reverse()
              .map((v) => (
                <li key={v.id}>
                  <p className="dm-small dm-muted">
                    {str(v, "origin") === "user"
                      ? text("你", "You")
                      : text("工作更新", "Work update")}{" "}
                    · {status(v)}
                  </p>
                  <p>{str(v, "text")}</p>
                  {v.state === "waiting_model" && (
                    <p role="status">
                      {text(
                        "请在模型设置中添加或选择支持的对话模型。",
                        "Add or select a supported conversation model in model settings.",
                      )}{" "}
                      <Link href="/workspace?settings=models">
                        {text("模型设置", "Model settings")}
                      </Link>
                    </p>
                  )}
                  {str(v, "reply") && (
                    <p className="dm-router-reply">{str(v, "reply")}</p>
                  )}
                  {v.state === "uncertain" && (
                    <small>
                      {text(
                        "请保留此输入，不要重复派单。操作 ID：",
                        "Keep this input and inspect it before delegating again. Operation: ",
                      )}
                      {str(v, "operation_id")}
                    </small>
                  )}
                </li>
              ))}
          </ul>
          <details className="dm-attention-management">
            <summary>
              {text("直接创建一项工作", "Create work directly")}
            </summary>
            <form
              className="dm-continuous-form"
              onSubmit={(e) => {
                e.preventDefault();
                void mutate(
                  "work-orders",
                  "POST",
                  { goal, project, grant_id: grant },
                  () => setGoal(""),
                );
              }}
            >
              <label>
                {text("工作目标", "Goal")}
                <textarea
                  value={goal}
                  onChange={(e) => setGoal(e.target.value)}
                  maxLength={8000}
                  required
                />
              </label>
              <div className="dm-continuous-fields">
                <label>
                  {text("注册的项目 ID", "Registered project ID")}
                  <input
                    value={project}
                    onChange={(e) => setProject(e.target.value)}
                    maxLength={100}
                    required
                  />
                </label>
                <label>
                  {text("设备授权 ID", "Device grant ID")}
                  <input
                    value={grant}
                    onChange={(e) => setGrant(e.target.value)}
                    maxLength={128}
                    required
                  />
                </label>
              </div>
              <button className="dm-button" disabled={busy || readUnavailable}>
                {text("创建工作", "Create work")}
              </button>
            </form>
          </details>
        </>
      )}
      {works.data?.items.length === 0 && (
        <p className="dm-muted">
          {text(
            "还没有安排工作。回到助手，告诉我想做什么。",
            "No work orders yet. Tell your assistant what you want to do.",
          )}
        </p>
      )}
      <label>
        {text("工作状态", "Work status")}
        <select
          value={workFilter}
          onChange={(e) => setWorkFilter(e.target.value)}
        >
          <option value="all">{text("全部", "All")}</option>
          <option value="attention">{text("待回应", "Needs attention")}</option>
          <option value="active">{text("处理中", "Active")}</option>
          <option value="ended">{text("已结束", "Ended")}</option>
        </select>
      </label>
      <ul className="dm-focus-list">
        {works.data?.items
          .filter(
            (v) =>
              workFilter === "all" ||
              (workFilter === "attention"
                ? ["input_required", "failed", "uncertain", "handoff"].includes(
                    str(v, "stage"),
                  )
                : workFilter === "ended"
                  ? v.state === "closed" ||
                    ["completed", "cancelled"].includes(str(v, "stage"))
                  : v.state === "active" &&
                    !["completed", "cancelled"].includes(str(v, "stage"))),
          )
          .map((v) => (
            <li key={v.id}>
              <div className="dm-section-heading">
                <button
                  className="dm-text-button"
                  aria-expanded={selected === v.id}
                  onClick={() => setSelected(selected === v.id ? "" : v.id)}
                >
                  {str(v, "title") || text("未命名工作", "Untitled work")}
                </button>
                <span className="dm-small">
                  {status(v)}
                  {v.data.verified === true
                    ? text(" · 验证通过", " · verified")
                    : ""}
                </span>
              </div>
              <p className="dm-small dm-muted">{str(v, "goal")}</p>
              {v.data.has_update === true && (
                <p className="dm-small">
                  {text(
                    "关注的 Thread 有新上下文",
                    "Subscribed thread has new context",
                  )}
                </p>
              )}
              {current?.id === v.id && (
                <div className="dm-work-detail">
                  <p>{str(v, "preview")}</p>
                  {str(v, "source_state") === "unavailable" && (
                    <p className="dm-small dm-muted">
                      {text(
                        "来源暂不可读，已隐藏摘要。可继续处理已有工作的停止或关闭。",
                        "Source unavailable; summaries are hidden. Existing work can still be stopped or closed.",
                      )}
                    </p>
                  )}
                  <p className="dm-small">
                    Codex · {str(v, "project")} ·{" "}
                    {str(v, "incarnation") ? (
                      <Link href={`/workspace/chats/${str(v, "thread_id")}`}>
                        {text("打开执行对话", "Execution chat")}
                      </Link>
                    ) : (
                      <span>
                        {text(
                          "接纳后可打开执行对话",
                          "Execution chat appears after admission",
                        )}
                      </span>
                    )}
                  </p>
                  {str(v, "execution_reason") && (
                    <p className="dm-small dm-muted">
                      {text(
                        "执行前需要有效、在线且支持持续任务协议的设备授权。",
                        "Execution requires a current, reachable device grant with continuous-task protocol support.",
                      )}
                    </p>
                  )}
                  <div className="dm-focus-actions">
                    {(v.state === "active"
                      ? ["execute", "pause", "cancel", "close", "reconcile"]
                      : v.state === "paused"
                        ? ["resume", "cancel", "close", "reconcile"]
                        : ["reconcile"]
                    ).map((action) => (
                      <button
                        key={action}
                        className="dm-text-button"
                        disabled={
                          busy ||
                          (readUnavailable && action !== "reconcile") ||
                          (!enabled && action !== "reconcile") ||
                          (action === "execute" &&
                            v.data.can_execute !== true) ||
                          (action === "execute" &&
                            !!str(v, "head") &&
                            !followups[v.id]?.trim()) ||
                          (action === "cancel" && v.data.can_cancel !== true) ||
                          (action === "close" && !!v.data.active_operation)
                        }
                        onClick={() =>
                          void mutate(
                            `work-orders/${v.id}/actions`,
                            "POST",
                            {
                              action:
                                action === "execute" && str(v, "head")
                                  ? "followup"
                                  : action,
                              text:
                                action === "execute"
                                  ? followups[v.id]?.length
                                    ? followups[v.id]
                                    : str(v, "goal")
                                  : "",
                              expected_revision: v.revision,
                            },
                            () => {
                              if (action === "execute")
                                setFollowups((drafts) => {
                                  if (drafts[v.id] !== followups[v.id])
                                    return drafts;
                                  const next = { ...drafts };
                                  delete next[v.id];
                                  return next;
                                });
                            },
                          )
                        }
                      >
                        {
                          {
                            execute: str(v, "head")
                              ? text("继续执行", "Continue")
                              : text("开始执行", "Execute"),
                            pause: text("暂停", "Pause"),
                            resume: text("恢复", "Resume"),
                            cancel: text("请求停止", "Request stop"),
                            close: text("结束工作", "Close work"),
                            reconcile: text("核对原结果", "Reconcile"),
                          }[action]
                        }
                      </button>
                    ))}
                  </div>
                  {v.state !== "closed" && (
                    <label>
                      {text("下一轮问题", "Next round")}
                      <textarea
                        value={followups[v.id] ?? ""}
                        onChange={(e) =>
                          setFollowups((drafts) => ({
                            ...drafts,
                            [v.id]: e.target.value,
                          }))
                        }
                        placeholder={text(
                          "填写下一步要求，再继续原会话。",
                          "Describe the next step before continuing the same session.",
                        )}
                        maxLength={8000}
                      />
                    </label>
                  )}
                  <details>
                    <summary>
                      {text("回执与引用", "Receipts & references")}
                    </summary>
                    {timeline.isPending ? (
                      <p role="status">
                        {text("正在读取回执…", "Loading receipts…")}
                      </p>
                    ) : timeline.isError ? (
                      <p role="alert">
                        {text("回执暂不可读", "Receipts unavailable")}
                      </p>
                    ) : (
                      <ul>
                        {timeline.data?.items.map((item) => (
                          <li key={item.id}>
                            <span>
                              {item.kind} · {status(item)}
                            </span>
                            <code>{item.id}</code>
                            {str(item, "preview") && (
                              <p>{str(item, "preview")}</p>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </details>
                </div>
              )}
            </li>
          ))}
      </ul>
      {enabled && (
        <details className="dm-attention-management">
          <summary>
            {text("GitHub 来源与规则", "GitHub source & rules")}
          </summary>
          {config.data && (
            <label className="dm-continuous-budget">
              {text("自动执行上限 / 天", "Automatic execution limit / day")}
              <select
                value={Number(config.data.config.data.native_budget ?? 0)}
                disabled={busy || readUnavailable}
                onChange={(e) =>
                  void mutate("continuous-config", "PATCH", {
                    enabled: config.data.config.data.enabled === true,
                    native_budget: Number(e.target.value),
                    expected_revision: config.data.config.revision,
                  })
                }
              >
                {[0, 1, 2].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
          )}
          <p className="dm-small dm-muted">
            {text(
              "来源观察和自动处理由你单独开启。执行上限默认 0。",
              "Enable source observation and automatic work separately. The execution limit starts at zero.",
            )}
          </p>
          <Link href="/admin/agents">
            {text(
              "管理设备与项目授权",
              "Manage device & project authorization",
            )}
          </Link>

          {sources.isError && (
            <p role="alert">{text("来源读取失败", "Source unavailable")}</p>
          )}
          {sources.isPending && (
            <p role="status">{text("正在读取来源…", "Loading source…")}</p>
          )}
          {rules.isError && (
            <p role="alert">
              {text(
                "规则读取失败，已显示的规则可能过时。",
                "Rules unavailable. Displayed rules may be stale.",
              )}
            </p>
          )}
          {rules.isPending && (
            <p role="status">{text("正在读取规则…", "Loading rules…")}</p>
          )}
          {sources.data?.items.map((src) => (
            <div key={src.id}>
              <p>
                {str(src, "configured_repository") ||
                  str(src, "repository") ||
                  text("部署尚未指定仓库", "No repository configured")}{" "}
                · {src.state}
              </p>
              <p className="dm-small dm-muted">
                {text(
                  "只读单仓库；首次建立基线。凭据由部署端 secret_ref 提供。",
                  "Read-only, one repository. Initial poll establishes a baseline. Credentials come from an operator secret reference.",
                )}
              </p>
              {str(src, "error") && <p role="alert">{str(src, "error")}</p>}
              <button
                className="dm-text-button"
                disabled={
                  busy ||
                  readUnavailable ||
                  sources.isError ||
                  !config.data?.github_configured
                }
                onClick={() =>
                  void mutate(`event-sources/${src.id}`, "PATCH", {
                    enabled:
                      src.state !== "enabled" ||
                      config.data?.config.data.enabled !== true,
                    expected_revision: src.revision,
                  })
                }
              >
                {src.state === "enabled" &&
                config.data?.config.data.enabled === true
                  ? text("暂停来源", "Disable source")
                  : text("启用来源", "Enable source")}
              </button>
            </div>
          ))}
          <form
            className="dm-continuous-form"
            onSubmit={(e) => {
              e.preventDefault();
              void mutate(
                "automation-rules",
                "POST",
                {
                  source_id: "github",
                  mode: "observe",
                  instruction,
                  project,
                  grant_id: grant,
                },
                () => setInstruction(""),
              );
            }}
          >
            <label>
              {text("关注规则", "Observation rule")}
              <textarea
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
                maxLength={4000}
                placeholder={text(
                  "例如：关注与登录、会话恢复相关的问题",
                  "For example: follow login and session-recovery issues",
                )}
                required
              />
            </label>
            <button
              className="dm-button"
              disabled={
                busy || readUnavailable || sources.isError || rules.isError
              }
            >
              {text("添加观察规则", "Add observe rule")}
            </button>
          </form>
          <ul className="dm-focus-list">
            {rules.data?.items.map((rule) => (
              <li key={rule.id}>
                <p>{str(rule, "instruction")}</p>
                <label>
                  {text("处理方式", "Mode")}
                  <select
                    value={rule.state}
                    disabled={busy || readUnavailable || rules.isError}
                    onChange={(e) =>
                      void mutate(`automation-rules/${rule.id}`, "PATCH", {
                        source_id: "github",
                        instruction: str(rule, "instruction"),
                        mode: e.target.value,
                        project: str(rule, "project"),
                        grant_id: str(rule, "grant_id"),
                        native_budget: e.target.value === "auto" ? 1 : 0,
                        expected_revision: rule.revision,
                      })
                    }
                  >
                    <option value="off">off</option>
                    <option value="observe">observe</option>
                    <option
                      value="auto"
                      disabled={
                        !str(rule, "project") ||
                        !str(rule, "grant_id") ||
                        Number(config.data?.config.data.native_budget ?? 0) ===
                          0
                      }
                    >
                      auto · 1 / UTC day
                    </option>
                  </select>
                </label>
              </li>
            ))}
          </ul>
          <h3>{text("待处理建议", "Suggestions")}</h3>
          {decisions.isError && (
            <p role="alert">
              {text("建议读取失败", "Suggestions unavailable")}
            </p>
          )}
          {decisions.isPending && (
            <p role="status">{text("正在读取建议…", "Loading suggestions…")}</p>
          )}
          {decisions.isSuccess &&
            !decisions.data.items.some((v) => v.state === "suggested") && (
              <p className="dm-muted">
                {text(
                  "暂无待处理建议。配置来源与观察规则后，建议会显示在这里。",
                  "No pending suggestions. Configure a source and observation rule to receive them here.",
                )}
              </p>
            )}
          <ul className="dm-focus-list">
            {decisions.data?.items
              .filter((v) => v.state === "suggested")
              .map((d) => (
                <li key={d.id}>
                  <p>{str(d, "title")}</p>
                  <p className="dm-small">{str(d, "goal")}</p>
                  <p className="dm-small dm-muted">{str(d, "rationale")}</p>
                  <div className="dm-focus-actions">
                    {["accept", "ignore"].map((action) => (
                      <button
                        className="dm-text-button"
                        key={action}
                        disabled={
                          busy ||
                          readUnavailable ||
                          decisions.isError ||
                          (action === "accept" &&
                            ((!project && !str(d, "project")) ||
                              (!grant && !str(d, "grant_id"))))
                        }
                        onClick={() =>
                          void mutate(
                            `agent-decisions/${d.id}/actions`,
                            "POST",
                            {
                              action,
                              expected_revision: d.revision,
                              project,
                              grant_id: grant,
                            },
                          )
                        }
                      >
                        {action === "accept"
                          ? text("接纳并执行", "Accept & execute")
                          : text("忽略", "Ignore")}
                      </button>
                    ))}
                  </div>
                </li>
              ))}
          </ul>
        </details>
      )}
    </section>
  );
}
