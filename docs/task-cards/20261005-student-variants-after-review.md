# E2E-03：真实基准后的三种变化页面验收

2026-10-05；Git根 `D:\jbcode\web ai\jianli`，HEAD b8534ee。上一个人诊断任务已交棒，见student-409-review/report.md。其87k上下文在本里程碑交接，保留学生runner和静态守卫。

继续已有closure-20261005，8001/3001、Mock外发关闭；不得重启/迁移/建库。使用真实UI生成的baseReportId 1c421762-226c-4895-8949-2752c1482b17及现有jobC/已上传两个项目版本。不重跑setup-job或baseline，不运行chain-reply（旧seed基准错误保持留档，另有免费SEED-02任务修未来夹具）。本任务从真实可定位缺口走完整链路，不把旧企业问题标为已回答。

允许修改student-browser-runner.mjs、student自有helpers/静态测试与student证据，不能改产品源码、seed、企业runner、正式清单。独占closure浏览器及合成写入；其他任务只能跑临时SQLite或只读审查。不得撤回现有A/B/A2、SQL修旧报告/任务、调用真实模型/材料、外发、Git提交/推送或P2stash。

先补强现有验收断言：材料变化必须确有引用链接；只岗位变化必须同时有新增/移除要求及同名Python要求分列、正确背景标签；材料与岗位共同变化必须逐项列解释。记录缺证为fail/blocked，不能只打印布尔值却不纳入判定。保存任务ID须在实际UI创建后立即落state，失败后复用任务，不重复创建。

顺序实际运行variant-materials→variant-job→variant-both；前项失败先诊断runner/页面，业务代码问题保存证据交棒Codex。随后viewport390及enterprise-recheck。390截图需要实际滚动到任务/比较标题可见且不被固定header遮挡，DOM存在不等于可见。每条需保存要求、引用、任务、基准/新报告ID、实际材料/目标、逐项变化、刷新重读证据。

可按目标单独批准的本机Chrome方式运行既有安装浏览器；所有分析实际必须Mock，任何外发/配置异常立即停。保存原始命令、脱敏输出和退出码；本地合成账号口令仅读取ignored文件、不进日志截图。最后限一屏交棒，Codex独立抽验和核对旧快照哈希，再本地提交。真实模型语义仍未验证。
