"use client";

import {
  BotIcon,
  BellIcon,
  CableIcon,
  InfoIcon,
  BrainIcon,
  PaletteIcon,
  UserCogIcon,
  UsersRoundIcon,
  UserIcon,
} from "lucide-react";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState } from "react";

import { Button, Card, Skeleton, Text } from "@/components/deermate/ui";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useAuth } from "@/core/auth/AuthProvider";
import { useI18n } from "@/core/i18n/hooks";

function SettingsPageLoading() {
  return <Skeleton label="Loading settings" />;
}

const AccountSettingsPage = dynamic(
  () =>
    import("./account-settings-page").then(
      (module) => module.AccountSettingsPage,
    ),
  { loading: SettingsPageLoading },
);
const AppearanceSettingsPage = dynamic(
  () =>
    import("./appearance-settings-page").then(
      (module) => module.AppearanceSettingsPage,
    ),
  { loading: SettingsPageLoading },
);
const ChannelsSettingsPage = dynamic(
  () =>
    import("./channels-settings-page").then(
      (module) => module.ChannelsSettingsPage,
    ),
  { loading: SettingsPageLoading },
);
const MemorySettingsPage = dynamic(
  () =>
    import("./memory-settings-page").then(
      (module) => module.MemorySettingsPage,
    ),
  { loading: SettingsPageLoading },
);
const NotificationSettingsPage = dynamic(
  () =>
    import("./notification-settings-page").then(
      (module) => module.NotificationSettingsPage,
    ),
  { loading: SettingsPageLoading },
);
const SubagentSettingsPage = dynamic(
  () =>
    import("./subagent-settings-page").then(
      (module) => module.SubagentSettingsPage,
    ),
  { loading: SettingsPageLoading },
);
const ModelSettingsPage = dynamic(
  () =>
    import("./model-settings-page").then((module) => module.ModelSettingsPage),
  { loading: SettingsPageLoading },
);
const UserSettingsPage = dynamic(
  () =>
    import("./user-settings-page").then((module) => module.UserSettingsPage),
  { loading: SettingsPageLoading },
);
const AboutSettingsPage = dynamic(
  () =>
    import("./about-settings-page").then((module) => module.AboutSettingsPage),
  { loading: SettingsPageLoading },
);

export type SettingsSection =
  | "models"
  | "users"
  | "account"
  | "appearance"
  | "channels"
  | "memory"
  | "subagents"
  | "notification"
  | "about";

type SettingsDialogProps = React.ComponentProps<typeof Dialog> & {
  defaultSection?: SettingsSection;
};

