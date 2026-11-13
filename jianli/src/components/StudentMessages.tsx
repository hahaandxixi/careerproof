"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "./AuthProvider";
import { NotificationWorkspace } from "./NotificationCenter";
import type { ApplicationView } from "@/lib/api/client";

export function openStudentMessages(trigger?: HTMLElement | null) {
  window.dispatchEvent(new CustomEvent("careerproof:open-workspace-messages", { detail: trigger }));
}

export default function StudentMessages() {
  const { user } = useAuth();
  return user?.role === "student" ? <Suspense fallback={null}><Drawer key={user.id} /></Suspense> : null;
}

function Drawer() {
  const pathname = usePathname();
  const router = useRouter();
  const intent = useSearchParams().get("messages");
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLElement | null>(null);
  const [active, setActive] = useState(false);
  useEffect(() => {
    function open(event: Event) {
      trigger.current = (event as CustomEvent<HTMLElement | null>).detail ?? null;
      if (dialog.current && !dialog.current.open) dialog.current.showModal();
      setActive(true);
    }
    window.addEventListener("careerproof:open-workspace-messages", open);
    return () => window.removeEventListener("careerproof:open-workspace-messages", open);
  }, []);
  useEffect(() => {
    if (pathname !== "/applications" || intent !== "1") return;
    const url = new URL(location.href);
    url.searchParams.delete("messages");
    history.replaceState(null, "", url);
    openStudentMessages();
  }, [pathname, intent]);
  function close(restore = true) {
    dialog.current?.close();
    setActive(false);
    if (restore) (trigger.current?.getClientRects().length ? trigger.current :
      document.querySelector<HTMLElement>('[aria-controls="job-workspace-messages"], .account-menu > summary'))?.focus({ preventScroll: true });
  }
  function openApplication(item: ApplicationView) {
    close(false);
    if (pathname === "/applications") window.dispatchEvent(new CustomEvent("careerproof:message-application", { detail: item }));
    else router.push(`/applications#application-${encodeURIComponent(item.id)}`);
  }
  return <dialog id="job-workspace-messages" ref={dialog} className="job-workspace-drawer" aria-labelledby="job-workspace-message-title"
    onCancel={event => { event.preventDefault(); close(); }} onClick={event => { if (event.target === event.currentTarget) close(); }}>
    <div className="job-workspace-drawer-inner">
      <header className="job-workspace-drawer-heading">
        <h2 id="job-workspace-message-title" className="section-title">消息</h2>
        <button type="button" className="btn-secondary" onClick={() => close()}>关闭消息</button>
      </header>
      <NotificationWorkspace active={active} onApplication={openApplication} canAct={() => Boolean(dialog.current?.open) && document.visibilityState !== "hidden"} />
    </div>
  </dialog>;
}
