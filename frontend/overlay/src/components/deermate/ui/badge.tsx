"use client";
import { AlertTriangle, type LucideIcon } from "lucide-react";

import { useI18n } from "@/core/i18n/hooks";

import { statusCopy, statusMap, type Variant } from "./status";
import { cn } from "./utils";

const tones: Record<Variant, string> = {
  default: "bg-canvas-soft-2 text-body",
  info: "bg-link-bg-soft text-link-deep",
  success: "bg-link-bg-soft text-link-deep",
  warning: "bg-warning-soft text-warning-deep",
  danger: "bg-error-soft text-error-deep",
  violet: "bg-violet-badge-bg text-violet-badge-text",
};
export function Badge({
  variant = "default",
  icon: Icon,
  children,
}: {
  variant?: Variant;
  icon?: LucideIcon;
  children: React.ReactNode;
}) {
  return (
    <span
      data-slot="dm-badge"
      data-variant={variant}
      data-size="sm"
      className={cn(
        "inline-flex min-h-ds-badge items-center gap-1 rounded-ds-xs px-2 py-1 text-caption",
        tones[variant],
      )}
    >
      {Icon && <Icon className="size-4 shrink-0" aria-hidden="true" />}
      {children}
    </span>
  );
}
export function StatusBadge({
  domain = "execution",
  status,
}: {
  domain?: string;
  status: string;
}) {
  const { locale } = useI18n();
  const value = statusMap[domain]?.[status];
  const label = value && statusCopy[value.labelKey as keyof typeof statusCopy];
  return (
    <Badge
      variant={value?.variant ?? "default"}
      icon={value?.icon ?? AlertTriangle}
    >
      {label ? label[locale === "zh-CN" ? 0 : 1] : status}
    </Badge>
  );
}
