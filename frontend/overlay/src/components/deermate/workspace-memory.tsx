"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useRef, useState } from "react";

import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { useAuth } from "@/core/auth/AuthProvider";
import { useI18n } from "@/core/i18n/hooks";

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
  onClose,
  zh,
}: {
  userId: string;
  factId: string;
  onClose: () => void;
  zh: boolean;
}) {
  const t = (a: string, b: string) => (zh ? a : b);
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
        t(
          "这个话题之后不会再整理进长期记忆。已有记忆可逐条忘记。",
          "This topic is excluded from future capture. Existing facts can be forgotten individually.",
        ),
      );
    } catch {
      setError(
        t(
          "这次没有保存，请稍后再试。",
          "This change was not saved. Try again.",
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
        className="dm-workspace dm-memory-source"
        onCloseAutoFocus={(e) => {
          e.preventDefault();
          opener.current?.focus();
        }}
      >
        <SheetHeader>
          <SheetTitle>{t("这条记忆从哪来", "Memory source")}</SheetTitle>
          <SheetDescription>
            {t(
              "保留你说过的话，方便核对有没有记错。",
              "Check the original statement and where this fact was included.",
            )}
          </SheetDescription>
        </SheetHeader>
        {source.isPending && (
          <p role="status">{t("在找原来的话…", "Loading source…")}</p>
        )}
        {source.isError && (
          <p role="alert">
            {t("暂时没读到来源。", "Source unavailable.")}
            <button className="dm-button" onClick={() => void source.refetch()}>
              {t("重试", "Retry")}
            </button>
          </p>
        )}
        {!source.isError && source.data && (
          <div className="dm-memory-source-body">
            <p className="dm-small dm-muted">
              {scopeLabel(source.data.scope, zh)} ·{" "}
              {new Date(source.data.updated_at * 1000).toLocaleString()}
            </p>
            {source.data.state !== "available" ? (
              <p>
                {t(
                  "来源已经不可用，这条记忆不再用于回答。",
                  "The source is unavailable; this memory is excluded from answers.",
                )}
              </p>
            ) : source.data.kind === "manual" ? (
              <p>
                {t(
                  "这条是你在记忆管理中保存或纠正的。",
                  "You saved or corrected this fact in memory settings.",
                )}
              </p>
            ) : (
              <>
                <blockquote>{source.data.text}</blockquote>
                {source.data.observed_at && (
                  <p className="dm-small dm-muted">
                    {new Date(source.data.observed_at * 1000).toLocaleString()}
                  </p>
                )}
                <Link
                  href={
                    source.data.kind === "inbox"
                      ? "/workspace"
                      : `/workspace/chats/${source.data.thread_id}`
                  }
                >
                  {t("回到原对话", "Open original conversation")}
                </Link>
                {source.data.kind === "chat" && (
                  <button className="dm-button" onClick={() => void exclude()}>
                    {t("这个话题不再记忆", "Exclude this topic")}
                  </button>
                )}
              </>
            )}
            {!!source.data.expires_at && (
              <p className="dm-small dm-muted">
                {t("有效期至", "Expires")}{" "}
                {new Date(source.data.expires_at * 1000).toLocaleDateString()}
              </p>
            )}
            <h3>{t("最近用在哪些对话", "Recently included in")}</h3>
            <p className="dm-small dm-muted">
              {t(
                "表示已加入回答上下文，不代表模型一定采纳了它。",
                "Included in model context; this does not prove the answer relied on it.",
              )}
            </p>
            {source.data.uses.length ? (
              <ul>
                {source.data.uses.map((v) => (
                  <li key={v.thread_id}>
                    <Link href={`/workspace/chats/${v.thread_id}`}>
                      {v.title || t("未命名对话", "Untitled chat")}
                    </Link>
                    <p className="dm-small dm-muted">
                      {new Date(v.included_at * 1000).toLocaleString()}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="dm-muted">
                {t("还没有可展示的使用记录。", "No visible usage records yet.")}
              </p>
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
    ? zh
      ? "这个项目"
      : "This project"
    : scope.startsWith("topic:")
      ? zh
        ? "当前话题"
        : "This topic"
      : zh
        ? "个人偏好与背景"
        : "Personal preferences and context";
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
  const t = (a: string, b: string) => (zh ? a : b);
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
        t(
          "操作还没确认，请稍后核对。",
          "This action is unconfirmed. Reconcile it later.",
        ),
      );
    }
  }
  if (!query.data || query.isError) return null;
  const v = query.data;
  const active = ["not_started", "processing", "queued"].includes(v.status);
  return (
    <section
      className={
        compact ? "dm-assistant-history" : "dm-memory-history ds-app-card"
      }
    >
      <h3>{t("把最近的事接回来", "Picking up recent context")}</h3>
      <p className="dm-small dm-muted">
        {active
          ? t(
              "会在后台整理最近七天、最多十个话题，不影响你继续聊天。",
              "Up to ten conversations from the past seven days, in the background.",
            )
          : ["stop", "undo", "interrupted"].includes(v.status)
            ? t(
                "最近资料的整理已停止。新对话仍按当前记忆设置处理。",
                "History import stopped. New chats still follow current memory settings.",
              )
            : t(
                "最近资料已核对。没把握的内容不会硬记下来。",
                "Recent context checked. Uncertain facts are left out.",
              )}
      </p>
      {v.total > 0 && (
        <p className="dm-small">
          {t("已处理", "Settled")} {v.settled}/{v.total}
        </p>
      )}
      {!compact && (
        <div className="dm-assistant-actions">
          {active && (
            <button className="dm-button" onClick={() => void action("stop")}>
              {t("停止整理", "Stop import")}
            </button>
          )}
          {v.total > 0 && v.status !== "undo" && (
            <button
              className="dm-text-button"
              onClick={() => void action("undo")}
            >
              {t("撤销这次新增", "Undo imported facts")}
            </button>
          )}
        </div>
      )}
      {error && <p role="alert">{error}</p>}
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
  const t = (a: string, b: string) => (zh ? a : b);
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
        t(
          "记录已变化，请到“关于你”核对后再操作。",
          "This fact changed. Review it in About you.",
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
    <div className="dm-memory-activity">
      <span role="status">
        {latest.status === "failed"
          ? t(
              "这次没有记下来，可以到“关于你”补充。",
              "This was not saved. You can add it in About you.",
            )
          : latest.status === "uncertain"
            ? t(
                "这次整理还没确认，不会重复调用模型。",
                "This capture is unconfirmed; the model will not be called again.",
              )
            : latest.status === "budget_wait"
              ? t(
                  "今天的整理额度已用完，聊天可以继续。",
                  "Today's capture allowance is used. You can keep chatting.",
                )
              : latest.status === "clarification"
                ? t(
                    "没确定你指的是哪条记忆，可以在“关于你”选一下。",
                    "Choose the memory you meant in About you.",
                  )
                : op
                  ? op.kind === "delete"
                    ? t(
                        "这条记忆已忘记。原对话仍然保留。",
                        "Memory forgotten. The original chat is retained.",
                      )
                    : t(
                        "记下了，之后会按这个来。",
                        "Saved for future conversations.",
                      )
                  : t(
                      "正在整理刚才提到的事…",
                      "Checking what you just shared…",
                    )}
      </span>
      {op && op.kind !== "delete" && (
        <>
          <button
            className="dm-text-button"
            onClick={() => setSource(op.fact_id)}
          >
            {t("来源", "Source")}
          </button>
          <button className="dm-text-button" onClick={() => void undo()}>
            {op.kind === "create" ? t("撤销", "Undo") : t("忘记这条", "Forget")}
          </button>
        </>
      )}
      <Link href="/workspace/memory">{t("关于你", "About you")}</Link>
      {source && (
        <MemorySource
          userId={userId}
          factId={source}
          zh={zh}
          onClose={() => setSource("")}
        />
      )}{" "}
      {error && <p role="alert">{error}</p>}
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
    <div className="dm-chat-memory-banner">
      {mode.data?.mode === "temporary" ? (
        <p role="status">
          {zh
            ? "临时对话 · 不读取或新增长期记忆，聊天记录仍会保存。"
            : "Temporary chat · No long-term memory is read or saved. Chat history is retained."}
        </p>
      ) : mode.data?.mode === "excluded" ? (
        <p role="status">
          {zh
            ? "这个话题不再整理进长期记忆。"
            : "This topic is excluded from long-term capture."}
        </p>
      ) : (
        <MemoryActivity userId={user.id} threadId={id} zh={zh} />
      )}
    </div>
  );
}
