"use client";

import { useEffect, useRef, type ReactNode } from "react";

/** Sticky side content aligned to the measured site header, not a magic offset. */
export default function StickyRail({ children }: { children: ReactNode }) {
  const rail = useRef<HTMLElement>(null);
  useEffect(() => {
    const header = document.querySelector<HTMLElement>(".site-header");
    const sync = () => {
      const offset = Math.ceil((header?.getBoundingClientRect().height ?? 64) + 16);
      rail.current?.style.setProperty("--case-rail-top", `${offset}px`);
    };
    sync();
    window.addEventListener("resize", sync);
    const observer = typeof ResizeObserver === "function" && header ? new ResizeObserver(sync) : null;
    if (observer && header) observer.observe(header);
    return () => { window.removeEventListener("resize", sync); observer?.disconnect(); };
  }, []);
  return <aside ref={rail} className="case-library-rail">{children}</aside>;
}
