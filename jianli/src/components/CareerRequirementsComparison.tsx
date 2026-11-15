"use client";

import { Fragment, useId, useState } from "react";
import type { JobRecommendation } from "@/lib/api/domain";
import { careerMissingRequirementLabel, careerRequirementRows } from "@/lib/career-plan-display";
import { verdictLabel } from "@/lib/verdict-display.js";

export default function CareerRequirementsComparison({ jobs }: { jobs: JobRecommendation[] }) {
  const [selected, setSelected] = useState<{ row: string; jobId: string } | null>(null);
  const id = useId();
  const rows = careerRequirementRows(jobs);
  if (!rows.length) return <p className="career-comparison-note">这份规划没有可对照的岗位要求明细。</p>;

  const groups = [
    { title: "差异项", rows: rows.filter(row => !row.shared) },
    { title: "共同要求", rows: rows.filter(row => row.shared) },
  ];
  return <div className="career-matrix-scroll" role="region" aria-label="岗位要求对照表" tabIndex={0}>
    <table className="career-matrix" style={{ minWidth: 148 + jobs.length * 164 }}>
      <caption className="sr-only">按技能查看各岗位保存的要求与规则判断</caption>
      <thead><tr><th scope="col">技能</th>{jobs.map(job => <th scope="col" key={job.jobId}>{job.jobTitle}</th>)}</tr></thead>
      {groups.filter(group => group.rows.length).map(group => <tbody key={group.title}>
        <tr className="career-matrix-group"><th scope="rowgroup" colSpan={jobs.length + 1}>{group.title}</th></tr>
        {group.rows.map((row, index) => {
          const active = selected?.row === row.key ? jobs.find(job => job.jobId === selected.jobId) : undefined;
          const activeItems = active && row.requirements.get(active.jobId);
          const detailId = `${id}-${row.shared ? "common" : "different"}-${index}`;
          return <Fragment key={row.key}>
            <tr><th scope="row">{row.label}</th>{jobs.map(job => {
              const items = row.requirements.get(job.jobId);
              if (!items) return <td className="career-matrix-empty" key={job.jobId}>{careerMissingRequirementLabel(job)}</td>;
              const labels = Array.from(new Set(items.map(item => verdictLabel(item.ruleVerdict))));
              const verdict = items.every(item => item.ruleVerdict === items[0].ruleVerdict) ? items[0].ruleVerdict : undefined;
              const open = active?.jobId === job.jobId;
              return <td key={job.jobId}><button type="button" className="career-matrix-cell" data-verdict={verdict} aria-expanded={open}
                aria-controls={open ? detailId : undefined}
                aria-label={`${job.jobTitle} · ${row.label} · ${items.length} 项，${labels.join("、")}`}
                onClick={() => setSelected(open ? null : { row: row.key, jobId: job.jobId })}>
                <span>{labels.join("、")}</span>{items.length > 1 && <small>{items.length} 项要求</small>}
              </button></td>;
            })}</tr>
            {active && activeItems && <tr className="career-matrix-detail"><td colSpan={jobs.length + 1}>
              <section id={detailId} aria-label={`${active.jobTitle} · ${row.label}要求明细`}>
                <h4>{active.jobTitle} · {row.label}</h4>
                <ol>{activeItems.map((item, itemIndex) => <li key={itemIndex}>
                  <p>{item.text}</p>
                  <small>{verdictLabel(item.ruleVerdict)} · 权重 {item.weight} · {item.isRequired ? "必需" : "非必需"}</small>
                </li>)}</ol>
              </section>
            </td></tr>}
          </Fragment>;
        })}
      </tbody>)}
    </table>
  </div>;
}
