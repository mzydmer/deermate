"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { dmCopy } from "@/components/deermate/i18n/copy";
import { ErrorBanner } from "@/components/deermate/ui";
import {
  Button,
  Disclosure,
  DisclosureTrigger,
  Text,
} from "@/components/deermate/ui";

import { ContinuousIntents, type ContinuousIntent } from "./continuous-intents";
import { Composer } from "./patterns/composer";
import { AssistantAvatar, MessageBody } from "./ui";
import { workspaceAPI } from "./workspace-api";
import { MemoryActivity } from "./workspace-memory";

type Inbox = {
  id: string;
  state: string;
  data: {
    text?: string;
    reply?: string;
    origin?: string;
    operation_id?: string;
  };
};
type Router = { session: { data?: { thread_id?: string } }; items: Inbox[] };

export function SecretaryConversation({
  userId,
  zh,
}: {
  userId: string;
  zh: boolean;
}) {
  const cache = useQueryClient();
  const [message, setMessage] = useState("");
  const [expanded, setExpanded] = useState(false);
  const [reconcile, setReconcile] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const pending = useRef(new ContinuousIntents());
  const submitted = useRef(false);
  const frozen = useRef<ContinuousIntent | null>(null);
  const journal = `deermate:secretary-pending:${userId}`;
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(journal);
      if (!raw) return;
      const value = JSON.parse(raw) as ContinuousIntent;
      if (
        typeof value.body?.text === "string" &&
        value.body.text.length <= 8000 &&
        typeof value.body.operation_id === "string" &&
        /^[a-f0-9-]{36}$/.test(value.body.operation_id)
      ) {
        frozen.current = {
          key: "restored",
          body: {
            text: value.body.text,
            operation_id: value.body.operation_id,
          },
        };
        setMessage(value.body.text);
        setReconcile(true);
      }
    } catch {
      /* A missing draft does not authorize replay. */
    }
  }, [journal]);
  const router = useQuery({
    queryKey: ["continuous", userId, "router"],
    queryFn: () => workspaceAPI<Router>(userId, "router"),
    refetchInterval: 3000,
    refetchIntervalInBackground: false,
    retry: 1,
  });
  async function send() {
    if (submitted.current || !message.trim()) return;
    submitted.current = true;
    setBusy(true);
    setError("");
    const intent =
      frozen.current ??
      pending.current.begin("router/messages", "POST", {
        text: message.trim(),
      });
    try {
      sessionStorage.setItem(journal, JSON.stringify(intent));
      if (sessionStorage.getItem(journal) !== JSON.stringify(intent))
        throw new Error("journal");
      frozen.current = intent;
      await workspaceAPI(userId, "router/messages", {
        method: "POST",
        body: JSON.stringify(intent.body),
      });
      pending.current.confirmed(intent);
      frozen.current = null;
      try {
        sessionStorage.removeItem(journal);
      } catch {
        /* Accepted request stays accepted. */
      }
      setReconcile(false);
      setMessage("");
      setExpanded(true);
      await cache.invalidateQueries({
        queryKey: ["continuous", userId, "router"],
      });
      void cache.invalidateQueries({
        queryKey: ["workspace-snapshot", userId],
      });
    } catch (e) {
      const status = (e as { status?: number }).status;
      pending.current.rejected(intent, status);
      if (status !== undefined && status >= 400 && status < 500) {
        frozen.current = null;
        try {
          sessionStorage.removeItem(journal);
        } catch {
          /* No delivery was admitted. */
        }
        setReconcile(false);
      } else {
        setReconcile(true);
      }
      setError(
        dmCopy(
          zh,
          "secretary-conversation.delivery.is.unconfirmed.send.again.to.reconcile..27b100",
        ),
      );
    } finally {
      submitted.current = false;
      setBusy(false);
    }
  }
  return (
    <section
      data-testid="assistant-conversation"
      className="dm-assistant-conversation"
      aria-label={dmCopy(
        zh,
        "secretary-conversation.talk.to.your.assistant.a508ae",
      )}
    >
      {router.isError && (
        <ErrorBanner role="alert">
          {dmCopy(
            zh,
            "secretary-conversation.could.not.refresh.this.conversation..cbe2aa",
          )}{" "}
          <Button
            variant="ghost"
            size="sm"
            type="button"
            onClick={() => void router.refetch()}
          >
            {dmCopy(zh, "secretary-conversation.retry.2cd694")}
          </Button>
        </ErrorBanner>
      )}
      {router.data?.items.some((item) => item.data.origin === "user") && (
        <Disclosure
          data-testid="assistant-recent-conversation"
          open={expanded}
          onToggle={(e) => setExpanded(e.currentTarget.open)}
          className="dm-assistant-recent-conversation"
        >
          <DisclosureTrigger>
            {dmCopy(zh, "secretary-conversation.recent.conversation.62c93e")}
          </DisclosureTrigger>
          <ol
            data-testid="assistant-messages"
            className="dm-assistant-messages"
            aria-label={dmCopy(
              zh,
              "secretary-conversation.recent.conversation.1678fb",
            )}
          >
            {router.data?.items
              .filter((v) => v.data.origin === "user")
              .slice(0, 6)
              .reverse()
              .map((v) => (
                <li key={v.id}>
                  <div
                    data-testid="assistant-user"
                    className="dm-assistant-user"
                  >
                    <Text as="span" size="caption" tone="muted" className="">
                      {dmCopy(zh, "secretary-conversation.you.a9b773")}
                    </Text>
                    <p>{v.data.text}</p>
                  </div>
                  {v.data.reply ? (
                    <div
                      data-testid="assistant-reply"
                      className="dm-assistant-reply"
                    >
                      <div className="flex items-center gap-2">
                        <AssistantAvatar />
                        <Text size="caption">DeerMate</Text>
                      </div>
                      <MessageBody value={v.data.reply} />
                    </div>
                  ) : (
                    <Text
                      as="p"
                      size="caption"
                      tone="muted"
                      className=""
                      role="status"
                    >
                      {v.state === "waiting_model" ? (
                        <>
                          {dmCopy(
                            zh,
                            "secretary-conversation.connect.a.conversation.model.to.continue..843f88",
                          )}{" "}
                          <Link href="/workspace?settings=models">
                            {dmCopy(
                              zh,
                              "secretary-conversation.connect.model.436a05",
                            )}
                          </Link>
                        </>
                      ) : v.state === "uncertain" ? (
                        dmCopy(
                          zh,
                          "secretary-conversation.received.the.outcome.is.unconfirmed.check.the.or.2d3d5e",
                        )
                      ) : ["pending", "dispatching", "acknowledged"].includes(
                          v.state,
                        ) ? (
                        dmCopy(
                          zh,
                          "secretary-conversation.reading.your.message..775571",
                        )
                      ) : (
                        dmCopy(
                          zh,
                          "secretary-conversation.this.turn.ended.check.your.work.for.the.result..9c7c6a",
                        )
                      )}
                    </Text>
                  )}
                </li>
              ))}
          </ol>
        </Disclosure>
      )}
      {router.data?.session.data?.thread_id && (
        <MemoryActivity
          userId={userId}
          threadId={router.data.session.data.thread_id}
          zh={zh}
        />
      )}
      <Composer
        zh={zh}
        value={message}
        onChange={setMessage}
        onSubmit={() => void send()}
        busy={busy}
        disabled={reconcile}
        label={dmCopy(
          zh,
          "secretary-conversation.what.would.you.like.to.do.today..e3086b",
        )}
        placeholder={dmCopy(
          zh,
          "secretary-conversation.pick.up.where.we.left.off.or.tell.me.something.n.856aa5",
        )}
        sendLabel={
          busy
            ? dmCopy(zh, "secretary-conversation.sending.ddd4e5")
            : reconcile
              ? dmCopy(zh, "secretary-conversation.reconcile.delivery.f8cb1c")
              : dmCopy(zh, "secretary-conversation.send.f1004b")
        }
      />
      {error && <ErrorBanner role="alert">{error}</ErrorBanner>}
    </section>
  );
}
