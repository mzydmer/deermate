"use client";
import { useEffect, useRef } from "react";

import { useSidebar } from "@/components/ui/sidebar";
/** Presentation changes must not replace the user's desktop preference. */
export function SidebarResponsiveBehavior() {
  const { open, setOpen } = useSidebar();
  const desktop = useRef(open);
  useEffect(() => {
    if (window.matchMedia("(min-width: 960px)").matches) desktop.current = open;
  }, [open]);
  useEffect(() => {
    const mobile = matchMedia("(width < 600px)");
    const tablet = matchMedia("(600px <= width < 960px)");
    const apply = () =>
      setOpen(mobile.matches ? true : tablet.matches ? false : desktop.current);
    apply();
    mobile.addEventListener("change", apply);
    tablet.addEventListener("change", apply);
    return () => {
      mobile.removeEventListener("change", apply);
      tablet.removeEventListener("change", apply);
    };
  }, [setOpen]);
  return null;
}
