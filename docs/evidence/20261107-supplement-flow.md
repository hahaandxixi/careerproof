# 2026-11-07 按需补证入口与新版材料接续

## 第一批：入口与表达

- 五步结构/key 不变；④ 改为“按需补证”，可选性质明确。
- 报告页顶部④与目录“按需补证”都进入同一 `#report-supplement` 面板。
- 报告区内“查看补证建议（N）”和“前往投递授权”双出口复用现有 section/hash。
- 补证列表只来自实际缺口（`gaps` + `partial`），规则不可评/unsupported 不计入；当前验收报告显示 1 项实际缺口。
- 无报告上下文时④指向 `/reports`，不绑定最近报告。

## 第二批：上传与接续

- 报告补证上传 URL 保留 sourceReport/sourceRequirement/sourceProjectVersion。
- 上传完成后 `ReportUploadReturn` 才会核对当前账号材料状态；处理中/失败不能显示可分析按钮。本次实测在最终构建上轮询到 completed 后才出现“使用新版材料重新分析”。
- 重分析链接：
  - 简历更新：替换简历版本，保留报告中的其他项目版本。
  - 项目更新：只在可确定对应 sourceProjectVersion 或报告只有一个项目时替换；多项目不能确定时不盲选最新。
  - 链接带 `compareTo=原报告`，经 job → task → report 传递为 `compareBase`，A/B 预选原报告/新报告，仍可调整。
- 材料版本选择仍由 JobDetailView 现有 picker 核对；不自动勾选外部 AI 同意，不自动提交分析。
- 旧报告、企业投递快照不变。

## 最终运行构建

`W4iKOYca6JhGY5Vm7nmtR`（3140）

## 实测结果

### 入口

- 1920×1080 / 1280×900：顶部④与目录均进入 `#report-supplement`，选中“按需补证”，标题 top 208 可见；步骤条 →4 按需补证。
- 双出口：查看补证建议（1）→ `#report-supplement`；前往投递授权 → `#report-sharing`，步骤条 →5。
- 补证区只列出 FastAPI 待补；钢琴 unsupported 未列为上传可解决缺口。

### 上传与预选

- 上传“验收补证简历-20261107”文本（`acceptance-resume-20261107.txt`）。
- 解析完成后出现“使用新版材料重新分析”。
- 跳转链接：
  `/jobs/1233f1e2-…?resumeVersionId=d18b3087-…&compareTo=b8a8f21a-…&projectVersionId=4e22b722-…`
- 原岗位显示已选简历“验收补证简历-20261107 · 第 1 版”，原项目仍保留；用户可取消/更换。
- 未点击前无新匹配请求。

### 真实 AI 与 A/B

- 手动勾选外部 AI 同意后才提交。
- 最终授权后生成的新报告 `d34c486b-8a96-442b-aaa0-78cedca3f5e0`；原报告 `b8a8f21a-28d4-4c25-a28d-f6b0751d44f3`。
- 此前未勾选同意的规则轮次和本次授权轮次分开；只有勾选同意的轮次显示 AI 分析完成。
- 报告页显示 **AI 分析完成**。
- A/B 下拉预选：
  - A = `b8a8f21a-…`（原报告）
  - B = `d34c486b-…`（新报告）
- 未修改历史报告或投递快照。

真实结果目录：`output/desktop-integration-20261106/supplement-analyze-ai2/`

## 验证

- 前端完整：715/715
- TypeScript：通过
- Next production build：通过，BUILD_ID `W4iKOYca6JhGY5Vm7nmtR`
- 页面截图来自最终构建：入口/上传/原岗位预选/新报告 A/B

## 未验/限制

- 未在本次再测企业已投递快照的独立页面回看；代码未改投递快照。
- 真实 AI 费用仍按现有 0 记录，不由本批伪造。
- 多项目替换逻辑有单元测试，但真实页面本次只验证了单项目 + 简历更新；没有用第二项目做真实上传。
- 失败/处理中材料只验证了等待期间不出现按钮；未人为制造失败上传。
