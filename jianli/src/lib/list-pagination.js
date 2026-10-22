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
  // 页码越界时（例如末页记录被撤回后仍停留在原页码）不得给出倒置区间「21–5」。
  // 此时本页确实没有记录，区间按 0–0 报；previous/next 仍按真实页码判断，用户能返回上一页。
  const withinPage = value.page <= pages;
  return { pages, previous: value.page > 1, next: value.page < pages,
    start: value.total && withinPage ? (value.page - 1) * value.pageSize + 1 : 0,
    end: value.total && withinPage ? Math.min(value.page * value.pageSize, value.total) : 0 };
}

// 分页读数由同一来源生成，避免「第 2 / 1 页 · 本页记录 21–5」这类自相矛盾的展示。
export function paginationSummary(value) {
  const bounds = pageBounds(value);
  const beyond = value.page > bounds.pages;
  return `共 ${value.total} 条 · 第 ${value.page} / ${bounds.pages} 页 · 本页记录 ${bounds.start}–${bounds.end}`
    + (beyond ? "（当前页已超出范围，请返回上一页）" : "");
}
