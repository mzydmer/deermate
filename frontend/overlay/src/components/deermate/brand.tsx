"use client";

import Script from "next/script";
import { useEffect, useRef, useState } from "react";

type Animation = {
  destroy: () => void;
  goToAndStop: (frame: number, isFrame: boolean) => void;
  addEventListener: (name: string, callback: () => void) => void;
};
declare global {
  interface Window {
    lottie?: { loadAnimation: (options: Record<string, unknown>) => Animation };
  }
}

export function DeerMark({ className = "" }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 128 128"
      fill="none"
      aria-hidden="true"
    >
      <g
        stroke="currentColor"
        strokeWidth="4"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M46 51 37 37 37 20M37 36 24 29M37 27 46 18M82 51 91 37 91 20M91 36 104 29M91 27 82 18" />
        <path d="M44 54 30 46 35 66 45 70M84 54 98 46 93 66 83 70M45 54Q64 44 83 54L81 84Q77 102 64 107Q51 102 47 84Z" />
      </g>
      <circle cx="55" cy="75" r="3" fill="currentColor" />
      <circle cx="73" cy="75" r="3" fill="currentColor" />
      <path
        d="m60 91 4 4 4-4"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function BrandMotion({ className = "" }: { className?: string }) {
  const host = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);
  const [rendered, setRendered] = useState(false);
  useEffect(() => {
    if (!ready || !host.current || !window.lottie) return;
    const controller = new AbortController();
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let animation: Animation | undefined;
    let disposed = false;
    void fetch("/deermate/secretary.json", { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("Brand asset unavailable");
        return response.json() as Promise<unknown>;
      })
      .then((animationData) => {
        if (disposed || !host.current) return;
        animation = window.lottie?.loadAnimation({
          container: host.current,
          renderer: "svg",
          loop: false,
          autoplay: !motion.matches,
          animationData,
        });
        animation?.addEventListener("DOMLoaded", () => {
          if (disposed) return;
          if (motion.matches) animation?.goToAndStop(89, true);
          setRendered(true);
        });
      })
      .catch(() => {
        /* The static vector mark remains visible. */
      });
    const settle = () => animation?.goToAndStop(89, true);
    motion.addEventListener("change", settle);
    return () => {
      disposed = true;
      controller.abort();
      motion.removeEventListener("change", settle);
      animation?.destroy();
    };
  }, [ready]);
  return (
    <span
      className={`dm-brand-motion ${className}`}
      aria-hidden="true"
      data-rendered={rendered}
    >
      <DeerMark className="dm-brand-fallback" />
      <span ref={host} className="dm-brand-player" />
      <Script
        id="deermate-lottie"
        src="/deermate/vendor/lottie-light-5.13.0.min.js"
        onReady={() => setReady(true)}
      />
    </span>
  );
}
