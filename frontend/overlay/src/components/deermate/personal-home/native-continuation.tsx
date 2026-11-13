"use client";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { dmCopy } from "@/components/deermate/i18n/copy";
import {
  Button,
  Disclosure,
  DisclosureTrigger,
  Field,
  Text,
  Textarea,
} from "@/components/deermate/ui";

import { type Continuation, homeAPI, type Item } from "./model";
export function NativeContinuation({
  user,
  item,
  zh,
  disabled,
  onRun,
}: {
  user: string;
  item: Item;
  zh: boolean;
  disabled: boolean;
  onRun: (
    body: Record<string, unknown>,
    question: string,
    scope: Continuation,
  ) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");
  const info = useQuery({
    queryKey: [
      "deermate",
      "home-continuation",
      user,
      item.topic.id,
      item.evidence.version,
    ],
    queryFn: ({ signal }) =>
      homeAPI<Continuation>(
        user,
        `attention-topics/${item.topic.id}/continuation`,
        { signal },
      ),
    enabled: open && !disabled,
    retry: false,
    gcTime: 0,
  });
  return (
    <Disclosure onToggle={(event) => setOpen(event.currentTarget.open)}>
      <DisclosureTrigger>
        {dmCopy(zh, "personal-home.execute.a.specific.next.step.49659d")}
      </DisclosureTrigger>
      {info.isLoading && (
        <p role="status">
          {dmCopy(zh, "personal-home.checking.the.existing.session..66db91")}
        </p>
      )}
      {info.isError && (
        <p>
          {dmCopy(
            zh,
            "personal-home.continuation.unavailable.inspect.the.original.ch.295020",
          )}
        </p>
      )}
      {info.data && (
        <form
          data-testid="memory-form"
          className="dm-memory-form"
          onSubmit={(event) => {
            event.preventDefault();
            void onRun(
              {
                kind: "continue",
                topic_id: item.topic.id,
                evidence_revision: item.evidence.version,
                message: message.trim(),
                continuation_fingerprint: info.data.fingerprint,
              },
              message.trim(),
              info.data,
            );
          }}
        >
          <p>
            {dmCopy(
              zh,
              "personal-home.uses.the.existing.project.and.executor.a2d30c",
            )}
            ：{info.data.project} · {info.data.executor}
          </p>
          <Field>
            {dmCopy(zh, "personal-home.what.should.this.step.do..da15f1")}
            <Textarea
              value={message}
              maxLength={1000}
              onChange={(event) => setMessage(event.target.value)}
              required
            />
          </Field>
          <Text as="p" size="caption" tone="muted" className="">
            {dmCopy(
              zh,
              "personal-home.one.continuation.in.the.existing.session.without.681618",
            )}
          </Text>
          <Button
            variant="primary"
            type="submit"
            disabled={disabled || !message.trim()}
          >
            {dmCopy(zh, "personal-home.execute.this.step.9f150a")}
          </Button>
        </form>
      )}
    </Disclosure>
  );
}
