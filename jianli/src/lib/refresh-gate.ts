// B-06：返回标签页时 visibilitychange、focus、pageshow 会紧邻触发，
// 逐个放行会造成重复请求、列表反复闪空、已打开报告被重复收起。
// 时间窗内的后续触发被合并吸收；窗口经过后再次触发仍会真实刷新，
// 隐藏导致的清空（clear）必须调用 reset，保证返回时一定重新加载。
export interface RefreshGateOptions {
  windowMs?: number;
  now?: () => number;
}

export function createRefreshGate(run: () => void, options: RefreshGateOptions = {}) {
  const windowMs = options.windowMs ?? 3000;
  const now = options.now ?? Date.now;
  let lastRun = Number.NEGATIVE_INFINITY;
  return {
    trigger(): boolean {
      const at = now();
      if (at - lastRun < windowMs) return false;
      lastRun = at;
      run();
      return true;
    },
    reset() { lastRun = Number.NEGATIVE_INFINITY; },
  };
}
