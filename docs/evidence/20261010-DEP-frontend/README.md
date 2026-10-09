# Next补丁与内嵌PostCSS独立验证

2026-10-10。Codex在backend/.tmp/dep-frontend-20261010中从f6ce263的HEAD:jianli Git归档建立仅跟踪源码的独立副本，不复制私有.env，不变更原node_modules/现有服务。框架后端已签收f574cb4；ZCode仍因明确五小时限额未执行，未反复重试。

## 两步升级及验证

1. Next15.5.25→15.5.27、sharp0.35.4→0.35.5、source-map-js1.2.1→1.2.2；独立npm install --ignore-scripts --no-audit --no-fund，首轮193测试通过。next-only-tree.raw.out证明Next补丁后仍携带postcss8.4.31。
2. 仅next节点下受控override postcss8.5.28，第二次安装只改变1包。root PostCSS维持8.5.26（原排序未命中版本）；不把root升级冒充内嵌修复。sharp/source-map-js采用定点override。npm ls next postcss sharp source-map-js --all exit0，final-tree.raw.out无invalid；lock-version-diff.json所有变化均为Next/SWC/env、sharp及对应平台原生包/libvips、source-map-js和Next内嵌PostCSS，其他版本未动。

候选metadata来自npm公开版本注册记录，四个registry.json保留；Next声明仍是postcss8.4.31，override是项目显式兼容方案，不宣称上游已经修复其声明。

独立runtime的实际Next-resolved PostCSS处理5组纯合成CSS，包括390px media、中文、注释、CSS变量/calc、supports与选择器，autoprefixer后CSS和source map与8.4.31基线完全一致。真实sharp0.35.5栅格化合成2x2SVG为PNG，尺寸/格式通过，sharp.versions记录实际Windows原生库含rsvg2.63.2。只证明此兼容探针，不冒称全部原生平台安全。

可重复命令（仓库根）：

```text
node scripts/dependencies/probe-frontend-compatibility.mjs --project-root backend/.tmp/dep-frontend-20261010 --baseline docs/evidence/20261010-DEP-frontend/css-before-override.json --output <新的证据路径.json>
```

probe拒绝覆盖原输出，不调用外部模型、不读取业务素材。首个metadata探针通过sharp/package.json exports读取失败，改用sharp公开versions对象；不是应用渲染失败。

升级后npm test再次193通过/0跳过；npm run build生产构建通过，Next15.5.27，BACKEND_ORIGIN明确loopback8001、NEXT_TELEMETRY_DISABLED=1。构建和类型检查顺序执行，npm run typecheck通过。日志在同目录。没有实际浏览器页面或数据库迁移，不用构建代替全链路验收。

## 残余审计与后续

默认npmmirror audit返回404 NOT_IMPLEMENTED（npm-audit.json），不是无漏洞；改用npm audit --registry=https://registry.npmjs.org --json取得真实审计（npm-audit-official.json）。仍有7个受影响包：braces、selector-parser及其传播到chokidar/fast-glob/micromatch/postcss-nested/tailwindcss的依赖项；不是7个独立漏洞。Next、PostCSS、sharp、source-map-js未在本次官方npm审计结果中出现，不能据此宣称永久安全或所有平台CVE消除。

braces公告仍无包级已知补丁（npm提示升级父tailwind至4.3.3并不等于braces已发布修补版本）；selector-parser修复7.1.6跨major，与tailwind3/postcss-nested6的范围不相容。不盲目全局强装、不运行npm audit fix --force。下一有界批次核对父依赖升级/替换方案或写明确低可达缓解与残余；当前管道只处理本地受信CSS/文件glob，未宣称部署不可达。

仅把验证过的package.json/lock提升到正式jianli；主node_modules仍是旧环境，实际页面验收必须选择新runtime或受控重新安装，不能用旧3000服务证明升级效果。新runtime源码与本轮正式前端源码一致，build生成的tsconfig/next-env修改只在独立副本，不提升。后续仍需开发工具/Mako处置、升级后迁移/双端页面及AI评测，P2保持暂停，无推送/部署/真实模型调用。
