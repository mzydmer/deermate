"use client";

import {
  type Sidebar,
  SidebarHeader,
  SidebarContent,
  SidebarFooter,
  SidebarRail,
  useSidebar,
} from "@/components/ui/sidebar";
import { useI18n } from "@/core/i18n/hooks";
import { useThreadActivity } from "@/core/threads/activity";

import { WorkspaceChannelsList } from "./channels/workspace-channels-list";
import { PluginNavigation } from "./plugin-navigation";
import { ProjectsSection } from "./projects-section";
import { RecentChatList } from "./recent-chat-list";
import { ThreadDeleteDialogProvider } from "./thread-delete-dialog";
import { WorkspaceHeader } from "./workspace-header";
import {
  WorkspaceNavChatList,
  WorkspaceAdvancedNav,
} from "./workspace-nav-chat-list";
import { WorkspaceNavMenu } from "./workspace-nav-menu";
import {
  WorkspaceSidebarFrame,
  useWorkspaceSidebarExpanded,
} from "./workspace-sidebar-frame";

export function WorkspaceSidebar({
  ...props
}: React.ComponentProps<typeof Sidebar>) {
  // One activity poll per workspace (off unless the Gateway offers it): new
  // and changed server-created threads reach the thread lists without a
  // reload, and a read on another device clears their dots here.
  useThreadActivity();
  return (
    <ThreadDeleteDialogProvider>
      <WorkspaceSidebarFrame variant="sidebar" collapsible="icon" {...props}>
        <WorkspaceSidebarContents />
      </WorkspaceSidebarFrame>
    </ThreadDeleteDialogProvider>
  );
}

function WorkspaceSidebarContents() {
  const isSidebarOpen = useWorkspaceSidebarExpanded();
  const { locale } = useI18n();
  const { isMobile } = useSidebar();
  return (
    <>
      <SidebarHeader className="py-0">
        <WorkspaceHeader />
      </SidebarHeader>
      <SidebarContent>
        <WorkspaceNavChatList />
        {isSidebarOpen && <RecentChatList />}
        <details className="dm-sidebar-more">
          <summary>{locale === "zh-CN" ? "更多" : "More"}</summary>
          <WorkspaceAdvancedNav />
          <PluginNavigation />
          <WorkspaceChannelsList />
          {isSidebarOpen && <ProjectsSection />}
        </details>
      </SidebarContent>
      <SidebarFooter>
        <WorkspaceNavMenu />
      </SidebarFooter>
      {!isMobile && <SidebarRail />}
    </>
  );
}
