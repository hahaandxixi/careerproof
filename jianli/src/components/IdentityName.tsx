import { displayIdentity } from "@/lib/demo-display-identity.js";

export default function IdentityName({ name, identityId }: { name: string; identityId?: string }) {
  const identity = displayIdentity(name, identityId);
  if (!identity.isExample) return name;
  return <span className="inline-flex max-w-full flex-wrap items-baseline gap-1.5" title={`原记录名称：${name}`}>
    <span>{identity.name}</span><span className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-xs font-normal leading-4 text-slate-600">示例</span>
  </span>;
}
