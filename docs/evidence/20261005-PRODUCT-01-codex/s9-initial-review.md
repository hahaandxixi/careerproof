# 第三方来源首轮独立复核（尚非完整签收）

2026-10-07。ZCode传智杯15仍是唯一夹具/runner写入者，当前实际Start Plan免费Flash。Codex只读复核，未修改业务源码或数据库。

## 实际证据

- 首轮 `s9-third-party-reference-2026-10-07T02-12-20-268Z` 真实UI上传完成，material-role=reference已选择，页面卡片显示“第三方参考”。其后项目选择器定位失败，属于runner问题；失败记录保留。
- 第二轮 `02-13-41-121Z` 从真实UI生成Mock报告 `9f198a94-a202-4c68-b643-8941a0ce5966`、分析 `a460e012-d9b0-472b-9544-9e18a65233a0`，创建专用任务 `5a23eb45-31fe-464d-aff0-d137c820246a`。原要求87278d08引用R1-E1、材料版本c80cacf1；保存/刷新保留reference来源，预览注明“第三方参考，不计入评级”，模拟clipboard与预览相同。该run整体失败：Part C未选择新任务材料，直接查找“生成新报告”按钮；不能把Part A/B成功写成整个S9通过。
- Codex执行 [s9-provenance-readonly.py](s9-provenance-readonly.py)，REPEATABLE READ/READ ONLY：[有效UTF-8原始结果](s9-provenance-readonly.raw.json)。新材料版本与报告材料快照均为reference、内容hash一致；报告已完成且owner正确；报告对应原要求的一条引用及草稿保存三元身份一致。要求verdict为claimed_only，evidenceLevel为null，标签“仅有第三方参考”：参考实现没有成为本人的数字实践等级。

## 审查修正与限制

Codex初版审计错误假定参考来源只保留等级1，断言失败；实际规则对仅参考来源不授予本人等级，null符合更直接的“不计个人实践评级”要求。修正审计为verdict=claimed_only、level=None及参考标签，未改产品。保留 [初版字段检查](s9-provenance-initial-inspection.raw.json) 与 [初版失败](s9-provenance-initial-inspection.raw.err)；初版中文因终端编码损坏不可用于语义引用，最终重新以PYTHONIOENCODING=utf-8取证。

还发现runner beforeAny位于上传前，上传解析也创建analysis_task；不能把报告阶段总量固定断言为+1，复用已完成报告则新增数应为0。新growth默认materials=[]，须真实选本人简历及reference并明确保存后再分析，确认COMPLETED后才测409/4099及冻结行不变。此审查在第二轮实际失败终态后点击“立即”交付，不中断运行中的浏览器。

专用任务冻结409、当前浏览器A2 userId补证、runner自审交棒、Codex独立页面抽验和最终旧行hash核对仍待完成。此记录不签收PRODUCT-01或完整S9，也不把模拟剪贴板等同真实系统剪贴板。
