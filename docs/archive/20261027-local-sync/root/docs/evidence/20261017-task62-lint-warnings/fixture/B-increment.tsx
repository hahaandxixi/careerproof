"use client";
import { useEffect, useRef } from "react";
export function B() {
  const generation = useRef(0);
  useEffect(() => {
    const ticket = ++generation.current;
    void Promise.resolve().then(() => { if (ticket === generation.current) { /* noop */ } });
    return () => { generation.current = generation.current + 1; };
  }, []);
  return null;
}
