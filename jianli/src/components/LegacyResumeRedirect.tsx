"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function LegacyResumeRedirect({ destination }: { destination: string }) {
  const router = useRouter();
  useEffect(() => { router.replace(destination); }, [destination, router]);
  return null;
}
