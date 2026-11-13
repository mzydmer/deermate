"use client";
import { fetch as authFetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";
export type Topic = {
  id: string;
  thread_id: string;
  title: string;
  goal: string;
  status: string;
  priority: number;
  revision: number;
  source_state: string;
  snoozed_until: number;
};
export type Evidence = {
  version: string;
  kind: string;
  task_id?: string;
  status: string;
  verified: boolean;
  validation_failed: boolean;
  tracking_degraded: boolean;
  cancel_requested: boolean;
  occurred_at: string;
  polled_at?: string;
  checked_at: number;
  stale: boolean;
  busy: boolean;
};
export type Item = {
  topic: Topic;
  evidence: Evidence;
  has_changes: boolean;
  followup_question: string;
};
export type Suggestion = {
  fact_id: string;
  fact_revision: number;
  question: string;
  reason: string;
};
export type Briefing = {
  version: string;
  local_date: string;
  timezone: string;
  checked_at: number;
  items: Item[];
  total: number;
  unavailable: number;
  suggestions: Suggestion[];
  suggestions_unavailable: boolean;
};
export type Intent = {
  id: string;
  kind: string;
  question: string;
  status: string;
  thread_id: string;
  run_id?: string;
  task_id?: string;
  project?: string;
  executor?: string;
};
export type Continuation = {
  project: string;
  executor: string;
  fingerprint: string;
};
export async function homeAPI<T>(
  user: string,
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await authFetch(`${getBackendBaseURL()}/api/me/${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", "X-Expected-User-Id": user },
  });
  if (!response.ok)
    throw new Error(
      response.status >= 400 && response.status < 500
        ? "changed"
        : "unavailable",
    );
  return (await response.json()) as T;
}
