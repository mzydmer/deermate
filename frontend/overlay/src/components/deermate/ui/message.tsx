"use client";
import { SafeStreamdown } from "@/core/streamdown/components";

import { DeerMark } from "../brand";

import { ScrollArea } from "./overlays";
export function AssistantAvatar() {
  return (
    <span
      data-slot="dm-assistant-avatar"
      data-size="sm"
      data-variant="default"
      role="img"
      aria-label="DeerMate"
      className="flex size-8 shrink-0 items-center justify-center rounded-ds-md bg-primary text-on-primary [&_svg]:size-5"
    >
      <DeerMark />
    </span>
  );
}
export function MessageBody({
  value,
  label = "Assistant message",
}: {
  value: string;
  label?: string;
}) {
  return (
    <ScrollArea
      tabIndex={0}
      role="region"
      aria-label={label}
      data-slot="dm-message-body"
      className="min-w-0 [&_[data-slot=scroll-area-viewport]]:max-h-ds-output"
      onKeyDown={(event) => {
        if (event.target !== event.currentTarget) return;
        const viewport = event.currentTarget.querySelector<HTMLElement>(
          '[data-slot="scroll-area-viewport"]',
        );
        if (!viewport) return;
        const line = Number.parseFloat(getComputedStyle(viewport).lineHeight);
        const step = {
          ArrowDown: line,
          ArrowUp: -line,
          PageDown: viewport.clientHeight,
          PageUp: -viewport.clientHeight,
          Home: -viewport.scrollHeight,
          End: viewport.scrollHeight,
        }[event.key];
        if (step !== undefined) {
          event.preventDefault();
          viewport.scrollTop += step;
        }
      }}
    >
      <div className="text-body-sm text-ink [&_p]:my-2 [&_code]:font-mono [&_pre]:overflow-x-auto [&_pre]:text-code [&_table]:w-full [&_table]:border-collapse [&_td]:border-b [&_td]:border-hairline [&_td]:p-2 [&_th]:text-left">
        <SafeStreamdown>{value}</SafeStreamdown>
      </div>
    </ScrollArea>
  );
}
