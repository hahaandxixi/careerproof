"use client";

// 根级错误边界：layout 本身抛错时接管整页。此处不依赖 globals.css，用内联样式保证可渲染。
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="zh-CN">
      <body style={{ margin: 0, fontFamily: "system-ui, sans-serif", background: "#f8fafc", color: "#0f172a" }}>
        <main style={{ maxWidth: "36rem", margin: "0 auto", padding: "4rem 1rem" }}>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700, margin: "0 0 1rem" }}>应用出现异常</h1>
          <p style={{ fontSize: "0.875rem", lineHeight: 1.6, color: "#475569", margin: "0 0 1.5rem" }}>
            页面框架发生了未处理的错误，需要重新加载后继续。
            {error.digest ? `（错误标识：${error.digest}）` : null}
          </p>
          <button
            type="button"
            onClick={reset}
            style={{
              padding: "0.625rem 1rem",
              borderRadius: "0.5rem",
              border: "none",
              background: "#4f46e5",
              color: "#fff",
              fontSize: "0.875rem",
              fontWeight: 500,
              cursor: "pointer",
            }}
          >
            重试
          </button>
        </main>
      </body>
    </html>
  );
}
