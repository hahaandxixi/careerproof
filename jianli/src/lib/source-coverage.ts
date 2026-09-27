import type { ReportEvidence, ReportItem } from "./api/domain";

export interface CoverageDisplay {
  kind: "function" | "file"; filePath: string; start: number; end: number;
  covered: number; total: number; complete: boolean; verified: boolean; citationIds: string[];
}

const positiveInteger = (value: unknown): value is number => Number.isSafeInteger(value) && Number(value) > 0;

function unionCount(ranges: [number, number][]): number {
  let count = 0, end = 0;
  for (const [left, right] of ranges.sort((a, b) => a[0] - b[0])) {
    count += Math.max(0, right - Math.max(end, left - 1));
    end = Math.max(end, right);
  }
  return count;
}

/** Display saved coverage only when its own cited source ranges agree. Never infer legacy bounds. */
export function coverageDisplay(item: Pick<ReportItem, "evidenceList" | "functionSourceCoverage" | "fileSourceCoverage">): CoverageDisplay[] {
  const rows: CoverageDisplay[] = [
    ...(item.functionSourceCoverage ?? []).map(row => ({ kind: "function" as const, filePath: row.file_path,
      start: row.function_line_start, end: row.function_line_end, covered: row.covered_line_count,
      total: row.function_line_end - row.function_line_start + 1, complete: row.fully_covered,
      verified: false, citationIds: row.citation_ids })),
    ...(item.fileSourceCoverage ?? []).map(row => ({ kind: "file" as const, filePath: row.file_path,
      start: 1, end: row.source_line_count, covered: row.covered_line_count, total: row.source_line_count,
      complete: row.fully_covered, verified: false, citationIds: row.citation_ids })),
  ];
  return rows.map(row => {
    const ids = Array.isArray(row.citationIds) ? row.citationIds : [];
    const entries: ReportEvidence[] = [];
    const validIds = ids.length > 0 && new Set(ids).size === ids.length && ids.every(id => {
      const matches = item.evidenceList.filter(e => e.citationId === id);
      if (matches.length !== 1) return false;
      entries.push(matches[0]);
      return true;
    });
    const validBounds = positiveInteger(row.start) && positiveInteger(row.end) && row.start <= row.end
      && positiveInteger(row.covered) && row.covered <= row.total;
    const compatible = validIds && entries.every(e => e.provenance === "portfolio" && e.filePath === row.filePath
      && positiveInteger(e.lineStart) && positiveInteger(e.lineEnd)
      && row.start <= e.lineStart && e.lineStart <= e.lineEnd && e.lineEnd <= row.end
      && e.snippet.split("\n").length === e.lineEnd - e.lineStart + 1
      && (row.kind === "function" ? e.functionLineStart === row.start && e.functionLineEnd === row.end : e.sourceLineCount === row.total));
    const sameSource = entries.length > 0 && entries.every(e => e.contentHash && e.contentHash === entries[0].contentHash
      && e.projectVersionId === entries[0].projectVersionId);
    const verified = validBounds && compatible && sameSource
      && unionCount(entries.map(e => [e.lineStart, e.lineEnd])) === row.covered
      && row.complete === (row.covered === row.total);
    // No links to missing, reference, duplicated or incompatible source records.
    return { ...row, verified, citationIds: verified ? ids : [] };
  });
}
