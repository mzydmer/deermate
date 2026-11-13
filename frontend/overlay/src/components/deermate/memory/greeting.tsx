"use client";
import { useEffect, useState } from "react";

import { dmCopy } from "@/components/deermate/i18n/copy";
import { Heading, Text } from "@/components/deermate/ui";

import { useProfile } from "./model";
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
  let greeting = dmCopy(zh, "personal-memory.hello.fcfca5");
  let date = "";
  if (now) {
    // Match the server briefing calendar, including an unsaved UTC profile.
    let timezone = profile.data?.timezone ?? "UTC";
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
        ? dmCopy(zh, "personal-memory.good.morning.22c413")
        : hour >= 12 && hour < 18
          ? dmCopy(zh, "personal-memory.good.afternoon.f75cbb")
          : dmCopy(zh, "personal-memory.good.evening.db7f32");
    date = new Intl.DateTimeFormat(dmCopy(zh, "personal-memory.en.us.218b02"), {
      timeZone: timezone,
      month: "long",
      day: "numeric",
      weekday: "long",
    }).format(now);
    if (fallback) date += " · UTC";
  }
  return (
    <>
      <Heading level={1}>
        {greeting}
        {profile.data?.display_name
          ? `${dmCopy(zh, "personal-memory...89b43e")}${profile.data.display_name}`
          : ""}
        {dmCopy(zh, "personal-memory...76b373")}
      </Heading>
      <Text as="p" tone="muted" className="">
        {date || dmCopy(zh, "personal-memory.your.personal.secretary.455551")}
      </Text>
    </>
  );
}
