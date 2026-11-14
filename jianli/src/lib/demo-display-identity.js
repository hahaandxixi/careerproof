// Verified existing fixture identities only. Never infer example status from names.
const identities = [
  { userId: "03766867-2df3-442a-8434-296275ee7545", displayName: "林同学" },
  { userId: "2f182cd4-31c1-49aa-8c38-5bb922476ab8", displayName: "唐同学" },
  { userId: "568df462-33af-4824-9ebd-11a9b2760e0a", displayName: "云栈科技" },
  {
    "userId": "3e1e80a0-c7e0-4203-9aa9-f770b7ba3fe3",
    "displayName": "陈同学"
  },
  {
    "userId": "b5ec33cb-c669-4ae5-8a86-c1a591f5d2de",
    "displayName": "林同学"
  },
  {
    "userId": "a12657c4-48d1-436c-96c9-857243294838",
    "displayName": "周同学"
  },
  {
    "userId": "b0bfd306-2277-4b1c-91d7-07920ab52e0e",
    "displayName": "赵同学"
  }
];

// Display-only aliases for verified technical fixtures. Stored titles, employers,
// report text and diagnostic records stay untouched; example disclosure remains.
const jobAliases = new Map([
  ["1233f1e2-169f-4ea5-a5a0-542fa940e897", {
    title: "材料核查实习生", companyName: "云栈科技", description: undefined,
    boundaryFixture: true,
  }],
  ["72e49e95-4f27-4412-ac94-f1675a5f8970", {
    title: "Django 后端开发实习生", companyName: "云栈科技", description: undefined,
  }],
  ["6c8ad563-ebf8-427c-b4a3-82905f37dbd0", {
    title: "数据工程实习生", companyName: "云栈科技", description: undefined,
  }],
  ["f05872f3-1b5f-4bb3-bfcd-9629d170b471", {
    title: "数据处理实习生", companyName: "云栈科技", description: undefined,
  }],
]);

const resumeAliasesWithoutOriginalFilename = new Map([
  ["d18b3087-99dc-4657-9a0d-7d26dc9d1a84", "数据工程方向简历"],
  ["1495ceaf-3251-4ab3-b84e-71b312f82009", "数据工程方向简历"],
  ["b827831f-f31a-4f71-b1c0-ee9e6459a58e", "Python 技能说明"],
  ["e6a6d7b2-8e26-48c0-a989-d9af8dda26db", "林同学的简历"],
]);

const materialAliases = new Map([
  ...resumeAliasesWithoutOriginalFilename,
  ["32593aad-3fbd-47fb-9397-70b5e6f32b95", "数据清洗工具"],
  ["c90a4283-f9ab-4247-8fdc-16ef6e7ae56a", "数据清洗工具"],
  ["4e22b722-44c7-4c19-8eb6-f22b5e8a2f8a", "数据清洗工具"],
  ["34c164be-b013-49ea-a6c1-f6bfbd3e2564", "文本清洗练习"],
  ["58c280fc-c6b1-48c5-8e5d-fed933ad1670", "文本清洗练习"],
  ["398da206-77d7-4ac8-b342-ded4c6d60a67", "数据清洗脚本"],
  ["d3caa012-3ea5-4c49-9dc3-a4d9ebe17fe8", "数据清洗脚本"],
  ["374469a7-f893-4f4c-9960-198fc65cf43e", "Python 技能说明"],
  ["10149ddd-d310-4c22-bf28-a499715c6d4d", "数据工程方向简历"],
  ["4df0cd38-f8d1-45d5-91b5-6f97958eb1dc", "数据工程方向简历"],
  ["80fc3405-f09e-4a01-95e7-940a02827104", "个人简历初稿"],
  ["eec74199-e26a-48a2-8a9a-058d27ad3a88", "个人简历初稿"],
  ["cc6e7c3d-63f5-4109-b581-9b3ae9a7224d", "林同学的简历"],
  ["7a17865f-1a64-41cd-8f31-984f060f32b9", "数据工程方向简历"],
  ["d5e9073d-3df2-44ee-832e-70ced6e69487", "数据工程方向简历"],
  ["cf78e715-485b-4b2a-94fa-bcb4256ac4dd", "唐同学的简历"],
  ["cecf2ec3-df56-4015-8ef7-1118c3910d96", "唐同学的简历"],
]);

export function demoJobAlias(id) {
  return jobAliases.get(id);
}

export function experienceJobCopy(job) {
  if (!job.isDemo || job.companyName !== "职证场景实验室（虚构）") return job;
  return {
    ...job,
    companyName: "职证场景实验室",
    description: job.description.replace(/(?:此为原创体验岗位，不是真实招聘。|合成示例岗位，不是真实招聘。|此为职证体验岗位。)$/, ""),
  };
}

/** Explicit historical boundary fixture; never used as a default/demo job. */
export function boundaryFixtureJob(id) {
  return jobAliases.get(id)?.boundaryFixture === true;
}

export function displayJobTitle(title, id) {
  return jobAliases.get(id)?.title ?? title;
}

export function displayMaterialTitle(title, id) {
  return materialAliases.get(id) ?? title;
}

/** Suppress fixture filenames only for these verified historical versions. */
export function hideOriginalResumeFilename(versionId) {
  return resumeAliasesWithoutOriginalFilename.has(versionId);
}

export function displayIdentity(originalName, identityId) {
  const known = identityId && identities.find(item => item.userId === identityId);
  return { name: known ? known.displayName : originalName, originalName, isExample: Boolean(known) };
}

export function identityLabel(originalName, identityId) {
  const value = displayIdentity(originalName, identityId);
  return value.name;
}
