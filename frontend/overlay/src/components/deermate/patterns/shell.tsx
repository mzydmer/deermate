"use client";
import { BookOpen, LayoutDashboard, Moon, Sun } from "lucide-react";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

import { WorkspaceSidebarTrigger } from "@/components/workspace/workspace-sidebar-trigger";

import { dmCopy } from "../i18n/copy";
import { IconButton, Spinner, Text } from "../ui";

export function TopBar({
  title,
  zh,
  trailing,
}: {
  title: string;
  zh: boolean;
  trailing?: React.ReactNode;
}) {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  return (
    <header data-testid="topbar" data-slot="dm-topbar" className="dm-topbar">
      <div className="flex min-w-0 items-center gap-3">
        <WorkspaceSidebarTrigger />
        <LayoutDashboard className="size-4 shrink-0" aria-hidden="true" />
        <Text tone="ink" className="truncate">
          {title}
        </Text>
        {trailing}
      </div>
      <div className="flex items-center gap-2">
        <IconButton
          label={dmCopy(zh, "common.docs")}
          icon={<BookOpen className="size-4" />}
          href="/docs"
        />
        <IconButton
          label={dmCopy(zh, "common.theme")}
          icon={
            mounted && resolvedTheme === "dark" ? (
              <Sun className="size-4" />
            ) : (
              <Moon className="size-4" />
            )
          }
          onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
        />
      </div>
    </header>
  );
}
export function AppShell({
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      {...props}
      data-testid="desk assistant"
      data-slot="dm-app-shell"
      className="dm-desk dm-assistant"
    >
      {children}
    </div>
  );
}
export function RouteProgress() {
  const path = usePathname();
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    setBusy(false);
  }, [path]);
  useEffect(() => {
    const start = (e: MouseEvent) => {
      const anchor = (e.target as Element).closest("a");
      if (
        anchor?.origin === location.origin &&
        anchor.pathname !== location.pathname &&
        !e.metaKey &&
        !e.ctrlKey
      )
        setBusy(true);
    };
    document.addEventListener("click", start);
    return () => document.removeEventListener("click", start);
  }, []);
  return busy ? (
    <div
      data-testid="route-progress"
      role="progressbar"
      aria-label="Loading page"
      className="dm-route-progress"
    />
  ) : null;
}
export function LoadingRow({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2">
      <Spinner label={label} />
      <Text size="caption">{label}</Text>
    </div>
  );
}
