"use client";

import { useEffect, useRef } from "react";

import { Button } from "@/components/deermate/ui";

export function MotionTabs({
  items,
  value,
  onChange,
}: {
  items: { id: string; label: string }[];
  value: string;
  onChange: (id: string) => void;
}) {
  const bar = useRef<HTMLDivElement>(null);
  const pill = useRef<HTMLSpanElement>(null);
  const initialized = useRef(false);
  useEffect(() => {
    const move = (animate: boolean) => {
      const tab = bar.current?.querySelector<HTMLButtonElement>(
        '[aria-selected="true"]',
      );
      const element = pill.current;
      if (!tab || !element) return;
      const previous = element.style.transition;
      if (!animate) element.style.transition = "none";
      element.style.transform = `translateX(${tab.offsetLeft}px)`;
      element.style.width = `${tab.offsetWidth}px`;
      if (!animate) {
        void element.offsetWidth;
        element.style.transition = previous;
      }
    };
    move(initialized.current);
    initialized.current = true;
    const observer = new ResizeObserver(() => move(false));
    if (bar.current) observer.observe(bar.current);
    return () => observer.disconnect();
  }, [value]);
  return (
    <div
      className="t-tabs relative inline-flex items-center gap-1 rounded-ds-md bg-canvas-soft-2 p-1"
      role="tablist"
      aria-label="Task status"
      ref={bar}
    >
      <span
        className="t-tabs-pill pointer-events-none absolute left-0 top-1 z-0 h-ds-control-sm rounded-ds-md bg-canvas"
        aria-hidden="true"
        ref={pill}
      />
      {items.map((item, index) => (
        <Button
          variant="ghost"
          size="sm"
          type="button"
          key={item.id}
          className="t-tab relative z-10 border-0 bg-transparent text-body"
          role="tab"
          aria-selected={value === item.id}
          aria-controls="dm-task-panel"
          id={`dm-tab-${item.id}`}
          tabIndex={value === item.id ? 0 : -1}
          onClick={() => onChange(item.id)}
          onKeyDown={(event) => {
            if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key))
              return;
            event.preventDefault();
            const next =
              event.key === "Home"
                ? 0
                : event.key === "End"
                  ? items.length - 1
                  : (index +
                      (event.key === "ArrowRight" ? 1 : -1) +
                      items.length) %
                    items.length;
            const target = items[next];
            if (target) {
              onChange(target.id);
              bar.current
                ?.querySelectorAll<HTMLButtonElement>('[role="tab"]')
                [next]?.focus();
            }
          }}
        >
          {item.label}
        </Button>
      ))}
    </div>
  );
}
