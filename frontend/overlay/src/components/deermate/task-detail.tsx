"use client";

import { ArrowUpRight } from "lucide-react";
import Link from "next/link";

import { dmCopy } from "@/components/deermate/i18n/copy";
import {
  Button,
  Disclosure,
  DisclosureTrigger,
  ErrorBanner,
  KeyValue,
  ScrollArea,
  Skeleton,
  StatusBadge,
  Text,
} from "@/components/deermate/ui";
import { useBackgroundTask } from "@/core/background-tasks";
import { useI18n } from "@/core/i18n/hooks";

import { Inspector } from "./patterns/inspector";

export type DeskTask = {
  threadId: string;
  task_id: string;
  task_name: string;
  status: string;
  updated_at: string;
  cancel_requested: boolean;
  tracking_degraded: boolean;
  error: string | null;
};

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

export function TaskDetail({
  task,
  onClose,
  restoreFocus,
}: {
  task: DeskTask | null;
  onClose: () => void;
  restoreFocus: () => void;
}) {
  const { locale } = useI18n();
  const zh = locale === "zh-CN";
  const detail = useBackgroundTask(task?.threadId ?? "", task?.task_id ?? "", {
    enabled: !!task,
  });
  const json =
    detail.data?.result == null
      ? null
      : JSON.stringify(detail.data.result, null, 2);
  const result = record(detail.data?.result);
  const validation = record(result?.validation);
  const verified =
    result?.validation_status === "passed" && validation?.exit_code === 0;
  const validationFailed =
    result?.validation_status === "failed" ||
    (typeof validation?.exit_code === "number" && validation.exit_code !== 0);
  const summary = typeof result?.summary === "string" ? result.summary : null;
  const testOutput = [validation?.stdout, validation?.stderr]
    .filter((value) => typeof value === "string" && value)
    .join("\n");
  const status = detail.data?.status ?? "";
  return (
    <Inspector
      open={!!task}
      onClose={onClose}
      restoreFocus={restoreFocus}
      title={
        task?.task_name ?? dmCopy(zh, "task-detail.work.you.can.verify..35fc98")
      }
      description={dmCopy(
        zh,
        "task-detail.from.the.gateway.s.durable.task.record..c9515b",
      )}
      zh={zh}
    >
      {detail.isLoading ? (
        <Skeleton label={dmCopy(zh, "task-detail.loading.evidence..eab808")} />
      ) : detail.isError ? (
        <ErrorBanner onRetry={() => void detail.refetch()}>
          {dmCopy(zh, "task-detail.could.not.load.the.result.af153f")}
        </ErrorBanner>
      ) : (
        detail.data && (
          <div data-testid="task-detail" className="grid gap-4">
            <div className="flex flex-wrap gap-2">
              <StatusBadge status={status} />
              {detail.data.tracking_degraded && (
                <StatusBadge domain="connection" status="offline" />
              )}
            </div>
            {detail.data.cancel_requested && (
              <Text>
                {dmCopy(
                  zh,
                  "task-detail.cancellation.was.requested.the.execution.state.d.0507ab",
                )}
              </Text>
            )}
            {summary && (
              <Text as="p" tone="ink">
                {summary}
              </Text>
            )}
            <KeyValue
              label={dmCopy(zh, "task-detail.execution.result.49b067")}
              value={summary ?? status}
            />
            <div>
              <Text size="caption">
                {dmCopy(zh, "task-detail.validation.c6cf01")}
              </Text>
              <div className="mt-2">
                <StatusBadge
                  domain="validation"
                  status={
                    verified
                      ? "passed"
                      : validationFailed
                        ? "failed"
                        : "unverified"
                  }
                />
              </div>
            </div>
            <KeyValue
              label={dmCopy(zh, "common.deployment")}
              value={dmCopy(zh, "common.undeployed")}
            />
            <KeyValue
              label={dmCopy(zh, "common.project")}
              value={typeof result?.project === "string" ? result.project : "—"}
              mono
            />
            <KeyValue
              label={dmCopy(zh, "common.executor")}
              value={
                typeof result?.executor === "string" ? result.executor : "—"
              }
              mono
            />
            <KeyValue label="Task ID" value={detail.data.task_id} mono copy />
            <KeyValue
              label={dmCopy(zh, "common.topic")}
              value={task?.threadId ?? "—"}
              mono
              copy
            />
            {detail.data.error && (
              <ErrorBanner>{detail.data.error}</ErrorBanner>
            )}
            {testOutput && (
              <Disclosure>
                <DisclosureTrigger>
                  {dmCopy(zh, "task-detail.test.output.a458b6")}
                </DisclosureTrigger>
                <ScrollArea
                  data-testid="evidence-scroll"
                  className="dm-evidence-scroll"
                >
                  <pre tabIndex={0}>{testOutput.slice(0, 12000)}</pre>
                </ScrollArea>
              </Disclosure>
            )}
            <Disclosure>
              <DisclosureTrigger>
                {dmCopy(zh, "task-detail.view.task.record.2787bc")}
              </DisclosureTrigger>
              <ScrollArea
                data-testid="evidence-scroll"
                className="dm-evidence-scroll"
              >
                <pre tabIndex={0}>
                  {json?.slice(0, 16000) ??
                    dmCopy(
                      zh,
                      "task-detail.no.result.is.available.yet..314e4a",
                    )}
                </pre>
              </ScrollArea>
            </Disclosure>
            <Button asChild variant="primary">
              <Link href={`/workspace/chats/${task?.threadId}`}>
                {dmCopy(zh, "task-detail.open.conversation.b0163e")}
                <ArrowUpRight className="size-4" />
              </Link>
            </Button>
          </div>
        )
      )}
    </Inspector>
  );
}
