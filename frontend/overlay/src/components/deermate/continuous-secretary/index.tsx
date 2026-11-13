"use client";
import { ListChecks } from "lucide-react";
import Link from "next/link";

import { dmCopy } from "@/components/deermate/i18n/copy";
import {
  Empty,
  ErrorBanner,
  SectionHeader,
  Skeleton,
} from "@/components/deermate/ui";
import {
  Button,
  Disclosure,
  DisclosureTrigger,
  Field,
  Select,
  Text,
  Textarea,
} from "@/components/deermate/ui";

import { AutomationSettings } from "./AutomationSettings";
import { useSecretaryController } from "./controller";
import { str } from "./model";
import { NewWorkForm } from "./NewWorkForm";
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
  const {
    busy,
    cache,
    prefix,
    config,
    works,
    router,
    error,
    enabled,
    mutate,
    message,
    setMessage,
    readUnavailable,
    status,
    goal,
    project,
    grant,
    setGoal,
    setProject,
    setGrant,
    workFilter,
    setWorkFilter,
    selected,
    setSelected,
    current,
    followups,
    setFollowups,
    timeline,
    sources,
    rules,
    instruction,
    setInstruction,
    decisions,
  } = useSecretaryController({ userId, zh, canRun, workOnly });
  if (!canRun) return null;
  const automation = enabled ? (
    <AutomationSettings
      zh={zh}
      config={config}
      busy={busy}
      readUnavailable={readUnavailable}
      mutate={mutate}
      sources={sources}
      rules={rules}
      instruction={instruction}
      project={project}
      grant={grant}
      setInstruction={setInstruction}
      decisions={decisions}
    />
  ) : null;
  if (
    workOnly &&
    works.isSuccess &&
    works.data.items.length === 0 &&
    !config.isError &&
    !error
  )
    return automation;
  return (
    <section
      data-testid="personal-home continuous"
      className="dm-personal-home dm-continuous"
      aria-label={dmCopy(
        zh,
        "continuous-secretary.continuous.secretary.60ec29",
      )}
    >
      <div data-testid="section-heading" className="dm-section-heading">
        <SectionHeader
          icon={ListChecks}
          title={<>{dmCopy(zh, "continuous-secretary.work.orders.34ec8a")}</>}
        />
        <Link href="/workspace/memory">
          {dmCopy(zh, "continuous-secretary.manage.memory.b84195")}
        </Link>
        <Button
          variant="ghost"
          size="sm"
          type="button"
          disabled={busy}
          onClick={() => void cache.invalidateQueries({ queryKey: prefix })}
        >
          {dmCopy(zh, "continuous-secretary.refresh.ae19c3")}
        </Button>
      </div>
      {config.isPending && (
        <Skeleton
          label={dmCopy(zh, "continuous-secretary.loading.settings..f0a02f")}
        />
      )}
      {works.isPending && (
        <Skeleton
          label={dmCopy(zh, "continuous-secretary.loading.work..188312")}
        />
      )}
      {(config.isError || works.isError || router.isError) && (
        <ErrorBanner role="alert">
          {dmCopy(
            zh,
            "continuous-secretary.refresh.failed.displayed.state.may.be.stale..566210",
          )}
        </ErrorBanner>
      )}
      {error && (
        <ErrorBanner
          data-testid="continuous-error"
          role="alert"
          className="dm-continuous-error"
        >
          {error}
        </ErrorBanner>
      )}
      {config.data && !enabled && (
        <Text as="p" tone="muted" role="status" className="">
          {dmCopy(
            zh,
            "continuous-secretary.the.secretary.is.temporarily.unavailable.try.aga.2f33e2",
          )}
        </Text>
      )}
      {enabled && !workOnly && (
        <>
          <form
            data-testid="continuous-form"
            className="dm-continuous-form"
            onSubmit={(e) => {
              e.preventDefault();
              void mutate("router/messages", "POST", { text: message }, () =>
                setMessage(""),
              );
            }}
          >
            <Field>
              {dmCopy(zh, "continuous-secretary.ask.your.secretary.96393a")}
              <Textarea
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                maxLength={8000}
                placeholder={dmCopy(
                  zh,
                  "continuous-secretary.follow.up.on.work.or.describe.a.new.goal..4a1e69",
                )}
                required
              />
            </Field>
            <Button
              variant="primary"
              type="submit"
              disabled={
                busy || readUnavailable || router.isError || !message.trim()
              }
            >
              {dmCopy(zh, "continuous-secretary.send.f1004b")}
            </Button>
          </form>
          {router.isPending && (
            <Skeleton
              label={dmCopy(
                zh,
                "continuous-secretary.loading.secretary.receipts..17da82",
              )}
            />
          )}
          <ul
            data-testid="focus-list router-messages"
            className="dm-focus-list dm-router-messages"
            aria-live="polite"
          >
            {router.data?.items
              .slice(0, 6)
              .reverse()
              .map((v) => (
                <li key={v.id}>
                  <Text as="p" size="caption" tone="muted" className="">
                    {str(v, "origin") === "user"
                      ? dmCopy(zh, "continuous-secretary.you.a9b773")
                      : dmCopy(
                          zh,
                          "continuous-secretary.work.update.65a3de",
                        )}{" "}
                    · {status(v)}
                  </Text>
                  <p>{str(v, "text")}</p>
                  {v.state === "waiting_model" && (
                    <p role="status">
                      {dmCopy(
                        zh,
                        "continuous-secretary.add.or.select.a.supported.conversation.model.in..19f591",
                      )}{" "}
                      <Link href="/workspace?settings=models">
                        {dmCopy(
                          zh,
                          "continuous-secretary.model.settings.ecc0c0",
                        )}
                      </Link>
                    </p>
                  )}
                  {str(v, "reply") && (
                    <p data-testid="router-reply" className="dm-router-reply">
                      {str(v, "reply")}
                    </p>
                  )}
                  {v.state === "uncertain" && (
                    <small>
                      {dmCopy(
                        zh,
                        "continuous-secretary.keep.this.input.and.inspect.it.before.delegating.039f3a",
                      )}
                      {str(v, "operation_id")}
                    </small>
                  )}
                </li>
              ))}
          </ul>
          <NewWorkForm
            zh={zh}
            mutate={mutate}
            goal={goal}
            project={project}
            grant={grant}
            setGoal={setGoal}
            setProject={setProject}
            setGrant={setGrant}
            busy={busy}
            readUnavailable={readUnavailable}
          />
        </>
      )}
      {works.data?.items.length === 0 && (
        <Empty
          title={dmCopy(
            zh,
            "continuous-secretary.no.work.orders.yet.tell.your.assistant.what.you..c1d2e5",
          )}
        />
      )}
      <Field>
        {dmCopy(zh, "continuous-secretary.work.status.7d8da6")}
        <Select
          value={workFilter}
          onChange={(e) => setWorkFilter(e.target.value)}
        >
          <option value="all">
            {dmCopy(zh, "continuous-secretary.all.bafb97")}
          </option>
          <option value="attention">
            {dmCopy(zh, "continuous-secretary.needs.attention.1af2e4")}
          </option>
          <option value="active">
            {dmCopy(zh, "continuous-secretary.active.b69c8c")}
          </option>
          <option value="ended">
            {dmCopy(zh, "continuous-secretary.ended.c0e3f9")}
          </option>
        </Select>
      </Field>
      <ul data-testid="focus-list" className="dm-focus-list">
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
              <div data-testid="section-heading" className="dm-section-heading">
                <Button
                  variant="ghost"
                  size="sm"
                  type="button"
                  aria-expanded={selected === v.id}
                  onClick={() => setSelected(selected === v.id ? "" : v.id)}
                >
                  {str(v, "title") ||
                    dmCopy(zh, "continuous-secretary.untitled.work.7bd514")}
                </Button>
                <Text as="span" size="caption" className="">
                  {status(v)}
                  {v.data.verified === true
                    ? dmCopy(zh, "continuous-secretary..verified.477c51")
                    : ""}
                </Text>
              </div>
              <Text as="p" size="caption" tone="muted" className="">
                {str(v, "goal")}
              </Text>
              {v.data.has_update === true && (
                <Text as="p" size="caption" className="">
                  {dmCopy(
                    zh,
                    "continuous-secretary.subscribed.thread.has.new.context.46014a",
                  )}
                </Text>
              )}
              {current?.id === v.id && (
                <div data-testid="work-detail" className="dm-work-detail">
                  <p>{str(v, "preview")}</p>
                  {str(v, "source_state") === "unavailable" && (
                    <Text as="p" size="caption" tone="muted" className="">
                      {dmCopy(
                        zh,
                        "continuous-secretary.source.unavailable.summaries.are.hidden.existing.bc3d54",
                      )}
                    </Text>
                  )}
                  <Text as="p" size="caption" className="">
                    Codex · {str(v, "project")} ·{" "}
                    {str(v, "incarnation") ? (
                      <Link href={`/workspace/chats/${str(v, "thread_id")}`}>
                        {dmCopy(
                          zh,
                          "continuous-secretary.execution.chat.86b374",
                        )}
                      </Link>
                    ) : (
                      <span>
                        {dmCopy(
                          zh,
                          "continuous-secretary.execution.chat.appears.after.admission.994dc8",
                        )}
                      </span>
                    )}
                  </Text>
                  {str(v, "execution_reason") && (
                    <Text as="p" size="caption" tone="muted" className="">
                      {dmCopy(
                        zh,
                        "continuous-secretary.execution.requires.a.current.reachable.device.gr.2a6bf0",
                      )}
                    </Text>
                  )}
                  <div data-testid="focus-actions" className="dm-focus-actions">
                    {(v.state === "active"
                      ? ["execute", "pause", "cancel", "close", "reconcile"]
                      : v.state === "paused"
                        ? ["resume", "cancel", "close", "reconcile"]
                        : ["reconcile"]
                    ).map((action) => (
                      <Button
                        variant="ghost"
                        size="sm"
                        type="button"
                        key={action}
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
                              ? dmCopy(
                                  zh,
                                  "continuous-secretary.continue.1d435b",
                                )
                              : dmCopy(
                                  zh,
                                  "continuous-secretary.execute.bb34cf",
                                ),
                            pause: dmCopy(
                              zh,
                              "continuous-secretary.pause.f55ca3",
                            ),
                            resume: dmCopy(
                              zh,
                              "continuous-secretary.resume.ac49a0",
                            ),
                            cancel: dmCopy(
                              zh,
                              "continuous-secretary.request.stop.5e056d",
                            ),
                            close: dmCopy(
                              zh,
                              "continuous-secretary.close.work.3330b9",
                            ),
                            reconcile: dmCopy(
                              zh,
                              "continuous-secretary.reconcile.23cbab",
                            ),
                          }[action]
                        }
                      </Button>
                    ))}
                  </div>
                  {v.state !== "closed" && (
                    <Field>
                      {dmCopy(zh, "continuous-secretary.next.round.379a04")}
                      <Textarea
                        value={followups[v.id] ?? ""}
                        onChange={(e) =>
                          setFollowups((drafts) => ({
                            ...drafts,
                            [v.id]: e.target.value,
                          }))
                        }
                        placeholder={dmCopy(
                          zh,
                          "continuous-secretary.describe.the.next.step.before.continuing.the.sam.5d01ec",
                        )}
                        maxLength={8000}
                      />
                    </Field>
                  )}
                  <Disclosure>
                    <DisclosureTrigger>
                      {dmCopy(
                        zh,
                        "continuous-secretary.receipts.references.f46949",
                      )}
                    </DisclosureTrigger>
                    {timeline.isPending ? (
                      <Skeleton
                        label={dmCopy(
                          zh,
                          "continuous-secretary.loading.receipts..22f800",
                        )}
                      />
                    ) : timeline.isError ? (
                      <ErrorBanner role="alert">
                        {dmCopy(
                          zh,
                          "continuous-secretary.receipts.unavailable.930826",
                        )}
                      </ErrorBanner>
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
                  </Disclosure>
                </div>
              )}
            </li>
          ))}
      </ul>
      {automation}
    </section>
  );
}
