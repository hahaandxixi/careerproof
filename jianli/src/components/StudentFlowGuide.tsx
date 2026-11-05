"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useAuth } from "./AuthProvider";
import FlowSteps from "./FlowSteps";
import { flowStepsForLocation, studentFlowLocation } from "@/lib/flow-steps";

export default function StudentFlowGuide() {
  const pathname = usePathname();
  const { user } = useAuth();
  const [context, setContext] = useState({ search: "", hash: "" });
  useEffect(() => {
    const update = () => setContext({ search: window.location.search, hash: window.location.hash });
    update(); window.addEventListener("hashchange", update); window.addEventListener("popstate", update);
    return () => { window.removeEventListener("hashchange", update); window.removeEventListener("popstate", update); };
  }, [pathname]);
  const currentKey = studentFlowLocation(pathname, user?.role, context.search, context.hash);
  const container = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const nav = container.current?.querySelector("nav");
    const current = nav?.querySelector<HTMLElement>('[aria-current="step"]');
    if (nav && current) {
      // Scroll only the guide, never move the document or keyboard focus.
      nav.scrollLeft = Math.max(0, current.offsetLeft - nav.offsetLeft - (nav.clientWidth - current.offsetWidth) / 2);
    }
  }, [pathname, currentKey]);
  return currentKey ? <div ref={container}><FlowSteps key={`${user?.id}:${pathname}`} steps={flowStepsForLocation(pathname, context.search)} currentKey={currentKey} /></div> : null;
}
