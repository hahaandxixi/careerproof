import Link from "next/link";
import type { EnterpriseReplyContext as ReplyContext } from "@/lib/api/domain";

export default function EnterpriseReplyContext({ context }: { context: ReplyContext }) {
  const reportHref = `/reports/${encodeURIComponent(context.reportId)}`;
  return <section className="rounded-xl border border-indigo-200 bg-indigo-50/50 p-4 text-sm leading-6">
    <h3 className="font-semibold">企业人工回复中针对本项的核验内容</h3>
    <p className="mt-1 text-xs text-slate-600">这是已发送回复的原文，不等于 AI 自动决定；任务和新报告不会改写原投递或替企业确认问题已解决。</p>
    <blockquote className="mt-3 whitespace-pre-wrap break-words">{context.text}</blockquote>
    <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs">
      <Link className="text-indigo-700 underline" href={`/applications#application-${encodeURIComponent(context.applicationId)}`}>返回这条投递回复</Link>
      <Link className="text-indigo-700 underline" href={`${reportHref}#requirement-${encodeURIComponent(context.requirementId)}`}>核对原报告要求</Link>
      {context.citationIds.map(id => <Link key={id} className="text-indigo-700 underline" href={`${reportHref}#citation-${encodeURIComponent(id)}`}>核对原引用 {id}</Link>)}
    </div>
  </section>;
}
