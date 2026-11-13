"use client";

import { useQueries } from "@tanstack/react-query";
import { ListChecks } from "lucide-react";
import { Search } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";

import { dmCopy } from "@/components/deermate/i18n/copy";
import { ErrorBanner, SectionHeader } from "@/components/deermate/ui";
import {
  Button,
  Card,
  Empty,
  Heading,
  Input,
  InputGroup,
  RelativeTime,
  SegmentedControl,
  Skeleton,
  StatusBadge,
  Text,
} from "@/components/deermate/ui";
import { useAuth } from "@/core/auth/AuthProvider";
import { fetchBackgroundTasks } from "@/core/background-tasks";
import { useI18n } from "@/core/i18n/hooks";
import { useThreads } from "@/core/threads/hooks";

import { ContinuousSecretary } from "./continuous-secretary";
import { AppShell } from "./patterns/shell";
import { TaskDetail, type DeskTask } from "./task-detail";
import { WorkspaceHeader } from "./workspace-assistant";

export function WorkspaceWork() {
  const { user } = useAuth();
  const { locale } = useI18n();
  const zh = locale === "zh-CN";
  const [search, setSearch] = useState("");
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
  const visible = tasks
    .filter((task) =>
      task.task_name.toLowerCase().includes(search.toLowerCase()),
    )
    .filter(
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
  return (
    <AppShell data-testid="desk assistant">
      <WorkspaceHeader
        title={dmCopy(zh, "workspace-work.my.work.1e404f")}
        zh={zh}
      />
      <main
        data-testid="assistant-work-page"
        className="dm-assistant-work-page grid-cols-1"
      >
        <div data-testid="section-heading" className="dm-section-heading">
          <Heading level={1}>
            {dmCopy(zh, "workspace-work.my.work.1e404f")}
          </Heading>
          <Button asChild variant="primary">
            <Link href="/workspace/chats/new">
              {dmCopy(zh, "common.newtopic")}
            </Link>
          </Button>
        </div>
        <Text as="p" tone="muted" className="">
          {dmCopy(
            zh,
            "workspace-work.replies.needed.progress.and.results.in.one.place.0679c2",
          )}
        </Text>
        <ContinuousSecretary
          userId={user.id}
          zh={zh}
          canRun={user.system_role === "admin"}
          workOnly
        />
        <section
          data-testid="native-work"
          className="dm-native-work min-w-0 grid-cols-1"
        >
          <div data-testid="section-heading" className="dm-section-heading">
            <SectionHeader
              icon={ListChecks}
              title={
                <>
                  {dmCopy(
                    zh,
                    "workspace-work.executions.from.your.chats.15d40b",
                  )}
                </>
              }
            />
            <SegmentedControl
              label={dmCopy(zh, "workspace-work.filter.d617c7")}
              value={filter}
              onChange={setFilter}
              items={[
                {
                  value: "all",
                  label: dmCopy(zh, "workspace-work.all.bafb97"),
                  count: tasks.length,
                },
                {
                  value: "attention",
                  label: dmCopy(zh, "workspace-work.needs.attention.1af2e4"),
                  count: tasks.filter(
                    (t) =>
                      ["failed", "input_required"].includes(t.status) ||
                      t.tracking_degraded,
                  ).length,
                },
                {
                  value: "active",
                  label: dmCopy(zh, "workspace-work.active.b69c8c"),
                  count: tasks.filter((t) =>
                    ["working", "submitted"].includes(t.status),
                  ).length,
                },
                {
                  value: "ended",
                  label: dmCopy(zh, "workspace-work.ended.c0e3f9"),
                  count: tasks.filter((t) =>
                    ["completed", "cancelled"].includes(t.status),
                  ).length,
                },
              ]}
            />
          </div>
          <InputGroup prefix={<Search className="size-4" aria-hidden="true" />}>
            <Input
              data-testid="work-search"
              aria-label={dmCopy(zh, "common.search")}
              placeholder={dmCopy(zh, "common.search")}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </InputGroup>
          {(threads.isLoading || queries.some((q) => q.isLoading)) && (
            <Skeleton
              label={dmCopy(zh, "workspace-work.loading.work..188312")}
            />
          )}
          {(threads.isError || queries.some((q) => q.isError)) && (
            <ErrorBanner role="alert">
              {dmCopy(
                zh,
                "workspace-work.some.records.could.not.be.refreshed.and.may.be.s.8f3120",
              )}
              <Button
                variant="ghost"
                size="sm"
                type="button"
                onClick={() => {
                  void threads.refetch();
                  queries.forEach((q) => void q.refetch());
                }}
              >
                {dmCopy(zh, "workspace-work.retry.2cd694")}
              </Button>
            </ErrorBanner>
          )}
          {!threads.isLoading &&
            !queries.some((q) => q.isLoading || q.isError) &&
            !visible.length && (
              <Empty
                title={dmCopy(
                  zh,
                  "workspace-work.no.executions.here.yet.tell.your.assistant.what..3e6e5b",
                )}
              />
            )}
          <ul
            data-testid="work-record-list"
            className="dm-work-record-list min-w-0 grid-cols-1"
          >
            {visible.map((task) => (
              <Card
                data-testid="work-record-row"
                as="li"
                variant="compact"
                key={`${task.threadId}-${task.task_id}`}
              >
                <div>
                  <div className="flex min-w-0 items-center gap-2">
                    <Heading level={3} className="min-w-0 flex-1 truncate">
                      {task.task_name ||
                        dmCopy(zh, "workspace-work.untitled.task.4ce5bd")}
                    </Heading>
                    <span className="shrink-0 min-[600px]:hidden">
                      <RelativeTime value={task.updated_at} locale={locale} />
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge
                      status={
                        task.status === "completed"
                          ? "completed_unverified"
                          : task.status
                      }
                    />
                    <span className="hidden min-[600px]:inline-flex">
                      <RelativeTime value={task.updated_at} locale={locale} />
                    </span>
                    {task.tracking_degraded && (
                      <StatusBadge domain="connection" status="offline" />
                    )}
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  type="button"
                  onClick={(e) => {
                    opener.current = e.currentTarget;
                    setSelected(task);
                  }}
                >
                  {dmCopy(zh, "workspace-work.view.details.b34027")}
                </Button>
              </Card>
            ))}
          </ul>
          <Text as="p" size="caption" tone="muted" className="">
            {dmCopy(
              zh,
              "workspace-work.shows.executions.from.your.twenty.most.recent.ch.b83e40",
            )}
          </Text>
        </section>
      </main>
      <TaskDetail
        task={selected}
        onClose={() => setSelected(null)}
        restoreFocus={() => {
          if (opener.current?.isConnected) opener.current.focus();
          else
            document
              .querySelector<HTMLInputElement>('[data-testid="work-search"]')
              ?.focus();
        }}
      />
    </AppShell>
  );
}
