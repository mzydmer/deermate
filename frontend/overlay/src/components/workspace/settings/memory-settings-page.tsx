"use client";

import { Brain } from "lucide-react";

import { dmCopy } from "@/components/deermate/i18n/copy";
import { PersonalMemoryPanel } from "@/components/deermate/personal-memory";
import { SectionHeader } from "@/components/deermate/ui";
import { useAuth } from "@/core/auth/AuthProvider";
import { useI18n } from "@/core/i18n/hooks";

export function MemorySettingsPage() {
  const { user } = useAuth();
  const { locale } = useI18n();
  const zh = locale === "zh-CN";
  if (!user?.id) return null;
  return (
    <div data-testid="settings-memory-page" className="dm-memory-settings">
      <SectionHeader
        icon={Brain}
        title={dmCopy(zh, "memory-settings-page.memory.management.dc630f")}
        description={dmCopy(
          zh,
          "memory-settings-page.review.the.memories.saved.for.you.inspect.their..1183be",
        )}
      />
      <PersonalMemoryPanel key={user.id} userId={user.id} zh={zh} embedded />
    </div>
  );
}
