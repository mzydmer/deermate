"use client";

import {
  Blocks,
  Bot,
  CalendarClock,
  LayoutDashboard,
  ListChecks,
  MessagesSquare,
  UserRound,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { dmCopy } from "@/components/deermate/i18n/copy";
import {
  SidebarGroup,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import { useI18n } from "@/core/i18n/hooks";

export function WorkspaceNavChatList() {
  const { locale } = useI18n();
  const zh = locale === "zh-CN";
  const path = usePathname();
  const links = [
    {
      href: "/workspace",
      title: dmCopy(zh, "workspace-nav-chat-list.assistant.e7461b"),
      icon: LayoutDashboard,
    },
    {
      href: "/workspace/work",
      title: dmCopy(zh, "workspace-nav-chat-list.my.work.1e404f"),
      icon: ListChecks,
    },
    {
      href: "/workspace/memory",
      title: dmCopy(zh, "workspace-nav-chat-list.about.you.38ca3c"),
      icon: UserRound,
    },
    {
      href: "/workspace/chats",
      title: dmCopy(zh, "workspace-nav-chat-list.all.chats.fdb146"),
      icon: MessagesSquare,
    },
  ];
  return (
    <SidebarGroup>
      <SidebarMenu>
        {links.map((v) => (
          <SidebarMenuItem key={v.href}>
            <SidebarMenuButton
              tooltip={v.title}
              isActive={path === v.href}
              asChild
            >
              <Link
                href={v.href}
                aria-current={path === v.href ? "page" : undefined}
              >
                <v.icon />
                <span>{v.title}</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        ))}
      </SidebarMenu>
    </SidebarGroup>
  );
}

export function WorkspaceAdvancedNav() {
  const { locale } = useI18n();
  const zh = locale === "zh-CN";
  const path = usePathname();
  const links = [
    {
      href: "/workspace/capabilities",
      title: dmCopy(
        zh,
        "workspace-nav-chat-list.tools.and.capabilities.fb0340",
      ),
      icon: Blocks,
    },
    {
      href: "/workspace/scheduled-tasks",
      title: dmCopy(zh, "workspace-nav-chat-list.scheduled.tasks.9fe862"),
      icon: CalendarClock,
    },
    {
      href: "/workspace/agents",
      title: dmCopy(zh, "workspace-nav-chat-list.agent.settings.38da81"),
      icon: Bot,
    },
  ];
  return (
    <SidebarGroup>
      <SidebarMenu>
        {links.map((v) => (
          <SidebarMenuItem key={v.href}>
            <SidebarMenuButton
              tooltip={v.title}
              isActive={path.startsWith(v.href)}
              asChild
            >
              <Link
                href={v.href}
                aria-current={path === v.href ? "page" : undefined}
              >
                <v.icon />
                <span>{v.title}</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        ))}
      </SidebarMenu>
    </SidebarGroup>
  );
}
