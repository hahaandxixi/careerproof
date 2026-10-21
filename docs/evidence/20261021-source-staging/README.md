# 冻结前源包 staging（2026-10-21）

状态：**staging，不是候选冻结包。**

- 来源提交：`6f6a1b1de0cf8117ff5f096932a7945c2aada92d`
- 包含最新打包排除提交 `ab66948`。
- 输出（gitignored）：`output/source/CareerProof-source-review-20261021-r9-staging.zip`
- ZIP 大小：2,183,275 bytes
- ZIP SHA256：`44c8e634269c635a6152795e05085e686ee8ae03a6aa4b9f4ddee69c755e4d7`
- 包内 `SOURCE_MANIFEST.json` 记录 848 个文件；逐文件 SHA256/大小复核，**0 mismatch、0 missing**；
- 解包到 `backend/.tmp/source-staging-20261021/`；
- 解包源码包专项测试：**23 passed**（修正 basetemp 父目录后；首次 9 个 setup 错误是路径不存在，不是包内容失败）；
- 未做干净安装、未跑全量、未做页面/人工验收；不是最终候选。

## 为什么不是最终包

- 人工 3/3 仍未完成（当前 6/12 检查项待填）；
- 11/10 冻结日未到；
- 当前工作区还有暂停的展示改动和未提交文档，均未进入本 staging；
- PDF 20–28 页和最终视频未同步。

## 复核

- 清单和哈希：`SOURCE_MANIFEST.json`
- 解包测试原始输出：本次运行终端；关键结果为 23 passed。
