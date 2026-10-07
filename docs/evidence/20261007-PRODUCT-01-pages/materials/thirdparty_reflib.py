"""合成第三方参考片段（S9 夹具，非真实材料，仅供隔离测试）。

声明：本文件全部内容为测试合成编写，用作 material_role=reference 的
上传材料，验证"第三方参考，不计入个人实践评级"的产品行为。
"""

def fetch_category_totals(rows):
    """按类目汇总数量的示例实现（具名函数，合成编写）。"""
    totals = {}
    for row in rows:
        category = row.get("category", "未分类")
        totals[category] = totals.get(category, 0) + 1
    return dict(sorted(totals.items()))
