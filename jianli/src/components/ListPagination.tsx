import type { PaginationInfo } from "@/lib/list-pagination.js";
import { pageBounds } from "@/lib/list-pagination.js";

export default function ListPagination({ value, busy, label, onPage }: {
  value: Pick<PaginationInfo, "total" | "page" | "pageSize">;
  busy: boolean; label: string; onPage(page: number): void;
}) {
  const bounds = pageBounds(value);
  return <nav aria-label={label} className="flex flex-wrap items-center gap-3 text-sm text-slate-600">
    <span>共 {value.total} 条 · 第 {value.page} / {bounds.pages} 页 · 本页记录 {bounds.start}–{bounds.end}</span>
    <button type="button" className="btn-secondary" disabled={busy || !bounds.previous} onClick={() => onPage(value.page - 1)}>上一页</button>
    <button type="button" className="btn-secondary" disabled={busy || !bounds.next} onClick={() => onPage(value.page + 1)}>下一页</button>
  </nav>;
}
