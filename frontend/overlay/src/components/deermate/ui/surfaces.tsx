"use client";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { AlertTriangle, Check, Copy, Inbox, LoaderCircle } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { Button, IconButton } from "./button";
export const Toast = toast;
export function Text({
  as: Tag = "span",
  size = "sm",
  tone = "body",
  mono = false,
  className,
  ...props
}: React.HTMLAttributes<HTMLElement> & {
  as?: "span" | "p" | "div" | "small";
  size?: "sm" | "md" | "caption";
  tone?: "ink" | "body" | "muted" | "danger" | "link";
  mono?: boolean;
}) {
  return (
    <Tag
      {...props}
      data-slot="dm-text"
      className={cn(
        size === "caption"
          ? "text-caption"
          : size === "md"
            ? "text-body-md"
            : "text-body-sm",
        tone === "muted"
          ? "text-mute"
          : tone === "danger"
            ? "text-error-deep"
            : tone === "link"
              ? "text-link-deep"
              : tone === "ink"
                ? "text-ink"
                : "text-body",
        mono && "font-mono",
        className,
      )}
    />
  );
}
export function Heading({
  level = 2,
  children,
  className,
  ...props
}: React.HTMLAttributes<HTMLHeadingElement> & { level?: 1 | 2 | 3 }) {
  const Tag = level === 1 ? "h1" : level === 3 ? "h3" : "h2";
  return (
    <Tag
      {...props}
      data-slot="dm-heading"
      className={cn(
        "font-semibold text-ink",
        level === 1
          ? "text-display-md"
          : level === 2
            ? "text-display-sm"
            : "text-body-sm font-medium",
        className,
      )}
    >
      {children}
    </Tag>
  );
}
export function Card({
  as: Tag = "div",
  variant = "default",
  className,
  ...props
}: React.HTMLAttributes<HTMLElement> & {
  as?: "div" | "section" | "li" | "aside";
  variant?: "default" | "compact";
}) {
  return (
    <Tag
      {...props}
      data-slot="dm-card"
      data-variant={variant}
      className={cn(
        "rounded-ds-md border border-hairline bg-canvas",
        variant === "compact" ? "p-4" : "p-6",
        className,
      )}
    />
  );
}
export function Panel(props: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      {...props}
      data-slot="dm-panel"
      className={cn(
        "rounded-ds-lg border border-hairline bg-canvas p-6",
        props.className,
      )}
    />
  );
}
export function SectionHeader({
  icon: Icon,
  title,
  description,
  trailing,
}: {
  icon: React.ElementType;
  title: React.ReactNode;
  description?: React.ReactNode;
  trailing?: React.ReactNode;
}) {
  return (
    <div data-slot="dm-section-header" className="flex items-center gap-3">
      <span className="flex size-ds-icon-block shrink-0 items-center justify-center rounded-ds-md border border-hairline bg-canvas-soft-2">
        <Icon className="size-5" aria-hidden="true" />
      </span>
      <div className="min-w-0 flex-1">
        <h2 className="text-body-sm-strong font-medium text-ink">{title}</h2>
        {description && (
          <p className="mt-1 text-caption text-body">{description}</p>
        )}
      </div>
      {trailing}
    </div>
  );
}
export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <span role="status" aria-label={label} data-slot="dm-spinner">
      <LoaderCircle className="dm-ui-spinner size-4" aria-hidden="true" />
    </span>
  );
}
export function Skeleton({
  label = "Loading",
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & { label?: string }) {
  return (
    <div
      {...props}
      role="status"
      aria-label={label}
      data-slot="dm-skeleton"
      className={cn(
        "dm-ui-skeleton min-h-10 rounded-ds-md bg-canvas-soft-2",
        className,
      )}
    />
  );
}
export function Empty({
  title,
  description,
  action,
  icon: Icon = Inbox,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  icon?: React.ElementType;
}) {
  return (
    <div
      data-slot="dm-empty"
      className="flex flex-col items-center gap-3 p-8 text-center"
    >
      <span className="flex size-ds-empty-icon items-center justify-center rounded-ds-md border border-hairline">
        <Icon className="size-5" aria-hidden="true" />
      </span>
      <Heading level={3}>{title}</Heading>
      {description && <Text>{description}</Text>}
      {action}
    </div>
  );
}
export function ErrorBanner({
  children,
  onRetry,
  retryLabel = "Retry",
}: {
  children: React.ReactNode;
  onRetry?: () => void;
  retryLabel?: string;
}) {
  return (
    <div
      role="alert"
      data-slot="dm-error-banner"
      className="flex flex-wrap items-center gap-3 rounded-ds-md border border-error-soft bg-error-soft p-3 text-body-sm text-error-deep"
    >
      <AlertTriangle className="size-4 shrink-0" aria-hidden="true" />
      <div className="min-w-0 flex-1">{children}</div>
      {onRetry && (
        <Button variant="ghost" size="sm" tone="danger" onClick={onRetry}>
          {retryLabel}
        </Button>
      )}
    </div>
  );
}
export function ErrorState({
  title,
  detail,
  action,
}: {
  title: React.ReactNode;
  detail?: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div role="alert">
      <Empty
        icon={AlertTriangle}
        title={title}
        description={detail}
        action={action}
      />
    </div>
  );
}
export function Kbd(props: React.HTMLAttributes<HTMLElement>) {
  return (
    <kbd
      {...props}
      data-slot="dm-kbd"
      className={cn(
        "rounded-ds-xs border border-hairline px-1 text-caption font-mono text-body",
        props.className,
      )}
    />
  );
}
export function Avatar({ name }: { name: string }) {
  return (
    <span
      data-slot="dm-avatar"
      className="flex size-8 items-center justify-center rounded-ds-full bg-canvas-soft-2 text-body-sm font-medium text-ink"
      aria-label={name}
    >
      {name.slice(0, 1).toUpperCase()}
    </span>
  );
}
export function CopyButton({
  value,
  label = "Copy",
}: {
  value: string;
  label?: string;
}) {
  const [copied, setCopied] = React.useState(false);
  return (
    <IconButton
      label={label}
      size="sm"
      icon={copied ? <Check className="size-4" /> : <Copy className="size-4" />}
      onClick={() =>
        void navigator.clipboard
          .writeText(value)
          .then(() => setCopied(true))
          .catch(() => setCopied(false))
      }
    />
  );
}
export function KeyValue({
  label,
  value,
  mono = false,
  copy = false,
}: {
  label: React.ReactNode;
  value: string;
  mono?: boolean;
  copy?: boolean;
}) {
  return (
    <div data-slot="dm-key-value" className="grid gap-1 py-2">
      <Text size="caption">{label}</Text>
      <div className="flex min-w-0 items-center gap-2">
        <Text tone="ink" mono={mono} className="min-w-0 break-all">
          {value}
        </Text>
        {copy && <CopyButton value={value} />}
      </div>
    </div>
  );
}
export function RelativeTime({
  value,
  timezone = Intl.DateTimeFormat().resolvedOptions().timeZone,
  locale = "en",
}: {
  value: string | number;
  timezone?: string;
  locale?: string;
}) {
  const date = new Date(typeof value === "number" ? value * 1000 : value);
  if (Number.isNaN(date.getTime())) return <Text size="caption">—</Text>;
  const full = new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: timezone,
  }).format(date);
  const seconds = Math.round((date.getTime() - Date.now()) / 1000);
  const unit =
    Math.abs(seconds) < 60
      ? "second"
      : Math.abs(seconds) < 3600
        ? "minute"
        : Math.abs(seconds) < 86400
          ? "hour"
          : "day";
  const divisor = { second: 1, minute: 60, hour: 3600, day: 86400 }[unit];
  const relative = new Intl.RelativeTimeFormat(locale, {
    numeric: "auto",
  }).format(Math.round(seconds / divisor), unit);
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <time
          tabIndex={0}
          dateTime={date.toISOString()}
          className="text-caption tabular-nums text-body"
        >
          {relative}
        </time>
      </TooltipTrigger>
      <TooltipContent>{full}</TooltipContent>
    </Tooltip>
  );
}
export function DataTable<T>({
  columns,
  rows,
  rowKey,
  loading,
  error,
  empty = "No records",
  onRetry,
}: {
  columns: {
    key: string;
    label: React.ReactNode;
    numeric?: boolean;
    render: (row: T) => React.ReactNode;
  }[];
  rows: T[];
  rowKey: (row: T) => string;
  loading?: boolean;
  error?: string;
  empty?: string;
  onRetry?: () => void;
}) {
  if (loading) return <Skeleton />;
  if (error) return <ErrorBanner onRetry={onRetry}>{error}</ErrorBanner>;
  if (!rows.length) return <Empty title={empty} />;
  return (
    <div
      role="region"
      tabIndex={0}
      aria-label="Data"
      data-slot="dm-data-table"
      className="overflow-x-auto rounded-ds-md border border-hairline"
    >
      <table className="w-full border-collapse text-body-sm">
        <thead className="bg-canvas-soft text-body-sm-strong text-body">
          <tr>
            {columns.map((c) => (
              <th
                key={c.key}
                scope="col"
                className={cn(
                  "px-4 py-3 font-medium",
                  c.numeric ? "text-right" : "text-left",
                )}
              >
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={rowKey(row)}
              className="h-ds-table-row border-t border-hairline"
            >
              {columns.map((c) => (
                <td
                  key={c.key}
                  className={cn(
                    "px-4 py-3",
                    c.numeric && "text-right tabular-nums",
                  )}
                >
                  {c.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
