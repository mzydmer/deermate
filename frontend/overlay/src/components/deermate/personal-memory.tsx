"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useRef, useState } from "react";

import { fetch as authFetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

type Profile = {
  owner: string;
  display_name: string;
  timezone: string;
  memory_enabled: boolean;
  proactive_enabled: boolean;
  revision: number;
};
type Fact = {
  id: string;
  content: string;
  category: string;
  revision: number;
  source_id: string;
  scope: string;
  updated_at: number;
};
type Reference = { id: string; status: string; revision: number };
type Operation = { id: string; status: string; fact_id: string };
type MemoryPage = {
  items: Fact[];
  references: Reference[];
  total_active: number;
};

async function personalAPI<T>(
  path: string,
  userId: string,
  init?: RequestInit,
): Promise<T> {
  const response = await authFetch(`${getBackendBaseURL()}/api/me/${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-Expected-User-Id": userId,
    },
  });
  if (!response.ok) {
    if (response.status === 409) throw new Error("conflict");
    if (response.status === 422) throw new Error("invalid");
    throw new Error("unavailable");
  }
  try {
    return (await response.json()) as T;
  } catch {
    throw new Error("unavailable");
  }
}

function useProfile(userId: string) {
  return useQuery({
    queryKey: ["deermate", "personal-profile", userId],
    queryFn: ({ signal }) =>
      personalAPI<Profile>("personal-profile", userId, { signal }),
    enabled: !!userId,
    gcTime: 0,
    retry: 1,
  });
}

export function PersonalGreeting({
  userId,
  zh,
}: {
  userId: string;
  zh: boolean;
}) {
  const profile = useProfile(userId);
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const timer = window.setInterval(() => setNow(new Date()), 60000);
    return () => window.clearInterval(timer);
  }, []);
  let greeting = zh ? "你好" : "Hello";
  let date = "";
  if (now) {
    let timezone = profile.data?.revision
      ? profile.data.timezone
      : Intl.DateTimeFormat().resolvedOptions().timeZone;
    let fallback = false;
    try {
      new Intl.DateTimeFormat("en", { timeZone: timezone });
    } catch {
      timezone = "UTC";
      fallback = true;
    }
    const hour = Number(
      new Intl.DateTimeFormat("en-GB", {
        timeZone: timezone,
        hour: "2-digit",
        hourCycle: "h23",
      }).format(now),
    );
    greeting =
      hour >= 5 && hour < 12
        ? zh
          ? "上午好"
          : "Good morning"
        : hour >= 12 && hour < 18
          ? zh
            ? "下午好"
            : "Good afternoon"
          : zh
            ? "晚上好"
            : "Good evening";
    date = new Intl.DateTimeFormat(zh ? "zh-CN" : "en-US", {
      timeZone: timezone,
      month: "long",
      day: "numeric",
      weekday: "long",
    }).format(now);
    if (fallback) date += " · UTC";
  }
  return (
    <>
      <h1>
        {greeting}
        {profile.data?.display_name
          ? `${zh ? "，" : ", "}${profile.data.display_name}`
          : ""}
        {zh ? "。" : "."}
      </h1>
      <p className="dm-muted">
        {date || (zh ? "你的私人秘书工作台" : "Your personal secretary")}
      </p>
    </>
  );
}

export function PersonalMemoryPanel({
  userId,
  zh,
}: {
  userId: string;
  zh: boolean;
}) {
  const t = (cn: string, en: string) => (zh ? cn : en);
  const cache = useQueryClient();
  const profile = useProfile(userId);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [searchText, setSearchText] = useState("");
  const [page, setPage] = useState(0);
  const [content, setContent] = useState("");
  const [category, setCategory] = useState("preference");
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
          ? t(
              "记录或设置已变化，请刷新后核对。",
              "The record or settings changed. Refresh to reconcile.",
            )
          : reason === "invalid"
            ? t(
                "请检查输入；不要保存密码、密钥或验证码。",
                "Check the input. Do not save passwords, keys or verification codes.",
              )
            : t(
                "连接暂不可用。再次点击会核对同一次保存。",
                "Connection unavailable. Retry will reconcile the same operation.",
              ),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <details
      className="dm-memory"
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>{t("个人设置与记忆", "Personal settings & memory")}</summary>
      {profile.isLoading && (
        <p role="status">{t("正在读取设置…", "Loading settings…")}</p>
      )}
      {profile.isError && (
        <p role="alert">
          {t("设置暂不可用。", "Settings unavailable.")}{" "}
          <button className="dm-button" onClick={() => void profile.refetch()}>
            {t("重试", "Retry")}
          </button>
        </p>
      )}
      {profile.data && (
        <ProfileForm
          key={`${userId}-${profile.data.revision}`}
          profile={profile.data}
          zh={zh}
        />
      )}
      {profile.data && (
        <>
          <div className="dm-section-heading">
            <h2>{t("我记住的事", "What I remember")}</h2>
            <button
              className="dm-button"
              onClick={() => void records.refetch()}
            >
              {t("刷新", "Refresh")}
            </button>
          </div>
          <p className="dm-muted">
            {t(
              "保存你希望在其他对话中继续使用的偏好、目标或背景。当前仅使用你主动保存的内容。",
              "Save preferences, goals or context for other conversations. Only explicitly saved facts are used here.",
            )}
          </p>
          <form
            className="dm-memory-form"
            onSubmit={(e) => {
              e.preventDefault();
              setQuery(searchText.trim());
              setPage(0);
            }}
          >
            <label>
              {t("搜索记忆", "Search memory")}
              <input
                value={searchText}
                maxLength={128}
                onChange={(e) => setSearchText(e.target.value)}
              />
            </label>
            <button className="dm-button">{t("搜索", "Search")}</button>
          </form>
          {records.isLoading && (
            <p role="status">{t("正在读取记忆…", "Loading memory…")}</p>
          )}
          {records.isError && (
            <p role="alert">
              {t(
                "记忆暂不可用，已保存的资料仍保留。",
                "Memory unavailable. Saved records are preserved.",
              )}
            </p>
          )}
          {data?.items.length === 0 && (
            <p className="dm-muted">
              {query
                ? t("没有匹配的记忆。", "No matching facts.")
                : t("还没有已生效的记忆。", "No active memories yet.")}
            </p>
          )}
          <ul className="dm-memory-list">
            {data?.items.map((fact) => (
              <li key={fact.id}>
                <p>{fact.content}</p>
                <span className="dm-small dm-muted">
                  {t("你主动保存", "Saved by you")} · {t("版本", "Version")}{" "}
                  {fact.revision}
                </span>
                <div className="dm-memory-actions">
                  <button
                    className="dm-button"
                    disabled={busy || !!pending.current}
                    onClick={() => {
                      setEditing(fact);
                      setContent(fact.content);
                      setCategory(fact.category);
                      document.getElementById("dm-memory-content")?.focus();
                    }}
                  >
                    {t("纠正", "Correct")}
                  </button>
                  <button
                    className="dm-button"
                    disabled={busy || !!pending.current}
                    onClick={() => void mutate("DELETE", fact)}
                  >
                    {t("忘记", "Forget")}
                  </button>
                </div>
              </li>
            ))}
            {data?.references
              .filter((ref) => ref.status !== "active")
              .map((ref) => (
                <li key={ref.id}>
                  <p>
                    {ref.status === "suppressed"
                      ? t(
                          "已停止使用，等待清理",
                          "No longer used; cleanup pending",
                        )
                      : t(
                          "这条记忆的更新尚未完成",
                          "This memory update is not complete",
                        )}
                  </p>
                  <button
                    className="dm-button"
                    disabled={busy || !!pending.current}
                    onClick={() => void mutate("DELETE", ref)}
                  >
                    {t("忘记并清理", "Forget and clean up")}
                  </button>
                </li>
              ))}
          </ul>
          {!query && data && data.total_active > 50 && (
            <div className="dm-memory-actions">
              <button
                className="dm-button"
                disabled={page === 0}
                onClick={() => setPage(page - 1)}
              >
                {t("上一页", "Previous")}
              </button>
              <span>
                {page + 1} / {Math.ceil(data.total_active / 50)}
              </span>
              <button
                className="dm-button"
                disabled={(page + 1) * 50 >= data.total_active}
                onClick={() => setPage(page + 1)}
              >
                {t("下一页", "Next")}
              </button>
            </div>
          )}
          <form
            className="dm-memory-form"
            onSubmit={(event) => {
              event.preventDefault();
              void mutate(editing ? "PATCH" : "POST", editing ?? undefined);
            }}
          >
            <label htmlFor="dm-memory-content">
              {editing
                ? t("纠正这条记忆", "Correct this fact")
                : t("告诉我需要记住什么", "What should I remember?")}
            </label>
            <textarea
              id="dm-memory-content"
              value={content}
              maxLength={1000}
              disabled={
                busy ||
                !!pending.current ||
                (!editing && !profile.data.memory_enabled)
              }
              onChange={(e) => setContent(e.target.value)}
              placeholder={t(
                "例如：回复请使用中文，先给结论。",
                "Example: Lead with the conclusion in your replies.",
              )}
            />
            <label>
              {t("类型", "Type")}
              <select
                value={category}
                disabled={busy || !!pending.current}
                onChange={(e) => setCategory(e.target.value)}
              >
                <option value="preference">{t("偏好", "Preference")}</option>
                <option value="goal">{t("目标", "Goal")}</option>
                <option value="context">{t("背景", "Context")}</option>
              </select>
            </label>
            <div className="dm-memory-actions">
              <button
                className="dm-button"
                disabled={
                  busy ||
                  (!content.trim() && !pending.current) ||
                  (!editing && !profile.data.memory_enabled)
                }
              >
                {busy
                  ? t("保存中…", "Saving…")
                  : pending.current
                    ? t("核对上次保存", "Reconcile previous save")
                    : t("保存记忆", "Save memory")}
              </button>
              {editing && (
                <button
                  type="button"
                  className="dm-button"
                  disabled={busy || !!pending.current}
                  onClick={() => {
                    setEditing(null);
                    setContent("");
                  }}
                >
                  {t("取消纠正", "Cancel correction")}
                </button>
              )}
            </div>
          </form>
          {error && <p role="alert">{error}</p>}
          {operation && (
            <p role="status">
              {operation.status === "completed"
                ? t("记忆已更新。", "Memory updated.")
                : operation.status === "invalidated"
                  ? t(
                      "设置或来源已变化，旧更新已停止。",
                      "Settings or sources changed. The old update was stopped.",
                    )
                  : t(
                      "更新已登记，正在后台核对。无需重复提交。",
                      "Update recorded; reconciling in the background. No resubmission is needed.",
                    )}
            </p>
          )}
        </>
      )}
    </details>
  );
}

function ProfileForm({ profile, zh }: { profile: Profile; zh: boolean }) {
  const t = (cn: string, en: string) => (zh ? cn : en);
  const cache = useQueryClient();
  const [name, setName] = useState(profile.display_name);
  const [zone, setZone] = useState(profile.timezone);
  const [enabled, setEnabled] = useState(profile.memory_enabled);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState("");
  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setFeedback("");
    try {
      await personalAPI<Profile>("personal-profile", profile.owner, {
        method: "PATCH",
        body: JSON.stringify({
          display_name: name.trim(),
          timezone: zone.trim(),
          memory_enabled: enabled,
          expected_revision: profile.revision,
        }),
      });
      await cache.invalidateQueries({
        queryKey: ["deermate", "personal-profile", profile.owner],
      });
      await cache.invalidateQueries({
        queryKey: ["deermate", "personal-memory", profile.owner],
      });
    } catch {
      setFeedback(
        t(
          "设置未保存。请检查时区或刷新后重试。",
          "Settings were not saved. Check the timezone or refresh and retry.",
        ),
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className="dm-memory-form" onSubmit={(event) => void save(event)}>
      <label>
        {t("希望我怎么称呼你", "What should I call you?")}
        <input
          value={name}
          maxLength={80}
          disabled={busy}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <label>
        {t("时区", "Timezone")}
        <input
          value={zone}
          maxLength={80}
          disabled={busy}
          onChange={(e) => setZone(e.target.value)}
          placeholder="Asia/Shanghai"
        />
      </label>
      <button
        type="button"
        className="dm-button"
        onClick={() =>
          setZone(Intl.DateTimeFormat().resolvedOptions().timeZone)
        }
        disabled={busy}
      >
        {t("使用设备时区", "Use device timezone")}
      </button>
      <label className="dm-memory-check">
        <input
          type="checkbox"
          checked={enabled}
          disabled={busy}
          onChange={(e) => setEnabled(e.target.checked)}
        />
        {t("开启个人记忆", "Enable personal memory")}
      </label>
      <p className="dm-muted">
        {t(
          "开启后，在新对话中使用你保存的记忆。关闭后停止使用，已有记忆仍可纠正或忘记。不会自动导入历史聊天。",
          "Use saved facts in new conversations. Turning this off stops personalization; existing facts remain manageable. No history is imported automatically.",
        )}
      </p>
      <button className="dm-button" disabled={busy}>
        {busy
          ? t("保存中…", "Saving…")
          : t("保存个人设置", "Save personal settings")}
      </button>
      {feedback && <p role="alert">{feedback}</p>}
    </form>
  );
}
