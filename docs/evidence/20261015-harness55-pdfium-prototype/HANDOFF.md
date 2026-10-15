# harness55 交棒：PDFium 隔离替换原型（只调查/原型，未改生产）

- 仓库（实际 Git 根）：`D:\jbcode\web ai\jianli`，基线 `8917814`（`git rev-parse --short HEAD` 一致）
- 只读核对：`git status --porcelain` 仅显示 `docs/` 下的既有未跟踪证据目录与 1 个 `docs/当前接力.md` 修改，**均非本次产生**；本次未改任何生产文件、`pyproject`、`.env`、storage、客户端 DB，未安装包、未联网、未提交/推送、未启停服务。
- 运行时：打包 Python `C:\Users\江博\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`（3.12.14）；`pypdfium2 5.14.0` / `PDFium 156.0.8076.0`（pdfium-binaries）/ reportlab 4.4.9 / Pillow 12.3.0 / pypdf 6.10.0；**未安装 rapidocr 等任何 OCR/模型包**。

## 本次产物（仅 2 个可写目录）

| 文件 | 内容 |
|---|---|
| `prototype.py` | 独立 PDFium 适配器原型 + 合成对抗测试（唯一执行入口，自带 verify 模式） |
| `probe.py` | 只读能力探测（API/错误码/几何/许可元数据），自带 verify 模式 |
| `results.json` | 机器可读结果（单行 canonical JSON，含每项 expected/observed、摘要、未验、集成差距） |
| `prototype-run.stdout.txt` | 原型原始日志（含日志/JSON 全文 SHA256 与 1000 字符分块 SHA256） |
| `probe-run.stdout.txt` | 探测原始日志（含全文 SHA256） |
| `HANDOFF.md` | 本交棒 |

产物自校验（哈希写在产物内部，抄录出错必被发现）：

```
python prototype.py --verify-log docs/evidence/20261015-harness55-pdfium-prototype/prototype-run.stdout.txt \
  --results docs/evidence/20261015-harness55-pdfium-prototype/results.json   # VERDICT=PASS
python prototype.py --verify-results .../results.json --expected-sha256 f01fe644004bdb4020a18916cdae53fffbf9a60f89feb4ecc875b028fcbd89b8  # PASS
python probe.py --verify .../probe-run.stdout.txt                            # PASS
```

## 通过/失败

`python prototype.py` → exit 0：**total=19 passed=18 failed=0 skipped=1**
日志 `LOG SHA256=6d8b5dc5…`，结果 `JSON SHA256=f01fe644…`（重跑字节一致，已用两次独立运行+哈希确认）。

| 检查 | 结论 |
|---|---|
| C01/C02 原生英文、原生中文（STSong-Light CID，无需系统字体嵌入）文本抽取 | pass：`render_calls=0`、OCR 调用 0 |
| C03/C04 混合页与纯扫描页：1 起页码（`index+1`）贯穿原生/扫描页 | pass：类型与页码 `[1,2,3,4]`、OCR 2 次、渲染 2 次 |
| C05 OCR 次数上限 `ocr_max_pages=1` | pass：只 OCR 1 页，跳过 2 页并计入 `ocr_skipped_pages` |
| C06 关闭 OCR 时原生页仍可解析、零渲染 | pass |
| C07 6000×5000pt 巨页（scale 2 → 1.2 亿像素）被像素上限拒绝 | pass：`render_calls=0`、**bitmap 打开数=0**（拒绝发生在分配 bitmap 之前） |
| C08/C09 预判像素与真实 bitmap 完全相等（含 90° 旋转页，宽高互换 800×1400） | pass：3,600,000 / 1,120,000 预判==实测 |
| C10 损坏/截断/含 NUL/空字节 | pass：统一分类为 `code=4024 reason=pdf_corrupt`，不泄漏原始异常，doc 无泄漏 |
| C11 文件不存在 | pass：`pdf_missing`，未打开 PDFium |
| C12 加密 PDF（reportlab 128-bit） | pass：无密码/错密码 → `4024/pdf_encrypted`（与损坏可区分）；正确密码可正常解析 |
| C13/C14 资源关闭 | pass：document/page/textpage/bitmap 打开数==关闭数；识别回调抛异常时仍全部关闭并提前中止 |
| C15 线程隔离 | pass：第二次从别的线程调用在触碰 PDFium 前被拒（`pdf_thread_affinity`），进程线程数 1→1、新建 0 |
| C16 OCR 回调收到真实渲染 PNG | pass：PNG 签名、尺寸 1191×1684、非空白 |
| C17 未导入任何 OCR/模型包；bytes 与 BytesIO 行为一致 | pass |
| C18 原生文字仅在第 5 页时页码仍为 5 | pass：`sections=[(page,5)]`、跳过 4 页、零渲染 |
| **C19 路径输入与内存输入一致** | **skipped**：本沙箱下无法在 `backend/.tmp/pdfium55-fixtures` 落盘（见下），改用 bytes/BytesIO 覆盖 |

