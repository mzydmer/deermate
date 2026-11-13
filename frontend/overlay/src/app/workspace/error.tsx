"use client";
import { dmCopy } from "@/components/deermate/i18n/copy";
import { Button, ErrorState } from "@/components/deermate/ui";
import { useI18n } from "@/core/i18n/hooks";
export default function WorkspaceError({ reset }: { reset: () => void }) {
  const { locale } = useI18n();
  const zh = locale === "zh-CN";
  return (
    <ErrorState
      title={dmCopy(zh, "common.pageerror")}
      detail={dmCopy(zh, "common.pageerror.detail")}
      action={<Button onClick={reset}>{dmCopy(zh, "common.retry")}</Button>}
    />
  );
}
