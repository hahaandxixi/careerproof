import Link from "next/link";

const CATEGORIES = {
  sexual_solicitation: "疑似色情招揽",
  abuse_threat: "疑似辱骂或威胁",
  recruitment_fraud: "疑似招聘收费或诈骗诱导",
  spam: "疑似垃圾广告",
} as const;
type Category = keyof typeof CATEGORIES;
type Finding = { category: Category; path: string; line: number };

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown> : null;
}

// Persisted task payloads may predate this check. Unknown schemas must not be
// interpreted as an all-clear result or echoed wholesale into the page.
export default function MaterialContentNotice({ report }: { report: unknown }) {
  const data = record(report);
  if (!data || data.version !== "local-content-warnings-v1" || data.warningOnly !== true
    || !Array.isArray(data.findings)) return null;
  const findings: Finding[] = [];
  for (const raw of data.findings.slice(0, 30)) {
    const item = record(raw);
    if (!item || typeof item.category !== "string"
      || !Object.hasOwn(CATEGORIES, item.category) || typeof item.path !== "string"
      || !Number.isSafeInteger(item.line) || (item.line as number) < 1) continue;
    findings.push({
      category: item.category as Category,
      path: item.path.slice(0, 1024),
      line: item.line as number,
    });
  }
  const incomplete = data.truncated === true || data.findings.length > 30;
  if (!findings.length && !incomplete) return null;

  return <section aria-label="本地内容核对提示" className="min-w-0 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-slate-800">
    <h2 className="font-semibold">本地内容核对提示</h2>
    <p className="mt-1">{findings.length ? "部分已解析文本命中本地风险规则，请核对后再分享。" : "本次内容核对未完整覆盖材料，请自行核对后再分享。"}</p>
    <p className="mt-1">这不是违规判定；正常源码、测试字符串或合法引用也可能命中。词表未命中不代表材料安全。</p>
    {incomplete && <p className="mt-2 font-medium">已达到扫描或展示上限，以下位置并非完整清单。</p>}
    {findings.length > 0 && <details className="mt-2">
      <summary className="cursor-pointer font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600">查看命中类别与位置（最多 30 条）</summary>
      <ul className="mt-2 space-y-2">{findings.map((finding, index) => <li key={`${finding.category}-${finding.path}-${finding.line}-${index}`}>
        <span className="font-medium">{CATEGORIES[finding.category]}</span>
        <span className="block break-all">{finding.path} · 第 {finding.line} 行</span>
      </li>)}</ul>
    </details>}
    <p className="mt-3"><Link href="/portfolio" className="font-medium text-indigo-700 underline underline-offset-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600">返回材料，上传修正后的新版本</Link></p>
    <p className="mt-1 text-xs leading-5 text-slate-700">新版本不会自动替换当前材料、已有报告或投递快照。检测仅针对已解析文本，不修改材料原文或评级。</p>
  </section>;
}