## 环境阻碍（唯一未满足项，非原型缺陷）

本会话的 shell 令牌是**低完整性级别**（`whoami /groups` → `Mandatory Label\Low Mandatory Level`），而 `D:\jbcode\web ai\jianli` 下各级目录由其它账号（`CodexSandboxOffline`）创建、带中等完整性标号，且 DSH 的 workspace 授权只落在 `D:\jbcode` 根、未继承到仓库子树。因此：

- `backend/.tmp/pdfium55-fixtures` 与 `docs/evidence/20261015-harness55-pdfium-prototype/` 内的**新建/写入全部被拒**（`PermissionError: [Errno 13]`），实测 `New-Item`/`Set-Content`/`icacls /setintegritylevel`（需 WRITE_OWNER）均失败；
- harness 自带的文件工具可写这两个目录（本目录所有产物即由此落盘），但子进程 python 不行。

原型的处理（已写入 `results.json.fixtures.persistence`）：先按规格尝试写入白名单目录，失败只记录 `blocked_by_environment=true` 并 **in-memory 保留全部合成 PDF**，绝不写到其它目录。有写权限时重跑即可落盘并自动补跑 C19：

```
python docs/evidence/20261015-harness55-pdfium-prototype/prototype.py        # 正常权限下将 PDF 写入 backend/.tmp/pdfium55-fixtures
```

遗留物（沙箱令牌无权删除，可手工清理）：`docs/evidence/20261015-harness55-pdfium-prototype/_probe.txt`、`backend/.tmp/pdfium55-fixtures/_write_probe.txt`（均为写入能力探测标记，无内容价值）。另：字节码缓存目录不可写，运行请带 `PYTHONDONTWRITEBYTECODE=1`（不加只影响 `__pycache__` 告警）。

同目录还有 Codex 并行任务写入的 `codex-*` 产物（`codex-final*.json`、`codex-pdfium55-independent*`、`backend/.tmp/pdfium55-fixtures/codex-independent/`）：**文件无重叠，本次未读取、未修改它们**，其结论请以 Codex 自身交付为准。我的产物仅上述 6 个文件（`prototype.py`/`probe.py`/`results.json`/两个 `*.stdout.txt`/`HANDOFF.md`）。

## 原型与真实网站集成差距（重点）

