"use client";

import { BrandMotion } from "@/components/deermate/brand";
import { useI18n } from "@/core/i18n/hooks";
import { useSearchParams } from "next/navigation";

export function Welcome({
  className = "",
}: {
  className?: string;
  mode?: "ultra" | "pro" | "thinking" | "flash";
}) {
  const { locale, t } = useI18n();
  const skill = useSearchParams().get("mode") === "skill";
  const zh = locale === "zh-CN";
  return (
    <div className={`dm-chat-welcome ${className}`}>
      <BrandMotion />
      <p className="dm-eyebrow">A GOOD PLACE TO START</p>
      <h1>
        {skill
          ? t.welcome.createYourOwnSkill
          : zh
            ? "从一件想完成的事开始。"
            : "Let’s make room for your next idea."}
      </h1>
      <p>
        {skill
          ? t.welcome.createYourOwnSkillDescription
          : zh
            ? "说说你的目标。一起把下一步变清楚。"
            : "Share a goal. We’ll work out the next step together."}
      </p>
    </div>
  );
}
