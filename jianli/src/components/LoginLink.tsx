"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { authEntry, authReturnFromLocation } from "@/lib/auth-return";

export default function LoginLink({ children, className, register = false }: {
  children: React.ReactNode; className?: string; register?: boolean;
}) {
  const pathname = usePathname();
  const [location, setLocation] = useState<string | null>(pathname);
  useEffect(() => {
    const update = () => setLocation(authReturnFromLocation(window.location.pathname, window.location.search, window.location.hash));
    update(); window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, [pathname]);
  return <Link className={className} href={authEntry(register ? "/register" : "/login", location)}>{children}</Link>;
}
