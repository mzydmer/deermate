"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { dmCopy } from "@/components/deermate/i18n/copy";
import { StatusBadge } from "@/components/deermate/ui";
import type { AgentThread } from "@/core/threads/types";

import {
  type Briefing,
  type Continuation,
  type Evidence,
  homeAPI,
  type Intent,
  type Topic,
} from "./model";

export function usePersonalHomeController({
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
      ? dmCopy(
          zh,
          "personal-home.the.source.or.state.changed.refresh.to.reconcile.7a4401",
        )
      : dmCopy(
          zh,
          "personal-home.unavailable.admitted.actions.are.reconciled.neve.352deb",
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
    if (Number.isNaN(date.getTime()))
      return dmCopy(zh, "personal-home.time.unknown.7bcd6a");
    return new Intl.DateTimeFormat(dmCopy(zh, "personal-home.en.us.218b02"), {
      timeZone: briefing.data?.timezone ?? "UTC",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  }
  function status(e: Evidence) {
    return (
      <StatusBadge
        domain={
          e.tracking_degraded
            ? "connection"
            : e.verified
              ? "validation"
              : "execution"
        }
        status={
          e.tracking_degraded
            ? "offline"
            : e.verified
              ? "passed"
              : e.status === "completed"
                ? "completed_unverified"
                : e.status
        }
      />
    );
  }
  const data = briefing.isError ? undefined : briefing.data;
  return {
    data,
    userId,
    zh,
    canRun,
    threads,
    onTask,
    cache,
    briefing,
    topics,
    thread,
    setThread,
    oldLink,
    setOldLink,
    goal,
    setGoal,
    busy,
    setBusy,
    error,
    setError,
    intent,
    setIntent,
    createNonce,
    pendingAction,
    pollUntil,
    operation,
    refresh,
    message,
    addTopic,
    editTopic,
    runAction,
    time,
    status,
  };
}
