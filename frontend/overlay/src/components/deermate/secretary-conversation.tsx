"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUp } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { ContinuousIntents, type ContinuousIntent } from "./continuous-intents";
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
  const t = (cn: string, en: string) => (zh ? cn : en);
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
        t(
          "这次发送还没确认。保留这句话，再点发送会核对同一次请求。",
          "Delivery is unconfirmed. Send again to reconcile this request.",
        ),
      );
    } finally {
      submitted.current = false;
      setBusy(false);
    }
  }
  return (
    <section
      className="dm-assistant-conversation"
      aria-label={t("和助手聊聊", "Talk to your assistant")}
    >
      {router.isError && (
        <p role="alert">
          {t("暂时读不到最新对话。", "Could not refresh this conversation.")}{" "}
          <button
            className="dm-text-button"
            onClick={() => void router.refetch()}
          >
            {t("重试", "Retry")}
          </button>
        </p>
      )}
      <details
        open={expanded}
        onToggle={(e) => setExpanded(e.currentTarget.open)}
        className="dm-assistant-recent-conversation"
      >
        <summary>{t("接着刚才的对话", "Recent conversation")}</summary>
        <ol
          className="dm-assistant-messages"
          aria-label={t("最近的对话", "Recent conversation")}
        >
          {router.data?.items
            .filter((v) => v.data.origin === "user")
            .slice(0, 6)
            .reverse()
            .map((v) => (
              <li key={v.id}>
                <div className="dm-assistant-user">
                  <span className="dm-small dm-muted">{t("你", "You")}</span>
                  <p>{v.data.text}</p>
                </div>
                {v.data.reply ? (
                  <div className="dm-assistant-reply">
                    <span className="dm-small dm-muted">DeerMate</span>
                    <p>{v.data.reply}</p>
                  </div>
                ) : (
                  <p className="dm-small dm-muted" role="status">
                    {v.state === "waiting_model" ? (
                      <>
                        {t(
                          "先连接一个对话模型，就可以接着聊。",
                          "Connect a conversation model to continue.",
                        )}{" "}
                        <Link href="/workspace?settings=models">
                          {t("连接模型", "Connect model")}
                        </Link>
                      </>
                    ) : v.state === "uncertain" ? (
                      t(
                        "这句话已收下，处理结果还没确认，请勿重复派单。",
                        "Received; the outcome is unconfirmed. Check the original operation.",
                      )
                    ) : ["pending", "dispatching", "acknowledged"].includes(
                        v.state,
                      ) ? (
                      t("在看你刚才说的事…", "Reading your message…")
                    ) : (
                      t(
                        "这次处理已结束，可到工作里查看结果。",
                        "This turn ended. Check your work for the result.",
                      )
                    )}
                  </p>
                )}
              </li>
            ))}
        </ol>
      </details>
      {router.data?.session.data?.thread_id && (
        <MemoryActivity
          userId={userId}
          threadId={router.data.session.data.thread_id}
          zh={zh}
        />
      )}
      <form
        className="dm-assistant-composer ds-app-card"
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
        aria-busy={busy}
      >
        <label htmlFor="dm-assistant-message">
          {t("今天想先做什么？", "What would you like to do today?")}
        </label>
        <textarea
          id="dm-assistant-message"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          maxLength={8000}
          rows={3}
          placeholder={t(
            "接着聊上次的事，或者交代一件新事。",
            "Pick up where we left off, or tell me something new.",
          )}
          disabled={busy || reconcile}
          required
        />
        <div className="dm-assistant-composer-footer">
          <span className="dm-small dm-muted">
            {t(
              "需要执行时，我会按已有的设备授权安排。",
              "Execution uses your existing device permissions.",
            )}
          </span>
          <button
            className="ds-app-button-primary"
            disabled={busy || !message.trim()}
          >
            <ArrowUp size={16} />
            {busy
              ? t("发送中", "Sending")
              : reconcile
                ? t("核对这次发送", "Reconcile delivery")
                : t("发送", "Send")}
          </button>
        </div>
      </form>
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
