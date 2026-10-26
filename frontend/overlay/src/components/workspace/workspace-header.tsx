"use client";

import { MessageSquarePlus } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { DeerMark } from "@/components/deermate/brand";
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import { useI18n } from "@/core/i18n/hooks";
import { useWorkspaceSidebarExpanded } from "./workspace-sidebar-frame";
import { WorkspaceSidebarTrigger } from "./workspace-sidebar-trigger";

export function WorkspaceHeader({ className = "" }: { className?: string }) {
  const { t } = useI18n();
  const pathname = usePathname();
  const expanded = useWorkspaceSidebarExpanded();
  return (
    <>
      <div className={`dm-sidebar-brand ${className}`}>
        <Link href="/workspace" aria-label="DeerMate">
          <DeerMark />
          {expanded && (
            <span>
              DeerMate<small>YOUR PERSONAL SECRETARY</small>
            </span>
          )}
        </Link>
        {expanded && <WorkspaceSidebarTrigger />}
      </div>
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton
            className="dm-new-chat"
            isActive={pathname === "/workspace/chats/new"}
            asChild
          >
            <Link href="/workspace/chats/new">
              <MessageSquarePlus size={16} />
              <span>{t.sidebar.newChat}</span>
            </Link>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    </>
  );
}
