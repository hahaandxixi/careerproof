// Only server-authorized internal destinations may be opened.
export function notificationHref(href: string) {
  const uuid = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
  return new RegExp(`^(?:/applications|/jobs/${uuid}/applications)#application-${uuid}$`).test(href);
}
export function notificationsChanged() {
  if (typeof window !== "undefined") window.dispatchEvent(new Event("notifications-changed"));
}

export function revealApplicationAnchor() {
  const id = applicationAnchorId();
  if (id) document.getElementById(`application-${id}`)?.scrollIntoView({ block: "center" });
}

export function applicationAnchorId(hash = typeof location === "undefined" ? "" : location.hash) {
  return /^#application-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(hash)
    ? hash.slice("#application-".length) : null;
}
export function clearApplicationAnchor(id: string) {
  if (typeof location !== "undefined" && applicationAnchorId() === id) {
    history.replaceState(history.state, "", location.pathname + location.search);
  }
}
export async function includeApplicationTarget<T extends { id: string; jobId: string }>(
  items: T[], lookup: (id: string) => Promise<T>, id: string | null, jobId?: string,
  onUnavailable?: () => void,
) {
  if (!id || items.some(item => item.id === id)) return items;
  let target: T;
  try {
    target = await lookup(id);
  } catch (error) {
    if (typeof error !== "object" || error === null || !("status" in error) || error.status !== 404) throw error;
    onUnavailable?.();
    return items;
  }
  if (target.id !== id || (jobId && target.jobId !== jobId)) {
    onUnavailable?.();
    return items;
  }
  return [...items, target];
}

/** Read and open only the authorized application. Each await may outlive the drawer. */
export async function openStudentNotification<T extends { id: string }>(
  id: string,
  api: {
    notificationTarget(id: string): Promise<{ href: string }>;
    applicationDetail(id: string): Promise<T>;
    readNotification(id: string): Promise<unknown>;
  },
  current: () => boolean,
  onRead: () => void,
): Promise<T | undefined> {
  const { href } = await api.notificationTarget(id);
  if (!current()) return;
  const target = href.startsWith("/applications#") && notificationHref(href)
    ? applicationAnchorId(href.slice("/applications".length)) : null;
  if (!target) throw new Error("通知目的地无效，请刷新。");
  const item = await api.applicationDetail(target);
  if (!current()) return;
  if (item.id !== target) throw new Error("通知对应的投递已不可访问，请刷新。");
  await api.readNotification(id);
  onRead();
  return current() ? item : undefined;
}
