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
export async function includeApplicationTarget<T extends { id: string; jobId: string }>(
  items: T[], lookup: (id: string) => Promise<T>, id: string | null, jobId?: string,
) {
  if (!id || items.some(item => item.id === id)) return items;
  const target = await lookup(id);
  if (target.id !== id || (jobId && target.jobId !== jobId)) throw new Error("通知对应投递与当前岗位不一致，请返回通知中心。");
  return [...items, target];
}
