import { fetch as authFetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

export async function workspaceAPI<T>(
  user: string,
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await authFetch(`${getBackendBaseURL()}/api/me/${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", "X-Expected-User-Id": user },
  });
  if (!response.ok)
    throw Object.assign(new Error("暂时没连上，请稍后核对原操作。"), {
      status: response.status,
    });
  return (await response.json()) as T;
}
