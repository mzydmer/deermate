"use client";
import Link from "next/link";

import { dmCopy } from "@/components/deermate/i18n/copy";
import {
  Button,
  Disclosure,
  DisclosureTrigger,
  ErrorBanner,
  Field,
  Heading,
  Input,
  Select,
  Skeleton,
  Text,
} from "@/components/deermate/ui";
import type { AgentThread } from "@/core/threads/types";
import { titleOfThread } from "@/core/threads/utils";

import { usePersonalHomeController } from "./controller";
import { NativeContinuation } from "./native-continuation";
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
  const {
    data,
    busy,
    refresh,
    briefing,
    time,
    goal,
    status,
    editTopic,
    runAction,
    intent,
    pendingAction,
    operation,
    pollUntil,
    topics,
    addTopic,
    thread,
    createNonce,
    setThread,
    oldLink,
    setOldLink,
    setGoal,
    error,
  } = usePersonalHomeController({ userId, zh, canRun, threads, onTask });
  return (
    <section
      data-testid="personal-home"
      className="dm-personal-home"
      aria-label={dmCopy(zh, "personal-home.today.s.focus.f51f5a")}
    >
      <div data-testid="section-heading" className="dm-section-heading">
        <Heading level={2}>
          {dmCopy(zh, "personal-home.today.s.focus.f51f5a")}
        </Heading>
        <Button
          variant="ghost"
          size="sm"
          type="button"
          disabled={busy}
          onClick={() => void refresh()}
        >
          {dmCopy(zh, "personal-home.refresh.focus.105838")}
        </Button>
      </div>
      {briefing.isLoading && (
        <Skeleton
          label={dmCopy(zh, "personal-home.checking.your.focus..86894a")}
        />
      )}
      {briefing.isError && (
        <ErrorBanner role="alert">
          {dmCopy(
            zh,
            "personal-home.focus.unavailable.your.existing.chats.and.tasks..a70f23",
          )}
        </ErrorBanner>
      )}
      {data && (
        <>
          <Text as="p" size="caption" tone="muted" className="">
            {data.local_date} · {data.timezone} ·{" "}
            {dmCopy(zh, "personal-home.records.checked.at.ca1d57")}{" "}
            {time(data.checked_at)}
          </Text>
          {data.items.length === 0 && (
            <Text as="p" tone="muted" className="">
              {dmCopy(
                zh,
                "personal-home.no.focus.items.to.show.today.follow.an.existing..333ec3",
              )}
            </Text>
          )}
          <ul data-testid="focus-list" className="dm-focus-list">
            {data.items.map((item) => (
              <li key={item.topic.id}>
                <div
                  data-testid="section-heading"
                  className="dm-section-heading"
                >
                  <Heading level={3}>
                    <Link href={`/workspace/chats/${item.topic.thread_id}`}>
                      {item.topic.title}
                    </Link>
                  </Heading>
                  {item.has_changes && (
                    <Text as="span" size="caption" className="">
                      {dmCopy(zh, "personal-home.record.changed.827bcf")}
                    </Text>
                  )}
                </div>
                {item.topic.goal && <p>{item.topic.goal}</p>}
                <p>{status(item.evidence)}</p>
                <Text as="p" size="caption" tone="muted" className="">
                  {item.evidence.occurred_at && (
                    <>
                      {dmCopy(zh, "personal-home.source.event.345884")}{" "}
                      {time(item.evidence.occurred_at)} ·{" "}
                    </>
                  )}
                  {item.evidence.polled_at && (
                    <>
                      {dmCopy(zh, "personal-home.executor.synced.d6a7d5")}{" "}
                      {time(item.evidence.polled_at)} ·{" "}
                    </>
                  )}
                  {dmCopy(
                    zh,
                    "personal-home.a.conversation.you.chose.to.follow.d20eab",
                  )}
                </Text>
                {item.evidence.cancel_requested && (
                  <Text as="p" size="caption" className="">
                    {dmCopy(
                      zh,
                      "personal-home.cancellation.was.requested.this.does.not.confirm.7fcba1",
                    )}
                  </Text>
                )}
                <div data-testid="focus-actions" className="dm-focus-actions">
                  <Link href={`/workspace/chats/${item.topic.thread_id}`}>
                    {item.evidence.busy
                      ? dmCopy(zh, "personal-home.view.ongoing.work.bcb5d6")
                      : dmCopy(zh, "personal-home.open.conversation.335957")}
                  </Link>
                  {item.evidence.task_id && (
                    <Button
                      variant="ghost"
                      size="sm"
                      type="button"
                      onClick={() =>
                        onTask(
                          item.topic.thread_id,
                          item.evidence.task_id!,
                          item.evidence.status,
                        )
                      }
                    >
                      {dmCopy(zh, "personal-home.view.result.b54491")}
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    type="button"
                    disabled={busy}
                    onClick={() =>
                      void editTopic(item.topic, "seen", item.evidence.version)
                    }
                  >
                    {dmCopy(zh, "personal-home.mark.read.742a5e")}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    type="button"
                    disabled={busy}
                    onClick={() => void editTopic(item.topic, "snooze_today")}
                  >
                    {dmCopy(zh, "personal-home.hide.for.today.d20a3b")}
                  </Button>
                </div>
                {!item.evidence.busy && !item.evidence.stale && (
                  <Disclosure
                    data-testid="focus-followup"
                    className="dm-focus-followup"
                  >
                    <DisclosureTrigger>
                      {dmCopy(zh, "personal-home.follow.up.c91f10")}
                    </DisclosureTrigger>
                    <p>{item.followup_question}</p>
                    <Button
                      variant="primary"
                      type="button"
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
                      {dmCopy(
                        zh,
                        "personal-home.ask.a.read.only.follow.up.45da44",
                      )}
                    </Button>
                    {item.evidence.task_id && (
                      <NativeContinuation
                        user={userId}
                        item={item}
                        zh={zh}
                        disabled={busy || !canRun}
                        onRun={runAction}
                      />
                    )}
                  </Disclosure>
                )}
              </li>
            ))}
          </ul>
          {data.unavailable > 0 && (
            <Text as="p" tone="muted" className="">
              {dmCopy(
                zh,
                "personal-home.some.sources.are.unavailable.or.archived.their.o.d98dee",
              )}
            </Text>
          )}
          {data.total > 3 && (
            <Text as="p" size="caption" className="">
              {dmCopy(zh, "personal-home.more-followed").replace(
                "{count}",
                String(data.total - 3),
              )}
            </Text>
          )}
          {data.suggestions.length > 0 && (
            <div data-testid="suggestions" className="dm-suggestions">
              <Heading level={3}>
                {dmCopy(zh, "personal-home.you.might.explore.next.f175c6")}
              </Heading>
              {data.suggestions.map((suggestion) => (
                <div key={suggestion.fact_id}>
                  <p>{suggestion.question}</p>
                  <Text as="p" size="caption" tone="muted" className="">
                    {dmCopy(
                      zh,
                      "personal-home.because.you.explicitly.saved.this.long.term.goal.a22cef",
                    )}
                  </Text>
                  <Button
                    variant="ghost"
                    size="sm"
                    type="button"
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
                    {dmCopy(zh, "personal-home.start.this.topic.3e80c9")}
                  </Button>
                </div>
              ))}
            </div>
          )}
          {data.suggestions_unavailable && (
            <Text as="p" tone="muted" className="">
              {dmCopy(
                zh,
                "personal-home.suggestions.unavailable.your.followed.topics.rem.6b1ffb",
              )}
            </Text>
          )}
        </>
      )}
      {intent && (
        <div data-testid="home-action" role="status" className="dm-home-action">
          <p>
            {intent.status === "completed"
              ? dmCopy(zh, "personal-home.follow.up.complete..9c4396")
              : intent.status === "failed"
                ? dmCopy(
                    zh,
                    "personal-home.follow.up.failed.open.its.record.to.inspect..4b1bda",
                  )
                : intent.status === "blocked"
                  ? dmCopy(
                      zh,
                      "personal-home.source.or.permission.changed.the.old.action.is.b.aa5329",
                    )
                  : intent.status === "uncertain"
                    ? dmCopy(
                        zh,
                        "personal-home.outcome.uncertain.only.the.original.operation.is.5d8f98",
                      )
                    : intent.status === "prepared"
                      ? dmCopy(
                          zh,
                          "personal-home.not.admitted.yet.you.can.retry.the.same.request..72a744",
                        )
                      : dmCopy(
                          zh,
                          "personal-home.admitted.and.in.progress..3b3173",
                        )}
          </p>
          {intent.status === "prepared" && (
            <Button
              variant="ghost"
              size="sm"
              type="button"
              disabled={busy}
              onClick={() => {
                pendingAction.current = intent;
                void runAction({}, intent.question);
              }}
            >
              {dmCopy(zh, "personal-home.retry.this.request.7b75ba")}
            </Button>
          )}
          {["uncertain", "running", "submitting"].includes(intent.status) && (
            <Button
              variant="ghost"
              size="sm"
              type="button"
              disabled={busy || operation.isFetching}
              onClick={() => {
                pollUntil.current = Date.now() + 120000;
                void operation.refetch();
              }}
            >
              {dmCopy(zh, "personal-home.reconcile.original.result.0e5620")}
            </Button>
          )}
          {intent.thread_id && (
            <Link href={`/workspace/chats/${intent.thread_id}`}>
              {dmCopy(zh, "personal-home.open.follow.up.result.d4f7b8")}
            </Link>
          )}
        </div>
      )}
      <Disclosure
        data-testid="attention-management"
        className="dm-attention-management"
      >
        <DisclosureTrigger>
          {dmCopy(zh, "personal-home.manage.focus.e53b7f")}
        </DisclosureTrigger>
        {topics.isError && (
          <ErrorBanner role="alert">
            {dmCopy(zh, "personal-home.could.not.load.followed.topics..0d348f")}
          </ErrorBanner>
        )}
        <ul data-testid="focus-list" className="dm-focus-list">
          {!topics.isError &&
            topics.data?.items.map((topic) => (
              <li key={topic.id}>
                <p>
                  {topic.source_state === "available"
                    ? topic.title
                    : dmCopy(
                        zh,
                        "personal-home.source.unavailable.or.archived.73afe1",
                      )}
                </p>
                <Text as="span" size="caption" tone="muted" className="">
                  {topic.status === "paused"
                    ? dmCopy(zh, "personal-home.paused.30dbde")
                    : topic.status === "completed"
                      ? dmCopy(zh, "personal-home.finished.c02a49")
                      : topic.snoozed_until > Date.now() / 1000
                        ? dmCopy(zh, "personal-home.hidden.for.today.233211")
                        : dmCopy(zh, "personal-home.following.ddc42f")}
                </Text>
                <div data-testid="focus-actions" className="dm-focus-actions">
                  {topic.status === "active" && (
                    <Button
                      variant="ghost"
                      size="sm"
                      type="button"
                      disabled={busy}
                      onClick={() => void editTopic(topic, "pause")}
                    >
                      {dmCopy(zh, "personal-home.pause.15134d")}
                    </Button>
                  )}
                  {(topic.status !== "active" ||
                    topic.snoozed_until > Date.now() / 1000) &&
                    topic.source_state === "available" && (
                      <Button
                        variant="ghost"
                        size="sm"
                        type="button"
                        disabled={busy}
                        onClick={() => void editTopic(topic, "resume")}
                      >
                        {dmCopy(zh, "personal-home.resume.475d37")}
                      </Button>
                    )}
                  {topic.status === "active" && (
                    <Button
                      variant="ghost"
                      size="sm"
                      type="button"
                      disabled={busy}
                      onClick={() => void editTopic(topic, "complete")}
                    >
                      {dmCopy(zh, "personal-home.finish.11df69")}
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    type="button"
                    disabled={busy}
                    onClick={() => void editTopic(topic, "remove")}
                  >
                    {dmCopy(zh, "personal-home.unfollow.1d3a98")}
                  </Button>
                </div>
              </li>
            ))}
        </ul>
        <form
          data-testid="memory-form"
          className="dm-memory-form"
          onSubmit={(event) => {
            event.preventDefault();
            void addTopic();
          }}
        >
          <Field>
            {dmCopy(zh, "personal-home.choose.an.existing.conversation.e0a67a")}
            <Select
              value={thread}
              disabled={busy || !!createNonce.current}
              onChange={(event) => setThread(event.target.value)}
            >
              <option value="">
                {dmCopy(zh, "personal-home.choose.a.conversation..76cedc")}
              </option>
              {threads.map((entry) => (
                <option key={entry.thread_id} value={entry.thread_id}>
                  {titleOfThread(
                    entry,
                    dmCopy(zh, "personal-home.untitled.conversation.11ea18"),
                  )}
                </option>
              ))}
            </Select>
          </Field>
          <Field>
            {dmCopy(
              zh,
              "personal-home.or.paste.an.older.conversation.link.cf7493",
            )}
            <Input
              value={oldLink}
              disabled={busy || !!createNonce.current}
              maxLength={1000}
              onChange={(event) => setOldLink(event.target.value)}
              placeholder="/workspace/chats/…"
            />
          </Field>
          <Field>
            {dmCopy(zh, "personal-home.what.would.you.like.to.follow..204d67")}
            <Input
              value={goal}
              disabled={busy || !!createNonce.current}
              maxLength={500}
              onChange={(event) => setGoal(event.target.value)}
            />
          </Field>
          <Button
            variant="primary"
            type="submit"
            disabled={busy || (!thread && !oldLink)}
          >
            {createNonce.current
              ? dmCopy(zh, "personal-home.reconcile.follow.f2687e")
              : dmCopy(zh, "personal-home.follow.this.conversation.13f11c")}
          </Button>
        </form>
      </Disclosure>
      {error && <ErrorBanner role="alert">{error}</ErrorBanner>}
    </section>
  );
}
