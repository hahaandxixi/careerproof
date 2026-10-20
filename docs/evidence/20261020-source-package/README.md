# 评审源码包与人工任务材料整理（2026-10-20）

独立于Agent源码修复提交。打包文档改显式白名单：介绍、安装/演示、架构能力、评测、AI隐私/真实辅助声明和许可。内部任务清单、协作、接力、旧截图/日志、历史PDF不进ZIP；开发仓库原记录保留。两份Agent测试所需JSON显式必需，避免清文档误删运行夹具。

build仅读取指定提交Git对象；检查保留文档的本地文件/目录链接，失效即拒绝，外部URL与锚点有效性不在本检查范围。运行生成凭据改代码路径及生成说明，不打包口令。历史PDF/MP4明确单独交付，未声称已生成最终稿或填写虚构哈希。

准备了沿用release_smoke既有内容的resume/v1/v2合成材料；首次独立用户步骤与空白记录并入原功能演示，不新建重复治理文档。人尚未执行；现有三例真实AI的人工结果仍0/3，真实输出未改。

工具专项：22 passed（test_source_package），目标Ruff通过；原始命令和结果在tool-tests-final.raw.out/tool-ruff-final.raw.out。此后将从本阶段明确提交实际生成ZIP并解包；精确提交、ZIP SHA、逐文件核验及解包离线测试另记verification.json。包内校验不等于干净安装、PG、页面、独立用户或正式比赛提交通过。

预先存在的使用指南账号打印段落、当前接力的空白变更与JobDetailView/match-readiness源码不并入本阶段提交；工作区保留。没有真实模型外发、数据库写入、服务启停、推送或部署。

## 实际提交包验收

来源提交 `31ff69f015517fed5531f12cef5abbcf0e9e2ac1`，Agent提交 `ca01e52`。实际ZIP在本机 `output/source/CareerProof-source-review-20261020-r6.zip`，SHA256 `4b6d2771ce11fb369c34a9d7be8bad0018ac7b90efd938441588686d6a344200`。837份提交文件逐一哈希一致，20份评审导航本地目标存在；两份Agent必需JSON和人工走查合成材料在包内，内部任务清单/接力/协作、凭据、旧PDF和他人未提交match-readiness均未进入。

解包到专属 `backend/.tmp/source-review-r6-20261020/` 后，从包内backend运行Agent4套与打包1套：73 passed，exit 0。导入来源日志证明执行器/工作流来自解包目录；离线Agent CLI校验包/源码匹配，exit 0、不构造provider。逐文件清单见package-manifest.json；验证范围和未验项见verification.json。复用既有Python依赖，未做干净安装/PG/页面/人工验收；此ZIP不是正式冻结候选，完整Git历史仍须仓库访问提供。
