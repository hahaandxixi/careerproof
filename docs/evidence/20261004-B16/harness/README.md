# B-16 复现 harness 说明

用途：在受控 Chromium 中逐字复刻 `jianli/src/components/ApplicationBoard.tsx:96` 的交付模式
（`createObjectURL → anchor.download → click → setTimeout(revoke, 1000)`），验证 1 秒撤销
是否会破坏下载。**全部合成数据；仅监听 127.0.0.1；不是真实产品页面的验收。**

## 文件

- `server.mjs`：仅回环的静态服务器（127.0.0.1:8931）。
- `index.html`：复现页。场景按钮 A 64KB / B 256MB / C 双击连下 / D 点击后 300ms 卸载 /
  E 撤销后 fetch 同一 URL（应失败）。页面侧计算每份合成文件的 SHA-256 写入 `REPRO_RESULTS`。
- `after-unload.html`：场景 D 的导航落点页。
- `cdp.mjs`：最小 CDP 客户端（Node 22 内置 WebSocket，无第三方依赖）。
- `driver.mjs`：按序执行 A–E，落盘后逐文件比对大小与 SHA-256。

## 复跑步骤（在可访问回环的浏览器环境）

```bash
node server.mjs &                                  # 终端 A（或后台）
curl -s -D - -o /dev/null http://127.0.0.1:8931/   # 应为 content-type: text/html; charset=utf-8
mkdir -p dl && node driver.mjs "D:\\绝对路径\\dl"   # 终端 B；退出码 0 且六项 match:true 为通过
```

结束后：结束 driver 启动的 chrome（`b16-chrome-*` 临时 profile 特征）与 server.mjs，
清空 dl 目录。切勿使用 `chrome.exe --version` 探测版本（Windows GUI 程序会挂起）。

## 已修复的 harness 缺陷史（勿回退）

1. `server.mjs`：`types` 键 `".html"` 与无点查询不匹配 → 页面以 `application/octet-stream`
   返回，Chrome 把复现页当下载保存（Codex 审计发现，2026-10-04）。
2. `cdp.mjs`：下载事件重复计数（实时回调 + 轮询重复扫描）→ 改为扫描指针。
3. `driver.mjs`：pageState 双重 `JSON.parse`；哈希比对引用不存在的 `file.name`（应为
   `suggested`）；场景 D 未在卸载前捕获源哈希；场景 E 前未回到复现页。
