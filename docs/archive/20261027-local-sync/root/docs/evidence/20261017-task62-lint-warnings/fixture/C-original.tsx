"use client";
import { useEffect, useRef } from "react";
export function C() {
  const generation = useRef(0);
  useEffect(() => {
    const ticket = ++generation.current;
    void Promise.resolve().then(() => { if (ticket === generation.current) { /* noop */ } });
    return () => { ++generation.current; };
  }, []);
  return null;
}