export function SettingsDialog(props: SettingsDialogProps) {
  const { defaultSection = "appearance", ...dialogProps } = props;
  const { t } = useI18n();
  const { user } = useAuth();
  const isAdmin = user?.system_role === "admin";
  const navigationRef = useRef<HTMLElement>(null);
  const [activeSection, setActiveSection] =
    useState<SettingsSection>(defaultSection);

  useEffect(() => {
    // When opening the dialog, ensure the active section follows the caller's intent.
    // This allows triggers like "About" to open the dialog directly on that page.
    if (dialogProps.open) {
      setActiveSection(defaultSection);
    }
  }, [defaultSection, dialogProps.open]);

  const sections = useMemo(() => {
    const items: {
      id: SettingsSection;
      label: string;
      icon: typeof BotIcon;
    }[] = [
      { id: "models", label: t.settings.sections.models, icon: BotIcon },
      {
        id: "account",
        label: t.settings.sections.account,
        icon: UserIcon,
      },
      {
        id: "appearance",
        label: t.settings.sections.appearance,
        icon: PaletteIcon,
      },
      {
        id: "notification",
        label: t.settings.sections.notification,
        icon: BellIcon,
      },
      {
        id: "channels",
        label: t.settings.sections.channels,
        icon: CableIcon,
      },
      {
        id: "memory",
        label: t.settings.sections.memory,
        icon: BrainIcon,
      },
      {
        id: "subagents",
        label: t.settings.sections.subagents,
        icon: UsersRoundIcon,
      },
      { id: "about", label: t.settings.sections.about, icon: InfoIcon },
    ];
    // User management is meaningless (and confusing) for non-admins, so the
    // entry point itself is hidden; the page still guards independently in
    // case a stale dialog store ever activates the section.
    if (isAdmin) {
      items.splice(1, 0, {
        id: "users",
        label: t.settings.sections.users,
        icon: UserCogIcon,
      });
    }
    return items;
  }, [
    isAdmin,
    t.settings.sections.models,
    t.settings.sections.users,
    t.settings.sections.account,
    t.settings.sections.appearance,
    t.settings.sections.channels,
    t.settings.sections.memory,
    t.settings.sections.subagents,
    t.settings.sections.notification,
    t.settings.sections.about,
  ]);
  // A `?settings=<section>` deep link (or a stale dialog store) can activate
  // a section this user's nav does not offer — e.g. user management for a
  // non-admin — so fall back to the first available section instead of
  // rendering a panel with no highlighted entry. The base list above is
  // non-empty, so the fallback itself always resolves.
  const activeId = sections.some((section) => section.id === activeSection)
    ? activeSection
    : sections[0]!.id;
  useEffect(() => {
    if (!dialogProps.open) return;
    const frame = requestAnimationFrame(() => {
      navigationRef.current
        ?.querySelector('[aria-current="page"]')
        ?.scrollIntoView({
          block: "nearest",
          inline: "nearest",
        });
    });
    return () => cancelAnimationFrame(frame);
  }, [dialogProps.open, activeId]);
  return (
    <Dialog
      {...dialogProps}
      onOpenChange={(open) => props.onOpenChange?.(open)}
    >
      <DialogContent
        className="dm-settings-dialog flex h-[75vh] max-h-[calc(100vh-2rem)] flex-col sm:max-w-5xl md:max-w-6xl"
        aria-describedby={undefined}
      >
        <DialogHeader className="gap-1">
          <DialogTitle>{t.settings.title}</DialogTitle>
          <Text as="p">{t.settings.description}</Text>
        </DialogHeader>
        <div className="grid min-h-0 min-w-0 flex-1 grid-cols-1 grid-rows-[auto_minmax(0,1fr)] gap-4 min-[960px]:grid-cols-[var(--ds-sizes-sidebar)_minmax(0,1fr)] min-[960px]:grid-rows-1">
          <Card variant="compact" asChild className="min-w-0 p-2">
            <nav
              ref={navigationRef}
              className="min-h-0 overflow-x-auto min-[960px]:overflow-y-auto"
            >
              <ul className="flex gap-2 min-[960px]:block min-[960px]:space-y-1">
                {sections.map(({ id, label, icon: Icon }) => {
                  const active = activeId === id;
                  return (
                    <li key={id} className="shrink-0">
                      <Button
                        type="button"
                        onClick={() => setActiveSection(id)}
                        aria-current={active ? "page" : undefined}
                        variant={active ? "secondary" : "ghost"}
                        className="w-full justify-start whitespace-nowrap"
                      >
                        <Icon className="size-4" />
                        <span>{label}</span>
                      </Button>
                    </li>
                  );
                })}
              </ul>
            </nav>
          </Card>
          <Card asChild className="h-full min-h-0 min-w-0 p-0">
            <ScrollArea
              data-testid="settings-content"
              className="h-full min-h-0 min-w-0"
            >
              <div className="space-y-8 p-6">
                {activeId === "models" && <ModelSettingsPage />}
                {activeId === "users" && <UserSettingsPage />}
                {activeId === "account" && <AccountSettingsPage />}
                {activeId === "appearance" && <AppearanceSettingsPage />}
                {activeId === "memory" && <MemorySettingsPage />}
                {activeId === "subagents" && <SubagentSettingsPage />}
                {activeId === "notification" && <NotificationSettingsPage />}
                {activeId === "channels" && <ChannelsSettingsPage />}
                {activeId === "about" && <AboutSettingsPage />}
              </div>
            </ScrollArea>
          </Card>
        </div>
      </DialogContent>
    </Dialog>
  );
}
