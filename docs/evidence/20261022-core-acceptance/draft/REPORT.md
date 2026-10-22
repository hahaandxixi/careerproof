# 私人草稿：标签页隐藏不丢未保存编辑

基线：`ba0c970`。原有PrivateAnswerDraft的三处display-path导入/显示变更保留，非本次成果；原diff和字节哈希见`preexisting-private-answer.patch`、`baseline-hashes.json`。本次没有提交Git、安装依赖、启停服务或调用网络。

## 根因与修复

旧子组件hidden调用clear、visible执行activate+load，未保存文字和引用被服务器基线替换。另有真实父层障碍：GrowthWorkspace在hidden及每次重读时将task置null，卸载草稿组件；仅修子组件仍会丢编辑。

本次改动六个文件：
- `PrivateAnswerDraft.tsx`：visibility事件接真实session.visibilityChanged；关闭旧预览，显示新的明确边界提示。
- `GrowthWorkspace.tsx`（根代理追加授权）：同身份同任务隐藏用hidden属性遮蔽且保留挂载，恢复重读不先卸载task。身份/任务仍由外层user.id:id键隔离。
- `private-answer-workflow.ts`：隐藏只暂停（纪元递增、失效在途回执、busy复位、来源待验），保留内存文字与引用；恢复读取更新已保存revision并保护已有编辑。恢复失败保留编辑、来源标failed，拒绝基于旧来源复制。dispose不可再激活；明确clear仍清除数据。
- 两个既有草稿测试：保留clear对身份/任务的破坏性清理边界，将原“普通隐藏必丢弃”文案验收调整为新行为。
- 新`private-answer-visibility.test.mjs`：六条真实生产session行为，覆盖普通往返、保存失败、在途保存+继续编辑、连续隐藏与迟到读取、切身份/任务旧请求、恢复失败与重试。

没有浏览器持久存储、模块全局缓存或自动保存；刷新/退出/切任务前仍须明确保存。草稿仍仅本人可见，不发企业、不进入投递或报告。

## 红→绿与命令

Node22.23.1：`C:/Users/江博/AppData/Local/hermes/node/node.exe`。
- 红：真实旧组件调用序列clear→activate+load，预期未保存文本，实际“已保存的正文”；1 failed，exit1。`red-old-visibility.raw.out`。
- 绿：`node --test tests/private-answer-visibility.test.mjs tests/private-answer-workflow.test.mjs tests/private-answer-recovery-notice.test.mjs`：63 passed、0failed/skip，exit0。`green-target.raw.out`。
- `node node_modules/typescript/bin/tsc --noEmit`（jianli目录）：exit0，`typecheck.raw.out`。此为共享工作树类型检查，最终接受副本由总控复验。
- 目标ESLint：复用`backend/.tmp/task62-lint/stage/jianli/node_modules/eslint/bin/eslint.js`及其同目录既有eslint.config.mjs，对上述六文件执行；exit0、0error/0warning。`lint-target-stage-config.raw.out`。
- 首次lint用根配置因根node_modules缺@eslint/eslintrc返回exit2，保留`lint-target.raw.out`；没有安装、改规则或跳过。

`agent-owned.diff`仅含本次新增差异，排除预存三处UUID展示改动；最终字节哈希见`final-hashes.json`。

## 未验证

无jsdom/happy-dom/linkedom/react-test-renderer或testing-library，按授权未安装。session六条是直接驱动真实生产逻辑，面板SSR仅证明文字与状态，不冒充真实React事件/挂载或浏览器切标签验收。父层保留挂载修复已检查实际调用链，仍需总控接受构建的真实浏览器离窗→返回，以及真实AuthProvider账号切换；不以源文本断言替代。无后端改动、PG或真实模型验证。
