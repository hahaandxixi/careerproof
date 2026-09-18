# CareerProof 第三方依赖清单

更新日期：2026-09-19。

本文件依据 `backend/pyproject.toml`、本地已安装 Python 包元数据，以及
`jianli/package-lock.json` 整理直接依赖。它用于比赛提交和仓库发布审阅，不能替代各依赖
随附的完整许可证文本。前端表记录锁文件解析后的版本；后端生产依赖由项目文件固定版本。

## 后端生产依赖

| 依赖 | 版本 | 许可证标识 |
| --- | ---: | --- |
| FastAPI | 0.116.1 | MIT |
| Uvicorn | 0.35.0 | BSD-3-Clause |
| Pydantic | 2.11.7 | MIT |
| pydantic-settings | 2.10.1 | MIT |
| SQLAlchemy | 2.0.43 | MIT |
| Alembic | 1.16.5 | MIT |
| asyncpg | 0.30.0 | Apache-2.0 |
| pgvector | 0.4.1 | MIT |
| PyJWT | 2.10.1 | MIT |
| pwdlib | 0.2.1 | MIT |
| python-multipart | 0.0.20 | Apache-2.0 |
| email-validator | 2.2.0 | Unlicense |
| HTTPX | 0.28.1 | BSD-3-Clause |
| PyMuPDF | 1.26.4 | AGPL-3.0 或 Artifex 商业许可 |
| python-docx | 1.2.0 | MIT |
| RapidOCR | 3.9.2 | Apache-2.0 |
| ONNX Runtime | 1.30.0 | MIT |
| Pillow | 12.3.0 | MIT-CMU |

## 后端开发依赖

| 依赖 | 版本 | 许可证标识 |
| --- | ---: | --- |
| aiosqlite | 0.21.0 | MIT |
| pytest | 8.4.2 | MIT |
| pytest-asyncio | 1.1.0 | Apache-2.0 |
| Ruff | 0.12.12 | MIT |

## 前端直接依赖

| 依赖 | 锁定版本 | 许可证标识 |
| --- | ---: | --- |
| Next.js | 15.5.25 | MIT |
| React | 19.0.0 | MIT |
| React DOM | 19.0.0 | MIT |
| @types/node | 22.20.1 | MIT |
| @types/react | 19.2.18 | MIT |
| @types/react-dom | 19.2.5 | MIT |
| Autoprefixer | 10.5.4 | MIT |
| PostCSS | 8.5.26 | MIT |
| Tailwind CSS | 3.4.19 | MIT |
| TypeScript | 5.9.3 | Apache-2.0 |

## 发布前许可阻断项

`PyMuPDF` 是当前唯一会直接影响整个仓库许可证选择的生产依赖。其包元数据为
“GNU Affero GPL 3.0 或 Artifex 商业许可”。在以下方案中作出选择前，不在仓库根目录添加
MIT 或 Apache-2.0 许可证：

1. 项目采用与该依赖兼容的 AGPL-3.0-or-later，并满足发布与网络服务场景的源代码提供义务；
2. 购买适用的 Artifex 商业许可；
3. 用许可证兼容的 PDF 文本提取和页面渲染组件替换 PyMuPDF，完成回归后再选择宽松许可证。

详细决策记录见 `docs/发布许可决策.md`。最终发布前还应从 Python 环境和
`package-lock.json` 生成包含传递依赖的完整清单，并保存各组件实际许可证文本。
