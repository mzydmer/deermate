"use client";
import * as SwitchPrimitive from "@radix-ui/react-switch";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import { ChevronsUpDown } from "lucide-react";
import * as React from "react";

import {
  Command,
  CommandEmpty,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";

import { Button } from "./button";
import { Popover, PopoverContent, PopoverTrigger } from "./overlays";
import { cn } from "./utils";
export function Switch(
  props: React.ComponentProps<typeof SwitchPrimitive.Root>,
) {
  return (
    <SwitchPrimitive.Root
      {...props}
      data-slot="dm-switch"
      data-size="md"
      data-variant="default"
      className={cn(
        "dm-ui-switch inline-flex size-ds-touch items-center justify-center",
        props.className,
      )}
    >
      <span className="dm-ui-switch-track flex h-6 w-10 items-center rounded-ds-full border border-control-border bg-canvas-soft-2 p-1">
        <SwitchPrimitive.Thumb className="dm-ui-switch-thumb size-4 rounded-ds-full bg-ink" />
      </span>
    </SwitchPrimitive.Root>
  );
}
export function SegmentedControl({
  items,
  value,
  defaultValue,
  onChange,
  label,
}: {
  items: { value: string; label: string; count?: number }[];
  value?: string;
  defaultValue?: string;
  onChange?: (v: string) => void;
  label: string;
}) {
  return (
    <TabsPrimitive.Root
      className="min-w-0 max-w-full"
      value={value}
      defaultValue={defaultValue ?? items[0]?.value}
      onValueChange={onChange}
    >
      <TabsPrimitive.List
        aria-label={label}
        className="inline-flex max-w-full gap-1 overflow-x-auto rounded-ds-md border border-hairline bg-canvas p-1"
      >
        {items.map((item) => (
          <TabsPrimitive.Trigger
            key={item.value}
            value={item.value}
            data-slot="dm-segment"
            className="dm-ui-segment inline-flex min-h-ds-control-sm items-center gap-2 rounded-ds-md px-3 text-body-sm text-body"
          >
            {item.label}
            {item.count !== undefined && (
              <span className="text-caption tabular-nums">{item.count}</span>
            )}
          </TabsPrimitive.Trigger>
        ))}
      </TabsPrimitive.List>
    </TabsPrimitive.Root>
  );
}
export {
  Command,
  CommandEmpty,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
export { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export function Combobox({
  items,
  value,
  defaultValue,
  onChange,
  label,
  emptyLabel = "No matches",
  disabled = false,
}: {
  items: { value: string; label: string }[];
  value?: string;
  defaultValue?: string;
  onChange?: (value: string) => void;
  label: string;
  emptyLabel?: string;
  disabled?: boolean;
}) {
  const [open, setOpen] = React.useState(false);
  const [local, setLocal] = React.useState(defaultValue ?? "");
  const selected = value ?? local;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          role="combobox"
          aria-label={label}
          aria-expanded={open}
          disabled={disabled}
        >
          {items.find((item) => item.value === selected)?.label ?? label}
          <ChevronsUpDown className="size-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent>
        <Command>
          <CommandInput placeholder={label} aria-label={label} />
          <CommandList>
            <CommandEmpty>{emptyLabel}</CommandEmpty>
            {items.map((item) => (
              <CommandItem
                key={item.value}
                value={item.label}
                onSelect={() => {
                  setLocal(item.value);
                  onChange?.(item.value);
                  setOpen(false);
                }}
              >
                {item.label}
              </CommandItem>
            ))}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
