"use client";

import { useQueries } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { useAuth } from "@/core/auth/AuthProvider";
import { fetchBackgroundTasks } from "@/core/background-tasks";
import { useI18n } from "@/core/i18n/hooks";
import { useThreads } from "@/core/threads/hooks";

import { ContinuousSecretary } from "./continuous-secretary";
import { TaskDetail, type DeskTask } from "./task-detail";
import { WorkspaceHeader } from "./workspace-assistant";

export function WorkspaceWork() {
  const { user } = useAuth();
  const { locale } = useI18n();
  const zh = locale === "zh-CN";
  const t = (a: string, b: string) => (zh ? a : b);
  const [filter, setFilter] = useState("all");
  const [selected, setSelected] = useState<DeskTask | null>(null);
  const opener = useRef<HTMLButtonElement | null>(null);
  const threads = useThreads({
    limit: 20,
    sortBy: "updated_at",
    sortOrder: "desc",
    select: ["thread_id", "updated_at", "values", "metadata"],
  });
  const queries = useQueries({
    queries: (threads.data ?? []).map((thread) => ({
      queryKey: ["deermate", "thread-tasks", user?.id, thread.thread_id],
      queryFn: () => fetchBackgroundTasks(thread.thread_id),
      retry: 1,
      refetchInterval: 10000,
      refetchIntervalInBackground: false,
    })),
  });
  const tasks = queries
    .flatMap((q, i) =>
      (q.data ?? []).map((task) => ({
        ...task,
        threadId: threads.data?.[i]?.thread_id ?? "",
      })),
    )
    .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at));
  const visible = tasks.filter(
    (task) =>
      filter === "all" ||
      (filter === "attention"
        ? ["failed", "input_required"].includes(task.status) ||
          task.tracking_degraded
        : filter === "active"
          ? ["working", "submitted"].includes(task.status)
          : ["completed", "cancelled"].includes(task.status)),
  );
  if (!user) return null;
  const labels: Record<string, string> = {
    submitted: t("排队中", "Queued"),
    working: t("处理中", "Running"),
    input_required: t("等你答复", "Needs your reply"),
    completed: t("执行已结束", "Execution ended"),
    failed: t("执行失败", "Failed"),
    cancelled: t("已停止", "Stopped"),
  };
  return (
    <div className="dm-desk dm-assistant">
      <WorkspaceHeader title={t("我的工作", "My work")} zh={zh} />
      <main className="dm-assistant-work-page">
        <h1>{t("我的工作", "My work")}</h1>
        <p className="dm-muted">
          {t(
            "哪些等你答复，哪些有了结果，都在这里。",
            "Replies needed, progress and results in one place.",
          )}
        </p>
        <ContinuousSecretary
          userId={user.id}
          zh={zh}
          canRun={user.system_role === "admin"}
          workOnly
        />
        <section className="dm-native-work">
          <div className="dm-section-heading">
            <h2>{t("对话里的执行记录", "Executions from your chats")}</h2>
            <label>
              {t("筛选", "Filter")}
              <select
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              >
                <option value="all">{t("全部", "All")}</option>
                <option value="attention">
                  {t("待回应", "Needs attention")}
                </option>
                <option value="active">{t("处理中", "Active")}</option>
                <option value="ended">{t("已结束", "Ended")}</option>
              </select>
            </label>
          </div>
          {(threads.isLoading || queries.some((q) => q.isLoading)) && (
            <p role="status">{t("正在读取工作…", "Loading work…")}</p>
          )}
          {(threads.isError || queries.some((q) => q.isError)) && (
            <p role="alert">
              {t(
                "有些记录暂时没读到。已显示的状态可能过时。",
                "Some records could not be refreshed and may be stale.",
              )}
              <button
                className="dm-text-button"
                onClick={() => {
                  void threads.refetch();
                  queries.forEach((q) => void q.refetch());
                }}
              >
                {t("重试", "Retry")}
              </button>
            </p>
          )}
          {!threads.isLoading &&
            !queries.some((q) => q.isLoading || q.isError) &&
            !visible.length && (
              <p className="dm-muted">
                {t(
                  "这里暂时没有执行记录。回到助手，交代想做的事就好。",
                  "No executions here yet. Tell your assistant what you want to do.",
                )}
              </p>
            )}
          <ul className="dm-work-record-list">
            {visible.map((task) => (
              <li
                className="ds-app-card"
                key={`${task.threadId}-${task.task_id}`}
              >
                <div>
                  <h3>{task.task_name || t("未命名任务", "Untitled task")}</h3>
                  <p className="dm-small dm-muted">
                    {labels[task.status] ?? task.status} ·{" "}
                    {new Date(task.updated_at).toLocaleString()}
                  </p>
                  {task.tracking_degraded && (
                    <p>
                      {t(
                        "连接暂不可用，尚未确认最新状态。",
                        "The latest state is unconfirmed while disconnected.",
                      )}
                    </p>
                  )}
                </div>
                <button
                  className="ds-app-button-secondary"
                  onClick={(e) => {
                    opener.current = e.currentTarget;
                    setSelected(task);
                  }}
                >
                  {t("查看详情", "View details")}
                </button>
              </li>
            ))}
          </ul>
          <p className="dm-small dm-muted">
            {t(
              "这里展示最近二十个对话中的执行。更早的记录仍可从原对话打开。",
              "Shows executions from your twenty most recent chats. Older records remain in their original chats.",
            )}
          </p>
        </section>
      </main>
      <TaskDetail
        task={selected}
        onClose={() => setSelected(null)}
        restoreFocus={() => opener.current?.focus()}
      />
    </div>
  );
}
