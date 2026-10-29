import type { MatchReport, ReportComparison, ReportEvidence } from "./api/domain.ts";
import { verdictLabel } from "./verdict-display.js";

export type ComparisonFilter = "changed" | "all" | "evidence" | "status" | "needs" | "unchanged";

// Report-local citation numbers are aliases, not source identities. Keep different
// versions, files, content, ranges and provenance separate even when names match.
export function comparisonSourceKey(source: ReportEvidence) {
  return JSON.stringify([source.projectVersionId || source.sourceId, source.projectFileId,
    source.filePath, source.lineStart, source.lineEnd, source.contentHash,
    source.snippet, source.provenance, source.evidenceType]);
}

export function groupComparisonSources(sources: ReportEvidence[]) {
  const groups = new Map<string, { source: ReportEvidence; citationIds: string[]; sourceIds: string[] }>();
  for (const source of sources) {
    const key = comparisonSourceKey(source);
    const group = groups.get(key) ?? { source, citationIds: [], sourceIds: [] };
    if (source.citationId && !group.citationIds.includes(source.citationId)) group.citationIds.push(source.citationId);
    if (source.sourceId && !group.sourceIds.includes(source.sourceId)) group.sourceIds.push(source.sourceId);
    groups.set(key, group);
  }
  return [...groups.values()];
}

export function comparisonRows(value: ReportComparison, base: MatchReport, current: MatchReport) {
  if (base.id !== value.baseId || current.id !== value.targetId) throw new Error("对比报告身份不一致，请重新读取。");
  const before = new Map(base.items.map(item => [item.requirementId, item]));
  const after = new Map(current.items.map(item => [item.requirementId, item]));
  return value.items.map(item => {
    const old = before.get(item.requirementId), now = after.get(item.requirementId);
    const added = groupComparisonSources(item.addedEvidence);
    const removed = groupComparisonSources(item.removedEvidence);
    const addedKeys = new Set(item.addedEvidence.map(comparisonSourceKey));
    // The server's content-based diff is authoritative; retained sources are the
    // target report's displayed sources that were not marked as newly displayed.
    const retained = groupComparisonSources((now?.evidenceList ?? []).filter(e => !addedKeys.has(comparisonSourceKey(e))));
    const evidenceChanged = item.changes.includes("evidence") || !!(added.length || removed.length);
    const statusChanged = !!old && !!now && old.verdict !== now.verdict;
    const levelChanged = item.baseLevel !== item.targetLevel;
    const needsEvidence = !!now && (["partial", "claimed_only", "gap"].includes(now.verdict)
      || ["rejected", "corrected"].includes(now.confirmationStatus ?? ""));
    const changed = evidenceChanged || statusChanged || levelChanged || item.changes.length > 0 || item.status !== "existing";
    const baseStatus = old ? verdictLabel(old.verdict) : "基准报告无此项";
    const targetStatus = now ? verdictLabel(now.verdict) : "当前报告无此项";
    const summary = item.status !== "existing"
      ? (item.status === "added" ? "当前报告新增该要求，无法直接与原要求判断比较。" : "当前报告不再包含该要求，基准报告仍可查看。")
      : evidenceChanged ? `新增展示 ${added.length} 处、移除展示 ${removed.length} 处引用；${statusChanged ? "判断状态已改变，请核对下方来源。" : "判断状态未改变。"}`
      : statusChanged ? "判断状态已改变，未记录引用集合变化；请核对解释和判定条件。"
      : levelChanged ? "证据等级发生变化，判断状态未改变；请核对判定记录。"
      : changed ? "解释、建议或判定背景有更新，判断状态未改变。"
      : "本项没有检测到变化。";
    return { item, old, now, added, removed, retained, evidenceChanged, statusChanged, levelChanged, needsEvidence, changed, baseStatus, targetStatus, summary };
  });
}

export type ComparisonRow = ReturnType<typeof comparisonRows>[number];
export function comparisonCounts(rows: ComparisonRow[]) {
  return { changed: rows.filter(r => r.changed).length, all: rows.length,
    evidence: rows.filter(r => r.evidenceChanged).length, status: rows.filter(r => r.statusChanged).length,
    needs: rows.filter(r => r.needsEvidence).length, unchanged: rows.filter(r => !r.changed).length };
}
export function filterComparisonRows(rows: ComparisonRow[], filter: ComparisonFilter) {
  return rows.filter(row => filter === "all" || filter === "changed" && row.changed
    || filter === "evidence" && row.evidenceChanged || filter === "status" && row.statusChanged
    || filter === "needs" && row.needsEvidence || filter === "unchanged" && !row.changed)
    .sort((a, b) => Number(b.statusChanged) - Number(a.statusChanged) || Number(b.evidenceChanged) - Number(a.evidenceChanged));
}

export function sourceRecordKind(source: ReportEvidence) {
  const name = source.filePath.split(/[\\/]/).at(-1) ?? "";
  if (/^(test_.*\.py|.*_test\.py|.*\.(test|spec)\.[cm]?[jt]sx?)$/i.test(name)) return "测试代码引用";
  if (/^(?:pytest|junit|test|run)[-_](?:output|results?|report)\.(txt|json|xml|log|out)$/i.test(name)) return "记录文件引用（需核对原文）";
  return "材料引用";
}
