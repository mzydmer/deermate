"use client";
import { BookOpen, ChevronUp, LogOut, Moon, Settings } from "lucide-react";
import Link from "next/link";
import { useTheme } from "next-themes";

import { dmCopy } from "@/components/deermate/i18n/copy";
import {
  Avatar,
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Text,
} from "@/components/deermate/ui";
import { useAuth } from "@/core/auth/AuthProvider";
import { useI18n } from "@/core/i18n/hooks";

import { useSettingsDialog } from "./settings";
import { useWorkspaceSidebarExpanded } from "./workspace-sidebar-frame";
export function WorkspaceNavMenu() {
  const { user, logout } = useAuth();
  const { locale, t } = useI18n();
  const { resolvedTheme, setTheme } = useTheme();
  const { openSettings } = useSettingsDialog();
  const expanded = useWorkspaceSidebarExpanded();
  const name = user?.email ?? "DeerMate";
  const zh = locale === "zh-CN";
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          aria-label={name}
          className={
            expanded ? "w-full justify-start" : "w-full justify-center px-0"
          }
        >
          <Avatar name={name} />
          {expanded && (
            <>
              <Text className="min-w-0 flex-1 truncate">{name}</Text>
              <ChevronUp className="size-4" />
            </>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent side="top" align="start">
        <DropdownMenuItem onSelect={() => openSettings("appearance")}>
          <Settings className="size-4" />
          {t.common.settings}
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href="/docs">
            <BookOpen className="size-4" />
            {dmCopy(zh, "common.docs")}
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem
          onSelect={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
        >
          <Moon className="size-4" />
          {dmCopy(zh, "common.theme")}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => void logout()}>
          <LogOut className="size-4" />
          {dmCopy(zh, "common.logout")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
