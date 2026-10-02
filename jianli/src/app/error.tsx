"use client";

// 路由段错误边界：捕获页面渲染异常，提供重试，避免整页白屏到框架默认错误页。
// 根布局仍会渲染，这里的内容位于布局的 <main> 内，不再嵌套 <main>。
export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <section className="mx-auto max-w-3xl space-y-5" role="alert">
      <h1 className="text-2xl font-bold">页面出现异常</h1>
      <p className="text-sm leading-6 text-slate-600">
        渲染这个页面时发生了未处理的错误。可以重试当前页面，或返回首页继续其他操作。
        {error.digest ? `（错误标识：${error.digest}）` : null}
      </p>
      <div className="flex gap-3">
        <button type="button" className="btn" onClick={reset}>
          重试此页面
        </button>
        <a className="btn-secondary" href="/">
          返回首页
        </a>
      </div>
    </section>
  );
}
