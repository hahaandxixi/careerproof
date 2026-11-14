"use client";
import { useEffect, useState } from "react";
import { skillRecordMeasure, type PanoramaSkill } from "@/lib/skill-panorama";
import styles from "./SkillPanorama.module.css";

export default function SkillOverviewRadar({ skills, selected, onSelect, opensDialog }: {
  skills: PanoramaSkill[]; selected: string | null; onSelect(key: string, trigger?: Element): void; opensDialog?: boolean;
}) {
  const [page, setPage] = useState(0);
  const pages = Math.ceil(skills.length / 8);
  const currentPage = Math.min(page, Math.max(0, pages - 1));
  useEffect(() => {
    const index = skills.findIndex(skill => skill.key === selected);
    if (index >= 0) setPage(Math.floor(index / 8));
  }, [selected, skills]);
  const slice = skills.slice(currentPage * 8, currentPage * 8 + 8);
  const visible = slice.length >= 3 ? slice : [];
  const point = (index: number, ratio: number) => {
    const angle = -Math.PI / 2 + index * 2 * Math.PI / visible.length;
    return { x: 250 + Math.cos(angle) * 112 * ratio, y: 225 + Math.sin(angle) * 112 * ratio };
  };
  const measures = visible.map(skillRecordMeasure);
  const area = visible.length > 0 && measures.every(measure => measure.ratio !== null)
    ? measures.map((measure, index) => {
      const { x, y } = point(index, measure.ratio!);
      return `${x},${y}`;
    }).join(" ")
    : "";
  return <section className={styles.radar} aria-label="技能记录概览">
    <div className={styles.radarHeading}><h2>技能记录概览</h2>
      {pages > 1 && <div className={styles.radarPages}><button type="button" className="btn-secondary btn-compact" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>上一组</button><span>{currentPage + 1} / {pages} 组</span><button type="button" className="btn-secondary btn-compact" disabled={currentPage + 1 >= pages} onClick={() => setPage(currentPage + 1)}>下一组</button></div>}
    </div>
    <p className={styles.radarHelp}>已加载记录中，有证据支持的占比</p>
    <details className={styles.radarHelp}><summary>统计范围</summary><p>已加载的每份报告按岗位要求计数，同一报告的同一要求只计一次；占比为有证据支持记录数除以该技能的全部已加载记录数，筛选不改变分母。未评估记录和本人复核另行标记。</p></details>
    {visible.length ? <svg className={styles.radarSvg} viewBox={visible.length === 3 ? "0 20 500 345" : "0 0 500 450"} role="group" aria-label="已加载记录中有证据支持的占比，选择技能查看来源">
      {[25, 50, 75, 100].map(value => <g key={value}><circle cx="250" cy="225" r={112 * value / 100} fill="none" stroke="#b4c6bd" strokeWidth="1"/><text x="254" y={225 - 112 * value / 100 - 3} className={styles.radarTick}>{value}%</text></g>)}
      {visible.map((skill, index) => { const end=point(index,1); return <line key={skill.key} x1="250" y1="225" x2={end.x} y2={end.y} stroke="#cbd7d0" />; })}
      {area && <polygon points={area} fill="#1d6c5a" fillOpacity={0.18} aria-hidden="true" />}
      {visible.map((skill, index) => { const next=(index+1)%visible.length, a=measures[index].ratio, b=measures[next].ratio; if (a === null || b === null) return null; const x=point(index,a), y=point(next,b); return <line key={skill.key} x1={x.x} y1={x.y} x2={y.x} y2={y.y} stroke="#1d6c5a" strokeWidth="2.5"/>; })}
      {visible.map((skill, index) => {
        const m=measures[index], mark=m.ratio === null ? null : point(index,m.ratio), raw=point(index,1.58);
        const label={x:Math.min(434,Math.max(66,raw.x)),y:Math.min(414,Math.max(31,raw.y))};
        const active=skill.key===selected, characters=Array.from(skill.name), labelName=characters.length > 8 ? `${characters.slice(0,7).join("")}…` : skill.name;
        return <g key={skill.key}>
          {mark && <circle cx={mark.x} cy={mark.y} r={active?6:4.5} fill="#1d6c5a" stroke="#fff" strokeWidth="2"/>}
          <g role="button" tabIndex={0} aria-haspopup={opensDialog ? "dialog" : undefined} aria-pressed={active} aria-label={`${skill.name}，${m.ratio === null ? "无可评估记录" : `有证据支持 ${m.supported}/${m.total} 条`}，未评估 ${m.unassessed} 条，需复核 ${m.review} 条，查看记录`} onClick={event => onSelect(skill.key, event?.currentTarget)} onKeyDown={event => { if(event.key==="Enter" || event.key===" "){event.preventDefault();onSelect(skill.key, event.currentTarget);} }} className={styles.radarAxis}>
            <title>{`${skill.name}：有证据支持 ${m.supported}/${m.total} 条，未评估 ${m.unassessed} 条，需复核 ${m.review} 条`}</title><rect x={label.x-64} y={label.y-23} width="128" height="47" rx="6" fill={active?"#e3f0e9":"#fffefa"} stroke={active?"#1d6c5a":"#d7ded7"} strokeWidth={active?2:1}/>
            <text x={label.x} y={label.y-4} textAnchor="middle" className={styles.radarLabel}>{labelName}</text>
            <text x={label.x} y={label.y+13} textAnchor="middle" className={styles.radarValue}>{m.ratio===null ? "未评估" : `${Math.round(m.ratio*100)}% · ${m.supported}/${m.total}`}{m.unassessed ? " · 未评估" : ""}</text>
            {m.review > 0 && <text x={label.x+55} y={label.y-9} textAnchor="middle" className={styles.radarReview}>!</text>}
          </g>
        </g>;
      })}
    </svg> : <p className={styles.radarHelp}>本组少于 3 个技能，请从左侧列表查看。</p>}
  </section>;
}
