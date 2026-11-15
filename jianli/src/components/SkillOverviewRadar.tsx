"use client";
import { useEffect, useState } from "react";
import { skillRecordMeasure, type PanoramaSkill } from "@/lib/skill-panorama";
import styles from "./SkillPanorama.module.css";

export default function SkillOverviewRadar({ skills, selected, onSelect }: {
  skills: PanoramaSkill[]; selected: string | null; onSelect(key: string): void;
}) {
  const [page, setPage] = useState(0);
  const assessed = skills.flatMap(skill => {
    const measure = skillRecordMeasure(skill);
    return measure.ratio === null ? [] : [{ skill, measure, ratio: measure.ratio }];
  });
  const pages = Math.ceil(assessed.length / 8);
  const currentPage = Math.min(page, Math.max(0, pages - 1));
  useEffect(() => {
    const index = skills.filter(skill => skillRecordMeasure(skill).ratio !== null).findIndex(skill => skill.key === selected);
    if (index >= 0) setPage(Math.floor(index / 8));
  }, [selected, skills]);
  const slice = assessed.slice(currentPage * 8, currentPage * 8 + 8);
  const visible = slice.length >= 3 ? slice : [];
  const radialPoint = (angle: number, ratio: number) => ({
    x: 250 + Math.cos(angle) * 112 * ratio,
    y: 225 + Math.sin(angle) * 112 * ratio,
  });
  const point = (index: number, ratio: number) => radialPoint(-Math.PI / 2 + index * 2 * Math.PI / visible.length, ratio);
  const area = visible.map(({ ratio }, index) => {
    const { x, y } = point(index, ratio);
    return `${x},${y}`;
  }).join(" ");
  return <section className={styles.radar} aria-label="技能记录概览">
    <div className={styles.radarHeading}><h2>技能记录概览</h2>
      {pages > 1 && <div className={styles.radarPages}><button type="button" className="btn-secondary btn-compact" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>上一组</button><span>{currentPage + 1} / {pages} 组</span><button type="button" className="btn-secondary btn-compact" disabled={currentPage + 1 >= pages} onClick={() => setPage(currentPage + 1)}>下一组</button></div>}
    </div>
    <details className={styles.radarHelp}><summary>统计范围</summary><p>已加载的每份报告按岗位要求计数，同一报告的同一要求只计一次；占比为有证据支持记录数除以该技能的全部已加载记录数，筛选不改变分母。未评估记录和本人复核另行标记。</p></details>
    {visible.length ? <svg className={styles.radarSvg} viewBox={visible.length === 3 ? "0 20 500 345" : "0 0 500 450"} role="group" aria-label="已加载记录中有证据支持的占比，选择技能">
      {[25, 50, 75, 100].map(value => <circle key={value} cx="250" cy="225" r={112 * value / 100} fill="none" className={styles.radarRing} />)}
      {visible.map(({ skill }, index) => { const end=point(index,1); return <line key={skill.key} x1="250" y1="225" x2={end.x} y2={end.y} stroke="var(--radar-axis)" />; })}
      <polygon points={area} fill="var(--radar-data)" fillOpacity={0.16} stroke="var(--radar-data)" strokeWidth="2.5" aria-hidden="true" />
      {[25, 50, 75, 100].map(value => {
        const tick = radialPoint(-Math.PI / 2 + Math.PI / visible.length, value / 100);
        return <text key={value} x={tick.x} y={tick.y + 4} textAnchor="middle" className={styles.radarTick} aria-hidden="true">{value}%</text>;
      })}
      {visible.map(({ skill, measure: m, ratio }, index) => {
        const mark=point(index,ratio), raw=point(index,1.58);
        const label={x:Math.min(434,Math.max(66,raw.x)),y:Math.min(414,Math.max(31,raw.y))};
        const active=skill.key===selected, characters=Array.from(skill.name);
        const labelName = characters.length > 8 && skill.name !== "TypeScript" ? `${characters.slice(0, 7).join("")}…` : skill.name;
        const support = `有证据支持 ${m.supported}/${m.total} 条`;
        return <g key={skill.key}>
          <g role="button" tabIndex={0} aria-pressed={active} aria-label={`${skill.name}，${support}，未评估 ${m.unassessed} 条，需复核 ${m.review} 条，选择技能`} onClick={() => onSelect(skill.key)} onKeyDown={event => { if(event.key==="Enter" || event.key===" "){event.preventDefault();onSelect(skill.key);} }} className={styles.radarAxis}>
            <circle cx={mark.x} cy={mark.y} r={active ? 6 : 4.5} className={ratio === 0 ? styles.radarZeroPoint : styles.radarPoint}/>
            <title>{`${skill.name}：${support}，未评估 ${m.unassessed} 条，需复核 ${m.review} 条`}</title><rect x={label.x-64} y={label.y-23} width="128" height="47" rx="6" className={styles.radarAxisFrame}/>
            <rect x={label.x-68} y={label.y-27} width="136" height="55" rx="9" className={styles.radarAxisFocus} aria-hidden="true"/>
            <text x={label.x} y={label.y-4} textAnchor="middle" className={styles.radarLabel}>{labelName}</text>
            <text x={label.x} y={label.y+13} textAnchor="middle" className={styles.radarValue}>{Math.round(ratio * 100)}% · {m.supported}/{m.total}{m.unassessed > 0 ? " · 含未评估" : ""}</text>
            {m.review > 0 && <text x={label.x+55} y={label.y-9} textAnchor="middle" className={styles.radarReview}>!</text>}
          </g>
        </g>;
      })}
    </svg> : <p className={styles.radarHelp}>本组少于 3 个已评估技能，请从列表查看。</p>}
  </section>;
}
