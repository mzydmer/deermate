"use client";
import { ListChecks } from "lucide-react";
import { useState } from "react";

import {
  Badge,
  Button,
  Card,
  Disclosure,
  DisclosureTrigger,
  Empty,
  ErrorBanner,
  Heading,
  KeyValue,
  RelativeTime,
  ScrollArea,
  SectionHeader,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
  Skeleton,
  StatusBadge,
  Text,
} from "@/components/deermate/ui";
import {
  isActiveBackgroundTask,
  type BackgroundTask,
  type BackgroundTaskDetail,
  useBackgroundTask,
  useBackgroundTasks,
  useCancelBackgroundTask,
} from "@/core/background-tasks";
import { useMcpTasksEnabled } from "@/core/features";
import { useI18n } from "@/core/i18n/hooks";

export function ThreadBackgroundTasks({ threadId }: { threadId: string }) {
  const { t } = useI18n();
  const { enabled } = useMcpTasksEnabled();
  const query = useBackgroundTasks(threadId, { enabled });
  const cancel = useCancelBackgroundTask(threadId);
  const tasks = query.data ?? [],
    active = tasks.filter(isActiveBackgroundTask),
    recent = tasks.filter((v) => !isActiveBackgroundTask(v));
  if (!enabled) return null;
  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button
          variant="secondary"
          size="sm"
          aria-label={t.backgroundTasks.label}
          data-testid="background-tasks-trigger"
        >
          <ListChecks className="size-4" />
          <span className="hidden lg:inline">{t.backgroundTasks.label}</span>
          {active.length > 0 && (
            <Badge>{active.length > 9 ? "9+" : active.length}</Badge>
          )}
        </Button>
      </SheetTrigger>
      <SheetContent className="dm-pattern-inspector-sheet">
        <SheetHeader className="p-0">
          <SheetTitle>{t.backgroundTasks.title}</SheetTitle>
          <SheetDescription>{t.backgroundTasks.description}</SheetDescription>
        </SheetHeader>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {query.isLoading ? (
            <Skeleton label={t.common.loading} />
          ) : query.isError ? (
            <ErrorBanner
              onRetry={() => void query.refetch()}
              retryLabel={t.backgroundTasks.retry}
            >
              {t.backgroundTasks.loadFailed}
            </ErrorBanner>
          ) : !tasks.length ? (
            <Empty
              icon={ListChecks}
              title={t.backgroundTasks.empty}
              description={t.backgroundTasks.emptyHint}
            />
          ) : (
            <div className="grid gap-6">
              {active.length > 0 && (
                <TaskSection
                  threadId={threadId}
                  title={t.backgroundTasks.active}
                  tasks={active}
                  cancellingTaskId={
                    cancel.isPending ? cancel.variables : undefined
                  }
                  onCancel={(id) => cancel.mutate(id)}
                />
              )}{" "}
              {recent.length > 0 && (
                <TaskSection
                  threadId={threadId}
                  title={t.backgroundTasks.recent}
                  tasks={recent}
                />
              )}
            </div>
          )}
          {cancel.error && <ErrorBanner>{cancel.error.message}</ErrorBanner>}
        </div>
      </SheetContent>
    </Sheet>
  );
}
function TaskSection({
  threadId,
  title,
  tasks,
  cancellingTaskId,
  onCancel,
}: {
  threadId: string;
  title: string;
  tasks: BackgroundTask[];
  cancellingTaskId?: string;
  onCancel?: (id: string) => void;
}) {
  return (
    <section className="grid gap-3">
      <SectionHeader icon={ListChecks} title={title} />
      {tasks.map((task) => (
        <BackgroundTaskCard
          key={task.task_id}
          threadId={threadId}
          task={task}
          isCancelling={cancellingTaskId === task.task_id}
          onCancel={onCancel}
        />
      ))}
    </section>
  );
}
function BackgroundTaskCard({
  threadId,
  task,
  isCancelling,
  onCancel,
}: {
  threadId: string;
  task: BackgroundTask;
  isCancelling: boolean;
  onCancel?: (id: string) => void;
}) {
  const { t, locale } = useI18n();
  const [open, setOpen] = useState(false);
  const detail = useBackgroundTask(threadId, task.task_id, { enabled: open });
  const active = isActiveBackgroundTask(task),
    cancelling = active && (task.cancel_requested || isCancelling);
  const canShowDetails =
    task.cancel_requested ||
    (task.status !== "submitted" &&
      (task.status !== "working" || task.tracking_degraded));
  return (
    <Card asChild variant="compact">
      <article
        data-testid={`background-task-${task.task_id}`}
        className="grid min-w-0 gap-3"
      >
        <Heading level={3} className="break-words">
          {task.task_name}
        </Heading>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge
            status={
              cancelling
                ? "cancellation_requested"
                : task.status === "completed"
                  ? "completed_unverified"
                  : task.status
            }
          />
          <RelativeTime value={task.updated_at} locale={locale} />
        </div>
        <Text as="div" size="caption">
          {t.backgroundTasks.created("")}{" "}
          <RelativeTime value={task.created_at} locale={locale} />
        </Text>
        {task.tracking_degraded && (
          <StatusBadge domain="connection" status="offline" />
        )}
        {task.error && <ErrorBanner>{task.error}</ErrorBanner>}
        <div className="flex flex-wrap gap-2">
          {canShowDetails && (
            <Button
              variant="ghost"
              size="sm"
              aria-expanded={open}
              onClick={() => setOpen((v) => !v)}
            >
              {open
                ? t.backgroundTasks.hideDetails
                : t.backgroundTasks.viewDetails}
            </Button>
          )}
          {active && onCancel && (
            <Button
              variant="secondary"
              size="sm"
              disabled={cancelling}
              loading={isCancelling}
              onClick={() => onCancel(task.task_id)}
            >
              {cancelling
                ? t.backgroundTasks.cancelling
                : t.backgroundTasks.cancel}
            </Button>
          )}
        </div>
        {open && (
          <BackgroundTaskDetails
            task={detail.data}
            isLoading={detail.isLoading}
            error={detail.error}
            onRetry={() => void detail.refetch()}
          />
        )}
      </article>
    </Card>
  );
}
function BackgroundTaskDetails({
  task,
  isLoading,
  error,
  onRetry,
}: {
  task: BackgroundTaskDetail | undefined;
  isLoading: boolean;
  error: Error | null;
  onRetry: () => void;
}) {
  const { t } = useI18n();
  if (isLoading) return <Skeleton label={t.common.loading} />;
  if (error)
    return (
      <ErrorBanner onRetry={onRetry} retryLabel={t.backgroundTasks.retry}>
        {t.backgroundTasks.detailsFailed}: {error.message}
      </ErrorBanner>
    );
  if (!task) return null;
  return (
    <div className="grid min-w-0 gap-3">
      {task.last_cancel_error && (
        <ErrorBanner>
          {t.backgroundTasks.cancellationRetrying(task.cancel_attempt_count)}:{" "}
          {task.last_cancel_error}
        </ErrorBanner>
      )}
      {task.notification_error && (
        <ErrorBanner>
          {task.notification_status === "dead_letter"
            ? t.backgroundTasks.notificationStopped
            : t.backgroundTasks.notificationRetrying(
                task.notification_attempt_count,
              )}
          : {task.notification_error}
        </ErrorBanner>
      )}
      {task.last_poll_error && (
        <ErrorBanner>{task.last_poll_error}</ErrorBanner>
      )}
      <KeyValue label="Task ID" value={task.task_id} mono copy />
      <DetailField
        label={t.backgroundTasks.result}
        value={task.result_preview ?? task.result}
      />
      <DetailField
        label={t.backgroundTasks.resultArtifact}
        value={task.result_artifact}
      />
      <DetailField
        label={t.backgroundTasks.inputRequired}
        value={task.input_required}
      />
      {task.input_required != null && (
        <Text>{t.backgroundTasks.inputUnavailable}</Text>
      )}
    </div>
  );
}
function DetailField({ label, value }: { label: string; value: unknown }) {
  if (value === undefined || value === null) return null;
  let text: string;
  try {
    text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  } catch {
    text = "[Unserializable result]";
  }
  return (
    <Disclosure>
      <DisclosureTrigger>{label}</DisclosureTrigger>
      <ScrollArea className="dm-evidence-scroll">
        <pre tabIndex={0}>{text}</pre>
      </ScrollArea>
    </Disclosure>
  );
}
