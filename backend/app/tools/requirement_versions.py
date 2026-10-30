"""Compare known fixed requirement facts without filling gaps in history."""

def compare_requirements(saved: list[dict] | None, current: list[dict]) -> dict:
    if saved is None:
        return {"status": "unknown", "changes": [], "missingFields": ["投递时岗位要求"]}
    def normalize(row):
        aliases = {"id": ("id", "requirementId"), "要求内容": ("title", "rawText", "text"),
                   "技能": ("skill", "skillName"), "权重": ("weight",), "是否必需": ("isRequired", "is_required")}
        return {name: next((row[k] for k in keys if k in row and row[k] is not None), None) for name, keys in aliases.items()}
    old, new = [normalize(r) for r in saved], [normalize(r) for r in current]
    if any(not r["id"] for r in old + new) or len({r["id"] for r in old}) != len(old) or len({r["id"] for r in new}) != len(new):
        return {"status": "unknown", "changes": [], "missingFields": ["可靠的要求标识"]}
    a, b = {r["id"]: r for r in old}, {r["id"]: r for r in new}
    changes, missing = [], set()
    for key in a.keys() | b.keys():
        if key not in a:
            changes.append(f"新增要求：{b[key]['技能'] or b[key]['要求内容']}")
        elif key not in b:
            changes.append(f"移除要求：{a[key]['技能'] or a[key]['要求内容']}")
        else:
            for field in ("要求内容", "技能", "权重", "是否必需"):
                if a[key][field] is None or b[key][field] is None:
                    missing.add(field)
                elif a[key][field] != b[key][field]:
                    changes.append(f"{a[key]['技能'] or '该要求'}的{field}已改变")
    return {"status": "changed" if changes else "unknown" if missing else "same",
            "changes": sorted(changes), "missingFields": sorted(missing)}
