"use client";
import * as PopoverPrimitive from "@radix-ui/react-popover";
import * as React from "react";

import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { SheetContent as BaseSheetContent } from "@/components/ui/sheet";

import { Button } from "./button";
import { cn } from "./utils";

export {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
export {
  Sheet,
  SheetClose,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
export {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
export {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
};
export const Popover = PopoverPrimitive.Root;
export const PopoverTrigger = PopoverPrimitive.Trigger;
export function PopoverContent(
  props: React.ComponentProps<typeof PopoverPrimitive.Content>,
) {
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Content
        {...props}
        data-slot="dm-popover"
        className="z-50 rounded-ds-md border border-hairline bg-canvas p-4 text-body-sm text-ink shadow-ds-level-3"
      />
    </PopoverPrimitive.Portal>
  );
}
export { ScrollArea } from "@/components/ui/scroll-area";
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  cancelLabel,
  onConfirm,
  busy = false,
  restoreFocus,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  title: string;
  description: string;
  confirmLabel: string;
  cancelLabel: string;
  onConfirm: () => void;
  busy?: boolean;
  restoreFocus?: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        onCloseAutoFocus={(event) => {
          if (restoreFocus) {
            event.preventDefault();
            restoreFocus();
          }
        }}
      >
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={busy}
          >
            {cancelLabel}
          </Button>
          <Button variant="danger" loading={busy} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function SheetContent({
  hideClose = false,
  className,
  ...props
}: React.ComponentProps<typeof BaseSheetContent> & { hideClose?: boolean }) {
  return (
    <BaseSheetContent
      {...props}
      data-hide-close={hideClose || undefined}
      className={cn(hideClose && "[&>button:last-child]:hidden", className)}
    />
  );
}
