# 2026-11-07 报告页导航与阅读外壳收口

## 改前（真实旧构建 `T_riSJXIBcIFENPt5a1iH`）

同一份报告 `b8a8f21a-28d4-4c25-a28d-f6b0751d44f3`，目录只切换隐藏面板：

- 材料来源/补充证据/投递授权没有共享报告身份；只有岗位对照面板内有标题。
- 1920×1080 顶部切到材料来源后，标题被滚到视口最上方并被固定顶栏遮挡（titleTop 0，header 65）。
- 1920×1080 深滚动 752 后切补充证据，scrollY 直接回到 0。
- 1280×900 深滚动 958 后切补充证据，scrollY 回到 45。
- 旧截屏目录：
  `output/desktop-integration-20261106/report-nav-before/`

## 实现

- 新增 `ReportPaperHeader`，把岗位名称、候选人、报告时间、分析状态放在四个面板共享的纸面头部，只显示一次。
- `ReportOverview` 只保留匹配统计、版本/分析入口和降级说明，不再重复姓名、岗位和时间。
- `ReportSections` 区分：
  - 目录切换：只更新面板和地址；顶部附近不滚动；深位置回到共享阅读起点。
  - 深层锚点：显示所属面板 → 展开 details → 按实测固定栏偏移定位 → 聚焦目标。
- 固定栏偏移由实际 `.site-header` 高度加 16px 写入 CSS 变量，目录 `sticky top` 和滚动共用，不靠增大魔法数字。
- 移除 `EvidenceAnchorRestore` 在报告页的重复 hash 恢复；Reader/SourcePanel 不再各自 scroll；EvidenceLink 在报告内由 ReportSections 统一负责滚动和焦点。
- 报告纸面最小高度按共享阅读区计算，短面板也保留一致的深滚动起点。
- 保留全部四个面板挂载；未提交的证据意见、A/B 版本选择不因切换清空。

## 改后（最终构建 `bN8RsoY334GeHl3GcrAtl`）

1920×1080 / 1280×900：

- 顶部切换四个目录：scrollY 均为 0，标题可见（titleTop 208）。
- 深滚动后切换四个目录：均回到 scrollY 83，纸面 top 81，标题 top 125，目录 top 81；标题不被固定顶栏遮挡。
- 引用 `#citation-R3-E1`：岗位对照面板可见，来源 article 可见，目标 top 81，焦点落在引用目标。
- 直达 `#report-supplement`：补充证据选中，标题可见。
- 真实 `Page.reload` 后：补充证据选中，标题 top 208 可见。
- 后退：回到补充证据；Tab 聚焦目录链接后 Enter 切换到材料来源可用。
- 证据意见草稿跨四个目录往返保持。
- A/B：报告 `f2a83ff2-fb8a-4753-8935-47dcf93a0ef2`（同岗位 5 份报告）选择 A `285eb729-1e30-4c35-a828-7868bbce5a95`、B `da4bfa50-3a76-438a-8447-b547636b9fd1`，往返四个目录后 A/B 值保持。

最终截屏目录：
`output/desktop-integration-20261106/report-nav-after-final2/`

A/B 与证据草稿：
`output/desktop-integration-20261106/report-nav-ab-probe2/`

真实刷新：
`output/desktop-integration-20261106/report-nav-refresh-probe/`

## 检查

- 前端完整测试：712/712
- TypeScript：通过
- ESLint：0 error（保留既有 `<img>` warning）
- Next production build：通过，最终 BUILD_ID `bN8RsoY334GeHl3GcrAtl`
- 未改历史报告、投递快照、材料版本或数据库；A/B 和证据草稿均为页面本地状态，没有保存。

## 未验

- 物理 Tab 遍历顺序只验证了目录链接 Enter 切换；完整从页首逐项 Tab 到四个面板未做穷举。
- 浏览器原生 200% 缩放未在本批复测。
- 1920 顶部截图和深位截图都来自最终构建；旧构建截图仅用作改前对照。
