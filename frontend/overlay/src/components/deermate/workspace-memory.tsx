"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useRef, useState } from "react";

import { dmCopy } from "@/components/deermate/i18n/copy";
import { ErrorBanner, Skeleton } from "@/components/deermate/ui";
import { Button, Heading, Text } from "@/components/deermate/ui";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { useAuth } from "@/core/auth/AuthProvider";
import { useI18n } from "@/core/i18n/hooks";

import { StatusBadge } from "./ui";
import { workspaceAPI } from "./workspace-api";

type Source = {
  kind: string;
  state: string;
  scope: string;
  text?: string;
  thread_id?: string;
  observed_at?: number;
  updated_at: number;
  expires_at?: number;
  uses: { thread_id: string; title: string; included_at: number }[];
};

export function MemorySource({
  userId,
  factId,
  restoreFocus,
  onClose,
  zh,
}: {
  userId: string;
  factId: string;
  restoreFocus?: () => void;
  onClose: () => void;
  zh: boolean;
}) {
  const opener = useRef<HTMLElement | null>(
    typeof document !== "undefined"
      ? (document.activeElement as HTMLElement)
      : null,
  );
  const source = useQuery({
    queryKey: ["memory-source", userId, factId],
    queryFn: () => workspaceAPI<Source>(userId, `memories/${factId}/source`),
    enabled: !!factId,
    refetchInterval: 3000,
    refetchIntervalInBackground: false,
    retry: 1,
    gcTime: 0,
  });
  const [error, setError] = useState("");
  async function exclude() {
    try {
      await workspaceAPI(userId, `topic-memory/${source.data!.thread_id}`, {
        method: "PATCH",
        body: JSON.stringify({ excluded: true }),
      });
      setError(
        dmCopy(
          zh,
          "workspace-memory.this.topic.is.excluded.from.future.capture.exist.468cb7",
        ),
      );
    } catch {
      setError(
        dmCopy(
          zh,
          "workspace-memory.this.change.was.not.saved.try.again..8f0400",
        ),
      );
    }
  }
  return (
    <Sheet
      open={!!factId}
      onOpenChange={(v) => {
        if (!v) onClose();
      }}
    >
      <SheetContent
        data-testid="workspace memory-source"
        className="dm-workspace dm-memory-source"
        onCloseAutoFocus={(e) => {
          e.preventDefault();
          if (restoreFocus) restoreFocus();
          else opener.current?.focus();
        }}
      >
        <SheetHeader className="p-0">
          <SheetTitle>
            {dmCopy(zh, "workspace-memory.memory.source.5a5266")}
          </SheetTitle>
          <SheetDescription>
            {dmCopy(
              zh,
              "workspace-memory.check.the.original.statement.and.where.this.fact.bc2023",
            )}
          </SheetDescription>
        </SheetHeader>
        {source.isPending && (
          <Skeleton
            label={dmCopy(zh, "workspace-memory.loading.source..696dbc")}
          />
        )}
        {source.isError && (
          <ErrorBanner role="alert">
            {dmCopy(zh, "workspace-memory.source.unavailable..a97028")}
            <Button
              variant="primary"
              type="button"
              onClick={() => void source.refetch()}
            >
              {dmCopy(zh, "workspace-memory.retry.2cd694")}
            </Button>
          </ErrorBanner>
        )}
        {!source.isError && source.data && (
          <div
            data-testid="memory-source-body"
            className="dm-memory-source-body"
          >
            <Text as="p" size="caption" tone="muted" className="">
              {scopeLabel(source.data.scope, zh)} ·{" "}
              {new Date(source.data.updated_at * 1000).toLocaleString()}
            </Text>
            {source.data.state !== "available" ? (
              <p>
                {dmCopy(
                  zh,
                  "workspace-memory.the.source.is.unavailable.this.memory.is.exclude.9c6ef5",
                )}
              </p>
            ) : source.data.kind === "manual" ? (
              <p>
                {dmCopy(
                  zh,
                  "workspace-memory.you.saved.or.corrected.this.fact.in.memory.setti.7969b4",
                )}
              </p>
            ) : (
              <>
                <blockquote>{source.data.text}</blockquote>
                {source.data.observed_at && (
                  <Text as="p" size="caption" tone="muted" className="">
                    {new Date(source.data.observed_at * 1000).toLocaleString()}
                  </Text>
                )}
                <Link
                  href={
                    source.data.kind === "inbox"
                      ? "/workspace"
                      : `/workspace/chats/${source.data.thread_id}`
                  }
                >
                  {dmCopy(
                    zh,
                    "workspace-memory.open.original.conversation.0bf45d",
                  )}
                </Link>
                {source.data.kind === "chat" && (
                  <Button
                    variant="primary"
                    type="button"
                    onClick={() => void exclude()}
                  >
                    {dmCopy(zh, "workspace-memory.exclude.this.topic.b2f72d")}
                  </Button>
                )}
              </>
            )}
            {!!source.data.expires_at && (
              <Text as="p" size="caption" tone="muted" className="">
                {dmCopy(zh, "workspace-memory.expires.dc61a8")}{" "}
                {new Date(source.data.expires_at * 1000).toLocaleDateString()}
              </Text>
            )}
            <Heading level={3}>
              {dmCopy(zh, "workspace-memory.recently.included.in.3aaf4d")}
            </Heading>
            <Text as="p" size="caption" tone="muted" className="">
              {dmCopy(
                zh,
                "workspace-memory.included.in.model.context.this.does.not.prove.th.908a0a",
              )}
            </Text>
            {source.data.uses.length ? (
              <ul>
                {source.data.uses.map((v) => (
                  <li key={v.thread_id}>
                    <Link href={`/workspace/chats/${v.thread_id}`}>
                      {v.title ||
                        dmCopy(zh, "workspace-memory.untitled.chat.bcab73")}
                    </Link>
                    <Text as="p" size="caption" tone="muted" className="">
                      {new Date(v.included_at * 1000).toLocaleString()}
                    </Text>
                  </li>
                ))}
              </ul>
            ) : (
              <Text as="p" tone="muted" className="">
                {dmCopy(
                  zh,
                  "workspace-memory.no.visible.usage.records.yet..53b54b",
                )}
              </Text>
            )}
            {error && <p role="status">{error}</p>}
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}

export function scopeLabel(scope: string, zh: boolean) {
  return scope.startsWith("project:")
    ? dmCopy(zh, "workspace-memory.this.project.9cac57")
    : scope.startsWith("topic:")
      ? dmCopy(zh, "workspace-memory.this.topic.c96822")
      : dmCopy(zh, "workspace-memory.personal.preferences.and.context.eeb729");
}

type History = {
  status: string;
  total: number;
  settled: number;
  topics: number;
};
export function HistoryProgress({
  userId,
  zh,
  compact = false,
}: {
  userId: string;
  zh: boolean;
  compact?: boolean;
}) {
  const cache = useQueryClient();
  const [error, setError] = useState("");
  const query = useQuery({
    queryKey: ["memory-history", userId],
    queryFn: () => workspaceAPI<History>(userId, "memory-history"),
    refetchInterval: 10000,
    retry: 1,
  });
  async function action(value: string) {
    try {
      await workspaceAPI(userId, "memory-history", {
        method: "POST",
        body: JSON.stringify({ action: value }),
      });
      await query.refetch();
      for (const key of [
        ["deermate", "personal-memory", userId],
        ["workspace-memory-summary", userId],
        ["memory-source", userId],
      ]) {
        void cache.invalidateQueries({ queryKey: key });
      }
    } catch {
      setError(
        dmCopy(
          zh,
          "workspace-memory.this.action.is.unconfirmed.reconcile.it.later..ff5076",
        ),
      );
    }
  }
  if (!query.data || query.isError) return null;
  const v = query.data;
  const active = ["not_started", "processing", "queued"].includes(v.status);
  if (compact)
    return (
      <div className="flex items-center gap-2">
        <StatusBadge domain="history" status={v.status} />
      </div>
    );
  return (
    <section
      className={
        compact ? "dm-assistant-history" : "dm-memory-history ds-app-card"
      }
    >
      <Heading level={3}>
        {dmCopy(zh, "workspace-memory.picking.up.recent.context.9df270")}
      </Heading>
      <Text as="p" size="caption" tone="muted" className="">
        {active
          ? dmCopy(
              zh,
              "workspace-memory.up.to.ten.conversations.from.the.past.seven.days.15183a",
            )
          : ["stop", "undo", "interrupted"].includes(v.status)
            ? dmCopy(
                zh,
                "workspace-memory.history.import.stopped.new.chats.still.follow.cu.dd0b0b",
              )
            : dmCopy(
                zh,
                "workspace-memory.recent.context.checked.uncertain.facts.are.left..d9e97b",
              )}
      </Text>
      {v.total > 0 && (
        <Text as="p" size="caption" className="">
          {dmCopy(zh, "workspace-memory.settled.e34f6b")} {v.settled}/{v.total}
        </Text>
      )}
      {!compact && (
        <div data-testid="assistant-actions" className="dm-assistant-actions">
          {active && (
            <Button
              variant="primary"
              type="button"
              onClick={() => void action("stop")}
            >
              {dmCopy(zh, "workspace-memory.stop.import.d29ba3")}
            </Button>
          )}
          {v.total > 0 && v.status !== "undo" && (
            <Button
              variant="ghost"
              size="sm"
              type="button"
              onClick={() => void action("undo")}
            >
              {dmCopy(zh, "workspace-memory.undo.imported.facts.fab7ff")}
            </Button>
          )}
        </div>
      )}
      {error && <ErrorBanner role="alert">{error}</ErrorBanner>}
    </section>
  );
}

type Activity = {
  items: {
    id: string;
    status: string;
    operations: { id: string; fact_id: string; status: string; kind: string }[];
  }[];
};
export function MemoryActivity({
  userId,
  threadId,
  zh,
}: {
  userId: string;
  threadId: string;
  zh: boolean;
}) {
  const cache = useQueryClient();
  const [source, setSource] = useState("");
  const [error, setError] = useState("");
  const activity = useQuery({
    queryKey: ["memory-activity", userId, threadId],
    queryFn: () =>
      workspaceAPI<Activity>(
        userId,
        `memory-activity?thread_id=${encodeURIComponent(threadId)}`,
      ),
    enabled: !!threadId && threadId !== "new",
    refetchInterval: 3000,
    refetchIntervalInBackground: false,
    retry: 1,
    gcTime: 0,
  });
  const latest = activity.isError ? undefined : activity.data?.items[0];
  const op = latest?.operations.find((v) => v.status === "completed");
  const [dismissed, setDismissed] = useState("");
  async function undo() {
    if (!op) return;
    try {
      const page = await workspaceAPI<{
        references: {
          id: string;
          revision: number;
          source_id: string;
          status: string;
        }[];
      }>(userId, "memories");
      const ref = page.references.find(
        (v) =>
          v.id === op.fact_id && v.source_id === op.id && v.status === "active",
      );
      if (!ref) throw new Error();
      await workspaceAPI(userId, `memories/${ref.id}`, {
        method: "DELETE",
        body: JSON.stringify({
          operation_id: `undo-${op.id.slice(0, 48)}`,
          expected_revision: ref.revision,
        }),
      });
      setDismissed(latest!.id);
      void cache.invalidateQueries({
        queryKey: ["workspace-memory-summary", userId],
      });
    } catch {
      setError(
        dmCopy(
          zh,
          "workspace-memory.this.fact.changed.review.it.in.about.you..ac9f13",
        ),
      );
    }
  }
  if (
    !latest ||
    dismissed === latest.id ||
    (latest.status === "completed" && !op) ||
    latest.status === "invalidated"
  )
    return null;
  return (
    <div data-testid="memory-activity" className="dm-memory-activity">
      <span role="status">
        {latest.status === "failed"
          ? dmCopy(
              zh,
              "workspace-memory.this.was.not.saved.you.can.add.it.in.about.you..54196f",
            )
          : latest.status === "uncertain"
            ? dmCopy(
                zh,
                "workspace-memory.this.capture.is.unconfirmed.the.model.will.not.b.36b3a5",
              )
            : latest.status === "budget_wait"
              ? dmCopy(
                  zh,
                  "workspace-memory.today.s.capture.allowance.is.used.you.can.keep.c.2dbae3",
                )
              : latest.status === "clarification"
                ? dmCopy(
                    zh,
                    "workspace-memory.choose.the.memory.you.meant.in.about.you..109b5a",
                  )
                : op
                  ? op.kind === "delete"
                    ? dmCopy(
                        zh,
                        "workspace-memory.memory.forgotten.the.original.chat.is.retained..616e8f",
                      )
                    : dmCopy(
                        zh,
                        "workspace-memory.saved.for.future.conversations..c2794b",
                      )
                  : dmCopy(
                      zh,
                      "workspace-memory.checking.what.you.just.shared..9d85cd",
                    )}
      </span>
      {op && op.kind !== "delete" && (
        <>
          <Button
            variant="ghost"
            size="sm"
            type="button"
            onClick={() => setSource(op.fact_id)}
          >
            {dmCopy(zh, "workspace-memory.source.58b22d")}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            type="button"
            onClick={() => void undo()}
          >
            {op.kind === "create"
              ? dmCopy(zh, "workspace-memory.undo.414c20")
              : dmCopy(zh, "workspace-memory.forget.63cfb8")}
          </Button>
        </>
      )}
      <Link href="/workspace/memory">
        {dmCopy(zh, "workspace-memory.about.you.38ca3c")}
      </Link>
      {source && (
        <MemorySource
          userId={userId}
          factId={source}
          zh={zh}
          onClose={() => setSource("")}
        />
      )}{" "}
      {error && <ErrorBanner role="alert">{error}</ErrorBanner>}
    </div>
  );
}

export function ChatMemoryBanner() {
  const { user } = useAuth();
  const { locale } = useI18n();
  const zh = locale === "zh-CN";
  const params = useParams<{ thread_id?: string }>();
  const id = params.thread_id ?? "";
  const mode = useQuery({
    queryKey: ["topic-memory", user?.id, id],
    queryFn: () =>
      workspaceAPI<{ mode: string }>(user!.id, `topic-memory/${id}`),
    enabled: !!user && !!id && id !== "new",
    retry: 1,
    gcTime: 0,
  });
  if (!user || !id || id === "new") return null;
  return (
    <div data-testid="chat-memory-banner" className="dm-chat-memory-banner">
      {mode.data?.mode === "temporary" ? (
        <p role="status">
          {dmCopy(
            zh,
            "workspace-memory.temporary.chat.no.long.term.memory.is.read.or.sa.075526",
          )}
        </p>
      ) : mode.data?.mode === "excluded" ? (
        <p role="status">
          {dmCopy(
            zh,
            "workspace-memory.this.topic.is.excluded.from.long.term.capture..9085c7",
          )}
        </p>
      ) : (
        <MemoryActivity userId={user.id} threadId={id} zh={zh} />
      )}
    </div>
  );
}
