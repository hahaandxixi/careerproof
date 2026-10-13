# HARNESS50 首页体验与原版视觉完善 · 证据

- 实际 Git 根：`D:/jbcode/web ai/jianli`（`git rev-parse --show-toplevel` 输出确认，非 D:\jbcode）
- 基线：`main` / `f781a5b`（工作区 `ahead 186`）
- 本轮唯一源码写入：`jianli/src/app/page.tsx`（+67 / -9）
- `jianli/src/components/SkillRadar.tsx` 的修改来自 Codex，本轮未触碰
- 未执行：npm ci / install / typecheck / build / 启动或重启服务 / 提交推送

## 静态自检结果（node structure-check.mjs）

```
目标文件: D:\jbcode\web ai\jianli\jianli\src\app\page.tsx
<Link> 数量: 7
Link 目标: /demo/heatmap /jobs /jobs/manage /portfolio /register
全部站内 href: /demo/heatmap /jobs /jobs/manage /portfolio /register
min-h-[44px] 出现次数: 5
含 use client: false（预期 false，首页应为服务端组件）
使用图片: false（预期 false）
结构检查: 标签配对与括号平衡通过
```

## 路由真实性核对（只读）

| 首页入口 | 实际实现 | 核对方式 |
| --- | --- | --- |
| `/jobs` | 公开岗位列表，无登录门 | 读 `jianli/src/app/jobs/page.tsx`（server component，仅透传 `q`） |
| `/portfolio` | 学生材料页，未登录显示“请先登录 / 登录学生账号后才能查看和上传自己的材料” | 读 `jianli/src/app/portfolio/page.tsx:112-119` |
| `/jobs/manage` | `redirect("/jobs/mine")`；`/jobs/mine` 为 `AccessGate roles={["enterprise","admin"]}` | 读 `jianli/src/app/jobs/manage/page.tsx`、`jobs/mine/page.tsx` |
| `/register` | 注册页，`UserRole = "student" \| "enterprise" \| "admin"` | 读 `jianli/src/app/register/page.tsx`、`lib/api/client.ts:8` |
| `/demo/heatmap` | 纯合成演示：`HeatmapDemo` 仅 import 静态夹具 `lib/heatmap-demo`，无 `useAuth`/`fetch`/`api` 调用 | 读 `components/HeatmapDemo.tsx:4,12` |

## 文案真实性自审

- “无需登录”仅用于 `/demo/heatmap`，其组件确无鉴权与网络调用。
- “当前需要企业账号登录后使用”对应 `/jobs/mine` 的 AccessGate 角色限制，未承诺任何成功认证或审批。
- “3 位虚构候选人对 4 项岗位要求”与 `HeatmapDemo.tsx:12` 的“3 位虚构候选人、4 项要求”一致。
- 合成示例段落明确写出：不创建真实投递、不调用网站模型、不产生真实评分；并说明对本人材料的分析需登录后发起。
- 未新增“AI 已认证/已录用/保证通过”类表述；底部边界说明改为中性白底，仅保留“证据支持≠能力认证”。

## 设计约束核对

- 移动优先：所有 grid 为单列起步（`md:grid-cols-2` / `md:grid-cols-3`），按钮组 `flex-wrap`，390px 下 CTA 为整行宽。
- 44px 触控：5 处 `min-h-[44px]`（hero 两枚、学生两枚、企业两枚、合成示例一枚均为 44px 高）。
- 焦点：沿用 `globals.css` 的 `:focus-visible` 靛蓝描边，未覆盖 outline。
- 语义：单一 `h1`，区块 `h2` + `aria-labelledby`，条目 `h3`，流程用 `ol/li`。
- 视觉：靛蓝（`indigo-50`→白渐变首屏、`indigo-700` 文字）、白卡片、`slate` 浅灰底，无新增依赖、无远端字体/图片、无动画。

## 未验证项（重要）

**页面未在浏览器验证**：本轮未启动/重启开发服务器，未渲染截图，未做 390px 与 200% 缩放实测。
以上结论仅为静态阅读与结构自检，不等于渲染通过。`node --check` 无法解析 JSX（预期失败，失败点在首个标签），因此本目录不声称做过类型检查或构建。
