# 残余依赖最终来源复核

2026-10-11。使用agent-reach的GitHub CLI API路由取得两条当前官方公告；npm官方registry只读查询braces最新与selector-parser六线发行版。原始响应先保存系统TEMP，交付记录仅保留公告标识、来源、更新时间、撤销字段、版本范围与补丁字段及原响应SHA；未升级/安装任何包。

实测四个查询均exit0：`gh api /advisories/GHSA-vfj7-8cjw-p6xm`、`gh api /advisories/GHSA-rj75-hqrm-r3gf`、`npm view braces version --registry https://registry.npmjs.org --json`、`npm view postcss-selector-parser@6 version --registry https://registry.npmjs.org --json`。

- [braces公告](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm)：当前first_patched_version=null，registry最新3.0.3，公告更新仍为2026-10-02，未撤销。
- [selector-parser公告](https://github.com/advisories/GHSA-rj75-hqrm-r3gf)：当前补丁7.1.6，六线最新6.1.4，公告更新仍为2026-10-05，未撤销。

本轮处置依据未变化：braces不能宣称包级修复，selector-parser不能无验证跨major强装；Tailwind4迁移另设有界范围。当前受信CSS/glob入口缓解与未来重新排序条件见20261010-DEP-residual/dependency-disposition.md，残余不算漏洞清零。复核不证明部署永久安全或所有新公告不存在。