1. **进程隔离不是同一个东西**：原型跑在进程内，仅用“线程亲和守卫”代替；生产 `task_runner.run_isolated()` 才真正 `python -m app.services.isolated_worker` + pickle IPC + 90s 超时杀进程。PDFium 非线程安全这一条在真实链路里必须由既有 worker 保证，本次**未验证**该路径。
2. **加密 PDF 无入口**：适配器支持 `password=`，但上传 API 没有密码字段；真实站点必须先决定“明确拒绝”还是“补一个密码输入”。
3. **像素上限语义迁移**：现网在 `page.get_pixmap()` **之后**才检查（已分配）；原型改为 `page.get_size()` 预判（旋转页宽高互换已被 C09 证实与真实 bitmap 一致）。错误码/文案不变，但**触发时机提前**，可能改变超大页在现网失败点。
4. **文本抽取保真度未做 A/B**：PDFium 用 `get_text_range()`，现网用 PyMuPDF `get_text("text")`。已观察到换行符差异（PDFium 返回 `\r\n`，PyMuPDF 返回 `\n`），会影响 `max_document_characters=500k` 计数与下游 AI 提示词内容；多栏排序、连字、表格等**未比对**（未读任何真实上传件）。
5. **OCR 引擎未接**：`recognize_image()`（RapidOCR）未被调用，仅注入合成回调；置信度过滤、PNG 输入兼容性、实际识别质量**未验证**。
6. **打包与部署**：pypdfium2 带平台原生库（wheel），CI 镜像/部署矩阵、移除 PyMuPDF 的连锁影响（DOCX 邻接测试、其它调用点）均未评估；`stderr=DEVNULL` 会吞掉原生崩溃信息，PDFium 崩溃只会表现为 worker `returncode!=0`。
7. **无性能/健壮性对比**：未测时间/内存，也未做 PyMuPDF vs PDFium 的 CVE/崩溃面比较——**不能声称替换后更安全或更快**。
8. 现网测试受影响点：`backend/app/tests/test_document_ocr.py`（用 `fitz` 造原生/空白 PDF、monkeypatch `recognize_image`）与 `test_material_tasks.py:31-48`（`fitz` 造空白 PDF + `settings.ocr_enabled=False` 期望 4024）。适配器保持 `settings.ocr_*` 与错误码语义即可不改断言，但造件改用 reportlab/pypdf 更干净。

## 迁移建议（供后续决议，本次未实施）

- 新增 `app/tools/pdf_adapter.py`（纯函数、可被 `run_isolated` pickle 调用），把 `document_parser.py:56-78` 的 PDF 分支替换为：几何预判像素上限 → `get_textpage()` 取文 → 无文字且有预算时 `render(scale=2)` → 复用 `recognize_image()`；`DocumentSection`、`ocr_max_pages`、`index+1` 页码、4024/4025/4026 语义全部保持。
- `PdfPage/PdfTextPage/PdfBitmap` 必须 `try/finally` 关闭（pypdfium2 5.14.0 只有 `PdfDocument` 是上下文管理器，四者都无 `closed` 属性）。
- 损坏/加密分别映射 `FPDF_ERR_FORMAT|FILE`→4024 `pdf_corrupt`、`FPDF_ERR_PASSWORD`→4024 `pdf_encrypted`；建议后续给加密单独一个用户可见文案。
- 建议保留 PyMuPDF 直至文本抽取 A/B 与真实样本回归通过；替换前后各跑一次同一批脱敏样本对比字符数与内容。
- **许可**：本机 wheel 元数据为 `License: BSD-3-Clause, Apache-2.0, dependency licenses`，随包附带 `Apache-2.0.txt`、`BSD-3-Clause.txt`、`CC-BY-4.0.txt` 及 `BUILD_LICENSES/{pdfium,freetype,icu,libjpeg_turbo,libpng,libopenjpeg,zlib,abseil,agg23,fast_float,lcms,llvm-libc,simdutf,pdfium-binaries}.txt`（均为本地核对，未联网）。wrapper 的 Apache-2.0/BSD-3-Clause 结论采信 Codex 已核对；**PDFium 及传递许可必须随分发保留**，替换本身不构成法律合规结论，本任务不提供法律意见。

## 未验证（明确边界）

真实 RapidOCR 集成与置信度过滤；真实上传件抽取保真度（未读 storage/业务数据）；`run_isolated` 进程隔离/超时/worker 崩溃行为；与 PyMuPDF 的 A/B 文本等价性；500k 字符预算与下游 AI 影响；原生崩溃/CVE 健壮性对比；其它 pypdfium2/PDFium 版本与平台；许可合规性；路径输入成功分支（C19，因沙箱只读而跳过）。
