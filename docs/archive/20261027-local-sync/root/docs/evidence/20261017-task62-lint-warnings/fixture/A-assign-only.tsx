"use client";
import { useEffect, useRef } from "react";
export function A() {
  const generation = useRef(0);
  const cancelled = useRef(false);
  useEffect(() => {
    cancelled.current = false;
    const ticket = ++generation.current;
    void Promise.resolve().then(() => { if (!cancelled.current && ticket === generation.current) { /* noop */ } });
    return () => { cancelled.current = true; };
  }, []);
  return null;
}
