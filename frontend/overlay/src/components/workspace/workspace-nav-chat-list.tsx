"use client";

import {
  Blocks,
  CalendarClock,
  LayoutDashboard,
  ListChecks,
  MessagesSquare,
  UserRound,
  Bot,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

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
      title: zh ? "助手" : "Assistant",
      icon: LayoutDashboard,
    },
    {
      href: "/workspace/work",
      title: zh ? "我的工作" : "My work",
      icon: ListChecks,
    },
    {
      href: "/workspace/memory",
      title: zh ? "关于你" : "About you",
      icon: UserRound,
    },
    {
      href: "/workspace/chats",
      title: zh ? "全部对话" : "All chats",
      icon: MessagesSquare,
    },
  ];
  return (
    <SidebarGroup>
      <SidebarMenu>
        {links.map((v) => (
          <SidebarMenuItem key={v.href}>
            <SidebarMenuButton isActive={path === v.href} asChild>
              <Link href={v.href}>
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
      title: zh ? "工具与能力" : "Tools and capabilities",
      icon: Blocks,
    },
    {
      href: "/workspace/scheduled-tasks",
      title: zh ? "定时任务" : "Scheduled tasks",
      icon: CalendarClock,
    },
    {
      href: "/workspace/agents",
      title: zh ? "智能体设置" : "Agent settings",
      icon: Bot,
    },
  ];
  return (
    <SidebarGroup>
      <SidebarMenu>
        {links.map((v) => (
          <SidebarMenuItem key={v.href}>
            <SidebarMenuButton isActive={path.startsWith(v.href)} asChild>
              <Link href={v.href}>
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
