// What the student can actually do on a job page, from saved material state only.
// A disabled submit button is not guidance: with no parsed resume the page used to show
// an empty chooser and a grey "生成我的匹配报告" button, so a first-time student could not
// tell what was missing or where to add it.
export type MatchReadiness =
  | { kind: "loading" }
  | { kind: "missing-resume"; message: string; actionLabel: string; actionHref: string }
  | { kind: "ready" };

const MISSING_RESUME_MESSAGE =
  "还没有解析完成的简历版本，所以暂时不能生成报告。先上传简历并等待解析完成，再回到这个岗位。";
const MATERIALS_HREF = "/portfolio";

export function matchReadiness({
  loading,
  completedResumeCount,
}: {
  loading: boolean;
  completedResumeCount: number;
}): MatchReadiness {
  // Loading is not "missing": telling someone to upload while their materials are still
  // loading would send them to create a duplicate.
  if (loading) return { kind: "loading" };
  if (completedResumeCount === 0) {
    return {
      kind: "missing-resume",
      message: MISSING_RESUME_MESSAGE,
      actionLabel: "去个人材料上传简历",
      actionHref: MATERIALS_HREF,
    };
  }
  return { kind: "ready" };
}
