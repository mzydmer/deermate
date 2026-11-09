"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRef, useState } from "react";

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
  const t = (a: string, b: string) => (zh ? a : b);
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
        t(
          "还没确认创建结果，再点会核对同一个话题。",
          "Creation is unconfirmed. Retry to reconcile this topic.",
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
        t("这次没保存，请再试一次。", "This change was not saved. Try again."),
      );
    }
  }
  if (query.isError || !query.data?.suggestions.length) return null;
  const current = status.data ?? intent;
  return (
    <section className="ds-app-card dm-goal-suggestions">
      <h2>{t("也可以接着聊", "Something else to explore")}</h2>
      {query.data.suggestions.slice(0, 2).map((v) => (
        <div key={v.fact_id}>
          <p>{v.question}</p>
          <p className="dm-small dm-muted">
            {t(
              "因为你之前提过这个长期目标。",
              "Based on a long-term goal you shared.",
            )}
          </p>
          <div className="dm-assistant-actions">
            <button
              className="dm-text-button"
              disabled={busy || (!!current && current.status !== "prepared")}
              onClick={() => void start(v)}
            >
              {busy
                ? t("创建中…", "Creating…")
                : t("开始这个话题", "Start this topic")}
            </button>
            <button className="dm-text-button" onClick={() => void dismiss(v)}>
              {t("不感兴趣", "Not interested")}
            </button>
          </div>
        </div>
      ))}
      {current && (
        <p role="status">
          {current.status === "completed" ? (
            <Link href={`/workspace/chats/${current.thread_id}`}>
              {t("看看这个话题", "Open conversation")}
            </Link>
          ) : current.status === "failed" || current.status === "blocked" ? (
            t(
              "这次没有开始，请核对模型或来源设置。",
              "This conversation did not start. Check the model and source.",
            )
          ) : (
            t(
              "话题已登记，正在核对原来的请求。",
              "Recorded; reconciling the original request.",
            )
          )}
        </p>
      )}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
