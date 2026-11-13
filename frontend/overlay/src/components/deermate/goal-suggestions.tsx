"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRef, useState } from "react";

import { dmCopy } from "@/components/deermate/i18n/copy";
import { ErrorBanner } from "@/components/deermate/ui";
import { Button, Card, Heading, Text } from "@/components/deermate/ui";

import { workspaceAPI } from "./workspace-api";

type Suggestion = { fact_id: string; fact_revision: number; question: string };
type Intent = {
  id: string;
  question: string;
  status: string;
  thread_id: string;
};
export function GoalSuggestions({
  userId,
  zh,
}: {
  userId: string;
  zh: boolean;
}) {
  const query = useQuery({
    queryKey: ["deermate", "briefing", userId],
    queryFn: () =>
      workspaceAPI<{ suggestions: Suggestion[] }>(userId, "briefing"),
    retry: 1,
    refetchInterval: 30000,
  });
  const pending = useRef<Intent | null>(null);
  const [intent, setIntent] = useState<Intent | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const status = useQuery({
    queryKey: ["goal-intent", userId, intent?.id],
    queryFn: () =>
      workspaceAPI<Intent>(userId, `briefing/actions/${intent!.id}`),
    enabled:
      !!intent && !["completed", "failed", "blocked"].includes(intent.status),
    refetchInterval: (q) =>
      ["completed", "failed", "blocked"].includes(q.state.data?.status ?? "")
        ? false
        : 3000,
    retry: 1,
    gcTime: 0,
  });
  async function start(v: Suggestion) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const prepared =
        pending.current ??
        (await workspaceAPI<Intent>(userId, "briefing/actions", {
          method: "POST",
          body: JSON.stringify({
            kind: "new_topic",
            fact_id: v.fact_id,
            fact_revision: v.fact_revision,
          }),
        }));
      if (prepared.question !== v.question) throw new Error();
      pending.current = prepared;
      const accepted = await workspaceAPI<Intent>(
        userId,
        `briefing/actions/${prepared.id}`,
        { method: "POST", body: "{}" },
      );
      pending.current = null;
      setIntent(accepted);
    } catch {
      setError(
        dmCopy(
          zh,
          "goal-suggestions.creation.is.unconfirmed.retry.to.reconcile.this..3a4b5a",
        ),
      );
      if (pending.current) setIntent(pending.current);
    } finally {
      setBusy(false);
    }
  }
  async function dismiss(v: Suggestion) {
    try {
      await workspaceAPI(userId, "workspace-feedback", {
        method: "POST",
        body: JSON.stringify({
          id: `suggest-${v.fact_id}`,
          version: `rev-${v.fact_revision}`,
          action: "dismiss",
        }),
      });
      await query.refetch();
    } catch {
      setError(
        dmCopy(
          zh,
          "goal-suggestions.this.change.was.not.saved.try.again..95620c",
        ),
      );
    }
  }
  if (query.isError || !query.data?.suggestions.length) return null;
  const current = status.data ?? intent;
  return (
    <Card
      data-testid="goal-suggestions"
      as="section"
      className="dm-goal-suggestions"
    >
      <Heading level={2}>
        {dmCopy(zh, "goal-suggestions.something.else.to.explore.74a2ec")}
      </Heading>
      {query.data.suggestions.slice(0, 2).map((v) => (
        <div key={v.fact_id}>
          <p>{v.question}</p>
          <Text as="p" size="caption" tone="muted" className="">
            {dmCopy(
              zh,
              "goal-suggestions.based.on.a.long.term.goal.you.shared..9ec814",
            )}
          </Text>
          <div data-testid="assistant-actions" className="dm-assistant-actions">
            <Button
              loading={busy}
              variant="ghost"
              size="sm"
              type="button"
              disabled={busy || (!!current && current.status !== "prepared")}
              onClick={() => void start(v)}
            >
              {busy
                ? dmCopy(zh, "goal-suggestions.creating..978565")
                : dmCopy(zh, "goal-suggestions.start.this.topic.3e80c9")}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              type="button"
              onClick={() => void dismiss(v)}
            >
              {dmCopy(zh, "goal-suggestions.not.interested.965c55")}
            </Button>
          </div>
        </div>
      ))}
      {current && (
        <p role="status">
          {current.status === "completed" ? (
            <Link href={`/workspace/chats/${current.thread_id}`}>
              {dmCopy(zh, "goal-suggestions.open.conversation.ca9762")}
            </Link>
          ) : current.status === "failed" || current.status === "blocked" ? (
            dmCopy(
              zh,
              "goal-suggestions.this.conversation.did.not.start.check.the.model..35756b",
            )
          ) : (
            dmCopy(
              zh,
              "goal-suggestions.recorded.reconciling.the.original.request..532152",
            )
          )}
        </p>
      )}
      {error && <ErrorBanner role="alert">{error}</ErrorBanner>}
    </Card>
  );
}
