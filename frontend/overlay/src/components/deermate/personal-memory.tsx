"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Brain, MoreHorizontal } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { dmCopy } from "@/components/deermate/i18n/copy";
import {
  Empty,
  ErrorBanner,
  SectionHeader,
  Skeleton,
} from "@/components/deermate/ui";
import {
  Button,
  ConfirmDialog,
  Disclosure,
  DisclosureTrigger,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  Field,
  IconButton,
  Input,
  Select,
  Text,
  Textarea,
} from "@/components/deermate/ui";

import {
  type Fact,
  invalidateHome,
  type MemoryPage,
  type Operation,
  personalAPI,
  type Reference,
  useProfile,
} from "./memory/model";
import { ProfileForm } from "./memory/profile-form";
import { StatusBadge } from "./ui";
import { MemorySource, scopeLabel } from "./workspace-memory";
export { PersonalGreeting } from "./memory/greeting";
export { personalAPI } from "./memory/model";
export function PersonalMemoryPanel({
  userId,
  zh,
  embedded = false,
}: {
  userId: string;
  zh: boolean;
  embedded?: boolean;
}) {
  const cache = useQueryClient();
  const profile = useProfile(userId);
  const [open, setOpen] = useState(embedded);
  const [source, setSource] = useState("");
  const [scopeFilter, setScopeFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [searchText, setSearchText] = useState("");
  const [page, setPage] = useState(0);
  const [content, setContent] = useState("");
  const [category, setCategory] = useState("preference");
  const actionOpener = useRef<HTMLButtonElement | null>(null);
  const memoryList = useRef<HTMLUListElement | null>(null);
  const restoreActionFocus = () => {
    if (actionOpener.current?.isConnected) actionOpener.current.focus();
    else memoryList.current?.focus();
  };
  const [forget, setForget] = useState<Fact | Reference | null>(null);
  const [editing, setEditing] = useState<Fact | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [operation, setOperation] = useState<Operation | null>(null);
  const pending = useRef<{ path: string; method: string; body: string } | null>(
    null,
  );
  const records = useQuery({
    queryKey: ["deermate", "personal-memory", userId, query, page],
    queryFn: ({ signal }) =>
      personalAPI<MemoryPage>("memories/search", userId, {
        signal,
        method: "POST",
        body: JSON.stringify({ query, offset: page * 50 }),
      }),
    enabled: !!userId && open && !!profile.data,
    gcTime: 0,
    retry: 1,
  });
  const data = records.isError ? undefined : records.data;
  const status = useQuery({
    queryKey: ["deermate", "memory-operation", userId, operation?.id],
    queryFn: ({ signal }) =>
      personalAPI<Operation>(`memory-operations/${operation!.id}`, userId, {
        signal,
      }),
    enabled:
      !!operation &&
      operation.status !== "completed" &&
      operation.status !== "invalidated",
    gcTime: 0,
    refetchInterval: (q) =>
      ["completed", "invalidated"].includes(q.state.data?.status ?? "")
        ? false
        : 3000,
    retry: 1,
  });
  useEffect(() => {
    if (
      status.data?.status === "completed" ||
      status.data?.status === "invalidated"
    ) {
      setOperation(status.data);
      invalidateHome(cache, userId);
      void cache.invalidateQueries({
        queryKey: ["deermate", "personal-memory", userId],
      });
    }
  }, [status.data, cache, userId]);

  async function mutate(method: string, fact?: Fact | Reference) {
    setBusy(true);
    setError("");
    setOperation(null);
    const request = pending.current ?? {
      path: fact ? `memories/${fact.id}` : "memories",
      method,
      body: JSON.stringify({
        operation_id: crypto.randomUUID(),
        content: method === "DELETE" ? "" : content.trim(),
        category: method === "DELETE" ? "" : category,
        expected_revision: fact?.revision ?? 0,
      }),
    };
    pending.current = request;
    try {
      const result = await personalAPI<Operation>(request.path, userId, {
        method: request.method,
        body: request.body,
      });
      pending.current = null;
      invalidateHome(cache, userId);
      setOperation(result);
      setContent("");
      setEditing(null);
      if (request.method !== "POST") {
        cache.setQueriesData<MemoryPage>(
          { queryKey: ["deermate", "personal-memory", userId] },
          (old) =>
            old
              ? {
                  ...old,
                  items: old.items.filter((item) => item.id !== result.fact_id),
                }
              : old,
        );
      }
      await cache.invalidateQueries({
        queryKey: ["deermate", "personal-memory", userId],
      });
    } catch (e) {
      const reason = e instanceof Error ? e.message : "unavailable";
      if (reason !== "unavailable") pending.current = null;
      setError(
        reason === "conflict"
          ? dmCopy(
              zh,
              "personal-memory.the.record.or.settings.changed.refresh.to.reconc.4ebd9a",
            )
          : reason === "invalid"
            ? dmCopy(
                zh,
                "personal-memory.check.the.input.do.not.save.passwords.keys.or.ve.0bf0d0",
              )
            : dmCopy(
                zh,
                "personal-memory.connection.unavailable.retry.will.reconcile.the..659c57",
              ),
      );
    } finally {
      setBusy(false);
    }
  }

  const contentView = (
    <>
      <ConfirmDialog
        restoreFocus={restoreActionFocus}
        open={!!forget}
        onOpenChange={(v) => {
          if (!v) setForget(null);
        }}
        title={dmCopy(zh, "personal-memory.forget.58fda9")}
        description={dmCopy(zh, "common.forget.warning")}
        confirmLabel={dmCopy(zh, "personal-memory.forget.58fda9")}
        cancelLabel={dmCopy(zh, "common.cancel")}
        busy={busy}
        onConfirm={() => {
          if (forget) void mutate("DELETE", forget).then(() => setForget(null));
        }}
      />
      {profile.isLoading && (
        <Skeleton
          label={dmCopy(zh, "personal-memory.loading.settings..f0a02f")}
        />
      )}
      {profile.isError && (
        <ErrorBanner role="alert">
          {dmCopy(zh, "personal-memory.settings.unavailable..0c0d78")}{" "}
          <Button
            variant="secondary"
            type="button"
            onClick={() => void profile.refetch()}
          >
            {dmCopy(zh, "personal-memory.retry.2cd694")}
          </Button>
        </ErrorBanner>
      )}
      {profile.data && (
        <Disclosure
          data-testid="memory-settings"
          className="dm-memory-settings"
        >
          <DisclosureTrigger>
            {dmCopy(zh, "personal-memory.memory.settings.and.profile.ff721e")}
          </DisclosureTrigger>
          <ProfileForm
            key={`${userId}-${profile.data.revision}`}
            profile={profile.data}
            zh={zh}
          />
        </Disclosure>
      )}
      {profile.data && (
        <>
          <div data-testid="section-heading" className="dm-section-heading">
            <SectionHeader
              icon={Brain}
              title={
                <>{dmCopy(zh, "personal-memory.what.i.remember.2fa10c")}</>
              }
            />
            <Button
              variant="secondary"
              type="button"
              onClick={() => void records.refetch()}
            >
              {dmCopy(zh, "personal-memory.refresh.140abb")}
            </Button>
          </div>
          <Text as="p" tone="muted" className="">
            {dmCopy(
              zh,
              "personal-memory.preferences.and.requirements.from.your.chats.app.dba997",
            )}
          </Text>
          <form
            data-testid="memory-form"
            className="dm-memory-form"
            onSubmit={(e) => {
              e.preventDefault();
              setQuery(searchText.trim());
              setPage(0);
            }}
          >
            <Field>
              {dmCopy(zh, "personal-memory.search.memory.0a3d11")}
              <Input
                value={searchText}
                maxLength={128}
                onChange={(e) => setSearchText(e.target.value)}
              />
            </Field>
            <Button variant="secondary" type="submit">
              {dmCopy(zh, "personal-memory.search.b3c8cd")}
            </Button>
          </form>
          {records.isLoading && (
            <Skeleton
              label={dmCopy(zh, "personal-memory.loading.memory..0539a4")}
            />
          )}
          {records.isError && (
            <ErrorBanner role="alert">
              {dmCopy(
                zh,
                "personal-memory.memory.unavailable.saved.records.are.preserved..8ab154",
              )}
            </ErrorBanner>
          )}
          {data?.items.length === 0 && (
            <Empty
              title={
                query
                  ? dmCopy(zh, "personal-memory.no.matching.facts..fd1b58")
                  : dmCopy(zh, "personal-memory.no.active.memories.yet..09a057")
              }
            />
          )}
          <Field
            data-testid="memory-scope-filter"
            className="dm-memory-scope-filter"
          >
            {dmCopy(zh, "personal-memory.scope.3ec802")}
            <Select
              value={scopeFilter}
              onChange={(e) => setScopeFilter(e.target.value)}
            >
              <option value="all">
                {dmCopy(zh, "personal-memory.all.bafb97")}
              </option>
              <option value="personal">
                {dmCopy(zh, "personal-memory.personal.ec8620")}
              </option>
              <option value="project:">
                {dmCopy(zh, "personal-memory.project.requirements.779053")}
              </option>
              <option value="topic:">
                {dmCopy(zh, "personal-memory.recent.topics.d6a015")}
              </option>
            </Select>
          </Field>
          <ul
            ref={memoryList}
            tabIndex={-1}
            aria-label={dmCopy(zh, "personal-memory.what.i.remember.2fa10c")}
            data-testid="memory-list"
            className="dm-memory-list"
          >
            {data?.items
              .filter(
                (fact) =>
                  scopeFilter === "all" || fact.scope.startsWith(scopeFilter),
              )
              .map((fact) => (
                <li key={fact.id}>
                  <p>{fact.content}</p>
                  <Text as="span" size="caption" tone="muted" className="">
                    {scopeLabel(fact.scope, zh)} ·{" "}
                    <Button
                      variant="ghost"
                      size="sm"
                      type="button"
                      onClick={(event) => {
                        actionOpener.current = event.currentTarget;
                        setSource(fact.id);
                      }}
                    >
                      {dmCopy(zh, "personal-memory.source.and.usage.f96741")}
                    </Button>{" "}
                    · {dmCopy(zh, "personal-memory.version.6145b7")}{" "}
                    {fact.revision}
                    {!!fact.expires_at &&
                      fact.expires_at < Date.now() / 1000 && (
                        <span>
                          {dmCopy(
                            zh,
                            "personal-memory..expired.excluded.from.answers.6a8dc2",
                          )}
                        </span>
                      )}
                  </Text>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <IconButton
                        onFocus={(event) => {
                          actionOpener.current = event.currentTarget;
                        }}
                        label={dmCopy(zh, "common.more")}
                        icon={<MoreHorizontal className="size-4" />}
                      />
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem onSelect={() => setSource(fact.id)}>
                        {dmCopy(zh, "personal-memory.source.and.usage.f96741")}
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        disabled={busy || !!pending.current}
                        onSelect={() => {
                          setEditing(fact);
                          setContent(fact.content);
                          setCategory(fact.category);
                          setTimeout(
                            () =>
                              document
                                .getElementById("dm-memory-content")
                                ?.focus(),
                            0,
                          );
                        }}
                      >
                        {dmCopy(zh, "personal-memory.correct.463a2f")}
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        disabled={busy || !!pending.current}
                        variant="destructive"
                        onSelect={() => setForget(fact)}
                      >
                        {dmCopy(zh, "personal-memory.forget.58fda9")}
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </li>
              ))}
            {data?.references
              .filter((ref) => ref.status !== "active")
              .map((ref) => (
                <li key={ref.id}>
                  <p>
                    {ref.status === "suppressed"
                      ? dmCopy(
                          zh,
                          "personal-memory.no.longer.used.cleanup.pending.ed4546",
                        )
                      : ref.status === "source_unavailable"
                        ? dmCopy(
                            zh,
                            "personal-memory.source.unavailable.this.memory.is.no.longer.used.0d377d",
                          )
                        : dmCopy(
                            zh,
                            "personal-memory.this.memory.update.is.not.complete.0a7f86",
                          )}
                  </p>
                  <Button
                    variant="secondary"
                    type="button"
                    disabled={busy || !!pending.current}
                    onClick={() => setForget(ref)}
                  >
                    {dmCopy(zh, "personal-memory.forget.and.clean.up.32c0e8")}
                  </Button>
                </li>
              ))}
          </ul>
          {!query && data && data.total_active > 50 && (
            <div data-testid="memory-actions" className="dm-memory-actions">
              <Button
                variant="secondary"
                type="button"
                disabled={page === 0}
                onClick={() => setPage(page - 1)}
              >
                {dmCopy(zh, "personal-memory.previous.2149c1")}
              </Button>
              <span>
                {page + 1} / {Math.ceil(data.total_active / 50)}
              </span>
              <Button
                variant="secondary"
                type="button"
                disabled={(page + 1) * 50 >= data.total_active}
                onClick={() => setPage(page + 1)}
              >
                {dmCopy(zh, "personal-memory.next.bbe67f")}
              </Button>
            </div>
          )}
          <form
            data-testid="memory-form"
            className="dm-memory-form"
            onSubmit={(event) => {
              event.preventDefault();
              void mutate(editing ? "PATCH" : "POST", editing ?? undefined);
            }}
          >
            <Field htmlFor="dm-memory-content">
              {editing
                ? dmCopy(zh, "personal-memory.correct.this.fact.47fc62")
                : dmCopy(zh, "personal-memory.what.should.i.remember..46dfc5")}
            </Field>
            <Textarea
              data-testid="memory-content"
              id="dm-memory-content"
              value={content}
              maxLength={1000}
              disabled={
                busy ||
                !!pending.current ||
                (!editing && !profile.data.memory_enabled)
              }
              onChange={(e) => setContent(e.target.value)}
              placeholder={dmCopy(
                zh,
                "personal-memory.example.lead.with.the.conclusion.in.your.replies.72152c",
              )}
            />
            <Field>
              {dmCopy(zh, "personal-memory.type.e1031f")}
              <Select
                value={category}
                disabled={busy || !!pending.current}
                onChange={(e) => setCategory(e.target.value)}
              >
                <option value="preference">
                  {dmCopy(zh, "personal-memory.preference.e60ed5")}
                </option>
                <option value="goal">
                  {dmCopy(zh, "personal-memory.goal.e359c7")}
                </option>
                <option value="context">
                  {dmCopy(zh, "personal-memory.context.3c6367")}
                </option>
              </Select>
            </Field>
            <div data-testid="memory-actions" className="dm-memory-actions">
              <Button
                loading={busy}
                variant="primary"
                type="submit"
                disabled={
                  busy ||
                  (!content.trim() && !pending.current) ||
                  (!editing && !profile.data.memory_enabled)
                }
              >
                {busy
                  ? dmCopy(zh, "personal-memory.saving..4c8592")
                  : pending.current
                    ? dmCopy(
                        zh,
                        "personal-memory.reconcile.previous.save.ba5580",
                      )
                    : dmCopy(zh, "personal-memory.save.memory.ef7ff2")}
              </Button>
              {editing && (
                <Button
                  variant="secondary"
                  type="button"
                  disabled={busy || !!pending.current}
                  onClick={() => {
                    setEditing(null);
                    setContent("");
                  }}
                >
                  {dmCopy(zh, "personal-memory.cancel.correction.bd2221")}
                </Button>
              )}
            </div>
          </form>
          {source && (
            <MemorySource
              restoreFocus={restoreActionFocus}
              userId={userId}
              factId={source}
              zh={zh}
              onClose={() => setSource("")}
            />
          )}
          {error && <ErrorBanner role="alert">{error}</ErrorBanner>}
          {operation && (
            <StatusBadge domain="memory" status={operation.status} />
          )}
        </>
      )}
    </>
  );
  return embedded ? (
    <section data-testid="memory" className="dm-memory">
      {contentView}
    </section>
  ) : (
    <Disclosure
      data-testid="memory"
      className="dm-memory"
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <DisclosureTrigger>
        {dmCopy(zh, "personal-memory.about.you.38ca3c")}
      </DisclosureTrigger>
      {contentView}
    </Disclosure>
  );
}
