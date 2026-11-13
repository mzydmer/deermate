"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  ListChecks,
  MessageSquarePlus,
  Shield,
  UserRound,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { dmCopy } from "@/components/deermate/i18n/copy";
import { ErrorBanner, Skeleton } from "@/components/deermate/ui";
import {
  Button,
  Card,
  Heading,
  RelativeTime,
  Text,
} from "@/components/deermate/ui";
import { useAuth } from "@/core/auth/AuthProvider";
import { useI18n } from "@/core/i18n/hooks";

import { GoalSuggestions } from "./goal-suggestions";
import { FocusRow } from "./patterns/focus-row";
import { AppShell } from "./patterns/shell";
import { TopBar } from "./patterns/shell";
import { PersonalGreeting, PersonalMemoryPanel } from "./personal-memory";
import { SecretaryConversation } from "./secretary-conversation";
import { SectionHeader } from "./ui";
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
    kind?: string;
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
  return <TopBar title={title} zh={zh} />;
}

export function WorkspaceAssistant() {
  const { user } = useAuth();
  const { locale } = useI18n();
  const zh = locale === "zh-CN";
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
        dmCopy(
          zh,
          "workspace-assistant.this.change.was.not.saved.try.again..aee450",
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
        dmCopy(
          zh,
          "workspace-assistant.creation.is.unconfirmed.retry.to.reconcile.the.s.9d1c47",
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
    <AppShell data-testid="desk assistant">
      <WorkspaceHeader
        title={dmCopy(zh, "workspace-assistant.assistant.e7461b")}
        zh={zh}
      />
      <main data-testid="assistant-grid" className="dm-assistant-grid">
        <div data-testid="assistant-main" className="dm-assistant-main">
          <section
            data-testid="assistant-greeting"
            className="dm-assistant-greeting"
          >
            <PersonalGreeting userId={owner} zh={zh} />
            <p>
              {snapshot.data?.items.length
                ? dmCopy(
                    zh,
                    "workspace-assistant.here.is.where.we.left.off..4a808a",
                  )
                : dmCopy(
                    zh,
                    "workspace-assistant.tell.me.what.is.on.your.mind..7bf0dd",
                  )}
            </p>
          </section>
          {snapshot.isLoading && (
            <Skeleton
              label={dmCopy(
                zh,
                "workspace-assistant.checking.recent.work..19d2de",
              )}
            />
          )}
          {snapshot.isError && (
            <ErrorBanner
              onRetry={() => void snapshot.refetch()}
              retryLabel={dmCopy(zh, "common.retry")}
            >
              {dmCopy(
                zh,
                "workspace-assistant.recent.updates.are.unavailable.you.can.still.cha.fd7aa3",
              )}
            </ErrorBanner>
          )}
          {!!snapshot.data?.items.length && (
            <section
              data-testid="assistant-focus"
              className="dm-assistant-focus"
              aria-labelledby="dm-focus-title"
            >
              <SectionHeader
                icon={ListChecks}
                title={
                  <span id="dm-focus-title">
                    {dmCopy(
                      zh,
                      "workspace-assistant.a.few.things.to.pick.up.349e7b",
                    )}{" "}
                    · {snapshot.data.items.length}
                  </span>
                }
                trailing={
                  <div className="flex items-center gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-expanded={focusOpen}
                      aria-controls="dm-focus-items"
                      onClick={() => setFocusOpen(!focusOpen)}
                    >
                      {focusOpen
                        ? dmCopy(zh, "workspace-assistant.hide.0be8b8")
                        : dmCopy(zh, "workspace-assistant.show.f2c46b")}
                    </Button>
                    <Button variant="ghost" size="sm" asChild>
                      <Link href="/workspace/work">
                        {dmCopy(zh, "workspace-assistant.all.work.e11d75")}
                        <ArrowRight className="size-4" />
                      </Link>
                    </Button>
                  </div>
                }
              />
              {focusOpen && (
                <ul data-testid="focus-items" id="dm-focus-items">
                  {snapshot.data.items.slice(0, 3).map((item) => (
                    <FocusRow
                      key={item.id}
                      title={
                        item.title ||
                        dmCopy(zh, "workspace-assistant.untitled.work.7bd514")
                      }
                      domain={
                        item.evidence.stale || item.evidence.tracking_degraded
                          ? "connection"
                          : item.evidence.validation_failed ||
                              item.evidence.verified
                            ? "validation"
                            : item.kind === "work"
                              ? "continuous"
                              : item.evidence.kind === "conversation"
                                ? "conversation"
                                : "execution"
                      }
                      status={
                        item.evidence.stale || item.evidence.tracking_degraded
                          ? "offline"
                          : item.evidence.validation_failed
                            ? "failed"
                            : item.evidence.verified
                              ? "passed"
                              : item.evidence.kind === "conversation"
                                ? "recorded"
                                : item.evidence.status === "completed"
                                  ? "completed_unverified"
                                  : item.evidence.status
                      }
                      meta={
                        <RelativeTime
                          value={item.evidence.occurred_at}
                          timezone={snapshot.data?.profile.timezone}
                          locale={locale}
                        />
                      }
                      action={
                        <Button asChild variant="secondary" size="sm">
                          <Link
                            href={
                              item.kind === "work"
                                ? `/workspace/work#${item.work_id}`
                                : `/workspace/chats/${item.thread_id}`
                            }
                            onClick={() => void feedback(item, "seen")}
                          >
                            {item.kind === "work"
                              ? dmCopy(
                                  zh,
                                  "workspace-assistant.view.work.c69e77",
                                )
                              : dmCopy(
                                  zh,
                                  "workspace-assistant.continue.chat.635c96",
                                )}
                            <ArrowRight className="size-4" />
                          </Link>
                        </Button>
                      }
                      menuLabel={dmCopy(zh, "common.more")}
                      menu={[
                        {
                          label: dmCopy(
                            zh,
                            "workspace-assistant.later.today.64be31",
                          ),
                          action: () => void feedback(item, "snooze_today"),
                        },
                        {
                          label: dmCopy(
                            zh,
                            "workspace-assistant.stop.reminding.me.7e982e",
                          ),
                          action: () => void feedback(item, "dismiss"),
                        },
                      ]}
                    />
                  ))}
                </ul>
              )}
            </section>
          )}
          {user.system_role === "admin" ? (
            <SecretaryConversation userId={owner} zh={zh} />
          ) : (
            <p>
              {dmCopy(
                zh,
                "workspace-assistant.open.your.own.chats.execution.requires.administr.34f1d3",
              )}
            </p>
          )}
          <div
            data-testid="assistant-actions assistant-new"
            className="dm-assistant-actions dm-assistant-new"
          >
            <Button variant="ghost" size="sm" asChild>
              <Link href="/workspace/chats/new">
                <MessageSquarePlus size={16} />
                {dmCopy(zh, "workspace-assistant.start.a.new.topic.666fd8")}
              </Link>
            </Button>
            <Button
              loading={creating}
              variant="ghost"
              size="sm"
              type="button"
              onClick={() => void temporary()}
              disabled={creating}
            >
              <Shield size={16} />
              {creating
                ? dmCopy(zh, "workspace-assistant.creating..978565")
                : dmCopy(zh, "workspace-assistant.temporary.chat.777201")}
            </Button>
          </div>
          {error && <ErrorBanner role="alert">{error}</ErrorBanner>}
        </div>
        <aside data-testid="assistant-aside" className="dm-assistant-aside">
          <Card as="section">
            <SectionHeader
              icon={UserRound}
              title={dmCopy(zh, "workspace-assistant.about.you.38ca3c")}
              trailing={
                <Button variant="ghost" size="sm" asChild>
                  <Link href="/workspace/memory">
                    {dmCopy(zh, "workspace-assistant.view.all.51f8dc")}
                  </Link>
                </Button>
              }
            />
            {snapshot.data && !snapshot.data.profile.auto_capture_enabled && (
              <p role="status">
                {dmCopy(
                  zh,
                  "workspace-assistant.automatic.capture.is.paused.saved.facts.remain.m.6239a0",
                )}
              </p>
            )}
            {snapshot.data && !snapshot.data.profile.memory_enabled && (
              <p role="status">
                {dmCopy(
                  zh,
                  "workspace-assistant.saved.memory.is.currently.excluded.from.answers..93728e",
                )}
              </p>
            )}
            {memory.isLoading && (
              <Skeleton
                label={dmCopy(zh, "workspace-assistant.loading.memory..0539a4")}
              />
            )}
            {memory.isError ? (
              <p>
                {dmCopy(
                  zh,
                  "workspace-assistant.memory.is.temporarily.unavailable..1ecb30",
                )}
              </p>
            ) : (
              <ul
                data-testid="assistant-memory-summary"
                className="dm-assistant-memory-summary"
              >
                {memories.map((v) => (
                  <li key={v.id}>{v.content}</li>
                ))}
              </ul>
            )}
            {!memory.isLoading && !memory.isError && !memories.length && (
              <Text as="p" tone="muted" className="">
                {dmCopy(
                  zh,
                  "workspace-assistant.nothing.saved.yet.just.start.talking.there.is.no.8ad7cb",
                )}
              </Text>
            )}
            <Link href="/workspace/memory">
              {dmCopy(
                zh,
                "workspace-assistant.correct.anything.i.get.wrong.7f98a3",
              )}
              <ArrowRight size={14} />
            </Link>
          </Card>
          {user.system_role === "admin" && (
            <GoalSuggestions userId={owner} zh={zh} />
          )}
          <HistoryProgress userId={owner} zh={zh} compact />
        </aside>
      </main>
    </AppShell>
  );
}

export function WorkspaceMemory() {
  const { user } = useAuth();
  const { locale } = useI18n();
  const zh = locale === "zh-CN";
  return user ? (
    <AppShell data-testid="desk assistant">
      <WorkspaceHeader
        title={dmCopy(zh, "workspace-assistant.about.you.38ca3c")}
        zh={zh}
      />
      <main
        data-testid="assistant-memory-page"
        className="dm-assistant-memory-page"
      >
        <Heading level={1}>
          {dmCopy(zh, "workspace-assistant.about.you.38ca3c")}
        </Heading>
        <Text as="p" tone="muted" className="">
          {dmCopy(
            zh,
            "workspace-assistant.preferences.goals.and.requirements.you.shared.co.03a477",
          )}
        </Text>
        <HistoryProgress userId={user.id} zh={zh} />
        <PersonalMemoryPanel userId={user.id} zh={zh} embedded />
      </main>
    </AppShell>
  ) : null;
}
