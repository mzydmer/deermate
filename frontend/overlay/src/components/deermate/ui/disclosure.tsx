"use client";
import { cn } from "@/lib/utils";
import * as Collapsible from "@radix-ui/react-collapsible";
import { ChevronRight } from "lucide-react";
import * as React from "react";
export function DisclosureTrigger({
  children,
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <Collapsible.Trigger
      {...props}
      data-slot="dm-disclosure-trigger"
      className={cn(
        "dm-ui-disclosure-trigger flex min-h-ds-control-md w-full items-center gap-2 rounded-ds-md text-left text-body-sm font-medium text-ink",
        className,
      )}
    >
      <ChevronRight className="size-4 shrink-0" aria-hidden="true" />
      {children}
    </Collapsible.Trigger>
  );
}
export function Disclosure({
  children,
  open,
  defaultOpen = false,
  onToggle,
  className,
  ...props
}: Omit<React.HTMLAttributes<HTMLDivElement>, "onToggle"> & {
  open?: boolean;
  defaultOpen?: boolean;
  onToggle?: (event: { currentTarget: { open: boolean } }) => void;
}) {
  const parts = React.Children.toArray(children);
  const trigger = parts.find(
    (v) => React.isValidElement(v) && v.type === DisclosureTrigger,
  );
  return (
    <Collapsible.Root
      {...props}
      open={open}
      defaultOpen={defaultOpen}
      onOpenChange={(v) => onToggle?.({ currentTarget: { open: v } })}
      data-slot="dm-disclosure"
      className={className}
    >
      {trigger}
      <Collapsible.Content className="grid gap-3 py-3">
        {parts.filter((v) => v !== trigger)}
      </Collapsible.Content>
    </Collapsible.Root>
  );
}
