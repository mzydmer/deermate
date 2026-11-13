"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { dmCopy } from "@/components/deermate/i18n/copy";
import { StatusBadge } from "@/components/deermate/ui";
import { fetch as authFetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

import { ContinuousIntents } from "../continuous-intents";

import {
  str,
  type Config,
  type Page,
  type RecordView,
  type Router,
} from "./model";

export function useSecretaryController({
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
  const cache = useQueryClient();
  const [message, setMessage] = useState("");
  const [goal, setGoal] = useState("");
  const [project, setProject] = useState("");
  const [grant, setGrant] = useState("");
  const [instruction, setInstruction] = useState("");
  const [selected, setSelected] = useState("");
  const [workFilter, setWorkFilter] = useState("all");
  useEffect(() => {
    if (workOnly) setSelected(window.location.hash.slice(1));
  }, [workOnly]);
  const [followups, setFollowups] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const intents = useRef(new ContinuousIntents());
  async function api<T>(
    path: string,
    method = "GET",
    body?: object,
  ): Promise<T> {
    const response = await authFetch(`${getBackendBaseURL()}/api/me/${path}`, {
      method,
      headers: {
        "Content-Type": "application/json",
        "X-Expected-User-Id": userId,
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    if (!response.ok) {
      const value = (await response.json().catch(() => null)) as {
        detail?: { message?: string };
      } | null;
      throw Object.assign(
        new Error(
          value?.detail?.message ??
            dmCopy(
              zh,
              "continuous-secretary.unavailable.refresh.and.inspect.the.original.ope.8852e5",
            ),
        ),
        { status: response.status },
      );
    }
    return (await response.json()) as T;
  }
  const prefix = ["continuous", userId];
  const config = useQuery({
    queryKey: [...prefix, "config"],
    queryFn: () => api<Config>("continuous-config"),
    enabled: canRun,
    refetchInterval: canRun ? 10000 : false,
  });
  const enabled =
    config.data?.interactive_available ??
    config.data?.module_available ??
    false;
  const works = useQuery({
    queryKey: [...prefix, "works"],
    queryFn: () => api<Page>("work-orders"),
    enabled: canRun,
    refetchInterval: enabled ? 5000 : false,
  });
  const router = useQuery({
    queryKey: [...prefix, "router"],
    queryFn: () => api<Router>("router"),
    enabled: canRun && enabled,
    refetchInterval: enabled ? 5000 : false,
  });
  const sources = useQuery({
    queryKey: [...prefix, "sources"],
    queryFn: () => api<Page>("event-sources"),
    enabled: canRun && enabled,
  });
  const rules = useQuery({
    queryKey: [...prefix, "rules"],
    queryFn: () => api<Page>("automation-rules"),
    enabled: canRun && enabled,
  });
  const decisions = useQuery({
    queryKey: [...prefix, "decisions"],
    queryFn: () => api<Page>("agent-decisions"),
    enabled: canRun && enabled,
    refetchInterval: enabled ? 10000 : false,
  });
  const timeline = useQuery({
    queryKey: [...prefix, "timeline", selected],
    queryFn: () => api<Page>(`work-orders/${selected}/timeline`),
    enabled: !!selected,
    refetchInterval: 5000,
  });
  const current = works.data?.items.find((v) => v.id === selected);
  const readUnavailable = config.isError || works.isError;
  async function mutate(
    path: string,
    method: string,
    body: object,
    done?: () => void,
  ) {
    if (busy) return;
    setBusy(true);
    setError("");
    const intent = intents.current.begin(path, method, body);
    try {
      await api(path, method, intent.body);
      intents.current.confirmed(intent);
      done?.();
    } catch (e) {
      intents.current.rejected(
        intent,
        (e as { status?: number } | null)?.status,
      );
      setError(e instanceof Error ? e.message : "Unavailable");
    } finally {
      setBusy(false);
      await cache.invalidateQueries({ queryKey: prefix });
    }
  }
  const status = (v: RecordView) => (
    <StatusBadge
      domain="continuous"
      status={
        v.kind === "work" && ["paused", "closed"].includes(v.state)
          ? v.state
          : str(v, "stage") || v.state
      }
    />
  );
  return {
    userId,
    zh,
    canRun,
    workOnly,
    cache,
    message,
    setMessage,
    goal,
    setGoal,
    project,
    setProject,
    grant,
    setGrant,
    instruction,
    setInstruction,
    selected,
    setSelected,
    workFilter,
    setWorkFilter,
    followups,
    setFollowups,
    busy,
    setBusy,
    error,
    setError,
    intents,
    api,
    prefix,
    config,
    enabled,
    works,
    router,
    sources,
    rules,
    decisions,
    timeline,
    current,
    readUnavailable,
    mutate,
    status,
  };
}
export type SecretaryController = ReturnType<typeof useSecretaryController>;
