# 传智杯60：分页后端独立复核

客户端：DeepSeek Harness，Flash／低。实际 Git 根 `D:/jbcode/web ai/jianli`；先核 HEAD/status。Z57已交棒，当前未提交文件不得还原或提交。

只读本轮 `backend/app/api/v1/{applications,evidence_growth,analysis,notifications}.py`、`services/{applications,evidence_growth,analysis}.py`、`schemas/pagination.py`、`tests/test_z57_pagination.py` 及必要夹具。重点：计数/切片同归属、企业管理权限和撤回排除、jobId过滤不跨学生、稳定排序/末页夹取、增长不可读记录有界不补页、通知新旧pageSize冲突422。检查其他内部/HTTP调用者是否仍把新信封当数组，优先可复现兼容缺陷。

唯一可写 `docs/evidence/20261017-HARNESS60-pagination-review/` 和自己的 `.tmp/h60-pagination-*` SQLite临时目录。不改源码/既有测试/配置/前端/正式文档。允许以已安装后端环境运行现有八条Z57聚焦测试一次，显式独占 basetemp/cache，禁止运行其他整套测试。Codex后续PG复验仅在另一个专属CI容器和随机cp_test命名空间进行，不共享本任务SQLite或临时目录。禁止连接任何PG/业务库、启停服务、模型外发、.env/凭据、安装、ACL、P2和Git提交推送。

20分钟或首轮完成即停止；首次失败保留，不自行修复。产出review.md、源码hash、原始测试日志，一屏交棒缺陷等级/file:line/反例/范围和未验证项。属于Z57后的第二次审查，不能把同一八条测试复跑冒充独立PG验收。
