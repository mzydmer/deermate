"use client";
import Link from "next/link";

import { AppShell, TopBar } from "@/components/deermate/patterns/shell";
import {
  Heading,
  Button,
  Skeleton,
  ErrorState,
} from "@/components/deermate/ui";
import { useFrontendExtensions } from "@/core/extensions/hooks";
import { pluginPages, pluginPageTitle } from "@/core/extensions/pages";
import { useI18n } from "@/core/i18n/hooks";

import { PluginSurfaces } from "./plugin-surfaces";
export function PluginPage({
  namespace,
  surfaceId,
}: {
  namespace: string;
  surfaceId: string;
}) {
  const query = useFrontendExtensions();
  const { locale, t } = useI18n();
  const page = pluginPages(query.data ?? []).find(
    ({ contribution, surface }) =>
      contribution.namespace === namespace && surface.id === surfaceId,
  );
  const title = page
    ? pluginPageTitle(page.surface, locale)
    : t.extensions.pageUnavailable;
  return (
    <AppShell>
      <TopBar title={title} zh={locale === "zh-CN"} />
      <main className="min-w-0 p-6">
        <Heading level={1}>{title}</Heading>
        {query.isPending ? (
          <Skeleton label={t.extensions.pageLoading} />
        ) : page ? (
          <PluginSurfaces
            slot="page"
            namespace={namespace}
            surfaceId={surfaceId}
          />
        ) : (
          <ErrorState
            title={t.extensions.pageUnavailable}
            detail={t.extensions.pageUnavailableHint}
            action={
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => window.location.reload()}>
                  {t.extensions.reload}
                </Button>
                <Button variant="ghost" asChild>
                  <Link href="/workspace/capabilities?tab=extensions">
                    {t.extensions.viewAll}
                  </Link>
                </Button>
              </div>
            }
          />
        )}
      </main>
    </AppShell>
  );
}
