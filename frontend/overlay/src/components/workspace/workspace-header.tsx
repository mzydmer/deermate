"use client";
import { MessageSquarePlus } from "lucide-react";
import Link from "next/link";

import { DeerMark } from "@/components/deermate/brand";
import { dmCopy } from "@/components/deermate/i18n/copy";
import { Button } from "@/components/deermate/ui";
import { useI18n } from "@/core/i18n/hooks";

import { useWorkspaceSidebarExpanded } from "./workspace-sidebar-frame";
import { WorkspaceSidebarTrigger } from "./workspace-sidebar-trigger";
export function WorkspaceHeader({ className = "" }: { className?: string }) {
  const { locale } = useI18n();
  const expanded = useWorkspaceSidebarExpanded();
  return (
    <>
      <div
        className={`dm-sidebar-brand ${expanded ? "" : "justify-center"} ${className}`}
      >
        <Link
          href="/workspace"
          aria-label="DeerMate"
          className={expanded ? "" : "hidden"}
        >
          <DeerMark />
          <span data-expanded={expanded}>DeerMate</span>
        </Link>
        <WorkspaceSidebarTrigger />
      </div>
      <div className="px-2">
        <Button
          asChild
          variant="secondary"
          className={
            expanded
              ? "w-full justify-start"
              : "w-full justify-center gap-0 px-0"
          }
        >
          <Link href="/workspace/chats/new">
            <MessageSquarePlus className="size-4" />
            <span
              data-testid="sidebar-label"
              className="dm-sidebar-label"
              data-expanded={expanded}
            >
              {dmCopy(locale === "zh-CN", "common.newtopic")}
            </span>
          </Link>
        </Button>
      </div>
    </>
  );
}
