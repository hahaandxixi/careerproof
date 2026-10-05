"""合成数据管线（新版）：具名实现，供隔离 E2E 测试使用。"""


def process_records(records):
    """按类目汇总金额，返回 {类目: 合计}。

    具名实现：process_records —— 与补证任务交付物同名。
    """
    totals = {}
    for record in records:
        key = record.get("category", "未分类")
        totals[key] = totals.get(key, 0) + float(record.get("amount", 0))
    return totals
