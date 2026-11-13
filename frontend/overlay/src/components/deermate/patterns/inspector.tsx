"use client";
import { Maximize2, PanelRightClose, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { dmCopy } from "../i18n/copy";
import {
  Heading,
  IconButton,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "../ui";
export function Inspector({
  open,
  onClose,
  title,
  description,
  restoreFocus,
  children,
  zh,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  restoreFocus: () => void;
  children: React.ReactNode;
  zh: boolean;
}) {
  const anchor = useRef<HTMLDivElement>(null);
  const floating = useRef<HTMLDivElement>(null);
  const stillOpen = useRef(open);
  stillOpen.current = open;
  const focusHeader = useCallback((node: HTMLDivElement | null) => {
    node?.querySelector("h2")?.focus();
  }, []);
  const [fits, setFits] = useState(false);
  const [overlay, setOverlay] = useState(false);
  useEffect(() => {
    const host = anchor.current?.parentElement;
    if (!host) return;
    const observer = new ResizeObserver(() => setFits(host.clientWidth >= 864));
    observer.observe(host);
    return () => observer.disconnect();
  }, []);
  const docked = fits && !overlay;
  useEffect(() => {
    const host = anchor.current?.parentElement;
    if (!host) return;
    host.toggleAttribute("data-inspector", open && docked);
    return () => host.removeAttribute("data-inspector");
  }, [open, docked]);
  useEffect(() => {
    if (!open || !docked) return;
    const escape = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
        restoreFocus();
      }
    };
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [open, docked, onClose, restoreFocus]);
  const header = (floating = false) => (
    <div className="flex items-center justify-between gap-2">
      {floating ? (
        <SheetTitle className="min-w-0 flex-1 break-words" tabIndex={-1}>
          {title}
        </SheetTitle>
      ) : (
        <Heading className="min-w-0 flex-1 break-words" level={2} tabIndex={-1}>
          {title}
        </Heading>
      )}
      <div className="flex shrink-0">
        <IconButton
          label={dmCopy(zh, "common.expand")}
          icon={<Maximize2 className="size-4" />}
          onClick={() => setOverlay(true)}
        />
        <IconButton
          label={dmCopy(zh, "common.dock")}
          icon={<PanelRightClose className="size-4" />}
          onClick={() => setOverlay(!overlay)}
          disabled={!fits}
        />
        <IconButton
          label={dmCopy(zh, "common.close")}
          icon={<X className="size-4" />}
          onClick={() => {
            onClose();
            restoreFocus();
          }}
        />
      </div>
    </div>
  );
  return (
    <>
      <div ref={anchor} data-slot="dm-inspector-anchor" />
      {docked ? (
        open && (
          <aside
            data-testid="pattern-inspector"
            data-slot="dm-inspector"
            aria-label={title}
            className="dm-pattern-inspector"
          >
            <div ref={focusHeader}>{header()}</div>
            <div
              data-testid="inspector-content"
              className="dm-inspector-content py-4"
            >
              {children}
            </div>
          </aside>
        )
      ) : (
        <Sheet
          open={open}
          onOpenChange={(v) => {
            if (!v) onClose();
          }}
        >
          <SheetContent
            hideClose
            ref={floating}
            onOpenAutoFocus={(e) => {
              e.preventDefault();
              floating.current?.querySelector<HTMLElement>("h2")?.focus();
            }}
            data-expanded={overlay || undefined}
            data-testid="pattern-inspector-sheet"
            className="dm-pattern-inspector-sheet data-[state=open]:duration-(--ds-legacyMotion-slow) data-[state=closed]:duration-(--ds-legacyMotion-medium)"
            onCloseAutoFocus={(e) => {
              e.preventDefault();
              if (!stillOpen.current) restoreFocus();
              else
                anchor.current?.parentElement
                  ?.querySelector<HTMLElement>('[data-slot="dm-inspector"] h2')
                  ?.focus();
            }}
          >
            <SheetHeader className="p-0">
              {header(true)}
              <SheetDescription className="sr-only">
                {description}
              </SheetDescription>
            </SheetHeader>
            <div
              data-testid="inspector-content"
              className="dm-inspector-content"
            >
              {children}
            </div>
          </SheetContent>
        </Sheet>
      )}
    </>
  );
}
