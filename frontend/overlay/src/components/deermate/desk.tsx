"use client";

import { useQueries, useQuery } from "@tanstack/react-query";
import {
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  Bot,
  Check,
  ChevronRight,
  Circle,
  Code2,
  FileSearch,
  ListChecks,
  LoaderCircle,
  LockKeyhole,
  RefreshCw,
  Settings2,
  Sparkles,
  Terminal,
  TriangleAlert,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { fetch as authFetch } from "@/core/api/fetcher";
import { useAuth } from "@/core/auth/AuthProvider";
import { fetchBackgroundTasks } from "@/core/background-tasks";
import { getBackendBaseURL } from "@/core/config";
import { useI18n } from "@/core/i18n/hooks";
import { useMCPConfig } from "@/core/mcp/hooks";
import { useModels } from "@/core/models/hooks";
import {
  buildComposerDraftKey,
  getSessionComposerDraftStorage,
  readComposerDraft,
  writeComposerDraft,
} from "@/core/threads/composer-draft";
import { useThreads } from "@/core/threads/hooks";
import { WorkspaceSidebarTrigger } from "@/components/workspace/workspace-sidebar-trigger";

import { BrandMotion } from "./brand";
import { MotionTabs } from "./motion-tabs";
import { TaskDetail, type DeskTask } from "./task-detail";

const labels: Record<string, [string, string]> = {
  submitted: ["排队中", "Queued"],
  working: ["执行中", "Working"],
  input_required: ["等待答复", "Needs input"],
  completed: ["已完成", "Completed"],
  failed: ["执行失败", "Failed"],
  cancelled: ["已取消", "Cancelled"],
};
const active = new Set(["submitted", "working", "input_required"]);
const threadParams = {
  limit: 20,
  sortBy: "updated_at" as const,
  sortOrder: "desc" as const,
  select: [
    "thread_id" as const,
    "updated_at" as const,
    "values" as const,
    "metadata" as const,
  ],
};

export function DeerMateDesk() {
  const { locale } = useI18n();
  const zh = locale === "zh-CN";
  const text = (cn: string, en: string) => (zh ? cn : en);
  const { user } = useAuth();
  const router = useRouter();
  const models = useModels();
  const mcp = useMCPConfig("deployment");
  const threads = useThreads(threadParams);
  const [filter, setFilter] = useState("all");
  const [draft, setDraft] = useState("");
  const [draftError, setDraftError] = useState(false);
  const [selected, setSelected] = useState<DeskTask | null>(null);
  const taskOpener = useRef<HTMLButtonElement | null>(null);
  const draftKey = buildComposerDraftKey({
    userId: user?.id ?? "anonymous",
    threadId: "new",
  });
  useEffect(() => {
    setDraft(
      readComposerDraft(getSessionComposerDraftStorage(), draftKey)?.text ?? "",
    );
  }, [draftKey]);
  const health = useQuery({
    queryKey: ["deermate", "gateway-health", user?.id],
    queryFn: async () => {
      const response = await authFetch(`${getBackendBaseURL()}/health/ready`);
      if (!response.ok) throw new Error("Gateway is not ready");
      return true;
    },
    refetchInterval: 30000,
    refetchIntervalInBackground: false,
    retry: 1,
  });
  const taskQueries = useQueries({
    queries: (threads.data ?? []).map((thread) => ({
      queryKey: ["deermate", "thread-tasks", user?.id, thread.thread_id],
      queryFn: () => fetchBackgroundTasks(thread.thread_id),
      refetchInterval: 15000,
      refetchIntervalInBackground: false,
      retry: 1,
    })),
  });
  const tasks = useMemo(
    () =>
      taskQueries
        .flatMap((query, index) =>
          (query.data ?? []).map((task) => ({
            ...task,
            threadId: threads.data?.[index]?.thread_id ?? "",
          })),
        )
        .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at)),
    [taskQueries, threads.data],
  );
  const loading =
    threads.isLoading || taskQueries.some((query) => query.isLoading);
  const errors = threads.isError || taskQueries.some((query) => query.isError);
  const visible = tasks.filter(
    (task) =>
      filter === "all" ||
      (filter === "active"
        ? active.has(task.status)
        : filter === "attention"
          ? task.status === "failed" ||
            task.status === "input_required" ||
            task.tracking_degraded
          : task.status === "completed"),
  );
  const configured =
    !mcp.error &&
    Object.entries(mcp.config?.mcp_servers ?? {}).some(
      ([name, config]) => name.startsWith("deermate") && config.enabled,
    );
  const count = (state: string) =>
    tasks.filter((task) =>
      state === "active" ? active.has(task.status) : task.status === state,
    ).length;
  const refresh = () => {
    void threads.refetch();
    void models.refetch();
    void health.refetch();
    taskQueries.forEach((query) => {
      void query.refetch();
    });
  };
  function prepareDraft() {
    if (!draft.trim()) return;
    const storage = getSessionComposerDraftStorage();
    writeComposerDraft(storage, draftKey, {
      text: draft.trim(),
      skillName: null,
    });
    if (readComposerDraft(storage, draftKey)?.text !== draft.trim()) {
      setDraftError(true);
      return;
    }
    router.push("/workspace/chats/new");
  }

  return (
    <div className="dm-desk">
      <header className="dm-topbar">
        <div>
          <WorkspaceSidebarTrigger />
          <span>{text("工作台", "Your desk")}</span>
          <span className="dm-breadcrumb">/</span>
          <span className="dm-muted">{text("总览", "Overview")}</span>
        </div>
        <div className="dm-topbar-right">
          <span className={`dm-health ${health.isError ? "is-unknown" : ""}`}>
            <i />
            {health.isLoading
              ? text("检查服务…", "Checking…")
              : health.isError
                ? text("服务暂不可用", "Service unavailable")
                : text("Gateway 正常", "Gateway ready")}
          </span>
          <Link
            href="/workspace?settings=account"
            className="dm-account"
            aria-label={text("账户设置", "Account settings")}
          >
            {(user?.email ?? "D").slice(0, 1).toUpperCase()}
          </Link>
        </div>
      </header>
      <div className="dm-page">
        <section className="dm-hero">
          <div className="dm-hero-copy">
            <p className="dm-eyebrow">A LITTLE HELP. A LOT MORE POSSIBILITY.</p>
            <h1>
              {text("把目标交给我，", "Your next idea,")}
              <br />
              <span>{text("把时间留给自己。", "in good hands.")}</span>
            </h1>
            <p>
              {text(
                "这里是你的私人秘书工作台。从一个目标开始，随时查看工作的每一步。",
                "Your personal secretary’s workspace. Start with a goal. Follow the work, every step of the way.",
              )}
            </p>
          </div>
          <div className="dm-hero-mark">
            <BrandMotion />
            <span>DeerMate</span>
            <small>
              {text("你的私人 Agent 秘书", "Your personal agent secretary")}
            </small>
          </div>
        </section>
        <div className="dm-work-grid">
          <div className="dm-primary">
            <section
              className="dm-compose"
              aria-label={text("准备新任务", "Prepare a task")}
            >
              <div className="dm-compose-title">
                <Sparkles size={17} />
                <span>
                  {text(
                    "今天，想完成什么？",
                    "What would you like to get done?",
                  )}
                </span>
                <span className="dm-small dm-muted">
                  {text("新任务", "NEW TASK")}
                </span>
              </div>
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  prepareDraft();
                }}
              >
                <label className="sr-only" htmlFor="dm-goal">
                  {text("任务目标", "Task goal")}
                </label>
                <textarea
                  id="dm-goal"
                  value={draft}
                  maxLength={8000}
                  onChange={(event) => {
                    setDraft(event.target.value);
                    setDraftError(false);
                  }}
                  placeholder={text(
                    "描述你的目标，我会陪你从这里开始…",
                    "Describe a goal. Let’s take it from here…",
                  )}
                />
                <div className="dm-compose-footer">
                  <span>
                    <LockKeyhole size={13} />
                    {text(
                      "草稿仅保存在当前浏览器会话",
                      "Draft stays in this browser session",
                    )}
                  </span>
                  <button
                    type="submit"
                    className="dm-button"
                    disabled={!draft.trim()}
                  >
                    {text("准备对话", "Prepare chat")}
                    <ArrowRight size={16} />
                  </button>
                </div>
              </form>
              {draftError && (
                <p role="alert">
                  {text(
                    "浏览器暂不能保存草稿。请直接新建对话并输入目标。",
                    "Draft storage is unavailable. Open a new conversation to enter your goal.",
                  )}
                  <Link href="/workspace/chats/new">
                    {text("新建对话", "New chat")}
                  </Link>
                </p>
              )}
            </section>
            <div className="dm-shortcuts">
              {[
                [
                  Code2,
                  text("修复一个 Bug", "Fix a bug"),
                  text(
                    "分析已注册项目的一个可复现 Bug，先说明原因和验证计划。",
                    "Analyze a reproducible bug in a registered project. Start with its cause and a validation plan.",
                  ),
                ],
                [
                  FileSearch,
                  text("检查代码改动", "Review a change"),
                  text(
                    "审阅项目的这份改动，列出有依据的问题与建议。",
                    "Review this project change and report evidence-based findings.",
                  ),
                ],
                [
                  ListChecks,
                  text("整理一项计划", "Plan a project"),
                  text(
                    "帮我把这个目标拆成可检查的步骤，标明需要我补充的信息。",
                    "Break this goal into verifiable steps and identify the information you need from me.",
                  ),
                ],
              ].map(([Icon, label, prompt]) => {
                const Glyph = Icon as typeof Code2;
                return (
                  <button
                    key={String(label)}
                    onClick={() => {
                      setDraft(String(prompt));
                      document.getElementById("dm-goal")?.focus();
                    }}
                  >
                    <Glyph size={16} />
                    <span>{String(label)}</span>
                    <ArrowUpRight size={13} />
                  </button>
                );
              })}
            </div>
            {!models.isLoading &&
              (models.error || models.models.length === 0) && (
                <div className="dm-setup-note">
                  <Settings2 size={17} />
                  <div>
                    <strong>
                      {models.error
                        ? text(
                            "暂时无法读取模型配置",
                            "Model configuration unavailable",
                          )
                        : text(
                            "让秘书开始协作，还差一步。",
                            "One more step to get started.",
                          )}
                    </strong>
                    <p>
                      {models.error
                        ? text(
                            "请重试；当前状态未知。",
                            "Retry to check the current state.",
                          )
                        : text(
                            "连接聊天模型后，即可在对话中提交目标。现在可以准备草稿、查看已有任务。",
                            "Connect a chat model to submit goals. You can prepare drafts and inspect existing tasks now.",
                          )}
                    </p>
                  </div>
                  <Link href="/workspace?settings=models">
                    {text("模型设置", "Model settings")}
                    <ArrowUpRight size={14} />
                  </Link>
                </div>
              )}
            <section className="dm-tasks" aria-labelledby="dm-task-title">
              <div className="dm-section-heading">
                <div>
                  <p className="dm-eyebrow">WORK IN MOTION</p>
                  <h2 id="dm-task-title">
                    {text("每件事，都有进展。", "A place for every next step.")}
                  </h2>
                </div>
                <button
                  className="dm-icon-button"
                  onClick={refresh}
                  aria-label={text("刷新工作台", "Refresh workspace")}
                >
                  <RefreshCw size={16} />
                </button>
              </div>
              <div className="dm-task-toolbar">
                <MotionTabs
                  value={filter}
                  onChange={setFilter}
                  items={[
                    { id: "all", label: text("全部", "All") },
                    { id: "active", label: text("进行中", "Active") },
                    { id: "done", label: text("已完成", "Done") },
                    { id: "attention", label: text("需关注", "Attention") },
                  ]}
                />
                <span className="dm-small dm-muted">
                  {text("最近 20 个对话", "Latest 20 conversations")}
                </span>
              </div>
              {errors && (
                <div role="alert" className="dm-fetch-error">
                  <TriangleAlert size={15} />
                  {text(
                    "部分任务未能读取，下面可能不是完整结果。",
                    "Some tasks could not be loaded. Results may be incomplete.",
                  )}
                  <button onClick={refresh}>{text("重试", "Retry")}</button>
                </div>
              )}
              <div
                id="dm-task-panel"
                role="tabpanel"
                aria-labelledby={`dm-tab-${filter}`}
                aria-busy={loading}
              >
                {loading && tasks.length === 0 ? (
                  <p className="dm-empty" role="status">
                    <LoaderCircle className="dm-spin" size={18} />
                    {text("正在整理任务…", "Gathering your tasks…")}
                  </p>
                ) : visible.length === 0 ? (
                  <div className="dm-empty">
                    <ArrowDownToLine size={25} />
                    <strong>
                      {errors
                        ? text(
                            "已读取的任务中暂无匹配项",
                            "No matches in available results",
                          )
                        : text(
                            "这里，留给下一件值得做的事。",
                            "Room for your next good idea.",
                          )}
                    </strong>
                    <span>
                      {text(
                        "新任务准备好后，执行记录会出现在这里。",
                        "Your execution records will appear here as work begins.",
                      )}
                    </span>
                  </div>
                ) : (
                  visible.map((task, index) => (
                    <button
                      key={`${task.threadId}:${task.task_id}`}
                      className="dm-task-row"
                      style={
                        {
                          "--dm-index": Math.min(index, 5),
                        } as React.CSSProperties
                      }
                      onClick={(event) => {
                        taskOpener.current = event.currentTarget;
                        setSelected(task);
                      }}
                    >
                      <span className={`dm-task-icon dm-state-${task.status}`}>
                        {task.status === "completed" ? (
                          <Check size={18} />
                        ) : task.status === "failed" ? (
                          <TriangleAlert size={18} />
                        ) : (
                          <Terminal size={18} />
                        )}
                      </span>
                      <span className="dm-task-label">
                        <strong>{task.task_name}</strong>
                        <span>
                          {text("后台执行", "Background task")} ·{" "}
                          {new Date(task.updated_at).toLocaleString(locale, {
                            month: "short",
                            day: "numeric",
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </span>
                      </span>
                      <span className={`dm-state dm-state-${task.status}`}>
                        {task.cancel_requested && task.status !== "cancelled"
                          ? text("取消待确认", "Cancel pending")
                          : (labels[task.status]?.[zh ? 0 : 1] ?? task.status)}
                        {task.tracking_degraded
                          ? text(" · 跟踪异常", " · stale")
                          : ""}
                      </span>
                      <ChevronRight size={15} />
                    </button>
                  ))
                )}
              </div>
            </section>
          </div>
          <aside
            className="dm-team"
            aria-label={text("执行团队", "Agent team")}
          >
            <p className="dm-eyebrow">YOUR SMALL, CAPABLE TEAM</p>
            <h2>{text("专事，专办。", "Good company.")}</h2>
            <p className="dm-team-intro">
              {text(
                "连接擅长这件事的 Agent。由你选择，按权限执行。",
                "Connect the right agent for the job. Your choices. Your permissions.",
              )}
            </p>
            <div className="dm-agent">
              <div className="dm-agent-icon">
                <Terminal size={18} />
              </div>
              <div>
                <strong>Codex</strong>
                <span>{text("实现与验证", "Build & validate")}</span>
              </div>
              <span
                className={`dm-agent-state ${configured ? "is-configured" : ""}`}
              >
                {mcp.isLoading
                  ? "…"
                  : mcp.error || user?.system_role !== "admin"
                    ? text("状态未知", "Unknown")
                    : configured
                      ? text("已配置", "Configured")
                      : text("未配置", "Not set up")}
              </span>
            </div>
            <p className="dm-agent-note">
              {text(
                "MCP 配置状态；不代表设备当前在线。",
                "MCP configuration only; device availability is not checked.",
              )}
            </p>
            <div className="dm-agent dm-agent-planned">
              <div className="dm-agent-icon">
                <Code2 size={18} />
              </div>
              <div>
                <strong>Claude Code</strong>
                <span>{text("设计与审阅", "Design & review")}</span>
              </div>
              <span className="dm-agent-state">
                {text("规划中", "Planned")}
              </span>
            </div>
            <div className="dm-agent dm-agent-planned">
              <div className="dm-agent-icon">
                <Bot size={18} />
              </div>
              <div>
                <strong>DeepSeek Harness</strong>
                <span>{text("专业执行", "Specialist work")}</span>
              </div>
              <span className="dm-agent-state">
                {text("规划中", "Planned")}
              </span>
            </div>
            <Link href="/workspace/capabilities" className="dm-team-link">
              {text("管理接入能力", "Manage capabilities")}
              <ArrowUpRight size={14} />
            </Link>
            <div className="dm-summary">
              <h3>{text("一眼看见进展", "At a glance")}</h3>
              <dl>
                <div>
                  <dt>
                    <Circle size={10} />
                    {text("进行中", "Active")}
                  </dt>
                  <dd>{errors || loading ? "—" : count("active")}</dd>
                </div>
                <div>
                  <dt>
                    <Check size={12} />
                    {text("已完成", "Completed")}
                  </dt>
                  <dd>{errors || loading ? "—" : count("completed")}</dd>
                </div>
                <div>
                  <dt>
                    <TriangleAlert size={12} />
                    {text("执行失败", "Failed")}
                  </dt>
                  <dd>{errors || loading ? "—" : count("failed")}</dd>
                </div>
              </dl>
              <small>
                {text(
                  "仅统计最近 20 个对话的已读取任务",
                  "Loaded tasks from the latest 20 conversations",
                )}
              </small>
            </div>
            <footer className="dm-private-note">
              <LockKeyhole size={15} />
              <span>
                {text(
                  "自己的部署，自己的工作。模型调用仍由你选择的服务商处理。",
                  "Your deployment, your work. Model requests are processed by your chosen provider.",
                )}
              </span>
            </footer>
          </aside>
        </div>
        <footer className="dm-page-footer">
          <span>
            DeerMate <i>·</i>{" "}
            {text("留一点时间，给生活。", "A little more time for life.")}
          </span>
          <span>
            Built with DeerFlow <ArrowUpRight size={11} />
          </span>
        </footer>
      </div>
      <TaskDetail
        task={selected}
        onClose={() => setSelected(null)}
        restoreFocus={() => taskOpener.current?.focus()}
      />
    </div>
  );
}
