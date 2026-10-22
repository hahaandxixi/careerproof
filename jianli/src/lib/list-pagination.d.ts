import type { Page } from "./api/domain";
export type ListPage<T> = Page<T> & { pageItemCount?: number };
export interface PaginationInfo { total: number; page: number; pageSize: number; pageItemCount: number }
export function unpackList<T>(value: T[] | ListPage<T>): { items: T[]; pagination?: PaginationInfo };
export function pageBounds(value: Pick<PaginationInfo, "total" | "page" | "pageSize">): {
  pages: number; previous: boolean; next: boolean; start: number; end: number;
};
export function paginationSummary(value: Pick<PaginationInfo, "total" | "page" | "pageSize">): string;
