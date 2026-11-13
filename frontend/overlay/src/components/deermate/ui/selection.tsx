"use client";
import { cn } from "@/lib/utils";
import * as SwitchPrimitive from "@radix-ui/react-switch";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import * as React from "react";
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
        "dm-ui-switch inline-flex h-6 w-10 items-center rounded-ds-full border border-control-border bg-canvas-soft-2 p-1",
        props.className,
      )}
    >
      <SwitchPrimitive.Thumb className="dm-ui-switch-thumb size-4 rounded-ds-full bg-ink" />
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
  Command as Combobox,
  CommandEmpty,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
export { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
