const SCENARIOS: Record<string, string> = {
  "Python 后端开发实习生": "event-api",
  "React 前端开发实习生": "event-console",
  "接口测试开发实习生": "booking-quality",
};

export default function ScenarioMaterials({ title, companyName, isDemo }: {
  title: string; companyName: string; isDemo?: boolean;
}) {
  const key = isDemo && companyName === "职证场景实验室（虚构）" ? SCENARIOS[title] : undefined;
  if (!key) return null;
  return <section className="panel" aria-label="本场景体验材料">
    <h2 className="text-lg font-semibold">用这套材料体验匹配</h2>
    <p className="mt-2 text-sm leading-6 text-slate-600">虚构简历与原创项目包配套使用，包含刻意保留的缺口。下载后到个人材料中上传，再在本页选择对应版本；不会自动写入你的账号或生成投递。</p>
    <div className="mt-3 flex flex-wrap gap-3">
      <a className="btn-secondary break-words" download href={`/demo-assets/scenarios/${key}-resume.txt`}>下载虚构简历（TXT）</a>
      <a className="btn-secondary break-words" download href={`/demo-assets/scenarios/${key}-project.zip`}>下载项目材料（ZIP）</a>
      <a className="inline-flex min-h-[44px] items-center text-sm text-indigo-700 underline" href="/portfolio">去个人材料上传 →</a>
    </div>
  </section>;
}
