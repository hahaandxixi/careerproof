# CareerProof 第三方依赖清单

更新日期：2026-10-13。

版本来自当前 `backend/pyproject.toml`、升级环境包元数据和 `jianli/package-lock.json`，
以下只列直接依赖；许可证标识来自本地包元数据及既有清单，不替代完整许可证文本和发布许可核查。

## 后端生产依赖

| 依赖 | 锁定版本 | 许可证标识 |
| --- | --- | --- |
| fastapi | 0.143.0 | MIT |
| starlette | 1.3.1 | BSD-3-Clause |
| uvicorn[standard] | 0.35.0 | BSD-3-Clause |
| pydantic | 2.11.7 | MIT |
| pydantic-settings | 2.10.1 | MIT |
| sqlalchemy[asyncio] | 2.0.43 | MIT |
| alembic | 1.16.5 | MIT |
| Mako | 1.4.2 | MIT |
| asyncpg | 0.30.0 | Apache-2.0 |
| pgvector | 0.4.1 | MIT |
| PyJWT | 2.15.0 | MIT |
| pwdlib[argon2] | 0.2.1 | MIT |
| python-multipart | 0.0.31 | Apache-2.0 |
| email-validator | 2.2.0 | Unlicense |
| httpx | 0.28.1 | BSD-3-Clause |
| PyMuPDF | 1.26.4 | AGPL-3.0 或 Artifex 商业许可（发布方案未定） |
| python-docx | 1.2.0 | MIT |
| rapidocr | 3.9.2 | Apache-2.0 |
| onnxruntime | 1.30.0 | MIT License |
| Pillow | 12.3.0 | MIT-CMU |
| fastembed | 0.8.1 | Apache-2.0 |

## 后端可选 MCP 依赖

| 依赖 | 锁定版本 | 许可证标识 |
| --- | --- | --- |
| mcp | 1.30.0 | MIT |
| sse-starlette | 3.0.3 | BSD-3-Clause |
| starlette | 1.3.1 | BSD-3-Clause |

## 后端开发依赖

| 依赖 | 锁定版本 | 许可证标识 |
| --- | --- | --- |
| aiosqlite | 0.21.0 | MIT |
| pytest | 9.0.3 | MIT |
| pytest-asyncio | 1.4.0 | Apache-2.0 |
| pip | 26.2.1 | MIT |
| ruff | 0.12.12 | MIT |

## 前端直接依赖

| 依赖 | 锁定版本 | 许可证标识 |
| --- | --- | --- |
| next | 15.5.27 | MIT |
| react | 19.0.0 | MIT |
| react-dom | 19.0.0 | MIT |
| @types/node | 22.20.1 | MIT |
| @types/react | 19.2.18 | MIT |
| @types/react-dom | 19.2.5 | MIT |
| autoprefixer | 10.5.4 | MIT |
| postcss | 8.5.26 | MIT |
| tailwindcss | 3.4.19 | MIT |
| typescript | 5.9.3 | Apache-2.0 |

## 发布前许可阻断项

用户已确认项目暂时保持私有，根许可证以后再定。PyMuPDF 的许可方案仍未决定。当前清单没有授予整个项目 MIT/Apache 许可，
也没有证明购买了商业许可或完成替换；不能据此把 LICENSE 标记为已完成。
需由项目所有者确认适用许可、组件替换或商业授权，再核对传递依赖的许可证文本。
当前交付状态见[比赛交付](docs/guides/比赛交付.md)，不要沿用已删除的旧许可文档链接。

2026-10-15正在验证PDFium替换原型，尚未改变运行依赖或解除上述阻断。
[pypdfium2官方说明](https://pypdfium2.readthedocs.io/en/stable/readme.html#licensing)
列出包装层Apache-2.0/BSD-3-Clause及PDFium/捆绑依赖的分别许可；二进制分发仍需附相应许可文本。
因此原型能运行不等于最终许可核对完成。其[线程限制](https://pypdfium2.readthedocs.io/en/stable/python_api.html#incompatibility-with-threading)
也需按现有独立解析进程验证，不能直接改为多线程并行调用。
