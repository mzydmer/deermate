"use client";

import Link from "next/link";
import {
  ArrowUpRight,
  CheckCircle2,
  Circle,
  FileText,
  LoaderCircle,
} from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { useBackgroundTask } from "@/core/background-tasks";
import { useI18n } from "@/core/i18n/hooks";

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
  const summary = typeof result?.summary === "string" ? result.summary : null;
  const testOutput = [validation?.stdout, validation?.stderr]
    .filter((value) => typeof value === "string" && value)
    .join("\n");
  const status = detail.data?.status ?? "";
  const statusLabels: Record<string, string> = {
    completed: "已完成",
    working: "执行中",
    failed: "执行失败",
    submitted: "排队中",
    input_required: "等待答复",
    cancelled: "已取消",
  };
  return (
    <Sheet
      open={!!task}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <SheetContent
        className="dm-workspace dm-details w-[min(96vw,540px)] sm:max-w-[540px]"
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          restoreFocus();
        }}
      >
        <SheetHeader>
          <p className="dm-eyebrow">TASK EVIDENCE</p>
          <SheetTitle className="dm-detail-title">
            {zh ? "每一步，都有据可查。" : "Work you can verify."}
          </SheetTitle>
          <SheetDescription>
            {zh
              ? "来自 Gateway 持久任务记录。"
              : "From the Gateway’s durable task record."}
          </SheetDescription>
        </SheetHeader>
        {detail.isLoading ? (
          <p role="status">
            <LoaderCircle className="dm-spin" size={16} />
            {zh ? "正在读取证据…" : "Loading evidence…"}
          </p>
        ) : detail.isError ? (
          <div role="alert">
            <p>{zh ? "无法读取任务结果" : "Could not load the result"}</p>
            <button
              className="dm-text-button"
              onClick={() => void detail.refetch()}
            >
              {zh ? "重试" : "Retry"}
            </button>
          </div>
        ) : (
          detail.data && (
            <div className="dm-detail-body">
              <div className={`dm-detail-state dm-state-${status}`}>
                {detail.data.status === "completed" ? (
                  <CheckCircle2 size={19} />
                ) : (
                  <Circle size={19} />
                )}
                <strong>
                  {zh ? (statusLabels[status] ?? status) : status}
                </strong>
              </div>
              {detail.data.cancel_requested && (
                <p>
                  {zh
                    ? "存在取消请求。是否已停止，请以当前执行状态为准。"
                    : "Cancellation was requested. The execution state determines whether it has stopped."}
                </p>
              )}
              {detail.data.tracking_degraded && (
                <p role="status">
                  {zh
                    ? "跟踪连接异常，状态可能已过时。"
                    : "Tracking degraded; this state may be stale."}
                </p>
              )}
              {summary && <p className="dm-result-summary">{summary}</p>}
              {verified && (
                <p className="dm-validation-pass">
                  <CheckCircle2 size={16} />
                  {zh ? "独立验证通过" : "Independent validation passed"}
                  <span>exit 0</span>
                </p>
              )}
              {typeof validation?.exit_code === "number" && !verified && (
                <p role="status">
                  {zh ? "验证结果" : "Validation"}: exit {validation.exit_code}
                </p>
              )}
              {testOutput && (
                <>
                  <h3>
                    <FileText size={16} />
                    {zh ? "测试输出" : "Test output"}
                  </h3>
                  <pre tabIndex={0}>
                    {testOutput.slice(0, 12000)}
                    {testOutput.length > 12000
                      ? "\n… output preview truncated"
                      : ""}
                  </pre>
                </>
              )}
              <details className="dm-raw-evidence">
                <summary>{zh ? "查看任务记录" : "View task record"}</summary>
                <dl>
                  <dt>Task ID</dt>
                  <dd>{detail.data.task_id}</dd>
                  <dt>{zh ? "任务类型" : "Task type"}</dt>
                  <dd>{detail.data.task_name}</dd>
                  <dt>{zh ? "更新时间" : "Updated"}</dt>
                  <dd>
                    {new Date(detail.data.updated_at).toLocaleString(locale)}
                  </dd>
                </dl>
                {detail.data.error && <p role="alert">{detail.data.error}</p>}
                <h3>
                  <FileText size={16} />
                  {zh ? "执行结果" : "Execution result"}
                </h3>
                {json ? (
                  <pre tabIndex={0}>
                    {json.slice(0, 16000)}
                    {json.length > 16000 ? "\n… preview truncated" : ""}
                  </pre>
                ) : (
                  <p>
                    {zh
                      ? "还没有可展示的结果。"
                      : "No result is available yet."}
                  </p>
                )}
              </details>
              <Link
                className="dm-button"
                href={`/workspace/chats/${task?.threadId}`}
              >
                {zh ? "打开原始对话" : "Open conversation"}
                <ArrowUpRight size={16} />
              </Link>
            </div>
          )
        )}
      </SheetContent>
    </Sheet>
  );
}
