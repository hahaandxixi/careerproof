// 根段加载骨架：路由切换时先渲染占位，避免白屏等待数据页面。
export default function Loading() {
  return (
    <div className="space-y-4" role="status" aria-label="正在加载页面">
      <div className="h-8 w-64 animate-pulse rounded-lg bg-slate-200" />
      <div className="panel h-20 animate-pulse" />
      <div className="panel h-20 animate-pulse" />
      <div className="panel h-20 animate-pulse" />
    </div>
  );
}
