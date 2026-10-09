# 传智杯23：首批依赖防御升级与回归

基线4c78ba7/main。用户新目标已授权依赖安装升级；本卡明确授权在独立本地venv下载已发布包、安装本项目依赖并修改下列pin，不调用真实模型、不推送或部署。BigModel个人GLM-5.3/最高，含Pillow跨major及认证兼容性；每周个人总消费最多70%，保留至少30%。

1. 目标：按次序python-multipart 0.0.20→0.0.31、Pillow11.3→12.3、PyJWT2.10.1→2.15；一次只处理一项，保存各自原始安装/测试日志。官方发布和PyPI已由Codex重新读取。参考已签收升级排序，无需重做全仓审计。
2. 唯一写范围：backend/pyproject.toml中这三个直接pin；backend/.venv-dependency23/新独立venv及其配置（补backend/.gitignore一行忽略它）；必要新增test_dependency_upgrade_regression.py；docs/evidence/20261009-DEP-01-first-batch/新证据。现有baseline两文件只读保留。禁止改生产源码/已有测试/.env/原backend/.venv/服务/业务库/前端/正式文档/P2stash/Git索引提交推送。必要生产兼容修复先以失败证据交棒Codex。
3. 环境：用当前Python3.12创建独立venv，先按baseline-pinned.txt安装现有环境完整固定版本（排除editable项目名）；安装项目-e --no-deps后pip check基线。再按每项候选更新venv并pip check。禁止顺便升级pytest/pip/FastAPI/Starlette及其他包；如解析器需要变动，先报告精确依赖冲突。现有服务继续用原venv，不重启。
4. 真实入口与失败：multipart正常/坏boundary/上传类型和大小/路径穿越；Pillow图像归一化、损坏图、像素/尺寸上限、vision预检及OCR启用/未启用路径；PyJWT签发/过期/畸形拒绝/jti撤销/旧token兼容/角色授权。优先跑已有有意义测试，缺项才补真实行为回归，不写只比较版本数字的测试、不mock库来迁就。
5. 三项顺序目标：test_portfolio_api.py、test_visual_evidence.py（现有vision/ocr测试按rg定位），test_auth.py与token/session/role相关测试；记录每项命令、模块、实际解释器、版本与退出码。只用合成MockTransport，不发送任何真实DeepSeek或其他模型请求。
6. 需要PG时过程级CAREERPROOF_TEST_DATABASE_URL=现有本地careerproof，仅现有随机cp_test fixture；先namespace校验、原快照不变。Codex不同时跑共享PG。最终运行受影响目标与pip check/Ruff；完整后端全量可在新venv阶段集成时执行，先交棒Codex决定范围。
7. 各次失败独立文件，原始输出不覆盖；不可运行检查标未验证。报告新venv与原venv版本差异、精确diff、行为回归、自审及下一项；一屏交棒，停止写入。不要把声明相容当运行通过、不要将这三包升级冒称全部依赖修完。
8. 本次不启动服务/迁移业务库/安装其他客户端插件；下一批FastAPI/Starlette、Next/PostCSS分别另卡。P2继续暂停。
