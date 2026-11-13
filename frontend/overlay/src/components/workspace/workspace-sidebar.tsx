"use client";

import { dmCopy } from "@/components/deermate/i18n/copy";
import { RouteProgress } from "@/components/deermate/patterns/shell";
import { SidebarResponsiveBehavior } from "@/components/deermate/patterns/sidebar";
import { Disclosure, DisclosureTrigger } from "@/components/deermate/ui";
import {
  type Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
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
  WorkspaceAdvancedNav,
  WorkspaceNavChatList,
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
      <SidebarResponsiveBehavior />
      <RouteProgress />
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
        <Disclosure data-testid="sidebar-more" className="dm-sidebar-more">
          <DisclosureTrigger>
            {dmCopy(locale === "zh-CN", "common.more")}
          </DisclosureTrigger>
          <WorkspaceAdvancedNav />
          <PluginNavigation />
          <WorkspaceChannelsList />
          {isSidebarOpen && <ProjectsSection />}
        </Disclosure>
      </SidebarContent>
      <SidebarFooter>
        <WorkspaceNavMenu />
      </SidebarFooter>
      {!isMobile && <SidebarRail />}
    </>
  );
}
