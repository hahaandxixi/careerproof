// Array support is for internal session callers; HTTP clients always return pages.
export function unpackList(value) {
  if (Array.isArray(value)) return { items: value };
  return { items: value.items, pagination: {
    total: value.total, page: value.page, pageSize: value.pageSize,
    pageItemCount: value.pageItemCount ?? value.items.length,
  } };
}

export function pageBounds(value) {
  const pages = Math.max(1, Math.ceil(value.total / value.pageSize));
  return { pages, previous: value.page > 1, next: value.page < pages,
    start: value.total ? (value.page - 1) * value.pageSize + 1 : 0,
    end: Math.min(value.page * value.pageSize, value.total) };
}
