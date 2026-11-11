"use client";

import { useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { usePathname, useRouter } from "next/navigation";
import { navigateEvidenceFragment } from "@/lib/evidence-anchor";
import { useAuth } from "./AuthProvider";

type Command = { id: string; label: string; group: string; href: string; aliases: string };
const REPORT_PATH = /^\/reports\/([^/]+)$/;

function commandsFor(pathname: string, role?: string): Command[] {
  const report = pathname.match(REPORT_PATH)?.[1];
  const reportHash = (hash: string) => report ? `/reports/${report}${hash}` : "/reports";
  if (role === "enterprise") return [
    { id: "jobs", label: "发现岗位", group: "岗位", href: "/jobs", aliases: "岗位 找工作 发现" },
    { id: "mine", label: "岗位管理", group: "岗位", href: "/jobs/mine", aliases: "管理 已发布 企业" },
    { id: "new", label: "发布岗位", group: "岗位", href: "/jobs/new", aliases: "新建 招聘 发布" },
    { id: "applications", label: "岗位投递", group: "投递", href: "/jobs/mine", aliases: "候选人 投递 筛选" },
  ];
  if (role === "admin") return [
    { id: "jobs", label: "发现岗位", group: "岗位", href: "/jobs", aliases: "岗位 找工作 发现" },
    { id: "manage", label: "岗位管理", group: "岗位", href: "/jobs/mine", aliases: "管理 已发布" },
    { id: "reports", label: "匹配报告", group: "报告", href: "/reports", aliases: "报告 证据 匹配" },
  ];
  return [
    { id: "portfolio", label: "我的材料", group: "材料", href: "/portfolio", aliases: "材料库 简历 项目 上传 补证" },
    { id: "jobs", label: "发现岗位", group: "岗位", href: "/jobs", aliases: "岗位 找工作 发现 推荐" },
    { id: "reports", label: "我的报告", group: "报告", href: "/reports", aliases: "报告 匹配 证据" },
    { id: "applications", label: "我的投递", group: "投递", href: "/applications", aliases: "投递 分享 授权" },
    { id: "skills", label: "技能全景", group: "报告", href: "/skills", aliases: "技能 技能全景 技能版图 材料支持" },
    ...(role === "student" ? [{ id: "interview", label: "模拟面试", group: "报告", href: "/interview", aliases: "模拟面试 面试 面试练习" }] : []),
    { id: "demo", label: "案例库", group: "材料", href: "/demo", aliases: "案例 案例库 示例项目 示例 下载 导入" },
    { id: "supplement", label: report ? "本报告 · 按需补证" : "按需补证（先选报告）", group: "报告", href: reportHash("#report-supplement"), aliases: "补证 缺口 上传新版 材料" },
    { id: "sharing", label: report ? "本报告 · 投递授权" : "投递授权（先选报告）", group: "投递", href: reportHash("#report-sharing"), aliases: "投递 授权 企业 分享" },
    { id: "sources", label: report ? "本报告 · 材料来源" : "报告材料来源", group: "报告", href: reportHash("#report-materials"), aliases: "来源 文件 版本 引用" },
    { id: "evidence", label: report ? "本报告 · 岗位对照" : "报告岗位对照", group: "报告", href: reportHash("#report-matching"), aliases: "证据 判断 引用 要求" },
    { id: "compare", label: report ? "本报告 · 版本对比 A/B" : "报告版本对比 A/B", group: "报告", href: reportHash("#report-comparison"), aliases: "对比 版本 A B 报告" },
  ];
}

export default function QuickCommandPalette() {
  const { user } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const dialog = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const results = useRef<HTMLDivElement>(null);
  const restoreFocus = useRef<HTMLElement | null>(null);
  const commands = useMemo(() => commandsFor(pathname, user?.role), [pathname, user?.role]);
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter(command => `${command.label} ${command.group} ${command.aliases}`.toLowerCase().includes(q));
  }, [commands, query]);

  useEffect(() => {
    const openDialog = () => {
      restoreFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      setQuery(""); setActive(0); setOpen(true);
    };
    const key = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault(); openDialog();
      }
    };
    const trigger = () => openDialog();
    window.addEventListener("keydown", key);
    window.addEventListener("careerproof:open-quick-command", trigger);
    return () => { window.removeEventListener("keydown", key); window.removeEventListener("careerproof:open-quick-command", trigger); };
  }, []);
  useEffect(() => {
    if (!open) return;
    const frame = requestAnimationFrame(() => input.current?.focus());
    return () => cancelAnimationFrame(frame);
  }, [open]);
  useEffect(() => { setActive(0); }, [query]);
  useEffect(() => {
    const list = results.current;
    const option = list?.querySelector('[aria-selected="true"]');
    if (!list || !option) return;
    const viewport = list.getBoundingClientRect();
    const item = option.getBoundingClientRect();
    const top = viewport.top + list.clientTop;
    const bottom = top + list.clientHeight;
    if (item.top < top) list.scrollTop += item.top - top;
    else if (item.bottom > bottom) list.scrollTop += item.bottom - bottom;
  }, [active, filtered, open]);
  useEffect(() => {
    if (!open) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = previous; };
  }, [open]);

  const close = () => {
    setOpen(false);
    requestAnimationFrame(() => {
      const previous = restoreFocus.current;
      const target = previous && previous !== document.body
        ? previous
        : document.querySelector<HTMLElement>(".quick-command-trigger");
      target?.focus?.();
    });
  };
  const choose = (command: Command | undefined) => {
    if (!command) return;
    const hashIndex = command.href.indexOf("#");
    const samePath = command.href.split("#")[0] === pathname;
    close();
    if (samePath && hashIndex >= 0) navigateEvidenceFragment(command.href.slice(hashIndex));
    else router.push(command.href);
  };
  const dialogKeys = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") { event.preventDefault(); close(); return; }
    if (event.key !== "Tab") return;
    const focusable = [...(dialog.current?.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), a[href]') ?? [])]
      .filter(node => node.getClientRects().length > 0);
    if (!focusable.length) return;
    const first = focusable[0], last = focusable[focusable.length - 1], current = document.activeElement as HTMLElement | null;
    if (event.shiftKey && (current === first || !focusable.includes(current as HTMLElement))) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && (current === last || !focusable.includes(current as HTMLElement))) { event.preventDefault(); first.focus(); }
  };
  return <>
    <button type="button" className="quick-command-trigger" onClick={() => window.dispatchEvent(new Event("careerproof:open-quick-command"))} aria-label="打开快捷跳转，Ctrl K">
      <span aria-hidden="true">⌕</span><span className="quick-command-trigger-label">快捷跳转</span><kbd>Ctrl K</kbd>
    </button>
    {open && <div className="quick-command-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) close(); }}>
      <div ref={dialog} className="quick-command-dialog" role="dialog" aria-modal="true" aria-labelledby="quick-command-title" onKeyDown={dialogKeys}>
        <div className="quick-command-head"><h2 id="quick-command-title">快捷跳转</h2><button type="button" className="quick-command-close" onClick={close} aria-label="关闭快捷跳转">Esc</button></div>
        <input ref={input} className="quick-command-input" value={query} onChange={event => setQuery(event.target.value)} onKeyDown={event => {
          if (event.key === "ArrowDown") { event.preventDefault(); setActive(value => Math.min(Math.max(0, filtered.length - 1), value + 1)); }
          else if (event.key === "ArrowUp") { event.preventDefault(); setActive(value => Math.max(0, value - 1)); }
          else if (event.key === "Enter") { event.preventDefault(); choose(filtered[active]); }
        }} placeholder="输入页面、报告或动作，例如“补证”“来源”“A/B”" aria-label="搜索页面与功能" role="combobox" aria-expanded="true" aria-controls="quick-command-results" aria-activedescendant={filtered[active] ? `quick-command-${filtered[active].id}` : undefined} />
        <div ref={results} id="quick-command-results" className="quick-command-results" role="listbox" aria-label="可跳转页面">
          {filtered.length ? filtered.map((command, index) => <button id={`quick-command-${command.id}`} key={command.id} role="option" aria-selected={index === active} type="button" className={`quick-command-item ${index === active ? "is-active" : ""}`} onMouseEnter={() => setActive(index)} onClick={() => choose(command)}>
            <span className="quick-command-item-main"><strong>{command.label}</strong><span>{command.aliases.split(" ").slice(0, 4).join(" · ")}</span></span><span className="quick-command-group">{command.group}</span>
          </button>) : <div className="quick-command-empty" role="status"><strong>没有匹配的页面或功能。</strong><p>试试“报告”“补证”“投递”或“案例”。</p></div>}
        </div>
        <div className="quick-command-hint"><span>↑↓ 选择</span><span>Enter 跳转</span><span>Esc 关闭并返回原位置</span></div>
      </div>
    </div>}
  </>;
}


