"use client";
import type { LucideIcon } from "lucide-react";
import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  Circle,
  CircleHelp,
  Clock3,
  LoaderCircle,
  Unplug,
  XCircle,
} from "lucide-react";
export type Variant =
  | "default"
  | "info"
  | "success"
  | "warning"
  | "danger"
  | "violet";
type Definition = { variant: Variant; labelKey: string; icon: LucideIcon };
export const statusMap: Record<string, Record<string, Definition>> = {
  continuous: {
    enabled: { variant: "info", labelKey: "enabled", icon: CheckCircle2 },
    disabled: { variant: "default", labelKey: "disabled", icon: Ban },
    ready: {
      variant: "default",
      labelKey: "continuous.ready",
      icon: CircleHelp,
    },
    waiting_budget: {
      variant: "default",
      labelKey: "continuous.waiting_budget",
      icon: CircleHelp,
    },
    waiting_model: {
      variant: "default",
      labelKey: "continuous.waiting_model",
      icon: CircleHelp,
    },
    waiting_assessor: {
      variant: "default",
      labelKey: "continuous.waiting_assessor",
      icon: CircleHelp,
    },
    waiting_policy: {
      variant: "warning",
      labelKey: "continuous.waiting_policy",
      icon: CircleHelp,
    },
    waiting_authorization: {
      variant: "warning",
      labelKey: "continuous.waiting_authorization",
      icon: CircleHelp,
    },
    rejected: {
      variant: "danger",
      labelKey: "continuous.rejected",
      icon: CircleHelp,
    },
    stale: {
      variant: "default",
      labelKey: "continuous.stale",
      icon: CircleHelp,
    },
    queued: {
      variant: "default",
      labelKey: "continuous.queued",
      icon: CircleHelp,
    },
    pending: {
      variant: "default",
      labelKey: "continuous.pending",
      icon: CircleHelp,
    },
    active: {
      variant: "default",
      labelKey: "continuous.active",
      icon: LoaderCircle,
    },
    running: {
      variant: "default",
      labelKey: "continuous.running",
      icon: LoaderCircle,
    },
    prepared: {
      variant: "default",
      labelKey: "continuous.prepared",
      icon: CircleHelp,
    },
    dispatching: {
      variant: "default",
      labelKey: "continuous.dispatching",
      icon: CircleHelp,
    },
    acknowledged: {
      variant: "default",
      labelKey: "continuous.acknowledged",
      icon: CircleHelp,
    },
    uncertain: {
      variant: "warning",
      labelKey: "continuous.uncertain",
      icon: CircleHelp,
    },
    settled: {
      variant: "default",
      labelKey: "continuous.settled",
      icon: CircleHelp,
    },
    paused: {
      variant: "default",
      labelKey: "continuous.paused",
      icon: CircleHelp,
    },
    closed: {
      variant: "default",
      labelKey: "continuous.closed",
      icon: CircleHelp,
    },
    completed: {
      variant: "default",
      labelKey: "continuous.completed",
      icon: CircleHelp,
    },
    verification_required: {
      variant: "warning",
      labelKey: "continuous.verification_required",
      icon: CircleHelp,
    },
    failed: {
      variant: "danger",
      labelKey: "continuous.failed",
      icon: CircleHelp,
    },
    input_required: {
      variant: "default",
      labelKey: "continuous.input_required",
      icon: CircleHelp,
    },
    cancel_requested: {
      variant: "warning",
      labelKey: "continuous.cancel_requested",
      icon: CircleHelp,
    },
    cancelling: {
      variant: "warning",
      labelKey: "continuous.cancelling",
      icon: CircleHelp,
    },
    cancelled: {
      variant: "default",
      labelKey: "continuous.cancelled",
      icon: CircleHelp,
    },
    handoff: {
      variant: "warning",
      labelKey: "continuous.handoff",
      icon: CircleHelp,
    },
  },
  history: {
    not_started: {
      variant: "default",
      labelKey: "historyNotStarted",
      icon: Clock3,
    },
    processing: {
      variant: "info",
      labelKey: "historyProcessing",
      icon: LoaderCircle,
    },
    queued: { variant: "default", labelKey: "historyQueued", icon: Clock3 },
    stop: { variant: "default", labelKey: "historyStopped", icon: Ban },
    undo: { variant: "default", labelKey: "historyStopped", icon: Ban },
    interrupted: {
      variant: "warning",
      labelKey: "historyInterrupted",
      icon: AlertTriangle,
    },
    completed: {
      variant: "default",
      labelKey: "historyCompleted",
      icon: CheckCircle2,
    },
  },
  conversation: {
    recorded: {
      variant: "default",
      labelKey: "conversationRecorded",
      icon: Circle,
    },
  },
  memory: {
    completed: {
      variant: "success",
      labelKey: "memoryUpdated",
      icon: CheckCircle2,
    },
    invalidated: {
      variant: "default",
      labelKey: "memoryInvalidated",
      icon: Ban,
    },
    queued: { variant: "default", labelKey: "queued", icon: Clock3 },
    pending: { variant: "info", labelKey: "memoryWorking", icon: LoaderCircle },
    working: { variant: "info", labelKey: "memoryWorking", icon: LoaderCircle },
    failed: { variant: "danger", labelKey: "memoryFailed", icon: XCircle },
    uncertain: {
      variant: "warning",
      labelKey: "unconfirmed",
      icon: CircleHelp,
    },
    budget_wait: { variant: "warning", labelKey: "budgetWait", icon: Clock3 },
    clarification: {
      variant: "warning",
      labelKey: "clarification",
      icon: CircleHelp,
    },
  },
  execution: {
    partial: { variant: "warning", labelKey: "partial", icon: AlertTriangle },
    partial_failed: {
      variant: "warning",
      labelKey: "partial",
      icon: AlertTriangle,
    },
    submitted: { variant: "default", labelKey: "queued", icon: Clock3 },
    pending: { variant: "default", labelKey: "queued", icon: Clock3 },
    working: { variant: "info", labelKey: "running", icon: LoaderCircle },
    running: { variant: "info", labelKey: "running", icon: LoaderCircle },
    input_required: {
      variant: "warning",
      labelKey: "needsReply",
      icon: CircleHelp,
    },
    completed: { variant: "default", labelKey: "executionEnded", icon: Circle },
    completed_unverified: {
      variant: "default",
      labelKey: "ended",
      icon: Circle,
    },
    failed: { variant: "danger", labelKey: "failed", icon: XCircle },
    cancelled: { variant: "default", labelKey: "cancelled", icon: Ban },
    uncertain: {
      variant: "warning",
      labelKey: "unconfirmed",
      icon: CircleHelp,
    },
  },
  work: {
    partial: { variant: "warning", labelKey: "partial", icon: AlertTriangle },
    ended: { variant: "default", labelKey: "ended", icon: Circle },
  },
  validation: {
    passed: { variant: "success", labelKey: "verified", icon: CheckCircle2 },
    failed: { variant: "danger", labelKey: "validationFailed", icon: XCircle },
    not_checked: {
      variant: "default",
      labelKey: "unchecked",
      icon: CircleHelp,
    },
    unverified: { variant: "default", labelKey: "unverified", icon: Circle },
  },
  connection: {
    expired: { variant: "warning", labelKey: "expired", icon: Clock3 },
    offline: { variant: "warning", labelKey: "offline", icon: Unplug },
    not_checked: {
      variant: "default",
      labelKey: "unchecked",
      icon: CircleHelp,
    },
    reachable: { variant: "info", labelKey: "reachable", icon: CheckCircle2 },
  },
};
export const statusCopy = {
  enabled: ["已启用", "Enabled"],
  disabled: ["已停用", "Disabled"],
  conversationRecorded: ["仅有对话记录", "Conversation recorded"],
  memoryUpdated: ["记忆已更新", "Memory updated"],
  memoryInvalidated: ["更新已停止", "Update stopped"],
  memoryWorking: ["整理中", "Organizing memory"],
  memoryFailed: ["整理失败", "Memory update failed"],
  budgetWait: ["等待额度", "Waiting for budget"],
  clarification: ["需要确认内容", "Clarification needed"],
  historyNotStarted: ["最近上下文 · 尚未整理", "Recent context · not started"],
  historyProcessing: ["正在整理最近上下文", "Organizing recent context"],
  historyQueued: ["最近上下文 · 等待整理", "Recent context · queued"],
  historyStopped: ["历史整理已停止", "History import stopped"],
  historyInterrupted: ["历史整理已中断", "History import interrupted"],
  historyCompleted: ["最近上下文已核对", "Recent context checked"],
  executionEnded: ["执行结束", "Execution ended"],
  "continuous.ready": ["待执行", "Ready"],
  "continuous.waiting_budget": [
    "今日后台额度已用尽",
    "Daily background budget exhausted",
  ],
  "continuous.waiting_model": ["等待模型配置", "Model configuration required"],
  "continuous.waiting_assessor": ["研判排队中", "Assessment queued"],
  "continuous.waiting_policy": [
    "当前规则已暂停派发",
    "Dispatch paused by current policy",
  ],
  "continuous.waiting_authorization": [
    "等待设备连接或有效授权",
    "Device connection or current grant required",
  ],
  "continuous.rejected": ["接纳前检查未通过", "Rejected before execution"],
  "continuous.stale": ["依据已变化，未派发", "Source changed; not dispatched"],
  "continuous.queued": ["等待接纳", "Queued"],
  "continuous.pending": ["待处理", "Pending"],
  "continuous.active": ["进行中", "Active"],
  "continuous.running": ["执行中", "Running"],
  "continuous.prepared": ["等待投递", "Prepared"],
  "continuous.dispatching": ["正在核对接纳", "Confirming admission"],
  "continuous.acknowledged": ["已接纳", "Acknowledged"],
  "continuous.uncertain": [
    "回执未确认，核对原操作",
    "Receipt unknown; inspect original operation",
  ],
  "continuous.settled": ["已收到回执", "Receipt received"],
  "continuous.paused": ["已暂停派单", "Dispatch paused"],
  "continuous.closed": ["已结束", "Closed"],
  "continuous.completed": ["执行结束", "Execution finished"],
  "continuous.verification_required": [
    "执行结束，尚需验证",
    "Verification required",
  ],
  "continuous.failed": ["执行失败", "Failed"],
  "continuous.input_required": ["等待你的输入", "Input required"],
  "continuous.cancel_requested": [
    "已请求停止，等待确认",
    "Stop requested; awaiting confirmation",
  ],
  "continuous.cancelling": ["等待停止确认", "Awaiting stop confirmation"],
  "continuous.cancelled": ["已确认停止", "Stopped"],
  "continuous.handoff": [
    "范围有变化，待重新安排",
    "Scope changed; routing required",
  ],
  partial: ["部分失败", "Partially failed"],
  queued: ["排队中", "Queued"],
  running: ["处理中", "Running"],
  needsReply: ["等你答复", "Needs reply"],
  ended: ["执行结束 · 未验证", "Ended · unverified"],
  failed: ["执行失败", "Execution failed"],
  cancelled: ["已取消", "Cancelled"],
  unconfirmed: ["结果未确认", "Unconfirmed"],
  verified: ["独立验证通过", "Validation passed"],
  validationFailed: ["验证失败", "Validation failed"],
  unchecked: ["未检查", "Not checked"],
  unverified: ["未验证", "Unverified"],
  expired: ["已过期", "Expired"],
  offline: ["连接中断", "Disconnected"],
  reachable: ["可达", "Reachable"],
} as const;
