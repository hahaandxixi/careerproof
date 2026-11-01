import type { ApplicationView } from "@/lib/api/client";
import { applicationReplyInfo } from "@/lib/application-display";

export default function ApplicationReply({ application, sent = false }: { application: ApplicationView; sent?: boolean }) {
  if (!application.replyText) return null;
  const reply = applicationReplyInfo(application);
  return <blockquote aria-label={sent ? "已发送回复" : "企业最新回复"} className="rounded-lg bg-indigo-50 p-3 text-sm whitespace-pre-wrap">
    <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
      <span className="font-semibold text-indigo-900">{sent ? "已发送 · " : ""}{reply.kind}</span>
      {reply.at ? <time className="text-sm text-slate-600" dateTime={reply.at}>{new Date(reply.at).toLocaleString("zh-CN")}</time> : <span className="text-sm text-slate-600">回复时间未记录</span>}
    </div>
    {application.replyText}
  </blockquote>;
}
