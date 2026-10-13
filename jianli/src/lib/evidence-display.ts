// 传智杯48：证据等级与分数尺度的唯一前端展示口径。
// 等级是序数（当前自动判定 1/2/3，名称与后端 app/tools/evidence_levels.py 一致），
// 不是 x/5 比例；分数是材料支持度（evidence-v3 单项可达 0/10/15/30/40/65），
// 65 只是当前规则上限，不得呈现为未达 100 的成绩或能力满分。
export const RULE_SCORE_CAP = 65;
export const RULE_SCORE_CAP_NOTE = "当前规则上限 65，分数仅表示材料支持度，不是能力满分或录用概率。";

const LEVEL_NAMES: Readonly<Record<number, string>> = { 1: "基础线索", 2: "局部操作", 3: "任务实现" };

/** 已知等级显示名称；未知历史等级保留原数字，不伪造 /3、/5 比例。 */
export function evidenceLevelName(level: number): string {
  const name = LEVEL_NAMES[level];
  if (name) return name;
  return `等级 ${level}`;
}
