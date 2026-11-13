"use client";
import { ArrowUp } from "lucide-react";

import { dmCopy } from "../i18n/copy";
import { ComposerSurface, Kbd, SendButton, Text, Textarea } from "../ui";

export function Composer({
  value,
  onChange,
  onSubmit,
  disabled = false,
  busy = false,
  label,
  placeholder,
  sendLabel,
  footer,
  zh = false,
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
  busy?: boolean;
  label: string;
  placeholder?: string;
  sendLabel: string;
  footer?: React.ReactNode;
  zh?: boolean;
}) {
  return (
    <ComposerSurface
      data-slot="dm-composer"
      data-testid="composer"
      className="dm-pattern-composer"
      aria-busy={busy}
      onSubmit={(event) => {
        event.preventDefault();
        if (value.trim() && !busy) onSubmit();
      }}
    >
      <Textarea
        data-testid="message-input"
        aria-label={label}
        placeholder={placeholder}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled || busy}
        maxLength={8000}
        rows={2}
        maxRows={8}
        onKeyDown={(event) => {
          if (
            event.key === "Enter" &&
            !event.shiftKey &&
            !event.nativeEvent.isComposing
          ) {
            event.preventDefault();
            if (value.trim() && !busy) onSubmit();
          }
        }}
      />
      <div className="flex items-center justify-between gap-3">
        <Text size="caption">{footer}</Text>
        <div className="flex items-center gap-3">
          <span
            data-testid="composer-shortcut"
            className="dm-composer-shortcut"
          >
            <Kbd>Shift + Enter</Kbd>
            <Text size="caption">{dmCopy(zh, "common.newline")}</Text>
          </span>
          <SendButton
            data-testid="composer-send"
            className="dm-composer-send"
            label={sendLabel}
            icon={<ArrowUp className="size-4" />}
            type="submit"
            disabled={!value.trim() || busy}
            loading={busy}
          />
        </div>
      </div>
    </ComposerSurface>
  );
}
