"use client";

import { useSearchParams } from "next/navigation";

import { BrandMotion } from "@/components/deermate/brand";
import { dmCopy } from "@/components/deermate/i18n/copy";
import { Heading, Text } from "@/components/deermate/ui";
import { useI18n } from "@/core/i18n/hooks";

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
    <div
      className={`dm-chat-welcome flex flex-col items-center gap-2 p-4 text-center ${className}`}
    >
      <BrandMotion />
      <Heading level={1}>
        {skill
          ? t.welcome.createYourOwnSkill
          : dmCopy(zh, "welcome.let.s.make.room.for.your.next.idea..185e48")}
      </Heading>
      <Text as="p" size="caption">
        {skill
          ? t.welcome.createYourOwnSkillDescription
          : dmCopy(
              zh,
              "welcome.share.a.goal.we.ll.work.out.the.next.step.togeth.962f15",
            )}
      </Text>
    </div>
  );
}
