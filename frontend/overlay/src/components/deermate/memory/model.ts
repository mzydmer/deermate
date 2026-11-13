"use client";
import { useQuery, type useQueryClient } from "@tanstack/react-query";

import { fetch as authFetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";
export type Profile = {
  owner: string;
  display_name: string;
  timezone: string;
  memory_enabled: boolean;
  auto_capture_enabled: boolean;
  proactive_enabled: boolean;
  revision: number;
};
export type Fact = {
  id: string;
  content: string;
  category: string;
  revision: number;
  source_id: string;
  scope: string;
  updated_at: number;
  expires_at?: number;
  source?: {
    kind: "chat" | "inbox";
    thread_id: string;
    run_id: string;
    message_id: string;
    observed_at: number;
  } | null;
};
export type Reference = { id: string; status: string; revision: number };
export type Operation = { id: string; status: string; fact_id: string };
export type MemoryPage = {
  items: Fact[];
  references: Reference[];
  total_active: number;
};
export function invalidateHome(
  cache: ReturnType<typeof useQueryClient>,
  user: string,
) {
  cache.setQueryData(
    ["deermate", "briefing", user],
    (old: object | undefined) => (old ? { ...old, suggestions: [] } : old),
  );
  void cache.invalidateQueries({ queryKey: ["deermate", "briefing", user] });
  for (const key of [
    "workspace-snapshot",
    "workspace-memory-summary",
    "memory-activity",
    "memory-source",
  ]) {
    void cache.invalidateQueries({ queryKey: [key, user] });
  }
}
export async function personalAPI<T>(
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
export function useProfile(userId: string) {
  return useQuery({
    queryKey: ["deermate", "personal-profile", userId],
    queryFn: ({ signal }) =>
      personalAPI<Profile>("personal-profile", userId, { signal }),
    enabled: !!userId,
    gcTime: 0,
    retry: 1,
  });
}
