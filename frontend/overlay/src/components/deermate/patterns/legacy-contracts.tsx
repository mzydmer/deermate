"use client";
// Fixture-only host for retained home contracts, never exposed in production.
import { useRef, useState } from "react";

import { useAuth } from "@/core/auth/AuthProvider";
import { useI18n } from "@/core/i18n/hooks";
import { useThreads } from "@/core/threads/hooks";

import { PersonalHome } from "../personal-home";
import { PersonalGreeting, PersonalMemoryPanel } from "../personal-memory";
import { TaskDetail, type DeskTask } from "../task-detail";

import { AppShell, TopBar } from "./shell";
export function LegacyContracts() {
  const { user } = useAuth();
  const [task, setTask] = useState<DeskTask | null>(null);
  const opener = useRef<HTMLElement | null>(null);
  const { locale } = useI18n();
  const threads = useThreads({
    limit: 20,
    sortBy: "updated_at",
    sortOrder: "desc",
  });
  if (!user) return null;
  const zh = locale === "zh-CN";
  return (
    <AppShell>
      <TopBar title="Component contracts" zh={zh} />
      <main className="grid gap-6 p-6">
        <PersonalGreeting userId={user.id} zh={zh} />
        <PersonalHome
          userId={user.id}
          zh={zh}
          canRun={user.system_role === "admin"}
          threads={threads.data ?? []}
          onTask={(threadId, task_id, status) => {
            opener.current = document.activeElement as HTMLElement;
            setTask({
              threadId,
              task_id,
              status,
              task_name: task_id,
              updated_at: new Date().toISOString(),
              cancel_requested: false,
              tracking_degraded: false,
              error: null,
            });
          }}
        />
        <PersonalMemoryPanel userId={user.id} zh={zh} />
      </main>
      <TaskDetail
        task={task}
        onClose={() => setTask(null)}
        restoreFocus={() => opener.current?.focus()}
      />
    </AppShell>
  );
}
