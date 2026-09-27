"""Small synthetic context-budget development set, not independent labels."""


def build_span_cases():
    short = (
        "def process_order(payload, store):\n"
        "    if not payload.get('order_id'):\n"
        "        raise ValueError('order id required')\n"
        "    store.write(payload)\n"
        "    return {'order_id': payload['order_id']}\n"
    )
    long = (
        "def process_order(payload, store):\n"
        + "".join(
            f"    if not payload.get('field_{index}'):\n"
            f"        raise ValueError('field {index} required')\n"
            for index in range(18)
        )
        + (
            "    try:\n"
            "        store.begin()\n"
            "        store.write(payload)\n"
            "        store.commit()\n"
            "    except Exception:\n"
            "        store.rollback()\n"
            "        raise\n"
            "    return {'order_id': payload['order_id']}\n"
        )
    )
    runbook = (
        "\n".join(
            [
                "备份恢复完整流程：需核查备份、恢复及一致性验证全部步骤。",
                "登记演练编号与操作人角色，执行环境使用隔离实例。",
                "记录数据集版本、记录数量及抽样校验方式。",
                "确认数据库版本与存储格式兼容。",
                "建立备份目标目录，记录剩余存储容量。",
                "检查执行账户仅具有必要的读写权限。",
                "保存当前 schema 定义及迁移版本。",
                "对关键表记录业务唯一键及约束。",
                "暂停目标数据写入，记录开始时间。",
                "发起一致性快照，等待完成状态。",
                "写出压缩备份，保存日志文件。",
                "计算备份文件哈希并核对传输完成。",
                "在隔离机器验证文件可以正常读取。",
                "创建空白目标数据库。",
                "安装对应的扩展与字符集。",
                "按依赖关系恢复表结构。",
                "导入数据并记录错误与告警。",
                "重建索引，校验主键冲突。",
                "核对外键约束与表间引用。",
                "比较恢复前后每张表的行数。",
                "抽样比较关键记录的字段值。",
                "执行业务只读查询核对订单与库存关联。",
                "记录演练结束时间及恢复耗时。",
                "清理演练访问授权并保存审批编号。",
                "一致性验证发现差异时停止交付，保留日志并重新检查恢复步骤。",
            ]
        )
        + "\n"
    )
    cross = [
        {
            "path": "project/steps.md",
            "content": "备份恢复执行步骤。\n记录隔离实例版本。\n暂停写入并保存快照。\n"
            "导出备份文件。\n核对文件哈希。\n创建空目标并导入备份。\n保存操作日志。\n",
        },
        {
            "path": "project/checks.md",
            "content": "备份恢复一致性验证。\n记录目标表清单。\n比较各表行数。\n"
            "核对关键唯一键。\n抽样比较字段。\n检查关联查询。\n保存差异处理记录。\n",
        },
    ]
    specs = [
        (
            "short_python",
            "Python",
            "Python业务函数包含输入校验、写入和完整响应",
            False,
            [{"path": "project/order.py", "content": short}],
        ),
        (
            "long_python",
            "Python",
            "Python业务处理包含字段校验、提交、异常回滚和返回分支",
            False,
            [{"path": "project/order.py", "content": long}],
        ),
        (
            "long_runbook",
            "备份恢复",
            "备份恢复需覆盖执行步骤及失败时的一致性验证",
            True,
            [{"path": "project/recovery.md", "content": runbook}],
        ),
        ("cross_file_runbook", "备份恢复", "备份恢复需覆盖执行步骤及一致性验证记录", True, cross),
    ]
    return {
        "version": "synthetic-context-span-v1",
        "createdBy": "project assistant",
        "annotationStatus": "provisional; independent human review pending",
        "scope": "4 context-budget development cases; not a holdout or capability proof",
        "cases": [
            {
                "id": name,
                "family": "context_budget",
                "category": name,
                "skill": skill,
                "query": query,
                "semanticScope": semantic,
                "labelStatus": "synthetic_provisional",
                "documents": documents,
                "gold": [
                    {
                        "path": doc["path"],
                        "lineStart": 1,
                        "lineEnd": len(doc["content"].splitlines()),
                        "support": "describes_behavior",
                    }
                    for doc in documents
                ],
            }
            for name, skill, query, semantic, documents in specs
        ],
    }
