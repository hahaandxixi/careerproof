"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";
import { useAuth } from "./AuthProvider";
import FlowSteps from "./FlowSteps";
import { flowStepsForLocation, studentFlowLocation } from "@/lib/flow-steps";

export default function StudentFlowGuide() {
  const pathname = usePathname();
  const { user } = useAuth();
  const currentKey = studentFlowLocation(pathname, user?.role);
  const container = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const nav = container.current?.querySelector("nav");
    const current = nav?.querySelector<HTMLElement>('[aria-current="step"]');
    if (nav && current) {
      // Scroll only the guide, never move the document or keyboard focus.
      nav.scrollLeft = Math.max(0, current.offsetLeft - nav.offsetLeft - (nav.clientWidth - current.offsetWidth) / 2);
    }
  }, [pathname, currentKey]);
  // Saved reports are reading surfaces; their own back, upload and sharing links remain available.
  return currentKey && pathname!=="/portfolio" && !/^\/reports\/[^/]+$/.test(pathname) ? <div ref={container}><FlowSteps key={pathname} steps={flowStepsForLocation(pathname)} currentKey={currentKey} /></div> : null;
}
