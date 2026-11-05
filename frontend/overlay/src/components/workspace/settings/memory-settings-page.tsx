"use client";

import { PersonalMemoryPanel } from "@/components/deermate/personal-memory";
import { useAuth } from "@/core/auth/AuthProvider";
import { useI18n } from "@/core/i18n/hooks";

export function MemorySettingsPage() {
  const { user } = useAuth();
  const { locale } = useI18n();
  const zh = locale === "zh-CN";
  if (!user?.id) return null;
  return (
    <div className="dm-memory-settings">
      <h2>{zh ? "记忆管理" : "Memory management"}</h2>
      <p className="dm-muted">
        {zh
          ? "查看我为你保存的记忆，核对来源，并随时修改或遗忘。"
          : "Review the memories saved for you, inspect their sources, and correct or forget them."}
      </p>
      <PersonalMemoryPanel key={user.id} userId={user.id} zh={zh} embedded />
    </div>
  );
}
